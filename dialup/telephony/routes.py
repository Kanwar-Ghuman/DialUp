"""Twilio endpoints: inbound calls, the language menu, the ConversationRelay socket, SMS, call status."""
import asyncio
import contextlib
import json
import time

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
ANSWER_GRACE = 5      # a spoken answer can arrive just after Twilio says the call ended
UNREACHED = {"busy", "no-answer", "failed", "canceled"}
TERMINAL_CALL = UNREACHED | {"completed"}
LIVE_LIMIT = 90  # seconds to answer on the same call before switching to a callback


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


class _Ear:
    """One pending read from the socket, reused across waits so a timeout never drops a message."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self._task: asyncio.Task | None = None

    def pending(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.ws.receive_text())
        return self._task


@router.websocket("/ws")
async def conversation_relay(ws: WebSocket):
    """Every call, inbound or outbound, lands here. The `mode` parameter says what it's for."""
    await ws.accept()
    s = services(ws)
    ctx: dict = {}
    turns: list[str] = []  # what the caller said so far on an intake call
    heard: list[str] = []  # pieces of the current answer; people pause mid-sentence
    timer: asyncio.Task | None = None
    line: tuple[str, str] | None = None  # (caller, token) while an inbound call holds the line
    ear = _Ear(ws)
    try:
        while True:
            if _live_expired(ctx):
                await _switch_to_callback(ws, s, ctx)
                break
            incoming = ear.pending()
            waiters = [incoming]
            spoken = s.notifier.live.pending(ctx["live_id"]) if ctx.get("live_id") else None
            if spoken:
                waiters.append(spoken)
            timeout = s.settings.speech_pause if heard else None
            done, _ = await asyncio.wait(waiters, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if spoken and spoken not in done:
                spoken.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await spoken
            if not done:  # caller went quiet: treat what we heard as one answer
                said = " ".join(heard)
                heard.clear()
                if ctx.get("live_id"):
                    if said:
                        s.inbox.deliver(ctx["live_id"], said)
                    continue
                if await _respond(ws, s, ctx, turns, said):
                    break
                continue
            if incoming in done:
                try:
                    raw = incoming.result()
                except WebSocketDisconnect:
                    _handle_hangup(s, ctx, turns, " ".join(heard))
                    break
                if _on_message(ctx, heard, json.loads(raw)):
                    said = heard.pop() if heard else ""
                    heard.clear()
                    if ctx.get("live_id"):
                        s.inbox.deliver(ctx["live_id"], said)
                    elif await _respond(ws, s, ctx, turns, said):
                        break
                elif ctx.get("mode") == "result" and timer is None and ctx.get("_result"):
                    timer = asyncio.create_task(_hang_up(ws, s.settings.result_hold))
                elif ctx.get("mode") == "intake" and ctx.get("caller") and line is None:
                    lines = getattr(s.notifier, "lines", None)
                    if lines:
                        line = (ctx["caller"], f"in-{id(ws)}")
                        await lines.hold(*line)
            if spoken and spoken in done:
                kind, text = spoken.result()
                heard.clear()
                await _say(ws, text)
                if kind == "result":
                    await _hang_up(ws, _speech_seconds(text))
                    break
                ctx["live_deadline"] = time.monotonic() + LIVE_LIMIT  # time to answer the question
    finally:
        if timer:
            timer.cancel()
        if ear._task and not ear._task.done():
            ear._task.cancel()
        if ear._task:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await ear._task  # retrieve its result so a disconnect isn't reported as a stray error
        if ctx.get("live_id"):
            s.notifier.live.close(ctx["live_id"])  # a late result is phoned out instead
        if line:
            s.notifier.lines.release(*line)


def _live_expired(ctx: dict) -> bool:
    deadline = ctx.get("live_deadline")
    return bool(ctx.get("live_id") and deadline and time.monotonic() > deadline)


async def _switch_to_callback(ws: WebSocket, s: Services, ctx: dict) -> None:
    """The lookup ran long. Hang up and let the normal callback deliver the result."""
    s.notifier.live.close(ctx.pop("live_id"))
    ctx.pop("live_deadline", None)
    lang = ctx.get("lang") or s.settings.default_language
    text = phrases(lang).still_working
    await _say(ws, text)
    await _hang_up(ws, _speech_seconds(text))


def _on_message(ctx: dict, heard: list[str], msg: dict) -> bool:
    """Record one socket message. Returns True when the caller just gave a complete answer
    (a keypress), so the caller should reply now instead of waiting out the pause."""
    kind = msg.get("type")
    if kind == "setup":
        ctx.update(msg.get("customParameters") or {})
        print(f"[call]   setup mode={ctx.get('mode')} lang={ctx.get('lang', '-')} "
              f"task={ctx.get('task', '-')}", flush=True)
        ctx["_result"] = ctx.get("mode") == "result"
        return False
    if kind == "prompt":
        said = msg.get("voicePrompt", "").strip()
        if said:
            heard.append(said)
        return False
    if kind == "dtmf" and (ctx.get("mode") == "ask" or ctx.get("live_id")):
        # A keypress answers a question too ("press 1 to confirm"). Ignored on other calls.
        heard[:] = [str(msg.get("digit", "")).strip()]
        return True
    if kind == "error":
        print(f"[call]   relay error: {msg}", flush=True)
    return False


async def _respond(ws: WebSocket, s: Services, ctx: dict, turns: list[str], said: str) -> bool:
    """Reply to one full answer. Returns True once the call is over."""
    if ctx.get("mode") == "intake":
        turns.append(said)
        lang = ctx.get("lang") or s.settings.default_language
        question, task_text, quick = await clarify(s.runner.llm, s.settings.model, lang, turns)
        if question:
            await _say(ws, question)
            return False
        if quick and getattr(s.notifier, "live", None):
            await _say(ws, phrases(lang).one_moment)
            _start_live(s, ctx, turns, task_text)
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


def _create_task(s: Services, ctx: dict, turns: list[str], task_text: str):
    lang = ctx.get("lang") or s.settings.default_language
    ctx["started"] = "1"
    task = s.store.create_task(ctx["caller"], task_text, Channel.VOICE, lang)
    s.journal.log(task.id, "intake", f"({lang}) {' / '.join(turns)}")
    return task


def _start_task(s: Services, ctx: dict, turns: list[str], task_text: str) -> str:
    task = _create_task(s, ctx, turns, task_text)
    s.runner.start(task.id)
    return phrases(task.language).got_it_task.format(task=task_text)


def _start_live(s: Services, ctx: dict, turns: list[str], task_text: str) -> None:
    """Answer on this call. Open the live queue before the agent starts, so a fast answer isn't missed."""
    task = _create_task(s, ctx, turns, task_text)
    s.notifier.live.open(task.id)
    ctx["live_id"] = task.id
    ctx["live_deadline"] = time.monotonic() + LIVE_LIMIT
    s.runner.start(task.id)


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


def _current_question(notifier, task: str) -> tuple[str | None, str | None, bool]:
    """(question, call sid, tracked). Untracked means a test caller: any status applies."""
    asking = getattr(notifier, "asking", None)
    if not isinstance(asking, dict) or task not in asking:
        return None, None, False
    entry = asking[task]
    if isinstance(entry, tuple):
        return entry[0], entry[1], True
    return entry, None, True


def _same_question_call(tracked: bool, current_sid: str | None, incoming_sid: str | None) -> bool:
    """A status event counts only for the call we're waiting on now."""
    if not tracked:
        return True
    if not current_sid:
        return False  # the call hasn't been placed yet
    return not incoming_sid or incoming_sid == current_sid


@router.post("/twilio/status")
async def call_status(request: Request, background: BackgroundTasks, task: str,
                      attempt: int = 1, kind: str = "result"):
    """Twilio reports how a question or result call ended. Retry if nobody picked up."""
    form = await twilio_form(request)
    s = services(request)
    outcome = form.get("CallStatus", "unknown")
    s.journal.log(task, "call", f"{'question' if kind == 'ask' else 'result'} call {outcome} (attempt {attempt})")

    t = s.store.get(task)
    sid = form.get("CallSid")
    lines = getattr(s.notifier, "lines", None)
    if lines and t and sid and outcome in TERMINAL_CALL:
        lines.release(t.caller, sid)  # frees the line only if this call still holds it

    if kind == "ask":
        if not s.inbox.is_waiting(task):
            return Response(status_code=204)  # answered, or the task moved on
        question, current_sid, tracked = _current_question(s.notifier, task)
        if not _same_question_call(tracked, current_sid, sid):
            return Response(status_code=204)  # a previous call ending; the current one is still open
        if outcome in UNREACHED and t and question and attempt <= s.settings.callback_retries:
            async def retry_question():
                await asyncio.sleep(ASK_RETRY_DELAY)
                _, now, _ = _current_question(s.notifier, task)
                if s.inbox.is_waiting(task) and now == current_sid:
                    s.journal.log(task, "call", f"retrying question call (attempt {attempt + 1})")
                    await s.notifier.call_question(t, question, attempt + 1)
            background.add_task(retry_question)
        elif outcome in UNREACHED or not tracked:
            s.inbox.no_answer(task)
        elif outcome == "completed":
            async def settle():  # they may have answered in the last seconds of the call
                await asyncio.sleep(ANSWER_GRACE)
                _, now, _ = _current_question(s.notifier, task)
                if s.inbox.is_waiting(task) and now == current_sid:
                    s.journal.log(task, "call", "question call ended without an answer")
                    s.inbox.no_answer(task)
            background.add_task(settle)
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
