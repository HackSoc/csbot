import unittest
from unittest import mock
import datetime
from collections import defaultdict
from functools import partial
import asyncio

import pytest

import csbot.events


@pytest.mark.asyncio
class TestHybridEventRunner:
    class EventHandler:
        def __init__(self):
            self.handlers = defaultdict(list)

        def add(self, e, f=None):
            if f is None:
                return partial(self.add, e)
            else:
                self.handlers[e].append(f)

        def __call__(self, e):
            return self.handlers[e]

    @pytest.fixture
    def event_runner(self, event_loop):
        handler = self.EventHandler()
        obj = mock.Mock()
        obj.add_handler = handler.add
        obj.get_handlers = mock.Mock(wraps=handler)
        obj.runner = csbot.events.HybridEventRunner(obj.get_handlers, event_loop)
        obj.exception_handler = mock.Mock(wraps=event_loop.get_exception_handler())
        event_loop.set_exception_handler(obj.exception_handler)
        return obj

    async def test_values(self, event_runner):
        """Check that basic values are passed through the event queue unmolested."""
        # Test that things actually get through
        await event_runner.runner.post_event('foo')
        assert event_runner.get_handlers.call_args_list == [mock.call('foo')]
        # The event runner doesn't care what it's passing through
        for x in ['bar', 1.3, None, object]:
            await event_runner.runner.post_event(x)
            print(event_runner.get_handlers.call_args)
            assert event_runner.get_handlers.call_args == mock.call(x)

    async def test_event_chain_synchronous(self, event_runner):
        """Check that an entire event chain runs (synchronously).

        All handlers for an event should be run before the next event, and any events that occur
        during an event handler should also be processed before the initial `post_event()` future
        has a result.
        """
        complete = []

        @event_runner.add_handler('a')
        def a(_):
            event_runner.runner.post_event('b')
            complete.append('a')

        @event_runner.add_handler('b')
        def b1(_):
            event_runner.runner.post_event('c')
            complete.append('b1')

        @event_runner.add_handler('b')
        def b2(_):
            event_runner.runner.post_event('d')
            complete.append('b2')

        @event_runner.add_handler('b')
        def b3(_):
            event_runner.runner.post_event('e')
            complete.append('b3')

        @event_runner.add_handler('c')
        def c(_):
            event_runner.runner.post_event('f')
            complete.append('c')

        @event_runner.add_handler('d')
        def d(_):
            complete.append('d')

        @event_runner.add_handler('e')
        def e(_):
            complete.append('e')

        await event_runner.runner.post_event('a')
        assert event_runner.get_handlers.mock_calls == [
            # Initial event
            mock.call('a'),
            # Event resulting from handler for 'a'
            mock.call('b'),
            # Ensure all handlers for 'b' finished ...
            mock.call('c'),
            mock.call('d'),
            mock.call('e'),
            # ... before first handler for 'c'
            mock.call('f'),
        ]
        assert complete == ['a', 'b1', 'b2', 'b3', 'c', 'd', 'e']

    async def test_event_chain_asynchronous(self, event_loop, event_runner):
        """Check that an entire event chain runs (asynchronously).

        Any events that occur during an event handler should be processed before the initial
        `post_event()` future has a result.
        """
        events = [asyncio.Event(loop=event_loop) for _ in range(2)]
        complete = []

        @event_runner.add_handler('a')
        async def a1(_):
            complete.append('a1')

        @event_runner.add_handler('a')
        async def a2(_):
            await events[0].wait()
            event_runner.runner.post_event('b')
            complete.append('a2')

        @event_runner.add_handler('b')
        async def b1(_):
            event_runner.runner.post_event('c')
            complete.append('b1')

        @event_runner.add_handler('b')
        async def b2(_):
            event_runner.runner.post_event('d')
            complete.append('b2')

        @event_runner.add_handler('b')
        async def b3(_):
            await events[1].wait()
            event_runner.runner.post_event('e')
            complete.append('b3')

        @event_runner.add_handler('c')
        async def c(_):
            event_runner.runner.post_event('f')
            complete.append('c')

        @event_runner.add_handler('d')
        async def d(_):
            complete.append('d')

        @event_runner.add_handler('e')
        async def e(_):
            complete.append('e')

        # Post the first event and allow some tasks to run:
        # - should have a post_event('a') call
        # - a1 should complete, a2 is blocked on events[0]
        future = event_runner.runner.post_event('a')
        await asyncio.wait({future}, loop=event_loop, timeout=0.1)
        assert not future.done()
        assert event_runner.get_handlers.mock_calls == [
            mock.call('a'),
        ]
        assert complete == ['a1']

        # Unblock a2 and allow some tasks to run:
        # - a2 should complete
        # - post_event('b') should be called (by a2)
        # - b1 and b2 should complete, b3 is blocked on events[1]
        # - post_event('c') and post_event('d') should be called (by b1 and b2)
        # - c should complete
        # - post_event('f') should be called (by c)
        # - d should complete
        events[0].set()
        await asyncio.wait({future}, loop=event_loop, timeout=0.1)
        assert not future.done()
        assert event_runner.get_handlers.mock_calls == [
            mock.call('a'),
            mock.call('b'),
            mock.call('c'),
            mock.call('d'),
            mock.call('f'),
        ]
        assert complete == ['a1', 'a2', 'b1', 'b2', 'c', 'd']

        # Unblock b3 and allow some tasks to run:
        # - b3 should complete
        # - post_event('e') should be called (by b3)
        # - e should complete
        # - future should complete, because no events or tasks remain pending
        events[1].set()
        await asyncio.wait({future}, loop=event_loop, timeout=0.1)
        assert future.done()
        assert event_runner.get_handlers.mock_calls == [
            mock.call('a'),
            mock.call('b'),
            mock.call('c'),
            mock.call('d'),
            mock.call('f'),
            mock.call('e'),
        ]
        assert complete == ['a1', 'a2', 'b1', 'b2', 'c', 'd', 'b3', 'e']

    async def test_event_chain_hybrid(self, event_loop, event_runner):
        """Check that an entire event chain runs (mix of sync and async handlers).

        Synchronous handlers complete before asynchronous handlers. Synchronous handlers for an
        event all run before synchronous handlers for the next event, but asynchronous handers can
        run out-of-order.
        """
        events = [asyncio.Event(loop=event_loop) for _ in range(2)]
        complete = []

        @event_runner.add_handler('a')
        def a1(_):
            complete.append('a1')

        @event_runner.add_handler('a')
        async def a2(_):
            await events[0].wait()
            event_runner.runner.post_event('b')
            complete.append('a2')

        @event_runner.add_handler('b')
        async def b1(_):
            await events[1].wait()
            event_runner.runner.post_event('c')
            complete.append('b1')

        @event_runner.add_handler('b')
        def b2(_):
            event_runner.runner.post_event('d')
            complete.append('b2')

        @event_runner.add_handler('c')
        def c1(_):
            complete.append('c1')

        @event_runner.add_handler('c')
        async def c2(_):
            complete.append('c2')

        @event_runner.add_handler('d')
        async def d1(_):
            complete.append('d1')

        @event_runner.add_handler('d')
        def d2(_):
            complete.append('d2')

        # Post the first event and allow some tasks to run:
        # - post_event('a') should be called (initial)
        # - a1 should complete, a2 is blocked on events[0]
        future = event_runner.runner.post_event('a')
        await asyncio.wait({future}, loop=event_loop, timeout=0.1)
        assert not future.done()
        assert event_runner.get_handlers.mock_calls == [
            mock.call('a'),
        ]
        assert complete == ['a1']

        # Unblock a2 and allow some tasks to run:
        # - a2 should complete
        # - post_event('b') should be called (by a2)
        # - b2 should complete, b1 is blocked on events[1]
        # - post_event('d') should be called
        # - d2 should complete (synchronous phase)
        # - d1 should complete (asynchronous phase)
        events[0].set()
        await asyncio.wait({future}, loop=event_loop, timeout=0.1)
        assert not future.done()
        assert event_runner.get_handlers.mock_calls == [
            mock.call('a'),
            mock.call('b'),
            mock.call('d'),
        ]
        assert complete == ['a1', 'a2', 'b2', 'd2', 'd1']

        # Unblock b1 and allow some tasks to run:
        # - b1 should complete
        # - post_event('c') should be called (by b1)
        # - c1 should complete (synchronous phase)
        # - c2 should complete (asynchronous phase)
        # - future should complete, because no events or tasks remain pending
        events[1].set()
        await asyncio.wait({future}, loop=event_loop, timeout=0.1)
        assert future.done()
        assert event_runner.get_handlers.mock_calls == [
            mock.call('a'),
            mock.call('b'),
            mock.call('d'),
            mock.call('c'),
        ]
        assert complete == ['a1', 'a2', 'b2', 'd2', 'd1', 'b1', 'c1', 'c2']

    async def test_overlapping_root_events(self, event_loop, event_runner):
        """Check that overlapping events get the same future."""
        events = [asyncio.Event(loop=event_loop) for _ in range(1)]
        complete = []

        @event_runner.add_handler('a')
        async def a(_):
            await events[0].wait()
            complete.append('a')

        @event_runner.add_handler('b')
        async def b(_):
            complete.append('b')

        # Post the first event and allow tasks to run:
        # - a is blocked on events[0]
        f1 = event_runner.runner.post_event('a')
        await asyncio.wait({f1}, loop=event_loop, timeout=0.1)
        assert not f1.done()
        assert complete == []

        # Post the second event and allow tasks to run:
        # - b completes
        # - a is still blocked on events[0]
        # - f1 and f2 are not done, because they're for the same run loop, and a is still blocked
        f2 = event_runner.runner.post_event('b')
        await asyncio.wait({f2}, loop=event_loop, timeout=0.1)
        assert not f2.done()
        assert not f1.done()
        assert complete == ['b']

        # Unblock a and allow tasks to run:
        # - a completes
        # - f1 and f2 are both done, because the run loop has finished
        events[0].set()
        await asyncio.wait([f1, f2], loop=event_loop, timeout=0.1)
        assert f1.done()
        assert f2.done()
        assert complete == ['b', 'a']

        # (Maybe remove this - not essential that they're the same future, only that they complete together)
        assert f2 is f1

    async def test_non_overlapping_root_events(self, event_loop, event_runner):
        """Check that non-overlapping events get new futures."""
        complete = []

        @event_runner.add_handler('a')
        async def a(_):
            complete.append('a')

        @event_runner.add_handler('b')
        async def b(_):
            complete.append('b')

        f1 = event_runner.runner.post_event('a')
        await asyncio.wait({f1}, loop=event_loop, timeout=0.1)
        assert f1.done()
        assert complete == ['a']

        f2 = event_runner.runner.post_event('b')
        assert not f2.done()
        assert f2 is not f1
        await asyncio.wait({f2}, loop=event_loop, timeout=0.1)
        assert f2.done()
        assert complete == ['a', 'b']

    @pytest.mark.asyncio(allow_unhandled_exception=True)
    async def test_exception_recovery(self, event_loop, event_runner):
        complete = []

        @event_runner.add_handler('a')
        def a1(_):
            raise Exception('a1')
            complete.append('a1')

        @event_runner.add_handler('a')
        def a2(_):
            complete.append('a2')

        @event_runner.add_handler('a')
        async def a3(_):
            raise Exception('a3')
            complete.append('a3')

        @event_runner.add_handler('a')
        async def a4(_):
            event_runner.runner.post_event('b')
            complete.append('a4')

        @event_runner.add_handler('b')
        def b1(_):
            raise Exception('b1')
            complete.append('b1')

        @event_runner.add_handler('b')
        async def b2(_):
            complete.append('b2')

        assert event_runner.exception_handler.call_count == 0
        future = event_runner.runner.post_event('a')
        await asyncio.wait({future}, loop=event_loop, timeout=0.1)
        assert future.done()
        assert future.exception() is None
        assert event_runner.runner.get_handlers.mock_calls == [
            mock.call('a'),
            mock.call('b'),
        ]
        assert complete == ['a2', 'a4', 'b2']
        assert event_runner.exception_handler.call_count == 3

        # Check that exception handler calls have the correct event context
        assert event_runner.exception_handler.mock_calls[0][1][1]['csbot_event'] == 'a'
        assert event_runner.exception_handler.mock_calls[1][1][1]['csbot_event'] == 'a'
        assert event_runner.exception_handler.mock_calls[2][1][1]['csbot_event'] == 'b'


