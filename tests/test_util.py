import asyncio
from unittest import mock

import pytest

from csbot import util


@pytest.mark.asyncio
async def test_maybe_future_none():
    assert util.maybe_future(None) is None


@pytest.mark.asyncio
async def test_maybe_future_non_awaitable():
    on_error = mock.Mock(spec=callable)
    assert util.maybe_future("foo", on_error=on_error) is None
    assert on_error.mock_calls == [
        mock.call("foo"),
    ]


@pytest.mark.asyncio
async def test_maybe_future_coroutine():
    async def foo():
        await asyncio.sleep(0)
        return "bar"

    future = util.maybe_future(foo())
    assert future is not None
    assert not future.done()
    await future
    assert future.done()
    assert future.exception() is None


@pytest.mark.asyncio
async def test_maybe_future_result_none():
    result = await util.maybe_future_result(None)
    assert result is None


@pytest.mark.asyncio
async def test_maybe_future_result_non_awaitable():
    on_error = mock.Mock(spec=callable)
    result = await util.maybe_future_result("foo", on_error=on_error)
    assert result == "foo"
    assert on_error.mock_calls == [
        mock.call("foo"),
    ]


@pytest.mark.asyncio
async def test_maybe_future_result_coroutine():
    async def foo():
        await asyncio.sleep(0)
        return "bar"

    result = await util.maybe_future_result(foo())
    assert result == "bar"


def test_truncate_utf8():
    assert util.truncate_utf8(b"0123456789", 20) == b"0123456789"
    assert util.truncate_utf8(b"0123456789", 10) == b"0123456789"
    assert util.truncate_utf8(b"0123456789", 9) == b"012345..."
    assert util.truncate_utf8(b"0123456789", 9, b"?") == b"01234567?"
    assert util.truncate_utf8(b"\xE2\x98\xBA\xE2\x98\xBA\xE2\x98\xBA", 8, b"?") == b"\xE2\x98\xBA\xE2\x98\xBA?"
    assert util.truncate_utf8(b"\xE2\x98\xBA\xE2\x98\xBA\xE2\x98\xBA", 8) == b"\xE2\x98\xBA..."


