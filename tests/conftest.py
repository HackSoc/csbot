from __future__ import annotations
import asyncio
from textwrap import dedent
from unittest import mock

import pytest
import aiofastforward
from aioresponses import aioresponses as aioresponses_
import toml

from csbot.irc import IRCClient
from csbot.core import Bot
from csbot import config
from . import mock_open_connection


@pytest.fixture
def event_loop(request, event_loop):
    marker = request.node.get_closest_marker('asyncio')
    if marker is not None and not marker.kwargs.get('allow_unhandled_exception', False):
        def handle_exception(loop, ctx):
            pytest.fail(ctx['message'])
        event_loop.set_exception_handler(handle_exception)
    return event_loop


@pytest.fixture
def fast_forward(event_loop):
    with aiofastforward.FastForward(event_loop) as forward:
        async def f(n):
            # The wait_for() prevents forward(n) from blocking if there isn't enough async work to do
            try:
                await asyncio.wait_for(forward(n), n)
            except asyncio.TimeoutError:
                pass
        yield f


@pytest.fixture
def config_example_mode():
    with config.example_mode():
        yield


@pytest.fixture
def irc_client_class():
    return IRCClient


@pytest.fixture
def pre_irc_client():
    """Hook for running a fixture before client is created."""
    pass


@pytest.fixture
def irc_client_config():
    return {}


@pytest.fixture
async def irc_client(request, event_loop, config_example_mode, irc_client_class, pre_irc_client, irc_client_config):
    # Create client and make it use our event loop
    bot_marker = request.node.get_closest_marker('bot')
    if bot_marker is not None:
        cls = bot_marker.kwargs.get('cls', Bot)
        config_ = bot_marker.kwargs['config']
        if isinstance(config_, str):
            config_ = toml.loads(dedent(config_))
        plugins = bot_marker.kwargs.get('plugins', None)
        client = cls(config=config_, plugins=plugins, loop=event_loop)
    else:
        client = irc_client_class(loop=event_loop, **irc_client_config)
    # Connect fake stream reader/writer (for tests that don't need the read loop)
    with mock_open_connection():
        await client.connect()

    # Mock all the things!
    client.send_line = mock.Mock(wraps=client.send_line)

    return client


class LineMatcher:
    def __init__(self, f, description):
        self.f = f
        self.description = description

    def __call__(self, line):
        return self.f(line)

    def __repr__(self):
        return self.description

    @classmethod
    def equals(cls, other):
        return cls(lambda line: line == other, f"`line == {other!r}`")

    @classmethod
    def contains(cls, other):
        return cls(lambda line: other in line, f"`{other!r} in line`")

    @classmethod
    def endswith(cls, other):
        return cls(lambda line: line.endswith(other), f"`line.endswith({other!r})`")


class IRCClientHelper:
    def __init__(self, irc_client):
        self.client = irc_client

    def reset_mock(self):
        self.client.send_line.reset_mock()
        self.client.writer.write.reset_mock()

    def patch(self, attrs, create=False):
        """Shortcut for patching attribute(s) of the client.

        If the attribute exists it is wrapped by the mock so that calls aren't
        blocked.
        """
        if isinstance(attrs, str):
            return mock.patch.object(self.client, attrs, create=create,
                                     wraps=getattr(self.client, attrs, None))
        else:
            return [mock.patch.object(self.client, attr, create=create,
                                      wraps=getattr(self.client, attr, None))
                    for attr in attrs]

    async def receive_bytes(self, bytes):
        """Shortcut for pushing received data to the client."""
        self.client.reader.feed_data(bytes)
        await asyncio.sleep(0)

    def assert_bytes_sent(self, bytes):
        """Check the raw bytes that have been sent via the transport.

        Compares *bytes* to the collection of everything sent to
        ``transport.write(...)``.  Resets the mock so the next call will not
        contain what was checked by this call.
        """
        sent = b''.join(args[0] for args, _ in self.client.writer.write.call_args_list)
        assert sent == bytes
        self.client.writer.write.reset_mock()

    def receive(self, lines):
        """Shortcut to push a series of lines to the client."""
        if isinstance(lines, str):
            lines = [lines]
        return [self.client.line_received(line) for line in lines]

    def assert_sent(self, matchers, *, any_order=False, reset_mock=True):
        """Check that a list of (unicode) strings have been sent.

        Resets the mock so the next call will not contain what was checked by
        this call.
        """
        sent_lines = [args[0] for name, args, kwargs in self.client.send_line.mock_calls]

        if callable(matchers) or isinstance(matchers, str):
            matchers = [matchers]
        matchers = [LineMatcher.equals(matcher) if not callable(matcher) else matcher
                    for matcher in matchers]

        if not matchers:
            pass
        elif any_order:
            for matcher in matchers:
                assert any(matcher(line) for line in sent_lines), f"sent line not found: {matcher}"
        else:
            # Find the start of the matching run of sent messages
            start = 0
            while start < len(sent_lines) and not matchers[0](sent_lines[start]):
                start += 1
            for i, matcher in enumerate(matchers):
                assert start + i < len(sent_lines), f"no line matching {matcher} in {sent_lines}"
                assert matcher(sent_lines[start + i]), f"expected {sent_lines[start + i]!r} to match {matcher}"

        if reset_mock:
            self.client.send_line.reset_mock()

    match_line = LineMatcher


@pytest.fixture
def irc_client_helper(irc_client):
    return IRCClientHelper(irc_client)


@pytest.fixture
async def run_client(event_loop, irc_client_helper):
    """Fixture for tests that require actually running the client.

    A test decorated with this function should be a coroutine, i.e. at some
    point it should yield control to allow the client to progress.

    >>> @pytest.mark.usefixtures("run_client")
    ... async def test_something(irc_client_helper):
    ...     await irc_client_helper.receive_bytes(b":nick!user@host PRIVMSG #channel :hello\r\n")
    ...     irc_client_helper.assert_sent('PRIVMSG #channel :what do you mean, hello?')
    """
    with mock_open_connection():
        # Start the client
        run_fut = event_loop.create_task(irc_client_helper.client.run())
        await irc_client_helper.client.connected.wait()
        # Allow the test to run
        yield irc_client_helper
        # Cleanly end the read loop and wait for client to exit
        irc_client_helper.client.disconnect()
        await run_fut


@pytest.fixture
def bot_helper_class():
    return BotHelper


@pytest.fixture
def bot_helper(irc_client, bot_helper_class) -> BotHelper:
    irc_client.bot_setup()
    return bot_helper_class(irc_client)


class BotHelper(IRCClientHelper):
    def __init__(self, bot):
        super().__init__(bot)

    def __getitem__(self, item):
        """Get plugin by name."""
        return self.client.plugins[item]

    @property
    def bot(self):
        return self.client


@pytest.fixture
def aioresponses():
    with aioresponses_() as m:
        yield m
