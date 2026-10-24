"""Dial-Up server. Run with: uvicorn dialup.app:app --port 8000"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from playwright.async_api import async_playwright

from .agent.runner import Notifier, Runner
from .config import Settings, load_settings
from .mock_sites import bus
from .services import Services
from .tasks.inbox import Inbox
from .tasks.journal import EventBus, Journal
from .tasks.store import Store
from .telephony import routes as telephony
from .web import live


def create_app(settings: Settings | None = None, notifier: Notifier | None = None, llm=None) -> FastAPI:
    """Pass a fake notifier or llm to run without Twilio or Claude (see scripts/smoke_test.py)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        s = settings or load_settings()
        store = Store(s.db_path)
        lost = store.fail_unfinished()
        bus_ = EventBus()
        journal = Journal(store, bus_)
        inbox = Inbox()

        if notifier is not None:
            notify = notifier
        else:
            from .telephony.notifier import TwilioNotifier
            notify = TwilioNotifier(s)

        if llm is not None:
            model = llm
        else:
            from anthropic import AsyncAnthropic
            model = AsyncAnthropic()

        runner = Runner(s, store, journal, inbox, notify, model)
        pw = await async_playwright().start()
        runner.browser = await pw.chromium.launch()

        app.state.services = Services(s, store, bus_, journal, inbox, notify, runner)
        print(f"\nDial-Up ready")
        print(f"  Twilio voice webhook  {s.public_url}/voice")
        print(f"  Twilio SMS webhook    {s.public_url}/sms")
        print(f"  Live view             http://localhost:8000/live")
        if lost:
            print(f"  Marked {lost} unfinished task(s) from last run as failed")
        print(flush=True)
        try:
            yield
        finally:
            await runner.browser.close()
            await pw.stop()

    app = FastAPI(title="Dial-Up", lifespan=lifespan)
    app.include_router(telephony.router)
    app.include_router(live.router)
    app.include_router(bus.router)

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/live")

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"ok": True}

    return app


app = create_app()
