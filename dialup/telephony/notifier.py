"""Reaches the caller through Twilio: an outbound call for voice tasks, a text for SMS tasks."""
import asyncio

from twilio.rest import Client

from ..config import Settings
from ..i18n import phrases
from ..tasks.models import Channel, Task
from ..tasks.live import LiveBoard
from . import twiml
from .lines import Lines


class TwilioNotifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = Client(settings.twilio_sid, settings.twilio_token)
        self.lines = Lines()
        self.live = LiveBoard()
        self.asking: dict[str, tuple[str, str | None]] = {}  # task id -> (question, call sid)

    async def ask(self, task: Task, question: str) -> None:
        if await self.live.ask(task.id, question):
            return  # they're still on the line; the open call speaks the question
        if task.channel == Channel.SMS:
            await self._text(task.caller, f"{question} {phrases(task.language).sms_reply_hint}")
        else:
            self.asking[task.id] = (question, None)  # sid arrives once the call is actually placed
            await self.call_question(task, question, attempt=1)

    async def call_question(self, task: Task, question: str, attempt: int) -> None:
        """Question call with a status callback, so a busy or unanswered call is retried."""
        status_url = f"{self.settings.public_url}/twilio/status?task={task.id}&attempt={attempt}&kind=ask"
        sid = await self._call(task, question, {"mode": "ask", "task": task.id}, status_url)
        self.asking[task.id] = (question, sid)

    async def send_result(self, task: Task, text: str) -> None:
        if await self.live.result(task.id, text):
            return  # spoken on the call they're already on
        if task.channel == Channel.SMS:
            await self._text(task.caller, text)
        else:
            await self.call_result(task, text, attempt=1)

    async def call_result(self, task: Task, text: str, attempt: int) -> None:
        """Result call with a status callback, so an unanswered call can be retried."""
        status_url = f"{self.settings.public_url}/twilio/status?task={task.id}&attempt={attempt}"
        await self._call(task, text, {"mode": "result", "task": task.id}, status_url)

    async def _call(self, task: Task, greeting: str, params: dict, status_url: str | None = None) -> str:
        """Dial `task.caller`, waiting until their line is free. Returns the Twilio call id."""
        params = {**params, "lang": task.language}
        token = f"dial-{task.id}-{status_url}"
        await self.lines.hold(task.caller, token)
        try:
            await asyncio.sleep(self.settings.call_delay)  # let the phone settle after the last call
            kwargs = {
                "to": task.caller,
                "from_": self.settings.twilio_number,
                "twiml": twiml.relay(self.settings, task.language, greeting, params),
            }
            if status_url:
                kwargs.update(status_callback=status_url, status_callback_method="POST")
            call = await asyncio.to_thread(self.client.calls.create, **kwargs)
        except Exception:
            self.lines.release(task.caller, token)
            raise
        self.lines.set_sid(task.caller, call.sid)  # the status callback frees the line
        return call.sid

    async def _text(self, to: str, body: str) -> None:
        await asyncio.to_thread(
            self.client.messages.create, to=to, from_=self.settings.twilio_number, body=body,
        )
