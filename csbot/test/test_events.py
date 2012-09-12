from twisted.trial import unittest

import csbot.events


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
        if callable(event):
            event()

    def test_values(self):
        """Check that basic values are passed through the event queue
        unmolested."""
        # Test that things actually get through
        self.runner.post_event('foo')
        self.assertEquals(self.handled_events, ['foo'])
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
        self.assertEquals(self.handled_events, [f1, f2, f3])

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
        self.assertEquals(self.handled_events,
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

        self.failUnlessRaises(Exception, self.runner.post_event, f1)
        self.assertEquals(self.handled_events, [f1])
        self.runner.post_event(f3)
        self.assertEquals(self.handled_events, [f1, f3, f4])
