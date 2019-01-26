import asyncio
from unittest import mock

import pytest
import responses as responses_

from csbot import test
from csbot.irc import IRCClient


@pytest.fixture
def irc_client_class():
    return IRCClient


@pytest.fixture
def pre_irc_client():
    """Hook for running a fixture before client is created."""
    pass


@pytest.fixture
async def irc_client(event_loop, irc_client_class, pre_irc_client):
    # Create client and make it use our event loop
    client = irc_client_class(loop=event_loop)
    # Connect fake stream reader/writer (for tests that don't need the read loop)
    with test.mock_open_connection(event_loop):
        await client.connect()

    # Mock all the things!
    client.send_line = mock.Mock(wraps=client.send_line)

    return client


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
        for l in lines:
            self.client.line_received(l)

    def assert_sent(self, lines):
        """Check that a list of (unicode) strings have been sent.

        Resets the mock so the next call will not contain what was checked by
        this call.
        """
        if isinstance(lines, str):
            lines = [lines]
        self.client.send_line.assert_has_calls([mock.call(l) for l in lines])
        self.client.send_line.reset_mock()


@pytest.fixture
def irc_client_helper(irc_client):
    return IRCClientHelper(irc_client)


@pytest.fixture
def run_client(event_loop, irc_client_helper):
    """Fixture for tests that require actually running the client.

    A test decorated with this function should be a coroutine, i.e. at some
    point it should ``yield`` in some way to allow the client to progress.

    >>> class TestFoo(IRCClientTestCase):
    ...     @pytest.mark.parametrize("run_client")
    ...     @pytest.mark.asyncio
    ...     def test_something(self):
    ...         self.receive_bytes(b":nick!user@host PRIVMSG #channel :hello\r\n")
    ...         yield
    ...         self.assert_sent('PRIVMSG #channel :what do you mean, hello?')
    """
    # Deliberately written in "synchronous" style with run_until_complete()
    # instead of await because async generators don't work in Python 3.5.
    with test.mock_open_connection(event_loop):
        # Start the client
        run_fut = event_loop.create_task(irc_client_helper.client.run())
        event_loop.run_until_complete(irc_client_helper.client.connected.wait())
        # Allow the test to run
        yield irc_client_helper
        # Cleanly end the read loop and wait for client to exit
        irc_client_helper.client.disconnect()
        event_loop.run_until_complete(run_fut)


@pytest.fixture
def bot_helper(irc_client):
    irc_client.bot_setup()
    return BotHelper(irc_client)


class BotHelper(IRCClientHelper):
    def __init__(self, bot):
        super().__init__(bot)

    def __getitem__(self, item):
        """Get plugin by name."""
        return self.client.plugins[item]


@pytest.fixture
def responses():
    with responses_.RequestsMock() as rsps:
        yield rsps
