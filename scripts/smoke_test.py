"""Offline end-to-end test. No Twilio, no Claude, no phone.

Starts the real server and drives it the way Twilio would (ConversationRelay WebSocket
and SMS webhook), with a scripted model in place of Claude and a fake caller that
answers questions. Run from the project root:

    python scripts/smoke_test.py
"""
import asyncio
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for key, value in {"TWILIO_SID": "ACtest", "TWILIO_TOKEN": "test", "TWILIO_NUMBER": "+15550000000",
                   "PUBLIC_HOST": "127.0.0.1:8765", "ANTHROPIC_API_KEY": "test"}.items():
    os.environ.setdefault(key, value)

import httpx  # noqa: E402
import uvicorn  # noqa: E402
import websockets  # noqa: E402

from dialup.app import create_app  # noqa: E402
from dialup.config import Settings  # noqa: E402
from dialup.tasks.models import TERMINAL, Channel, Status  # noqa: E402
from dialup.telephony import twiml  # noqa: E402

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
CALLER = "+15551112222"


# ---------- Scripted stand-in for Claude ----------

def _tool(name, **args):
    return ("tool", name, args)


def _last_result(messages, contains):
    for m in reversed(messages):
        if m["role"] == "user" and isinstance(m["content"], list):
            for part in m["content"]:
                text = part.get("content", "") if isinstance(part, dict) else ""
                if contains in text:
                    return text
    return ""


def booking_script(messages, step):
    plan = [
        _tool("goto", url=f"{BASE}/bus"),
        _tool("read_page"),
        _tool("fill", label="From", value="San Diego"),
        _tool("fill", label="To", value="Los Angeles"),
        _tool("click", text="Search"),
        _tool("read_page"),
        _tool("confirm", summary="Hold a seat on the cheapest bus, 19 dollars?"),
        _tool("click", text="Hold seat 3"),
        _tool("read_page"),
        _tool("ask_user", question="What name should the seat be under?"),
    ]
    if step < len(plan):
        return plan[step]
    name = _last_result(messages, "Caller said:").removeprefix("Caller said: ") or "Unknown"
    rest = [
        _tool("fill", label="Passenger name", value=name),
        _tool("click", text="Confirm hold"),
        _tool("read_page"),
    ]
    i = step - len(plan)
    if i < len(rest):
        return rest[i]
    page = _last_result(messages, "Seat held")
    return _tool("finish", summary=f"Done. {page.replace(chr(10), ' ')}")


def unconfirmed_script(messages, step):
    """Tries to book without asking the caller first. Should be blocked."""
    plan = [
        _tool("goto", url=f"{BASE}/bus"),
        _tool("fill", label="From", value="San Diego"),
        _tool("fill", label="To", value="Los Angeles"),
        _tool("click", text="Search"),
        _tool("click", text="Hold seat 3"),
    ]
    if step < len(plan):
        return plan[step]
    blocked = _last_result(messages, "BLOCKED")
    return _tool("give_up", reason="blocked" if blocked else "not blocked")


def impossible_script(messages, step):
    return _tool("give_up", reason="There are no buses to the moon.")


def looping_script(messages, step):
    if step == 0:
        return _tool("goto", url=f"{BASE}/bus")
    return _tool("click", text="Teleport")  # doesn't exist, so it fails every time


def unreachable_script(messages, step):
    """Asks a question the caller never gets. Should move on without waiting for the timeout."""
    if step == 0:
        return _tool("ask_user", question="What name should the seat be under?")
    return _tool("give_up", reason="I couldn't reach you to get a name.")


def intake_decision(transcript):
    """Vague requests get one follow-up; everything else starts right away."""
    turns = [line.removeprefix("Caller: ") for line in transcript.splitlines() if line.startswith("Caller: ")]
    if "vague" in turns[0].lower() and len(turns) == 1:
        return {"ready": False, "question": "Where from and where to?", "task": turns[0]}
    return {"ready": True, "task": " ".join(turns)}


