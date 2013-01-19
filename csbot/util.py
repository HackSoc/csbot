import shlex


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
    # Work around shlex's broken unicode handling in Python <= 2.7.2
    if isinstance(raw, unicode):
        raw = raw.encode('utf-8')
    # Start with a shlex instance similar to shlex.split
    lex = shlex.shlex(raw, posix=True)
    lex.whitespace_split = True
    # Restrict quoting characters to "
    lex.quotes = '"'
    # Parse the string
    return list(lex)

def format_date(bot, date):
    return date.strftime(bot.config_get('date_format'))

def format_time(bot, date):
    return date.strftime(bot.config_get('time_format'))

def sensible_time(bot, datetime, prefix=False):
    if datetime.day == datetime.today().day:
        if prefix:
            return 'at ' + format_time(bot, datetime)
        else:
            return format_time(bot, datetime)
    else:
        if prefix:
            return 'on ' + format_date(bot, datetime)
        else:
            return format_date(bot, datetime)
