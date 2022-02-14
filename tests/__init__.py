import asyncio
import os
from unittest import mock


class MockStreamReader(asyncio.StreamReader):
    pass


class MockStreamWriter(asyncio.StreamWriter):
    def close(self):
        self._reader.feed_eof()


def paused(f):
    """Wrap a coroutine function so it waits until explicitly enabled.
    """
    event = asyncio.Event()
    resume = event.set

    async def _f(*args, **kwargs):
        await event.wait()
        result = await f(*args, **kwargs)
        event.clear()
        return result

    return _f, resume


async def open_mock_connection(*args, loop=None, **kwargs):
    """Create a mock reader and writer pair.
    """
    reader = MockStreamReader(loop=loop)
    writer = MockStreamWriter(None, None, reader, loop)
    writer.write = mock.Mock()
    return reader, writer


def mock_open_connection():
    """Give a mock reader and writer when a stream connection is opened.

    >>> with mock_open_connection():
    ...     await self.client.connect()
    ...     irc_client.quit('blah')
    ...     irc_client_helper.assert_bytes_sent(client, b'QUIT :blah\r\n')
    """
    return mock.patch('asyncio.open_connection', side_effect=open_mock_connection)


def mock_open_connection_paused():
    """When connection is opened, wait until resumed, then give a mock reader and writer.

    >>> with mock_open_connection_paused() as m:
    ... irc_client.disconnect()
    ... await irc_client.disconnected.wait()
    ... m.resume()
    ... await irc_client.connected.wait()
    """
    f, resume = paused(open_mock_connection)
    return mock.patch('asyncio.open_connection', side_effect=f, resume=resume)


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


def fixture_file(*path):
    """Get the path to a fixture file."""
    return os.path.join(os.path.dirname(__file__), 'fixtures', *path)


def read_fixture_file(*path, mode='rb'):
    """Read the contents of a fixture file."""
    with open(fixture_file(*path), mode) as f:
        return f.read()
