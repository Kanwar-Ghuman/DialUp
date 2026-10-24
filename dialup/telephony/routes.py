"""Twilio endpoints: inbound calls, the language menu, the ConversationRelay socket, SMS, call status."""
import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Request, Response, WebSocket, WebSocketDisconnect

from ..agent.intake import clarify
from ..i18n import detect, phrases
from ..services import Services, services
from ..tasks.models import Channel
from . import twiml
from .security import twilio_form

router = APIRouter()

RETRY_DELAY = 30      # seconds before calling back again after an unanswered result call
ASK_RETRY_DELAY = 10  # busy usually means the caller is still hanging up from the last call
UNREACHED = {"busy", "no-answer", "failed", "canceled"}


def _xml(body: str) -> Response:
    return Response(body, media_type="text/xml")


def _intake(s: Services, lang: str, caller: str) -> Response:
    """Start the conversation in `lang`."""
    params = {"mode": "intake", "caller": caller, "lang": lang}
    return _xml(twiml.relay(s.settings, lang, phrases(lang).greeting, params))


# ---------- Voice ----------

@router.post("/voice")
async def inbound_call(request: Request):
    """One language: go straight to the conversation. Several: play the language menu first."""
    form = await twilio_form(request)
    s = services(request)
    if len(s.settings.languages) == 1:
        return _intake(s, s.settings.default_language, form["From"])
    return _xml(twiml.language_menu(s.settings, action="/voice/language"))


@router.post("/voice/language")
async def chose_language(request: Request):
    form = await twilio_form(request)
    s = services(request)
    langs = s.settings.languages
    digit = form.get("Digits", "")
    lang = langs[int(digit) - 1] if digit.isdigit() and 1 <= int(digit) <= len(langs) else s.settings.default_language
    print(f"[call]   language menu: pressed {digit or 'nothing'} -> {lang}", flush=True)
    return _intake(s, lang, form["From"])


@router.websocket("/ws")
async def conversation_relay(ws: WebSocket):
    """Every call, inbound or outbound, lands here. The `mode` parameter says what it's for."""
    await ws.accept()
    s = services(ws)
    ctx: dict[str, str] = {}
    turns: list[str] = []  # what the caller said so far on an intake call
    heard: list[str] = []  # pieces of the current answer; people pause mid-sentence
    timer: asyncio.Task | None = None
    try:
        while True:
            try:
                raw = await (asyncio.wait_for(ws.receive_text(), s.settings.speech_pause)
                             if heard else ws.receive_text())
            except asyncio.TimeoutError:  # caller went quiet: treat what we heard as one answer
                said = " ".join(heard)
                heard.clear()
                if await _respond(ws, s, ctx, turns, said):
                    break
                continue
            msg = json.loads(raw)
            kind = msg.get("type")
            if kind == "setup":
                ctx = msg.get("customParameters") or {}
                print(f"[call]   setup mode={ctx.get('mode')} lang={ctx.get('lang', '-')} "
                      f"task={ctx.get('task', '-')}", flush=True)
                if ctx.get("mode") == "result":
                    # The result is the greeting. Hang up once it's been read.
                    timer = asyncio.create_task(_hang_up(ws, s.settings.result_hold))
            elif kind == "prompt":
                said = msg.get("voicePrompt", "").strip()
                if said:
                    heard.append(said)
            elif kind == "error":
                print(f"[call]   relay error: {msg}", flush=True)
    except WebSocketDisconnect:
        _handle_hangup(s, ctx, turns, " ".join(heard))
    finally:
        if timer:
            timer.cancel()


async def _respond(ws: WebSocket, s: Services, ctx: dict[str, str], turns: list[str], said: str) -> bool:
    """Reply to one full answer. Returns True once the call is over."""
    if ctx.get("mode") == "intake":
        turns.append(said)
        lang = ctx.get("lang") or s.settings.default_language
        question, task_text = await clarify(s.runner.llm, s.settings.model, lang, turns)
        if question:
            await _say(ws, question)
            return False
        reply = _start_task(s, ctx, turns, task_text)
    else:
        reply = _handle_speech(s, ctx, said)
    await _say(ws, reply)
    await _hang_up(ws, _speech_seconds(reply))
    return True


