"""Routes a caller's answer back to the task that asked the question."""
import asyncio
from collections.abc import Awaitable, Callable


class Inbox:
    def __init__(self):
        self._waiting: dict[str, asyncio.Future] = {}

    async def ask(self, task_id: str, send: Callable[[], Awaitable[None]], timeout: float) -> str | None:
        """Register first, then send the question, so a fast answer is never missed."""
        fut = asyncio.get_running_loop().create_future()
        self._waiting[task_id] = fut
        try:
            await send()
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self._waiting.pop(task_id, None)

    def deliver(self, task_id: str, answer: str) -> bool:
        fut = self._waiting.get(task_id)
        if fut and not fut.done():
            fut.set_result(answer)
            return True
        return False