class TestEvent(unittest.TestCase):
    class DummyBot(object):
        pass

    def _assert_events_equal(self, e1, e2, bot=True,
                             event_type=True, datetime=True, data=True):
        """Test helper for comparing two events.  ``<property>=False`` disables
        checking that property of the events."""
        if bot:
            self.assertIs(e1.bot, e2.bot)
        if event_type:
            self.assertEqual(e1.event_type, e2.event_type)
        if datetime:
            self.assertEqual(e1.datetime, e2.datetime)
        if data:
            for k in list(e1.keys()) + list(e2.keys()):
                self.assertEqual(e1[k], e2[k])

    def test_create(self):
        # Test data
        data = {'a': 1, 'b': 2, 'c': None}
        dt = datetime.datetime.now()
        bot = self.DummyBot()

        # Create the event
        e = csbot.events.Event(bot, 'event.type', data)
        # Check that the event's datetime can be reasonably considered "now"
        self.assertTrue(dt <= e.datetime)
        self.assertTrue(abs(e.datetime - dt) < datetime.timedelta(seconds=1))
        # Check that the bot, event type and data made it through
        self.assertIs(e.bot, bot)
        self.assertEqual(e.event_type, 'event.type')
        for k, v in data.items():
            self.assertEqual(e[k], v)

    def test_extend(self):
        # Test data
        data1 = {'a': 1, 'b': 2, 'c': None}
        data2 = {'c': 'foo', 'd': 'bar'}
        et1 = 'event.type'
        et2 = 'other.event'
        bot = self.DummyBot()

        # Create an event
        e1 = csbot.events.Event(bot, et1, data1)

        # Unchanged event
        e2 = csbot.events.Event.extend(e1)
        self._assert_events_equal(e1, e2)

        # Change event type only
        e3 = csbot.events.Event.extend(e2, et2)
        # Check the event type was changed
        self.assertEqual(e3.event_type, et2)
        # Check that everything else stayed the same
        self._assert_events_equal(e1, e3, event_type=False)

        # Change the event type and data
        e4 = csbot.events.Event.extend(e1, et2, data2)
        # Check the event type was changed
        self.assertEqual(e4.event_type, et2)
        # Check the data was updated
        for k in data1:
            if k not in data2:
                self.assertEqual(e4[k], data1[k])
        for k in data2:
            self.assertEqual(e4[k], data2[k])
        # Check that everything else stayed the same
        self._assert_events_equal(e1, e4, event_type=False, data=False)