# @pytest.mark.skip
class TestRateLimited:
    @pytest.mark.asyncio
    async def test_bursts(self, event_loop, fast_forward):
        f = mock.Mock(spec=callable)
        # Test with 2 calls per 2 seconds
        rl = util.RateLimited(f, period=2.0, count=2, loop=event_loop)
        rl.start()

        # First 2 calls should complete immediately
        await asyncio.wait([rl(1), rl(2)], timeout=0)
        assert f.mock_calls == [mock.call(1), mock.call(2)]

        # 3rd and 4th calls should be blocked until enough time has passed
        f3 = rl(3)
        f4 = rl(4)
        await asyncio.wait([f3, f4], timeout=0)
        assert not f3.done()
        assert not f4.done()
        assert f.mock_calls == [mock.call(1), mock.call(2)]
        # Fast-forward time, now 3rd and 4th calls should be processed
        await fast_forward(2)
        await asyncio.wait([f3, f4], timeout=0)
        assert f3.done()
        assert f4.done()
        assert f.mock_calls == [mock.call(1), mock.call(2), mock.call(3), mock.call(4)]

        rl.stop()

    @pytest.mark.asyncio
    async def test_constant_rate(self, event_loop, fast_forward):
        f = mock.Mock(spec=callable)
        # Test with 2 calls per 2 seconds
        rl = util.RateLimited(f, period=2.0, count=2, loop=event_loop)
        rl.start()

        # First 2 calls should complete immediately
        await asyncio.wait([rl(1)], timeout=0)
        await fast_forward(1)
        await asyncio.wait([rl(2)], timeout=0)
        assert f.mock_calls == [mock.call(1), mock.call(2)]

        # 3rd and 4th calls should be blocked until enough time has passed
        f3 = rl(3)
        f4 = rl(4)
        # Once 1 second passes, 1st call is outside the period, allowing 3rd call to be processed
        # (but not 4th)
        await fast_forward(1)
        await asyncio.wait([f3, f4], timeout=0)
        assert f3.done()
        assert not f4.done()
        assert f.mock_calls == [mock.call(1), mock.call(2), mock.call(3)]
        # After 1 more second passes, 2nd call is outside the period, allowing 4th call to be processed
        await fast_forward(1)
        await asyncio.wait([f4], timeout=0)
        assert f4.done()
        assert f.mock_calls == [mock.call(1), mock.call(2), mock.call(3), mock.call(4)]

        rl.stop()

    @pytest.mark.asyncio
    async def test_restart_with_clear(self, event_loop, fast_forward):
        f = mock.Mock(spec=callable)
        # Test with 2 calls per 2 seconds
        rl = util.RateLimited(f, period=2.0, count=2, loop=event_loop)
        rl.start()

        # Fire 3 calls, 2 should get processed, 3rd should be blocked
        f1 = rl(1)
        f2 = rl(2)
        f3 = rl(3)
        await asyncio.wait([f1, f2, f3], timeout=0)
        assert f.mock_calls == [mock.call(1), mock.call(2)]
        assert not f3.done()

        # Stop the runner, 3rd call should be cancelled, and no more calls should execute
        rl.stop()
        f.reset_mock()
        assert f3.cancelled()
        await fast_forward(2)
        assert f.mock_calls == []

        # Restart the runner, still no more calls should execute
        rl.start()
        await fast_forward(2)
        assert f.mock_calls == []

        # Should process another 2 calls immediately, because no calls have happened recently
        await asyncio.wait([rl(4), rl(5)], timeout=0)
        assert f.mock_calls == [mock.call(4), mock.call(5)]

        # If runner gets restarted, should process 2 more calls immediately, because internal data has been cleared
        rl.stop()
        rl.start()
        await asyncio.wait([rl(6), rl(7)])
        assert f.mock_calls == [mock.call(4), mock.call(5), mock.call(6), mock.call(7)]

        rl.stop()

    @pytest.mark.asyncio
    async def test_restart_without_clear(self, event_loop, fast_forward):
        f = mock.Mock(spec=callable)
        # Test with 2 calls per 2 seconds
        rl = util.RateLimited(f, period=2.0, count=2, loop=event_loop)
        rl.start()

        # 2 calls should get processed immediately, 2 should be blocked
        f1, f2, f3, f4 = rl(1), rl(2), rl(3), rl(4)
        await asyncio.wait([f1, f2, f3, f4], timeout=0)
        assert f.mock_calls == [mock.call(1), mock.call(2)]

        # Stop the runner, last 2 calls should not happen if time is advanced, but are not cancelled
        rl.stop(False)
        assert not f3.cancelled()
        assert not f4.cancelled()
        await fast_forward(4)
        assert not f3.done()
        assert not f4.done()
        assert f.mock_calls == [mock.call(1), mock.call(2)]

        # Start the runner again, enough time has passed that the next 2 calls can execute immediately
        rl.start()
        await asyncio.wait([f3, f4], timeout=0)
        assert f3.done()
        assert f4.done()
        assert f.mock_calls == [mock.call(1), mock.call(2), mock.call(3), mock.call(4)]

        # Add new calls, restart the runner without advancing time, those calls will still be blocked
        f5, f6 = rl(5), rl(6)
        rl.stop(False)
        rl.start()
        await asyncio.wait([f5, f6], timeout=0)
        assert not f5.done()
        assert not f6.done()
        # But advance time, and they should be executed
        await fast_forward(2)
        await asyncio.wait([f5, f6], timeout=0)
        assert f5.done()
        assert f6.done()

        rl.stop()

    @pytest.mark.asyncio
    async def test_call_before_start(self, event_loop, fast_forward):
        f = mock.Mock(spec=callable)
        # Test with 2 calls per 2 seconds
        rl = util.RateLimited(f, period=2.0, count=2, loop=event_loop)

        # Call before .start(), doesn't get executed
        f1 = rl(1)
        await fast_forward(2)
        await asyncio.wait([f1], timeout=0)
        assert not f1.done()

        # Start the runner, call gets executed immediately
        rl.start()
        await asyncio.wait([f1], timeout=0)
        assert f1.done()

        rl.stop()

    @pytest.mark.asyncio
    async def test_exception(self, event_loop, fast_forward):
        f = mock.Mock(spec=callable, side_effect=Exception("fail"))
        # Test with 2 calls per 2 seconds
        rl = util.RateLimited(f, period=2.0, count=2, loop=event_loop)
        rl.start()

        f1 = rl(1)
        await asyncio.wait([f1], timeout=0)
        assert f1.done()
        assert f1.exception() is not None

        rl.stop()

    @pytest.mark.asyncio
    async def test_start_stop(self, event_loop):
        f = mock.Mock(spec=callable)
        # Test with 2 calls per 2 seconds
        rl = util.RateLimited(f, period=2.0, count=2, loop=event_loop)

        # Stop when already stopped is fine
        rl.stop()

        # Start when already started raises an exception
        rl.start()
        with pytest.raises(AssertionError):
            rl.start()

        rl.stop()

    @pytest.mark.asyncio
    async def test_stop_returns_cancelled_calls(self, event_loop):
        f = mock.Mock(spec=callable)
        # Test with 2 calls per 2 seconds
        rl = util.RateLimited(f, period=2.0, count=2, loop=event_loop)

        rl.start()
        await asyncio.wait([rl(1), rl(2), rl(3), rl(4)], timeout=0)
        assert f.mock_calls == [mock.call(1), mock.call(2)]
        cancelled = rl.stop()
        assert cancelled == [((3,), {}), ((4,), {})]
