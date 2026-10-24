"""One place to record what happens: saves to the store, prints, and pushes to the live view."""
import asyncio

from .models import Status
from .store import Store


class EventBus:
    """Fan-out of events to live-view subscribers (Server-Sent Events)."""

    def __init__(self):
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, message: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass  # slow viewer, drop rather than block the agent


class Journal:
    def __init__(self, store: Store, bus: EventBus):
        self.store = store
        self.bus = bus

    def log(self, task_id: str, kind: str, text: str) -> None:
        event = self.store.add_event(task_id, kind, text)
        print(f"[{task_id}] {kind:<7} {text}", flush=True)
        self.bus.publish({"type": "event", "event": event})

    def update(self, task_id: str, **fields) -> None:
        self.store.update(task_id, **fields)
        task = self.store.get(task_id)
        if task:
            self.bus.publish({"type": "task", "task": task.to_dict()})

    def status(self, task_id: str, status: Status, **fields) -> None:
        self.update(task_id, status=status, **fields)
        self.log(task_id, "status", status.value)
