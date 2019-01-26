import asyncio
import os
from io import StringIO
from textwrap import dedent
import functools
from unittest import mock

import pytest

from csbot.core import Bot


class MockStreamReader(asyncio.StreamReader):
    pass


class MockStreamWriter(asyncio.StreamWriter):
    def close(self):
        self._reader.feed_eof()


def mock_open_connection(loop):
    """Give a mock reader and writer when a stream connection is opened.

    >>> with mock_open_connection(loop):
    ...     await self.client.connect()
    ...     irc_client.quit('blah')
    ...     irc_client_helper.assert_bytes_sent(client, b'QUIT :blah\r\n')
    """
    def create_connection(*args, **kwargs):
        reader = MockStreamReader(loop=loop)
        writer = MockStreamWriter(None, None, reader, loop)
        writer.write = mock.Mock()
        fut = asyncio.Future(loop=loop)
        fut.set_result((reader, writer))
        return fut
    return mock.patch('asyncio.open_connection', side_effect=create_connection)


class IRCClientTestCase:
    client = None
    client_helper = None

    @pytest.fixture(autouse=True)
    def bind_client(self, irc_client, irc_client_helper):
        self.client = irc_client
        self.client_helper = irc_client_helper

    def reset_mock(self):
        return self.client_helper.reset_mock()

    def patch(self, *args, **kwargs):
        return self.client_helper.patch(*args, **kwargs)

    def receive_bytes(self, *args, **kwargs):
        return self.client_helper.receive_bytes(*args, **kwargs)

    def assert_bytes_sent(self, *args, **kwargs):
        return self.client_helper.assert_bytes_sent(*args, **kwargs)

    def receive(self, *args, **kwargs):
        return self.client_helper.receive(*args, **kwargs)

    def assert_sent(self, *args, **kwargs):
        return self.client_helper.assert_sent(*args, **kwargs)


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


def fixture_file(*path):
    """Get the path to a fixture file."""
    return os.path.join(os.path.dirname(__file__), 'fixtures', *path)


def read_fixture_file(*path, mode='rb'):
    """Read the contents of a fixture file."""
    with open(fixture_file(*path), mode) as f:
        return f.read()