class ScriptedLLM:
    def __init__(self):
        self.messages = self  # mimic client.messages.create
        self.systems: dict[str, str] = {}

    async def create(self, *, messages, system="", tools=(), **_):
        if tools and tools[0]["name"] == "intake_decision":
            block = SimpleNamespace(type="tool_use", id="tu_intake", name="intake_decision",
                                    input=intake_decision(messages[0]["content"]))
            return SimpleNamespace(content=[block], usage=SimpleNamespace(input_tokens=300, output_tokens=40))
        goal = messages[0]["content"].lower()
        self.systems[goal] = system
        step = sum(1 for m in messages if m["role"] == "assistant")
        script = (impossible_script if "moon" in goal else looping_script if "teleport" in goal
                  else unconfirmed_script if "sneaky" in goal else unreachable_script if "unreachable" in goal
                  else booking_script)
        _, name, args = script(messages, step)
        block = SimpleNamespace(type="tool_use", id=f"tu_{step}", name=name, input=args)
        return SimpleNamespace(content=[block], usage=SimpleNamespace(input_tokens=900, output_tokens=60))


# ---------- Fake Twilio + fake caller ----------

async def relay_call(params: dict, *speech: str | tuple[str, ...]) -> list[dict]:
    """Act like Twilio ConversationRelay: setup, then the caller says each line after the
    server speaks. A tuple is one answer said in pieces, with short pauses between them.
    Collects everything the server says until it hangs up."""
    received = []
    lines = list(speech)

    async def say(ws, line):
        for piece in (line if isinstance(line, tuple) else (line,)):
            await ws.send(json.dumps({"type": "prompt", "voicePrompt": piece, "last": True}))
            await asyncio.sleep(0.1)

    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
        await ws.send(json.dumps({"type": "setup", "callSid": "CAtest", "customParameters": params}))
        await say(ws, lines.pop(0))
        async for raw in ws:
            msg = json.loads(raw)
            received.append(msg)
            if msg["type"] == "end":
                break
            if msg["type"] == "text" and lines:
                await say(ws, lines.pop(0))
    return received


async def relay_keypress(params: dict, digit: str) -> None:
    """Like relay_call, but the caller presses a key instead of speaking."""
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
        await ws.send(json.dumps({"type": "setup", "callSid": "CAtest", "customParameters": params}))
        await ws.send(json.dumps({"type": "dtmf", "digit": digit}))
        async for raw in ws:
            if json.loads(raw)["type"] == "end":
                break


async def sms(body: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE}/sms", data={"From": CALLER, "Body": body})
        r.raise_for_status()
        return ET.fromstring(r.text).findtext("Message")


class FakeCaller:
    """Answers questions like a person would, and records what they were told."""

    def __init__(self):
        self.results: dict[str, str] = {}
        self.questions: list[str] = []
        self.asking: dict[str, str] = {}
        self.keypresses: list[str] = []

    async def ask(self, task, question):
        self.questions.append(question)
        if "unreachable" in task.goal.lower():
            asyncio.create_task(self._busy(task))
            return
        if "Say yes" in question or "确认请说" in question:
            if task.channel == Channel.VOICE and task.language == "en":
                asyncio.create_task(self._press(task, "1"))  # English voice confirms by keypad
                return
            answer = "是" if task.language == "zh" else "yes"
        else:
            answer = "王小明" if task.language == "zh" else "Kanwar"
        asyncio.create_task(self._answer(task, answer))

    async def _press(self, task, digit):
        await asyncio.sleep(0.3)
        self.keypresses.append(digit)
        await relay_keypress({"mode": "ask", "task": task.id}, digit)

    async def _answer(self, task, answer):
        await asyncio.sleep(0.3)
        if task.channel == Channel.SMS:
            await sms(answer)
        else:
            await relay_call({"mode": "ask", "task": task.id}, answer)

    async def _busy(self, task):
        """Twilio reports the question call as busy, with no retries left."""
        await asyncio.sleep(0.3)
        async with httpx.AsyncClient() as client:
            await client.post(f"{BASE}/twilio/status?task={task.id}&attempt=2&kind=ask",
                              data={"CallStatus": "busy"})

    async def send_result(self, task, text):
        self.results[task.id] = text


# ---------- Test ----------

async def wait_for(store, caller: FakeCaller, task_id: str, timeout=60):
    for _ in range(int(timeout / 0.2)):
        t = store.get(task_id)
        if t and t.status in TERMINAL and task_id in caller.results:
            return t
        await asyncio.sleep(0.2)
    raise TimeoutError(f"task {task_id} didn't finish")


