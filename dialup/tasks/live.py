"""A task answered on the call the caller is already on, instead of a callback."""
import asyncio


class LiveBoard:
    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = {}

    def open(self, task_id: str) -> None:
        self._queues[task_id] = asyncio.Queue()

    def close(self, task_id: str) -> None:
        """Drop the open call. A result that arrives after this is phoned out instead."""
        self._queues.pop(task_id, None)

    def covers(self, task_id: str) -> bool:
        return task_id in self._queues

    async def ask(self, task_id: str, question: str) -> bool:
        q = self._queues.get(task_id)
        if q is None:
            return False
        await q.put(("ask", question))
        return True

    async def result(self, task_id: str, text: str) -> bool:
        q = self._queues.get(task_id)
        if q is None:
            return False
        await q.put(("result", text))
        return True

    def pending(self, task_id: str):
        """Await the next thing to say, or None if this call is no longer live."""
        q = self._queues.get(task_id)
        return None if q is None else asyncio.create_task(q.get())
