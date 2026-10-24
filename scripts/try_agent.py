"""Try the real agent (real Claude, real browser, mock sites) with your terminal as the phone.

No Twilio, no ngrok. Needs ANTHROPIC_API_KEY in .env. Run from the project root:

    python scripts/try_agent.py "Find the cheapest bus from San Diego to Los Angeles tomorrow and hold a seat"
    python scripts/try_agent.py --lang zh "帮我订明天去洛杉矶最便宜的巴士"
    python scripts/try_agent.py --auto Kanwar "..."      # answer every question with "Kanwar", say yes to confirms
    python scripts/try_agent.py --budget 0.02 "..."       # watch the supervisor stop it

When the agent "calls" you, type an answer. Press Enter on a blank line to not pick up.
"""
import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()  # before importing dialup, so the real API key wins

import uvicorn  # noqa: E402
import websockets  # noqa: E402
from anthropic import AsyncAnthropic  # noqa: E402

from dialup.app import create_app  # noqa: E402
from dialup.config import Settings  # noqa: E402
from dialup.tasks.models import TERMINAL  # noqa: E402

PORT = 8766  # not 8000, so it can run next to the real server
BASE = f"http://127.0.0.1:{PORT}"
CALLER = "+15550001111"


async def relay(params: dict, speech: str) -> None:
    """Talk to the server the way Twilio ConversationRelay does."""
    try:
        async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
            await ws.send(json.dumps({"type": "setup", "callSid": "CAlocal", "customParameters": params}))
            await ws.send(json.dumps({"type": "prompt", "voicePrompt": speech, "last": True}))
            async for raw in ws:
                if json.loads(raw)["type"] == "end":
                    break
    except websockets.ConnectionClosed:
        pass  # server shut down while the "call" was still open


class TerminalPhone:
    """Stands in for TwilioNotifier: questions show up here, you answer by typing."""

    def __init__(self, auto: str | None):
        self.auto = auto
        self.done = asyncio.Event()
        self.result = ""

    async def ask(self, task, question):
        asyncio.create_task(self._answer(task, question))

    async def _answer(self, task, question):
        print(f"\n📞 CALL: {question}", flush=True)
        if self.auto is not None:
            is_confirm = "Say yes" in question or "确认请说" in question
            answer = ("是" if task.language == "zh" else "yes") if is_confirm else self.auto
            print(f"   (auto) {answer}")
        else:
            answer = (await asyncio.to_thread(input, "   your answer (blank = don't pick up): ")).strip()
        if answer:
            await relay({"mode": "ask", "task": task.id, "lang": task.language}, answer)

    async def send_result(self, task, text):
        self.result = text
        self.done.set()


async def main(a):
    settings = Settings(
        twilio_sid="AClocal", twilio_token="local", twilio_number="+15550000000",
        public_host=f"127.0.0.1:{PORT}", site_base=BASE,
        model=a.model, max_steps=a.max_steps, max_minutes=a.max_minutes, token_budget=400_000,
        ask_timeout=a.ask_timeout, result_hold=1, max_concurrent=1, callback_retries=0,
        validate_twilio=False, db_path=tempfile.NamedTemporaryFile(suffix=".db", delete=False).name,
        languages=("en", "zh"), cost_budget=a.budget,
    )
    phone = TerminalPhone(a.auto)
    app = create_app(settings=settings, notifier=phone, llm=AsyncAnthropic(timeout=60, max_retries=2))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)

    started = time.monotonic()
    print(f"\nTask ({a.lang}): {a.request}\n", flush=True)
    await relay({"mode": "intake", "caller": CALLER, "lang": a.lang}, a.request)
    await phone.done.wait()

    store = app.state.services.store
    task = store.recent(1)[0]
    for _ in range(50):  # the status write can land just after the callback
        if task.status in TERMINAL:
            break
        await asyncio.sleep(0.1)
        task = store.get(task.id)
    print(f"\n📞 RESULT CALL: {phone.result}")
    print(f"\nstatus={task.status.value}  steps={task.steps}  tokens={task.tokens}  "
          f"time={time.monotonic() - started:.0f}s")

    server.should_exit = True
    await serving


if __name__ == "__main__":
    import os
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("request")
    p.add_argument("--lang", default="en", choices=["en", "zh"])
    p.add_argument("--auto", metavar="ANSWER", help="answer every question with this, say yes to confirms")
    p.add_argument("--budget", type=float, default=float(os.getenv("COST_BUDGET", "0.50")), help="USD per task")
    p.add_argument("--ask-timeout", type=int, default=20, help="seconds to wait for your answer")
    p.add_argument("--max-steps", type=int, default=25)
    p.add_argument("--max-minutes", type=float, default=5)
    p.add_argument("--model", default=os.getenv("MODEL", "claude-sonnet-5-5"))
    asyncio.run(main(p.parse_args()))
