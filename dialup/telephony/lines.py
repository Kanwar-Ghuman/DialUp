"""One phone line per caller, so Dial-Up never rings someone who is already on a call with it."""
import asyncio


class Lines:
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self._sid: dict[str, str | None] = {}  # caller -> id of the call holding the line

    def _lock(self, caller: str) -> asyncio.Lock:
        return self._locks.setdefault(caller, asyncio.Lock())

    async def hold(self, caller: str, sid: str) -> None:
        """Wait until this caller is free, then take the line for `sid`."""
        await self._lock(caller).acquire()
        self._sid[caller] = sid

    def set_sid(self, caller: str, sid: str) -> None:
        """The outbound call now has a Twilio id. Status events release it by that id."""
        if self._lock(caller).locked():
            self._sid[caller] = sid

    def release(self, caller: str, sid: str) -> None:
        """Free the line when that call ends. A status for an older call does nothing."""
        if self._sid.get(caller) != sid:
            return
        self._sid[caller] = None
        lock = self._lock(caller)
        if lock.locked():
            lock.release()
