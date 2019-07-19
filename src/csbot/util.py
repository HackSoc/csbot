import shlex
from itertools import tee
from collections import deque
import asyncio
import logging
import typing
from typing import (
    Dict,
    Iterator,
    Set,
    TypeVar,
)

import attr
import aiohttp
from async_generator import asynccontextmanager
import requests


LOG = logging.getLogger(__name__)

T = TypeVar("T")


def nick(user):
    """Get nick from user string.

    >>> nick('csyorkbot!~csbot@example.com')
    'csyorkbot'
    """
    return user.split('!', 1)[0]


def username(user):
    """Get username from user string.

    >>> username('csyorkbot!~csbot@example.com')
    'csbot'
    """
    return user.rsplit('@', 1)[0].rsplit('~', 1)[1]


def host(user):
    """Get hostname from user string.

    >>> host('csyorkbot!~csbot@example.com')
    'example.com'
    """
    return user.rsplit('@', 1)[1]


def is_channel(channel):
    """Check if *channel* is a channel or private chat.

    >>> is_channel('#cs-york')
    True
    >>> is_channel('csyorkbot')
    False
    """
    return channel.startswith('#')


def parse_arguments(raw):
    """Parse *raw* into a list of arguments using :mod:`shlex`.

    The :mod:`shlex` lexer is customised to be more appropriate for grouping
    natural language arguments by only treating ``"`` as a quote character.
    This allows ``'`` to be used naturally.  A :exc:`~exceptions.ValueError`
    will be raised if the string couldn't be parsed.

    >>> parse_arguments("a test string")
    ['a', 'test', 'string']
    >>> parse_arguments("apostrophes aren't a problem")
    ['apostrophes', "aren't", 'a', 'problem']
    >>> parse_arguments('"string grouping" is useful')
    ['string grouping', 'is', 'useful']
    >>> parse_arguments('just remember to "match your quotes')
    Traceback (most recent call last):
      File "<stdin>", line 1, in ?
    ValueError: No closing quotation
    """
    # Start with a shlex instance similar to shlex.split
    lex = shlex.shlex(raw, posix=True)
    lex.whitespace_split = True
    # Restrict quoting characters to "
    lex.quotes = '"'
    # Parse the string
    return list(lex)


def simple_http_get(url, stream=False):
    """A deliberately dumb wrapper around :func:`requests.get`.

    This should be used for the vast majority of HTTP GET requests.  It turns
    off SSL certificate verification and sets a non-default User-Agent, thereby
    succeeding at most "just get the content" requests. Note that it can
    generate a ConnectionError exception if the url is not resolvable.

    *stream* controls the "streaming mode" of the HTTP client, i.e. deferring
    the acquisition of the response body.  Use this if you need to impose a
    maximum size or process a large response.  *The entire content must be
    consumed or ``response.close()`` must be called.*
    """
    headers = {'User-Agent': 'csbot/0.1'}
    return requests.get(url, verify=False, headers=headers, stream=stream)


@asynccontextmanager
async def simple_http_get_async(url, **kwargs):
    session_kwargs = {
        'headers': {
            'User-Agent': 'csbot/0.1',
        },
    }
    kwargs.setdefault('ssl', False)
    async with aiohttp.ClientSession(**session_kwargs) as session:
        async with session.get(url, **kwargs) as resp:
            yield resp


def pairwise(iterable):
    """Pairs elements of an iterable together,
    e.g. s -> (s0,s1), (s1,s2), (s2, s3), ...
    """
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def cap_string(s, l):
    """If a string is longer than a particular length,
    it gets truncated and has '...' added to the end.
    """
    if len(s) <= l:
        return s

    return s[0:l-3] + "..."


