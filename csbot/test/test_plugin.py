from twisted.trial import unittest

from csbot.test.helpers import MethodRecorderMixin


class TestMethodRecorder(unittest.TestCase):
    """Test that the :class:`MethodRecorderMixin` helper works as expected.
    """

    class Example(object):
        class_attribute = 'class_attribute'

        def __init__(self):
            self.object_attribute = 'object_attribute'

        def object_method(self, x, y):
            return (y, x)

        @classmethod
        def class_method(cls, x, y):
            return (y, x)

        @staticmethod
        def static_method(x, y):
            return (y, x)

        def noop(self, *args, **kwargs):
            pass

    class RecordingExample(MethodRecorderMixin, Example):
        pass

    def test_attribute_handling(self):
        # Clean method recorder, no recorded method calls
        p = self.RecordingExample()
        self.assertEqual(p.recorded_method_calls, [])

        # Non-existent attributes should still cause an AttributeError
        self.assertRaises(AttributeError, lambda: p.non_existent)

        # Check that an object attribute is unmangled when accessed
        self.assertEqual(p.object_attribute, 'object_attribute')
        self.assertIs(p.object_attribute,
            super(MethodRecorderMixin, p).__getattribute__('object_attribute'))

        # Check the same for a class attribute
        self.assertEqual(p.class_attribute, 'class_attribute')
        self.assertIs(p.class_attribute,
            super(MethodRecorderMixin, p).__getattribute__('class_attribute'))

        # An object method, however, should be wrapped, and not be the same as
        # the method accessed from the base class
        self.assertIsNot(p.object_method,
            super(MethodRecorderMixin, p).__getattribute__('object_method'))

        # The same for class methods and static methods when accessed on the
        # object
        self.assertIsNot(p.class_method,
            super(MethodRecorderMixin, p).__getattribute__('class_method'))
        self.assertIsNot(p.static_method,
            super(MethodRecorderMixin, p).__getattribute__('static_method'))

        # None of the above should have called any methods
        self.assertEqual(p.recorded_method_calls, [])

    def test_method_results(self):
        # Check that method results actually end up at the caller
        p = self.RecordingExample()
        self.assertEqual(p.object_method(1, 2), (2, 1))
        self.assertEqual(p.class_method(3, 4), (4, 3))
        self.assertEqual(p.static_method(5, 6), (6, 5))

    def test_method_calls_recorded(self):
        # Check that method calls are recorded
        p = self.RecordingExample()
        p.object_method(1, 2)
        p.class_method(3, 4)
        p.static_method(5, 6)
        p.noop('foo', bar='baz')
        self.assertEqual(p.recorded_method_calls, [
            ('object_method', (1, 2), {}),
            ('class_method', (3, 4), {}),
            ('static_method', (5, 6), {}),
            ('noop', ('foo',), {'bar': 'baz'}),
        ])

    def test_non_object_methods_not_recorded(self):
        P = self.RecordingExample
        self.assertRaises(AttributeError, lambda: P.recorded_method_calls)
        self.assertEqual(P.class_method(1, 2), (2, 1))
        self.assertRaises(AttributeError, lambda: P.recorded_method_calls)
        self.assertEqual(P.static_method(3, 4), (4, 3))
        self.assertRaises(AttributeError, lambda: P.recorded_method_calls)
