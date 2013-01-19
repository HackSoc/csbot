import os


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