def ordinal(value):
    """
    Converts zero or a *postive* integer (or their string
    representations) to an ordinal value.

    http://code.activestate.com/recipes/576888-format-a-number-as-an-ordinal/

    >>> for i in range(1,13):
    ...     ordinal(i)
    ...
    u'1st'
    u'2nd'
    u'3rd'
    u'4th'
    u'5th'
    u'6th'
    u'7th'
    u'8th'
    u'9th'
    u'10th'
    u'11th'
    u'12th'

    >>> for i in (100, '111', '112',1011):
    ...     ordinal(i)
    ...
    u'100th'
    u'111th'
    u'112th'
    u'1011th'

    """
    try:
        value = int(value)
    except ValueError:
        return value

    if value % 100//10 != 1:
        if value % 10 == 1:
            ordval = u"%d%s" % (value, "st")
        elif value % 10 == 2:
            ordval = u"%d%s" % (value, "nd")
        elif value % 10 == 3:
            ordval = u"%d%s" % (value, "rd")
        else:
            ordval = u"%d%s" % (value, "th")
    else:
        ordval = u"%d%s" % (value, "th")

    return ordval


def pluralize(n, singular, plural):
    return '{0} {1}'.format(n, singular if n == 1 else plural)


def is_ascii(s):
    """Returns true if all characters in a string can be represented in ASCII.
    """
    return all(ord(c) < 128 for c in s)


def maybe_future(result, *, on_error=None, log=LOG, loop=None):
    """Make *result* a future if possible, otherwise return None.

    If *result* is not None but also not awaitable, it is passed to *on_error*
    if supplied, otherwise logged as a warning on *log*.
    """
    if result is None:
        return None
    try:
        future = asyncio.ensure_future(result, loop=loop)
    except TypeError:
        if on_error:
            on_error(result)
        else:
            log.warning('maybe_future() ignoring non-awaitable result %r', result)
        return None
    return future


async def maybe_future_result(result, **kwargs):
    """Get actual result from *result*.

    If *result* is awaitable, return the result of awaiting it, otherwise just
    return *result*.
    """
    future = maybe_future(result, **kwargs)
    if future:
        return await future
    else:
        return result


def truncate_utf8(b: bytes, maxlen: int, ellipsis: bytes = b"...") -> bytes:
    """Trim *b* to a maximum of *maxlen* bytes (including *ellipsis* if longer), without breaking UTF-8 sequences."""
    if len(b) <= maxlen:
        return b
    # Cut down to 1 byte more than we need
    b = b[:maxlen - len(ellipsis) + 1]
    # Find the last non-continuation byte
    for i in range(len(b) - 1, -1, -1):
        if not 0x80 <= b[i] <= 0xBF:
            # Break the string to exclude the last UTF-8 sequence
            b = b[:i]
            break
    return b + ellipsis


def topological_sort(data: Dict[T, Set[T]]) -> Iterator[Set[T]]:
    """Get topological ordering from dependency data.

    Generates sets of items with equal ordering position.
    """
    data = data.copy()
    while True:
        # Find keys with no more dependencies
        resolved = set(k for k, deps in data.items() if not deps)
        # Finished when no more dependencies got resolved
        if not resolved:
            break
        else:
            yield resolved
        # Remove resolved dependencies from remaining items
        data = {k: deps - resolved for k, deps in data.items() if k not in resolved}
    # Any remaining data means circular dependencies
    if data:
        raise ValueError(f"circular dependencies detected: {data!r}")


