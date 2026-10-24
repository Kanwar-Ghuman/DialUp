"""Shared objects, built once at startup and stored on app.state.services."""
from dataclasses import dataclass

from starlette.requests import HTTPConnection

from .agent.runner import Notifier, Runner
from .config import Settings
from .tasks.inbox import Inbox
from .tasks.journal import EventBus, Journal
from .tasks.store import Store


@dataclass
class Services:
    settings: Settings
    store: Store
    bus: EventBus
    journal: Journal
    inbox: Inbox
    notifier: Notifier
    runner: Runner


def services(conn: HTTPConnection) -> Services:
    """Works for both HTTP requests and WebSockets."""
    return conn.app.state.services