class TestCommandEvent(unittest.TestCase):
    def setUp(self):
        self.nick = 'csbot'

    def _check_valid_command(self, message, prefix, command, data):
        """Test helper for checking the result of parsing a command from a
        message."""
        e = csbot.events.Event(None, 'test.event', {'message': message})
        c = csbot.events.CommandEvent.parse_command(e, prefix, self.nick)
        self.assertEqual(c['command'], command)
        self.assertEqual(c['data'], data)
        return c

    def _check_invalid_command(self, message, prefix):
        """Test helper for verifying that an invalid command is not
        interpreted as a valid command."""
        e = csbot.events.Event(None, 'test.event', {'message': message})
        c = csbot.events.CommandEvent.parse_command(e, prefix, self.nick)
        self.assertIs(c, None)
        return c

    def test_parse_command(self):
        # --> Test variations on command and data text with no prefix involvement
        # Just a command
        self._check_valid_command('testcommand', '',
                                  'testcommand', '')
        # Command and data
        self._check_valid_command('test command data', '',
                                  'test', 'command data')
        # Leading/trailing spaces are ignored
        self._check_valid_command('    test command', '', 'test', 'command')
        self._check_valid_command('test command    ', '', 'test', 'command')
        self._check_valid_command('  test   command  ', '', 'test', 'command')
        # Non-alphanumeric commands
        self._check_valid_command('!#?$ you !', '', '!#?$', 'you !')

        # --> Test what happens with a command prefix
        # Not a command
        self._check_invalid_command('just somebody talking', '!')
        # A simple command
        self._check_valid_command('!hello', '!', 'hello', '')
        # ... with data
        self._check_valid_command('!hello there', '!', 'hello', 'there')
        # ... and repeated prefix
        self._check_valid_command('!hello !there everybody', '!',
                                  'hello', '!there everybody')
        # Leading spaces
        self._check_valid_command('   !hello', '!', 'hello', '')
        # Spaces separating the prefix from the command shouldn't trigger it
        self._check_invalid_command('!  hello', '!')
        # The prefix can be part of the command if repeated
        self._check_valid_command('!!hello', '!', '!hello', '')
        self._check_valid_command('!!', '!', '!', '')

        # --> Test a longer prefix
        # As long as it is a prefix of the first "part", should be fine
        self._check_valid_command('dosomething now', 'do', 'something', 'now')
        # ... but if there's a space in between it's not a command any more
        self._check_invalid_command('do something now', 'do')

        # --> Test unicode
        # Unicode prefix
        self._check_valid_command('\u0CA0test', '\u0CA0', 'test', '')
        # Shouldn't match part of a UTF8 multibyte sequence: \u0CA0 = \xC2\xA3
        self._check_invalid_command('\u0CA0test', '\xC2')
        # Unicode command
        self._check_valid_command('!\u0CA0_\u0CA0', '!', '\u0CA0_\u0CA0', '')

        # Test "conversational", i.e. mentioned by nick
        self._check_valid_command('csbot: do something', '!', 'do', 'something')
        self._check_valid_command('   csbot, do   something ', '!', 'do', 'something')
        self._check_valid_command('csbot:do something', '!', 'do', 'something')
        self._check_invalid_command('csbot do something', '!')

    def test_arguments(self):
        """Test argument grouping/parsing.  These tests are pretty much just
        testing :func:`csbot.util.parse_arguments`, which should have its own
        tests."""
        # No arguments
        c = self._check_valid_command('!foo', '!', 'foo', '')
        self.assertEqual(c.arguments(), [])
        # Some simple arguments
        c = self._check_valid_command('!foo bar baz', '!', 'foo', 'bar baz')
        self.assertEqual(c.arguments(), ['bar', 'baz'])
        # ... with extra spaces
        c = self._check_valid_command('!foo    bar   baz   ', '!',
                                      'foo', 'bar   baz')
        self.assertEqual(c.arguments(), ['bar', 'baz'])
        # Forced argument grouping with quotes
        c = self._check_valid_command('!foo "bar baz"', '!',
                                      'foo', '"bar baz"')
        self.assertEqual(c.arguments(), ['bar baz'])
        # ... with extra spaces
        c = self._check_valid_command('!foo    "bar   baz "  ', '!',
                                      'foo', '"bar   baz "')
        self.assertEqual(c.arguments(), ['bar   baz '])
        # Escaped quote preserved
        c = self._check_valid_command(r'!foo ba\"r', '!', 'foo', r'ba\"r')
        self.assertEqual(c.arguments(), ['ba"r'])
        # Unmatched quotes break
        c = self._check_valid_command('!foo ba"r', '!', 'foo', 'ba"r')
        self.assertRaises(ValueError, c.arguments)
        # No mangling in the command part
        c = self._check_valid_command('!"foo bar', '!', '"foo', 'bar')
        c = self._check_valid_command('"foo bar', '"', 'foo', 'bar')
