import os
from StringIO import StringIO
from textwrap import dedent

from twisted.trial import unittest
from twisted.test import proto_helpers

from csbot.core import Bot, BotProtocol


class TempEnvVars(object):
    """A context manager for temporarily changing the values of enviroment
    variables."""
    def __init__(self, changes):
        self.changes = changes
        self.restore = {}

    def __enter__(self):
        for k, v in self.changes.iteritems():
            if k in os.environ:
                self.restore[k] = os.environ[k]
            os.environ[k] = v
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        for k, v in self.changes.iteritems():
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
        self.transport_ = proto_helpers.StringTransport()
        self.protocol_ = BotProtocol(self.bot_)
        self.protocol_.transport = self.transport_

        for p in self.PLUGINS:
            setattr(self, p, self.bot_.plugins[p])

    def tearDown(self):
        """Lose references to bot and plugins."""
        self.bot_ = None
        self.transport_ = None
        self.protocol_ = None
        for p in self.PLUGINS:
            setattr(self, p, None)
