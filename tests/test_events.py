import unittest

from twisted.words.protocols import irc
from nose.tools import eq_

import csbot.events as events


class MockBot(object):
    """A mock Bot for event proxy testing which just stores all events.
    """
    def __init__(self):
        self.events = []

    def post_event(self, event):
        self.events.append(event)


class MockBotProtocol(object):
    """A mock BotProtocol for event proxy testing.
    """
    def __init__(self):
        self.bot = MockBot()


class TestEventProxy(unittest.TestCase):
    def test_automatic_proxy(self):
        class Protocol(MockBotProtocol):
            @events.proxy
            def some_event(self, foo, bar):
                pass

            @events.proxy
            def another_event(self, x):
                pass

        protocol = Protocol()
        protocol.some_event('hello', 'world')
        protocol.another_event('foo')

        eq_(len(protocol.bot.events), 2)

        e1 = protocol.bot.events[0]
        eq_(e1.event_type, 'some_event')
        eq_(e1.foo, 'hello')
        eq_(e1.bar, 'world')

        e2 = protocol.bot.events[1]
        eq_(e2.event_type, 'another_event')
        eq_(e2.x, 'foo')

    def test_explicit_proxy(self):
        class Protocol(MockBotProtocol):
            @events.proxy('a', 'b')
            def event1(self, alpha, bravo):
                pass

            @events.proxy(name='renamed2')
            def event2(self, alpha, bravo):
                pass

            @events.proxy('a', 'b', name='renamed3')
            def event3(self, alpha, bravo):
                pass

        protocol = Protocol()
        protocol.event1('foo', 'bar')
        protocol.event2('foo', 'bar')
        protocol.event3('foo', 'bar')

        eq_(len(protocol.bot.events), 3)

        e1 = protocol.bot.events[0]
        eq_(e1.event_type, 'event1')
        eq_(e1.a, 'foo')
        eq_(e1.b, 'bar')

        e2 = protocol.bot.events[1]
        eq_(e2.event_type, 'renamed2')
        eq_(e2.alpha, 'foo')
        eq_(e2.bravo, 'bar')

        e3 = protocol.bot.events[2]
        eq_(e3.event_type, 'renamed3')
        eq_(e3.a, 'foo')
        eq_(e3.b, 'bar')

    def test_modifying_proxy(self):
        class Protocol(MockBotProtocol):
            @events.proxy
            def event1(self, foo, bar):
                """Switch order of event arguments.
                """
                return (bar, foo)

            @events.proxy('x')
            def event2(self, foo, bar):
                """Sum 2 event arguments into a single argument.
                """
                return (foo + bar,)

        protocol = Protocol()
        protocol.event1('foo', 'bar')
        protocol.event2(12, 8)

        eq_(len(protocol.bot.events), 2)

        e1 = protocol.bot.events[0]
        eq_(e1.event_type, 'event1')
        eq_(e1.foo, 'bar')
        eq_(e1.bar, 'foo')

        e2 = protocol.bot.events[1]
        eq_(e2.event_type, 'event2')
        eq_(e2.x, 20)