class RateLimited:
    """An asynchronous wrapper around calling *f* that is rate limited to *count* calls per *period* seconds.

    Calling the rate limiter returns a future that completes with the result of calling *f* with the same arguments.
    :meth:`start` and :meth:`stop` control whether or not calls are actually processed.
    """
    def __init__(self, f, *, period: float = 2.0, count: int = 5, loop=None, log=LOG):
        assert period > 0.0
        assert count > 0
        self.f = f
        self._period = period
        self._count = count
        self._loop = loop or asyncio.get_event_loop()
        self._log = log
        self._call_queue = asyncio.Queue()
        self._call_history = deque()
        self._task = None

    def __call__(self, *args, **kwargs):
        future = self._loop.create_future()
        self._call_queue.put_nowait((args, kwargs, future))
        return future

    def get_delay(self) -> float:
        """Get number of seconds to wait before processing the next call."""
        now = self._loop.time()
        # Prune call history to the relevant period
        queue_start = now - self._period
        while len(self._call_history) > 0 and self._call_history[0] <= queue_start:
            self._call_history.popleft()
        # If we still have space, then can call immediately
        if len(self._call_history) < self._count:
            return 0.0
        # Otherwise, we can call when the first item will drop out of the relevant period
        next_call = self._call_history[0] + self._period
        return next_call - now

    async def run(self):
        while True:
            delay = self.get_delay()
            if delay > 0.0:
                self._log.debug(f"waiting {delay} seconds until next call to {self.f}")
                await asyncio.sleep(delay)
            args, kwargs, future = await self._call_queue.get()
            try:
                result = self.f(*args, **kwargs)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
            self._call_queue.task_done()
            self._call_history.append(self._loop.time())

    def start(self):
        """Start async task to process calls."""
        assert self._task is None
        self._task = asyncio.ensure_future(self.run(), loop=self._loop)

    def stop(self, clear=True):
        """Stop async call processing.

        If *clear* is True (the default), any pending calls not yet processed have their futures cancelled. If it's
        False, then those pending calls will still be queued when :meth:`start` is called again.

        Returns list of ``(args, kwargs)`` pairs of cancelled calls.
        """
        if self._task is None:
            return
        self._task.cancel()
        self._task = None
        cancelled = []
        if clear:
            self._call_history.clear()
            while True:
                try:
                    args, kwargs, future = self._call_queue.get_nowait()
                    future.cancel()
                    self._call_queue.task_done()
                    cancelled.append((args, kwargs))
                except asyncio.QueueEmpty:
                    break
        return cancelled


def type_validator(_obj, attrib: attr.Attribute, value):
    """An attrs validator that inspects the attribute type."""
    if attrib.type is None:
        raise TypeError(f"'{attrib.name}' has no type to check")
    elif getattr(attrib.type, "__origin__", None) is typing.Union:
        if any(isinstance(value, t) for t in attrib.type.__args__):
            return True
    elif isinstance(value, attrib.type):
        return True
    raise TypeError(f"'{attrib.name}' must be {attrib.type} (got {value} that is a {type(value)}",
                    attrib, value)


class PrettyStreamHandler(logging.StreamHandler):
    """Wrap log messages with severity-dependent ANSI terminal colours.

    Use in place of :class:`logging.StreamHandler` to have log messages coloured
    according to severity.

    >>> handler = PrettyStreamHandler()
    >>> handler.setFormatter(logging.Formatter('[%(levelname)-8s] %(message)s'))
    >>> logging.getLogger('').addHandler(handler)

    *stream* corresponds to the same argument to :class:`logging.StreamHandler`,
    defaulting to stderr.

    *colour* overrides TTY detection to force colour on or off.

    This source for this class is released into the public domain.

    .. codeauthor:: Alan Briolat <alan.briolat@gmail.com>
    """
    #: Mapping from logging levels to ANSI colours.
    COLOURS = {
        logging.DEBUG: '\033[36m',      # Cyan foreground
        logging.WARNING: '\033[33m',    # Yellow foreground
        logging.ERROR: '\033[31m',      # Red foreground
        logging.CRITICAL: '\033[31;7m'  # Red foreground, inverted
    }
    #: ANSI code for resetting the terminal to default colour.
    COLOUR_END = '\033[0m'

    def __init__(self, stream=None, colour=None):
        super(PrettyStreamHandler, self).__init__(stream)
        if colour is None:
            self.colour = self.stream.isatty()
        else:
            self.colour = colour

    def format(self, record):
        """Get a coloured, formatted message for a log record.

        Calls :func:`logging.StreamHandler.format` and applies a colour to the
        message if appropriate.
        """
        msg = super(PrettyStreamHandler, self).format(record)
        if self.colour:
            colour = self.COLOURS.get(record.levelno, '')
            return colour + msg + self.COLOUR_END
        else:
            return msg
