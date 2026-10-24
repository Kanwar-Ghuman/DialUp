"""Reaches the caller through Twilio: an outbound call for voice tasks, a text for SMS tasks."""
import asyncio

from twilio.rest import Client

from ..config import Settings
from ..i18n import phrases
from ..tasks.models import Channel, Task
from . import twiml


class TwilioNotifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = Client(settings.twilio_sid, settings.twilio_token)
        self.asking: dict[str, str] = {}  # task id -> question being asked, for retries

    async def ask(self, task: Task, question: str) -> None:
        if task.channel == Channel.SMS:
            await self._text(task.caller, f"{question} {phrases(task.language).sms_reply_hint}")
        else:
            self.asking[task.id] = question
            await self.call_question(task, question, attempt=1)

    async def call_question(self, task: Task, question: str, attempt: int) -> None:
        """Question call with a status callback, so a busy or unanswered call is retried."""
        status_url = f"{self.settings.public_url}/twilio/status?task={task.id}&attempt={attempt}&kind=ask"
        await self._call(task, question, {"mode": "ask", "task": task.id}, status_url)

    async def send_result(self, task: Task, text: str) -> None:
        if task.channel == Channel.SMS:
            await self._text(task.caller, text)
        else:
            await self.call_result(task, text, attempt=1)

    async def call_result(self, task: Task, text: str, attempt: int) -> None:
        """Result call with a status callback, so an unanswered call can be retried."""
        status_url = f"{self.settings.public_url}/twilio/status?task={task.id}&attempt={attempt}"
        await self._call(task, text, {"mode": "result", "task": task.id}, status_url)

    async def _call(self, task: Task, greeting: str, params: dict, status_url: str | None = None) -> None:
        params = {**params, "lang": task.language}
        kwargs = {
            "to": task.caller,
            "from_": self.settings.twilio_number,
            "twiml": twiml.relay(self.settings, task.language, greeting, params),
        }
        if status_url:
            kwargs.update(status_callback=status_url, status_callback_method="POST")
        await asyncio.to_thread(self.client.calls.create, **kwargs)

    async def _text(self, to: str, body: str) -> None:
        await asyncio.to_thread(
            self.client.messages.create, to=to, from_=self.settings.twilio_number, body=body,
        )
