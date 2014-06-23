import unittest
import datetime

import csbot.events
import collections


class TestImmediateEventRunner(unittest.TestCase):
    def setUp(self):
        self.runner = csbot.events.ImmediateEventRunner(self.handle_event)
        self.handled_events = []

    def tearDown(self):
        self.runner = None
        self.handled_events = None

    def handle_event(self, event):
        """Record objects passed through the event handler in order.  If they
        are callable, call them."""
        self.handled_events.append(event)
        if isinstance(event, collections.Callable):
            event()

    def test_values(self):
        """Check that basic values are passed through the event queue
        unmolested."""
        # Test that things actually get through
        self.runner.post_event('foo')
        self.assertEqual(self.handled_events, ['foo'])
        # The event runner doesn't care what it's passing through
        for x in ['bar', 1.3, None, object]:
            self.runner.post_event(x)
            self.assertIs(self.handled_events[-1], x)

    def test_event_chain(self):
        """Check that chains of events get handled."""
        def f1():
            self.runner.post_event(f2)

        def f2():
            self.runner.post_event(f3)

        def f3():
            pass

        self.runner.post_event(f1)
        self.assertEqual(self.handled_events, [f1, f2, f3])

    def test_event_tree(self):
        """Check that trees of events are handled breadth-first."""
        def f1():
            self.runner.post_event(f2)
            self.runner.post_event(f3)

        def f2():
            self.runner.post_event(f4)

        def f3():
            self.runner.post_event(f5)
            self.runner.post_event(f6)

        def f4():
            self.runner.post_event(f3)

        def f5():
            pass

        def f6():
            pass

        self.runner.post_event(f1)
        self.assertEqual(self.handled_events,
                         [f1, f2, f3, f4, f5, f6, f3, f5, f6])

    def test_exception_recovery(self):
        """Check that exceptions propagate out of the event runner but don't
        leave it broken.

        (In an early version of ImmediateEventRunner, an exception would leave
        the runner's queue non-empty and new root events would accumulate
        instead of being processed.)
        """
        def f1():
            self.runner.post_event(f2)
            raise Exception()

        def f2():
            pass

        def f3():
            self.runner.post_event(f4)

        def f4():
            pass

        self.assertRaises(Exception, self.runner.post_event, f1)
        self.assertEqual(self.handled_events, [f1])
        self.runner.post_event(f3)
        self.assertEqual(self.handled_events, [f1, f3, f4])


class TestEvent(unittest.TestCase):
    class DummyProtocol(object):
        pass

    def _assert_events_equal(self, e1, e2, protocol=True, bot=True,
                             event_type=True, datetime=True, data=True):
        """Test helper for comparing two events.  ``<property>=False`` disables
        checking that property of the events."""
        if protocol:
            self.assertIs(e1.protocol, e2.protocol)
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
        bot = object()
        protocol = self.DummyProtocol()
        protocol.bot = bot

        # Create the event
        e = csbot.events.Event(protocol, 'event.type', data)
        # Check that the event's datetime can be reasonably considered "now"
        self.assertTrue(dt <= e.datetime)
        self.assertTrue(abs(e.datetime - dt) < datetime.timedelta(seconds=1))
        # Check that the protocol, event type and data made it through
        self.assertIs(e.protocol, protocol)
        self.assertIs(e.bot, bot)
        self.assertEqual(e.event_type, 'event.type')
        for k, v in data.items():
            self.assertEqual(e[k], v)

        # Check that .bot really is a shortcut to .protocol.bot
        broken_protocol = self.DummyProtocol()
        broken_event = csbot.events.Event(broken_protocol, 'broken')
        self.assertRaises(AttributeError, lambda: broken_event.bot)

    def test_extend(self):
        # Test data
        data1 = {'a': 1, 'b': 2, 'c': None}
        data2 = {'c': 'foo', 'd': 'bar'}
        et1 = 'event.type'
        et2 = 'other.event'
        bot = object()
        protocol = self.DummyProtocol()
        protocol.bot = bot

        # Create an event
        e1 = csbot.events.Event(protocol, et1, data1)

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
    def _check_valid_command(self, message, prefix, command, data):
        """Test helper for checking the result of parsing a command from a
        message."""
        e = csbot.events.Event(None, 'test.event', {'message': message})
        c = csbot.events.CommandEvent.parse_command(e, prefix)
        self.assertEqual(c['command'], command)
        self.assertEqual(c['data'], data)
        return c

    def _check_invalid_command(self, message, prefix):
        """Test helper for verifying that an invalid command is not
        interpreted as a valid command."""
        e = csbot.events.Event(None, 'test.event', {'message': message})
        c = csbot.events.CommandEvent.parse_command(e, prefix)
        self.assertIs(c, None)
        return c

    def test_parse_command(self):
        # Test variations on command and data text with no prefix involvement
        ## Just a command
        self._check_valid_command('testcommand', '',
                                  'testcommand', '')
        ## Command and data
        self._check_valid_command('test command data', '',
                                  'test', 'command data')
        ## Leading/trailing spaces are ignored
        self._check_valid_command('    test command', '', 'test', 'command')
        self._check_valid_command('test command    ', '', 'test', 'command')
        self._check_valid_command('  test   command  ', '', 'test', 'command')
        ## Non-alphanumeric commands
        self._check_valid_command('!#?$ you !', '', '!#?$', 'you !')

        # Test what happens with a command prefix
        ## Not a command
        self._check_invalid_command('just somebody talking', '!')
        ## A simple command
        self._check_valid_command('!hello', '!', 'hello', '')
        ## ... with data
        self._check_valid_command('!hello there', '!', 'hello', 'there')
        ## ... and repeated prefix
        self._check_valid_command('!hello !there everybody', '!',
                                  'hello', '!there everybody')
        ## Leading spaces
        self._check_valid_command('   !hello', '!', 'hello', '')
        ## Spaces separating the prefix from the command shouldn't trigger it
        self._check_invalid_command('!  hello', '!')
        ## The prefix can be part of the command if repeated
        self._check_valid_command('!!hello', '!', '!hello', '')
        self._check_valid_command('!!', '!', '!', '')

        # Test a longer prefix
        ## As long as it is a prefix of the first "part", should be fine
        self._check_valid_command('dosomething now', 'do', 'something', 'now')
        ## ... but if there's a space in between it's not a command any more
        self._check_invalid_command('do something now', 'do')

        # Test unicode
        ## Unicode prefix
        self._check_valid_command('\u0CA0test', '\u0CA0', 'test', '')
        ## Shouldn't match part of a UTF8 multibyte sequence: \u0CA0 = \xC2\xA3
        self._check_invalid_command('\u0CA0test', '\xC2')
        ## Unicode command
        self._check_valid_command('!\u0CA0_\u0CA0', '!', '\u0CA0_\u0CA0', '')

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