def _handle_hangup(s: Services, ctx: dict[str, str], turns: list[str], said: str) -> None:
    """The caller hung up mid-conversation. Still use what they said."""
    mode = ctx.get("mode")
    if mode == "intake" and not ctx.get("started"):
        heard = [*turns, said] if said else turns
        if heard:
            _start_task(s, ctx, heard, " ".join(heard))
    elif mode == "ask" and said:
        _handle_speech(s, ctx, said)


def _start_task(s: Services, ctx: dict[str, str], turns: list[str], task_text: str) -> str:
    lang = ctx.get("lang") or s.settings.default_language
    ctx["started"] = "1"
    task = s.store.create_task(ctx["caller"], task_text, Channel.VOICE, lang)
    s.journal.log(task.id, "intake", f"({lang}) {' / '.join(turns)}")
    s.runner.start(task.id)
    return phrases(lang).got_it_task.format(task=task_text)


def _handle_speech(s: Services, ctx: dict[str, str], said: str) -> str:
    mode = ctx.get("mode")
    lang = ctx.get("lang") or s.settings.default_language
    say = phrases(lang)
    if mode == "ask":
        if s.inbox.deliver(ctx.get("task", ""), said):
            return say.thanks
        return say.late_answer
    return say.goodbye


async def _say(ws: WebSocket, text: str) -> None:
    await ws.send_text(json.dumps({"type": "text", "token": text, "last": True}))


def _speech_seconds(text: str) -> float:
    """Rough time to read `text` aloud, so the call doesn't end mid-sentence."""
    cjk = sum(1 for ch in text if ord(ch) >= 0x2E80)
    return 2 + cjk * 0.25 + (len(text) - cjk) * 0.07


async def _hang_up(ws: WebSocket, delay: float) -> None:
    await asyncio.sleep(delay)  # let text-to-speech finish
    try:
        await ws.send_text(json.dumps({"type": "end"}))
    except Exception:
        pass  # caller already hung up


@router.post("/twilio/status")
async def call_status(request: Request, background: BackgroundTasks, task: str,
                      attempt: int = 1, kind: str = "result"):
    """Twilio reports how a question or result call ended. Retry if nobody picked up."""
    form = await twilio_form(request)
    s = services(request)
    outcome = form.get("CallStatus", "unknown")
    s.journal.log(task, "call", f"{'question' if kind == 'ask' else 'result'} call {outcome} (attempt {attempt})")

    t = s.store.get(task)
    if kind == "ask":
        if not s.inbox.is_waiting(task):
            return Response(status_code=204)  # answered, or the task moved on
        question = s.notifier.asking.get(task)
        if outcome in UNREACHED and t and question and attempt <= s.settings.callback_retries:
            async def retry_question():
                await asyncio.sleep(ASK_RETRY_DELAY)
                if s.inbox.is_waiting(task):
                    s.journal.log(task, "call", f"retrying question call (attempt {attempt + 1})")
                    await s.notifier.call_question(t, question, attempt + 1)
            background.add_task(retry_question)
        else:
            s.inbox.no_answer(task)
        return Response(status_code=204)

    if outcome in UNREACHED and t and t.result and attempt <= s.settings.callback_retries:
        async def retry():
            await asyncio.sleep(RETRY_DELAY)
            s.journal.log(task, "call", f"retrying result call (attempt {attempt + 1})")
            await s.notifier.call_result(t, t.result, attempt + 1)
        background.add_task(retry)
    return Response(status_code=204)


# ---------- SMS ----------

@router.post("/sms")
async def inbound_sms(request: Request):
    """Text the task instead of calling. Replies to a pending question go back to that task."""
    form = await twilio_form(request)
    s = services(request)
    caller, body = form["From"], form.get("Body", "").strip()

    waiting = s.store.waiting_for(caller)
    if waiting and s.inbox.deliver(waiting.id, body):
        return _xml(twiml.sms_reply(phrases(waiting.language).thanks))

    lang = detect(body, s.settings.languages, s.settings.default_language)
    if not body:
        return _xml(twiml.sms_reply(phrases(lang).sms_empty))

    task = s.store.create_task(caller, body, Channel.SMS, lang)
    s.journal.log(task.id, "intake", f"(sms, {lang}) {body}")
    s.runner.start(task.id)
    return _xml(twiml.sms_reply(phrases(lang).got_it_sms))
