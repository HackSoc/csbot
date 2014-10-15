import unittest
from unittest import mock
import asyncio
import os
from io import StringIO
from textwrap import dedent

from csbot.core import Bot, BotClient


def mock_client(cls, *args, **kwargs):
    """Create an instance of a mocked subclass of *cls*.

    *cls* should be :class:`IRCClient` or a subclass of it.  The event loop and
    transport are mocked, and a :meth:`reset_mock` method is added for resetting
    all mocks on the client.
    """
    class MockIRCClient(cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.send_raw = mock.Mock(wraps=self.send_raw)

            # Mock an asyncio event loop where delayed calls are immediate
            self.loop = mock.Mock()
            self.loop.get_debug.return_value = True
            def call_soon(func, *args):
                func(*args)
                return asyncio.Handle(func, args, self.loop)
            self.loop.call_soon = call_soon
            def call_later(delay, func, *args):
                return call_soon(func, *args)
            self.loop.call_later = call_later
            self.loop.time.return_value = 100.0

        def connect(self):
            # Connect to a mock transport
            self.connection_made(mock.Mock())

        def reset_mock(self):
            self.send_raw.reset_mock()
            self.loop.reset_mock()
            if self.transport is not None:
                self.transport.reset_mock()

    return MockIRCClient(*args, **kwargs)


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


class BotTestCase(unittest.TestCase):
    """Common functionality for bot test case.

    A :class:`unittest.TestCase` with bot and plugin test fixtures.  Creates a
    bot from :attr:`CONFIG`, binding it to ``self.bot``, and also binding every
    plugin in :attr:`PLUGINS` to ``self.plugin``.
    """
    CONFIG = ""
    PLUGINS = []

    def setUp(self):
        """Create bot and plugin bindings."""
        # Bot and protocol stuff, suffixed with _ so they can't clash with
        # possible/likely plugin names
        self.bot_ = Bot(StringIO(dedent(self.CONFIG)))
        self.bot_.bot_setup()
        self.protocol_ = mock_client(BotClient, self.bot_)
        self.protocol_.connect()
        self.protocol_.reset_mock()
        self.transport_ = self.protocol_.transport

        for p in self.PLUGINS:
            setattr(self, p, self.bot_.plugins[p])

    def tearDown(self):
        """Lose references to bot and plugins."""
        self.bot_ = None
        self.transport_ = None
        self.protocol_ = None
        for p in self.PLUGINS:
            setattr(self, p, None)


def fixture_file(*path):
    """Get the path to a fixture file."""
    return os.path.join(os.path.dirname(__file__), 'fixtures', *path)


def read_fixture_file(*path, mode='rb'):
    """Read the contents of a fixture file."""
    with open(fixture_file(*path), mode) as f:
        return f.read()
