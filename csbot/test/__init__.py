import asyncio
import os
from io import StringIO
from textwrap import dedent
import gc
import functools
from unittest import mock

import pytest
import responses

from csbot.core import Bot


class MockStreamReader(asyncio.StreamReader):
    pass


class MockStreamWriter(asyncio.StreamWriter):
    def close(self):
        self._reader.feed_eof()


class IRCClientTestCase:
    #: The IRCClient (sub)class to instrument
    CLIENT_CLASS = None

    loop = None
    client = None

    @pytest.fixture
    def irc_client_class(self):
        assert self.CLIENT_CLASS is not None, "no CLIENT_CLASS set on test case"
        return self.CLIENT_CLASS

    @pytest.fixture
    def pre_irc_client(self):
        """Hook for running a fixture before client is created."""
        pass

    @pytest.fixture(autouse=True)
    def irc_client(self, event_loop, irc_client_class, pre_irc_client):
        self.loop = event_loop
        # Create client and make it use our event loop
        self.client = irc_client_class(loop=self.loop)
        # Connect fake stream reader/writer (for tests that don't need the read loop)
        with self.mock_open_connection():
            self.loop.run_until_complete(self.client.connect())

        # Mock all the things!
        self.client.send_line = mock.Mock(wraps=self.client.send_line)

        return self.client

    @pytest.fixture
    async def run_client(self, event_loop, irc_client):
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
        with self.mock_open_connection():
            # Start the client
            run_fut = event_loop.create_task(irc_client.run())
            await irc_client.connected.wait()
            # Allow the test to run
            yield
            # Cleanly end the read loop and wait for client to exit
            irc_client.disconnect()
            await run_fut

    def mock_open_connection(self):
        """Give a mock reader and writer when a stream connection is opened.

        >>> with self.mock_open_connection():
        ...     self.loop.run_until_complete(self.client.connect())
        ...     self.client.quit('blah')
        ...     self.assert_bytes_sent(b'QUIT :blah\r\n')
        """
        def create_connection(*args, **kwargs):
            reader = MockStreamReader(loop=self.loop)
            writer = MockStreamWriter(None, None, reader, self.loop)
            writer.write = mock.Mock()
            fut = asyncio.Future(loop=self.loop)
            fut.set_result((reader, writer))
            return fut
        return mock.patch('asyncio.open_connection', side_effect=create_connection)

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

    def receive_bytes(self, bytes):
        """Shortcut for pushing received data to the client."""
        self.client.reader.feed_data(bytes)

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


class TempEnvVars(object):
    """A context manager for temporarily changing the values of environment
    variables."""
    def __init__(self, changes):
        self.changes = changes
        self.restore = {}

    def __enter__(self):
        for k, v in self.changes.items():
            if k in os.environ:
                self.restore[k] = os.environ[k]
            os.environ[k] = v
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        for k, v in self.changes.items():
            if k in self.restore:
                os.environ[k] = self.restore[k]
            else:
                del os.environ[k]


class BotTestCase(IRCClientTestCase):
    """Common functionality for bot test case.

    A :class:`unittest.TestCase` with bot and plugin test fixtures.  Creates a
    bot from :attr:`CONFIG`, binding it to ``self.bot``, and also binding every
    plugin in :attr:`PLUGINS` to ``self.plugin``.
    """
    BOT_CLASS = Bot
    CONFIG = ""
    PLUGINS = []
    bot_ = None

    @pytest.fixture
    def irc_client_class(self):
        return functools.partial(self.BOT_CLASS, StringIO(dedent(self.CONFIG)))

    @pytest.fixture(autouse=True)
    def bot_setup(self, irc_client):
        """Create/destroy bot and plugin bindings."""
        irc_client.bot_setup()
        # Keep old tests happy with an alias...
        self.bot_ = irc_client
        for p in self.PLUGINS:
            setattr(self, p, self.bot_.plugins[p])

        yield

        self.bot_ = None
        for p in self.PLUGINS:
            setattr(self, p, None)

    @pytest.fixture
    def responses(self):
        with responses.RequestsMock() as rsps:
            yield rsps


def fixture_file(*path):
    """Get the path to a fixture file."""
    return os.path.join(os.path.dirname(__file__), 'fixtures', *path)


def read_fixture_file(*path, mode='rb'):
    """Read the contents of a fixture file."""
    with open(fixture_file(*path), mode) as f:
        return f.read()