def check(label: str, ok: bool, detail: str = ""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        raise SystemExit(1)


async def main():
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    settings = Settings(
        twilio_sid="ACtest", twilio_token="test", twilio_number="+15550000000",
        public_host=f"127.0.0.1:{PORT}", site_base=BASE, model="scripted",
        max_steps=25, max_minutes=5, token_budget=400_000, ask_timeout=30, result_hold=1,
        max_concurrent=3, callback_retries=1, validate_twilio=False, db_path=db,
        speech_pause=0.5,
    )
    caller = FakeCaller()
    llm = ScriptedLLM()
    app = create_app(settings=settings, notifier=caller, llm=llm)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    store = app.state.services.store

    def newest_id():
        return store.recent(1)[0].id

    print("\nTwiML")
    doc = ET.fromstring(twiml.relay(settings, "en", 'Say "hi" & <wave>', {"mode": "intake", "caller": CALLER}))
    relay_el = doc.find("./Connect/ConversationRelay")
    check("relay TwiML parses and escapes", relay_el is not None and relay_el.get("welcomeGreeting") == 'Say "hi" & <wave>')
    check("keypresses are turned on", relay_el.get("dtmfDetection") == "true")

    print("\n1. Voice: book a bus")
    said = await relay_call({"mode": "intake", "caller": CALLER},
                            "Find the cheapest bus from San Diego to Los Angeles tomorrow and hold a seat")
    check("caller hears confirmation", any("call you back" in m.get("token", "") for m in said))
    check("call hangs up", said[-1]["type"] == "end")
    t = await wait_for(store, caller, newest_id())
    check("task done", t.status == Status.DONE, t.status.value)
    check("agent asked for a name", any("name" in q for q in caller.questions))
    check("caller was asked to confirm before the hold", any("Say yes" in q for q in caller.questions))
    check("confirmed by pressing 1 on the keypad", caller.keypresses == ["1"], str(caller.keypresses))
    check("cheapest bus held for Kanwar", "NightRider" in t.result and "Kanwar" in t.result, t.result)

    print("\n2. SMS: book a bus")
    reply = await sms("Find the cheapest bus from San Diego to Los Angeles and hold a seat")
    check("texter gets confirmation", "text you back" in (reply or ""), reply)
    t = await wait_for(store, caller, newest_id())
    check("task done", t.status == Status.DONE, t.status.value)
    check("seat held", "Seat held" in t.result)

    print("\n3. Impossible task")
    await relay_call({"mode": "intake", "caller": CALLER}, "Book me a bus to the moon")
    t = await wait_for(store, caller, newest_id())
    check("agent gives up", t.status == Status.GAVE_UP, t.status.value)
    check("caller hears why", "moon" in caller.results[t.id], caller.results[t.id])

    print("\n4. Stuck agent")
    await relay_call({"mode": "intake", "caller": CALLER}, "Teleport me to Los Angeles")
    t = await wait_for(store, caller, newest_id())
    kinds = [(e["kind"], e["text"]) for e in store.events(t.id)]
    check("guard warns first", any(k == "guard" and x.startswith("warning") for k, x in kinds))
    check("guard stops it", t.status == Status.STOPPED, t.status.value)
    check("stopped well before the step cap", t.steps < settings.max_steps, f"{t.steps} steps")
    check("caller still gets a callback", "had to stop" in caller.results[t.id], caller.results[t.id])

    print("\n5. Live view")
    async with httpx.AsyncClient() as client:
        page = await client.get(f"{BASE}/live")
        tasks = (await client.get(f"{BASE}/api/tasks")).json()
        bus_page = await client.get(f"{BASE}/bus")
    check("live page loads", page.status_code == 200 and "Dial-Up live" in page.text)
    check("API lists all tasks with events", len(tasks) == 4 and all(t["events"] for t in tasks))
    check("mock bus site loads", "BusBook" in bus_page.text)

    print("\n6. Language menu and Chinese")
    async with httpx.AsyncClient() as client:
        menu = (await client.post(f"{BASE}/voice", data={"From": CALLER})).text
        zh = (await client.post(f"{BASE}/voice/language", data={"From": CALLER, "Digits": "2"})).text
        none = (await client.post(f"{BASE}/voice/language", data={"From": CALLER, "Digits": ""})).text
    m = ET.fromstring(menu)
    says = [e.text for e in m.iter("Say")]
    check("menu is a Gather with both languages", m.find("Gather") is not None
          and says == ["For English, press 1.", "中文服务，请按 2。"], str(says))
    zr = ET.fromstring(zh).find("./Connect/ConversationRelay")
    check("pressing 2 starts a Chinese conversation", zr.get("ttsLanguage") == "cmn-CN"
          and zr.get("welcomeGreeting").startswith("你好"), zr.get("ttsLanguage"))
    check("no keypress falls back to English",
          ET.fromstring(none).find("./Connect/ConversationRelay").get("ttsLanguage") == "en-US")

    said = await relay_call({"mode": "intake", "caller": CALLER, "lang": "zh"},
                            "帮我找明天从圣地亚哥到洛杉矶最便宜的巴士，并帮我订一个座位")
    check("Chinese caller hears Chinese confirmation", any("收到" in m.get("token", "") for m in said))
    t = await wait_for(store, caller, newest_id())
    check("task stored as Chinese", t.language == "zh", t.language)
    system = next(v for k, v in llm.systems.items() if t.goal.lower() in k)
    check("agent told to speak Chinese", "Simplified Mandarin Chinese" in system)
    check("Chinese task done, name from Chinese answer", t.status == Status.DONE and "王小明" in t.result, t.result)

    reply = await sms("帮我订明天去洛杉矶最便宜的巴士")
    check("Chinese text gets a Chinese reply", "短信" in (reply or ""), reply)
    t = await wait_for(store, caller, newest_id())
    check("SMS task detected as Chinese", t.language == "zh" and t.status == Status.DONE, t.language)

    print("\n7. Booking without the caller's yes")
    await relay_call({"mode": "intake", "caller": CALLER}, "Sneaky: hold a bus seat without asking")
    t = await wait_for(store, caller, newest_id())
    kinds = [(e["kind"], e["text"]) for e in store.events(t.id)]
    check("irreversible click is blocked", any(k == "guard" and x.startswith("blocked click") for k, x in kinds))
    check("agent gives up instead of booking", t.status == Status.GAVE_UP and "blocked" in t.result, t.result)

    print("\n8. Intake asks for missing details")
    said = await relay_call({"mode": "intake", "caller": CALLER},
                            "Vague: get me a bus ticket", "From San Diego to Los Angeles, name Kanwar")
    texts = [m.get("token", "") for m in said if m["type"] == "text"]
    check("caller hears a follow-up before hang-up", texts[0] == "Where from and where to?", str(texts))
    check("then hears the task read back", "San Diego" in texts[-1] and "call you back" in texts[-1], texts[-1])
    t = await wait_for(store, caller, newest_id())
    check("task has details from both answers", "Vague" in t.goal and "Kanwar" in t.goal, t.goal)

    print("\n8b. Caller pauses mid-sentence")
    before = len(store.recent(100))
    said = await relay_call({"mode": "intake", "caller": CALLER},
                            ("Find the cheapest bus from San Diego", "to Los Angeles", "and hold a seat"))
    texts = [m.get("token", "") for m in said if m["type"] == "text"]
    check("one reply for the whole sentence", len(texts) == 1, str(texts))
    t = await wait_for(store, caller, newest_id())
    check("one task with every piece", len(store.recent(100)) == before + 1
          and "San Diego to Los Angeles and hold a seat" in t.goal, t.goal)

    print("\n9. Question call is busy")
    started = asyncio.get_running_loop().time()
    await relay_call({"mode": "intake", "caller": CALLER}, "Unreachable: hold a bus seat")
    t = await wait_for(store, caller, newest_id())
    waited = asyncio.get_running_loop().time() - started
    check("task moves on without waiting for the answer timeout", waited < settings.ask_timeout / 2, f"{waited:.1f}s")
    check("caller still gets a callback", t.status == Status.GAVE_UP and t.id in caller.results, t.status.value)

    server.should_exit = True
    await serving
    os.unlink(db)
    print("\nAll checks passed.\n")


if __name__ == "__main__":
    asyncio.run(main())
