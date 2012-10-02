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
