import shlex
from itertools import tee
from collections import deque, OrderedDict
import asyncio
import logging
from typing import (
    Dict,
    Iterator,
    List,
    Set,
    TypeVar,
)

import requests
from async_generator import asynccontextmanager
import aiohttp


LOG = logging.getLogger(__name__)

T = TypeVar("T")


class User(object):
    def __init__(self, raw):
        self.raw = raw
        self.nick = raw.split('!', 1)[0] if '!' in raw else None
        self.username = raw.rsplit('@', 1)[0].rsplit('~', 1)[1]
        self.host = raw.rsplit('@', 1)[1]


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


class NamedObject(object):
    """Make objects that have specific :meth:`__repr__` text.

    This is mostly useful for singleton objects that you want to give a
    useful description for auto-generated documentation purposes.
    """
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


class StructMeta(type):
    """A metaclass for :class:`Struct` to turn class attributes into fields.
    """

    @classmethod
    def __prepare__(mcs, name, bases):
        """Use :class:`collections.OrderedDict` to preserve attribute order.
        """
        return OrderedDict()

    def __new__(mcs, name, bases, attrs):
        # Don't molest the base class, there are no fields on it
        if bases == (object,):
            return type.__new__(mcs, name, bases, attrs)

        # Find fields in base classes
        attrs['_fields'] = []
        for b in bases:
            attrs['_fields'] += getattr(b, '_fields', [])
        # Find attributes in this class that should be fields
        attrs['_fields'] += [k for k, v in attrs.items()
                             if not k.startswith('_') and not callable(v)]
        # Build new class
        return type.__new__(mcs, name, bases, attrs)


class Struct(object, metaclass=StructMeta):
    """A mutable alternative to :func:`collections.namedtuple`.

    To use this class, create a subclass of it.  Any non-callable, non-"hidden"
    class attributes in the subclass will become struct fields.  Setting of
    attribute values is limited to attributes recognised as fields.  The class
    attribute value is effectively the field's default value.

    A struct constructor allows both positional arguments (based on field
    order) and keyword arguments (based on field name).  If a field's default
    value is :attr:`REQUIRED`, then an exception will be raised unless its
    value was set by the constructor.

    Examples:

    >>> class Foo(Struct):
    ...     a = Struct.REQUIRED
    ...     b = 12
    ...     c = None
    ...
    >>> Foo()
    Traceback (most recent call last):
        ...
    ValueError: value required for attribute: a
    >>> Foo(123)
    Foo(a=123, b=12, c=None)
    >>> Foo(123, c='Hello, world')
    Foo(a=123, b=12, c='Hello, world')
    >>> Foo(bar=False)
    Traceback (most recent call last):
        ...
    AttributeError: struct field does not exist: bar
    >>> x = Foo(123)
    >>> x.b
    12
    >>> x.b = 21
    >>> x
    Foo(a=123, b=21, c=None)
    >>> x.bar = False
    Traceback (most recent call last):
        ...
    AttributeError: struct field does not exist: bar
    """
    #: Singleton object to signify an attribute that *must* be set
    REQUIRED = NamedObject('Struct.REQUIRED')

    #: Field names of the struct, in order (populated by :class:`StructMeta`)
    _fields: List[str]

    def __init__(self, *args, **kwargs):
        values = OrderedDict()
        # Allow positional arguments, but not too many
        if len(args) > len(self._fields):
            raise TypeError('__init__ takes at most {} arguments ({} given)'
                            .format(len(self._fields), len(args)))
        # Apply positional arguments
        values.update(zip(self._fields, args))

        # Apply keyword arguments
        values.update(kwargs)

        # Set attribute values - those that don't exist will raise errors
        for k, v in values.items():
            setattr(self, k, v)

        # Check that required attributes were set
        for k in self._fields:
            if getattr(self, k) is Struct.REQUIRED:
                raise ValueError('value required for attribute: ' + k)

    def __setattr__(self, key, value):
        """Prevent setting of non-field attributes.
        """
        if key not in self._fields:
            raise AttributeError('struct field does not exist: {}'.format(key))
        else:
            object.__setattr__(self, key, value)

    def __repr__(self):
        """Give a useful representation for the struct object.
        """
        return '{}({})'.format(self.__class__.__name__,
                               ', '.join('{}={!r}'.format(k, getattr(self, k))
                                         for k in self._fields))


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
