import shlex
from itertools import tee

import requests


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


def simple_http_get(url):
    """A deliberately dumb wrapper around :func:`requests.get`.

    This should be used for the vast majority of HTTP GET requests.  It turns
    off SSL certificate verification and sets a non-default User-Agent, thereby
    succeeding at most "just get the content" requests.
    """
    headers = {'User-Agent': 'csbot/0.1'}
    return requests.get(url, verify=False, headers=headers)

def pairwise(iterable):
    """Pairs elements of an iterable together,
    e.g. s -> (s0,s1), (s1,s2), (s2, s3), ..."""
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)
