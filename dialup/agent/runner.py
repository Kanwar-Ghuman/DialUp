"""Runs tasks in the background: Claude decides, the browser acts, the guard supervises."""
import asyncio
import json
from typing import Protocol

from playwright.async_api import Browser as PWBrowser

from ..config import Settings
from ..i18n import phrases
from ..tasks.inbox import Inbox
from ..tasks.journal import Journal
from ..tasks.models import Status, Task
from ..tasks.store import Store
from . import guardrails
from .guards import Guard
from .prompts import NO_TOOL_NUDGE, SUPERVISOR_WARNING, system_prompt
from .tools import BROWSER_TOOLS, TOOLS, Browser


class Notifier(Protocol):
    """How the runner reaches the caller. Twilio in prod, a fake in tests."""
    async def ask(self, task: Task, question: str) -> None: ...
    async def send_result(self, task: Task, text: str) -> None: ...


class Runner:
    MAX_ASKS = 4         # calls to the caller per task (questions + confirmations)
    MAX_UNANSWERED = 2   # unanswered calls before we stop trying

    def __init__(self, settings: Settings, store: Store, journal: Journal,
                 inbox: Inbox, notifier: Notifier, llm):
        self.settings = settings
        self.store = store
        self.journal = journal
        self.inbox = inbox
        self.notifier = notifier
        self.llm = llm
        self.browser: PWBrowser | None = None  # set at startup
        self._slots = asyncio.Semaphore(settings.max_concurrent)
        self._running: set[asyncio.Task] = set()

    def start(self, task_id: str) -> None:
        t = asyncio.create_task(self._run(task_id))
        self._running.add(t)
        t.add_done_callback(self._running.discard)

    async def _run(self, task_id: str) -> None:
        async with self._slots:
            task = self.store.get(task_id)
            self.journal.status(task_id, Status.RUNNING)
            context = await self.browser.new_context()
            try:
                status, spoken = await self._loop(task, Browser(await context.new_page()))
            except Exception as e:  # never leave a caller without a callback
                self.journal.log(task_id, "error", f"{type(e).__name__}: {e}")
                status, spoken = Status.FAILED, phrases(task.language).crash
            finally:
                await context.close()

            self.journal.status(task_id, status, result=spoken)
            self.journal.log(task_id, "result", spoken)
            try:
                await self.notifier.send_result(self.store.get(task_id), spoken)
            except Exception as e:
                self.journal.log(task_id, "error", f"callback failed: {e}")

    async def _loop(self, task: Task, browser: Browser) -> tuple[Status, str]:
        s = self.settings
        guard = Guard(s.max_steps, s.max_minutes * 60, s.token_budget,
                      s.cost_budget, s.price_in, s.price_out)
        say = phrases(task.language)
        system = system_prompt(s.site_base, task.language)
        messages: list[dict] = [{"role": "user", "content": f"Caller's request: {task.goal}"}]
        asks = unanswered = 0

        while True:
            reply = await self.llm.messages.create(
                model=s.model, max_tokens=1024, system=system, tools=TOOLS, messages=messages,
            )
            guard.record_usage(reply.usage.input_tokens, reply.usage.output_tokens)
            messages.append({"role": "assistant", "content": reply.content})

            calls = [b for b in reply.content if b.type == "tool_use"]
            results: list[dict] = []
            if not calls:
                guard.record_action("no_tool", {})

            for call in calls:
                guard.record_action(call.name, call.input)
                self.journal.log(task.id, "step", _describe(call.name, call.input))

                if call.name == "finish":
                    return Status.DONE, call.input["summary"]
                if call.name == "give_up":
                    return Status.GAVE_UP, say.gave_up.format(reason=call.input["reason"])
                if call.name == "ask_user":
                    if asks >= self.MAX_ASKS:
                        output = (f"BLOCKED: you already called the caller {self.MAX_ASKS} times. "
                                  "Don't call again. finish or give_up with what you have.")
                    else:
                        asks += 1
                        answer = await self._ask(task, call.input["question"])
                        if answer is None:
                            unanswered += 1
                            if unanswered >= self.MAX_UNANSWERED:
                                self.journal.log(task.id, "guard", "stopped: caller didn't answer twice")
                                return Status.GAVE_UP, say.no_answer
                            output = "The caller didn't answer. Continue without it if you can, otherwise give_up."
                        else:
                            output = f"Caller said: {answer}"
                elif call.name in BROWSER_TOOLS:
                    output = await self._browse(task, browser, guard, call.name, call.input)
                else:
                    output = f"unknown tool {call.name}"
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": output})

            self.journal.update(task.id, steps=guard.steps, tokens=guard.tokens)

            verdict = guard.check()
            if verdict.action == "stop":
                self.journal.log(task.id, "guard", f"stopped: {verdict.reason}")
                return Status.STOPPED, say.stopped.format(reason=verdict.reason)

            if results:
                if verdict.action == "warn":
                    self.journal.log(task.id, "guard", f"warning: {verdict.reason}")
                    results.append({"type": "text", "text": SUPERVISOR_WARNING.format(reason=verdict.reason)})
                messages.append({"role": "user", "content": results})
            else:
                messages.append({"role": "user", "content": NO_TOOL_NUDGE})

    async def _browse(self, task: Task, browser: Browser, guard: Guard, name: str, args: dict) -> str:
        if name == "fill":
            reason = await guardrails.check_fill(browser.page, args.get("label", ""), args.get("value", ""))
            if reason:
                self.journal.log(task.id, "guard", f"blocked fill: {reason}")
                return f"BLOCKED: {reason}"
        try:
            output = await browser.run(name, args)
        except Exception as e:
            first_line = (str(e).splitlines() or [""])[0][:200]
            output = f"error: {type(e).__name__}: {first_line}"
            self.journal.log(task.id, "error", output)
        if name == "read_page":
            guard.record_page(output)
        return output

    async def _ask(self, task: Task, question: str) -> str | None:
        """Calls (or texts) the caller and waits. Returns their answer, or None if no answer."""
        self.journal.status(task.id, Status.WAITING)
        answer = await self.inbox.ask(
            task.id, lambda: self.notifier.ask(task, question), self.settings.ask_timeout,
        )
        self.journal.log(task.id, "answer", answer if answer is not None else "(no answer)")
        self.journal.status(task.id, Status.RUNNING)
        return answer


def _describe(name: str, args: dict) -> str:
    if not args:
        return name
    return f"{name} {json.dumps(args, ensure_ascii=False)[:160]}"
