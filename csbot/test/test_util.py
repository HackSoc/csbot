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
