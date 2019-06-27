import asyncio
import typing
from unittest import mock

import attr
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


class TestTypeValidator:
    def test_bare_type(self):
        @attr.s
        class A:
            x: str = attr.ib(validator=util.type_validator)

        A("foo")
        with pytest.raises(TypeError):
            A(12)
        with pytest.raises(TypeError):
            A(None)

    def test_optional(self):
        @attr.s
        class B:
            x: typing.Optional[str] = attr.ib(validator=util.type_validator)

        B("foo")
        B(None)
        with pytest.raises(TypeError):
            B(12)

    def test_union(self):
        @attr.s
        class C:
            x: typing.Union[int, float] = attr.ib(validator=util.type_validator)

        C(12)
        C(12.34)
        with pytest.raises(TypeError):
            C(None)
        with pytest.raises(TypeError):
            C("12")

    def test_no_type(self):
        @attr.s
        class D:
            x = attr.ib(validator=util.type_validator)

        with pytest.raises(TypeError):
            D(None)
        with pytest.raises(TypeError):
            D("foo")
        with pytest.raises(TypeError):
            D(12)

    def test_nested_union(self):
        @attr.s
        class E:
            x: typing.Union[typing.Union[typing.Optional[int], str], bool] = attr.ib(validator=util.type_validator)

        E(None)
        E("foo")
        E(12)
        E(False)
        with pytest.raises(TypeError):
            E(12.34)
