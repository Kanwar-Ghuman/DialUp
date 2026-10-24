"""A caller is never rung while they are already on a call, and an old call's status
can't cancel the question we're asking now."""
import asyncio

from dialup.telephony.lines import Lines
from dialup.telephony.routes import _same_question_call


def test_second_call_waits_until_the_first_ends():
    async def run():
        lines = Lines()
        await lines.hold("+1", "inbound")
        started = False

        async def second():
            nonlocal started
            await lines.hold("+1", "outbound")
            started = True

        waiting = asyncio.create_task(second())
        await asyncio.sleep(0.05)
        assert not started
        lines.release("+1", "old-call")  # a status for some other call
        await asyncio.sleep(0.05)
        assert not started
        lines.release("+1", "inbound")
        await waiting
        assert started

    asyncio.run(run())


def test_status_for_an_older_call_is_ignored():
    assert _same_question_call(True, "CA2", "CA1") is False
    assert _same_question_call(True, None, "CA1") is False  # not dialed yet
    assert _same_question_call(True, "CA2", "CA2") is True
    assert _same_question_call(False, None, None) is True  # test caller, no tracking
