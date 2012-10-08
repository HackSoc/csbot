import os


class MethodRecorderMixin(object):
    """A mixin that records every method call made.

    In this case, a "method" is any callable object attribute, excluding
    ``__init__``.  Other attributes should remain untouched, including static
    and class methods.
    """
    def __init__(self, *args, **kwargs):
        super(MethodRecorderMixin, self).__init__(*args, **kwargs)
        self.recorded_method_calls = []

    def __getattribute__(self, name):
        # Will raise AttributeError as normal if the attribute is missing
        attr = super(MethodRecorderMixin, self).__getattribute__(name)

        # Wrap callable attributes in a function that records the method call
        if callable(attr):
            def f(*args, **kwargs):
                self.recorded_method_calls.append((name, args, kwargs))
                return attr(*args, **kwargs)
            return f
        else:
            return attr


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
