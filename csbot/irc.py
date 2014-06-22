import asyncio
import logging
import signal
import re
from collections import namedtuple
import codecs

from ._rfc import NUMERIC_REPLIES


LOG = logging.getLogger('csbot.irc')


class IRCParseError(Exception):
    """Raised by :meth:`IRCMessage.parse` when a message can't be parsed."""


class IRCMessage(namedtuple('_IRCMessage',
                            'prefix command params command_name raw')):
    """Represents an IRC message.

    The IRC message format, paraphrased and simplified from RFC2812, is::

        message = [":" prefix " "] command {" " parameter} [" :" trailing]

    This is represented as a :class:`namedtuple` with the following attributes:

    :param prefix: Prefix part of the message, usually the origin
    :type prefix: str or None
    :param command: IRC command
    :type command: str
    :param params: List of command parameters (including trailing)
    :type params: list of str
    :param command_name: Name of IRC command (see below)
    :type command_name: str
    :param raw: The raw IRC message
    :type raw: str

    The *command_name* attribute is intended to be the "readable" form of the
    *command*.  Usually it will be the same as *command*, but numeric replies
    recognised in RFC2812 will have their corresponding name instead.
    """

    #: Regular expression to extract message components from a message.
    REGEX = re.compile(r'(:(?P<prefix>\S+) )?(?P<command>\S+)'
                       r'(?P<params>( (?!:)\S+)*)( :(?P<trailing>.*))?')

    @classmethod
    def parse(cls, line):
        """Create an :class:`IRCMessage` object by parsing a raw message."""
        match = cls.REGEX.match(line)
        if match is None:
            raise IRCParseError(line)
        else:
            groups = match.groupdict()
            # Store raw IRC message
            groups['raw'] = line
            # Split space-separated parameters
            groups['params'] = groups['params'].split()
            # Trailing is really just another parameter
            if groups['trailing']:
                groups['params'].append(groups['trailing'])
            del groups['trailing']
            # Create command_name, which is either the RFC2812 name for a
            # numeric command, or just the received command.
            groups['command_name'] = NUMERIC_REPLIES.get(groups['command'],
                                                         groups['command'])
            return cls(**groups)

    @classmethod
    def create(cls, command, params=None, prefix=None):
        """Create an :class:`IRCMessage` from its core components.

        The *raw* and *command_name* attributes will be generated based on the
        message details.
        """
        args = {
            'prefix': prefix or None,
            'command': command,
            'params': params or [],
            'command_name': NUMERIC_REPLIES.get(command, command),
            'raw': ''.join([
                (':' + prefix + ' ') if prefix else '',
                command,
                cls._raw_params(params or []),
            ]),
        }
        return cls(**args)

    @property
    def pretty(self):
        """Get a more readable version of the raw IRC message.

        Pretty much identical to the raw IRC message, but numeric commands
        that have names end up being ``NUMERIC/NAME``.
        """
        return ''.join([
            (':' + self.prefix + ' ') if self.prefix else '',
            self.command,
            ('/' + self.command_name) if self.command != self.command_name else '',
            self._raw_params(self.params),
        ])

    def pad_params(self, length, default=None):
        """Pad parameters to *length* with *default*.

        Useful when a command has optional parameters:

        >>> msg = IRCMessage.parse(':nick!user@host KICK #channel other')
        >>> channel, nick, reason = msg.params
        Traceback (most recent call last):
          ...
        ValueError: need more than 2 values to unpack
        >>> channel, nick, reason = msg.pad_params(3)
        """
        return self.params + [default] * (length - len(self.params))

    @staticmethod
    def _raw_params(params):
        if len(params) > 0 and ' ' in params[-1]:
            trailing = params[-1]
            params = params[:-1]
        else:
            trailing = None

        raw = ''
        if len(params) > 0:
            raw += ' ' + ' '.join(params)
        if trailing is not None:
            raw += ' :' + trailing
        return raw


class IRCUser(namedtuple('_IRCUser', 'raw nick user host')):
    """Provide access to the parts of an IRC user string.

    The following parts of the user string are available, set to *None* if that
    part of the string is absent:

    :param raw: Raw user string
    :param nick: Nick of the user
    :param user: Username of the user (excluding leading ``~``)
    :param host: Hostname of the user

    >>> u = IRCUser.parse('my_nick!some_user@host.name')
    >>> u.nick
    'my_nick'
    >>> u.user
    'some_user'
    >>> u.host
    'host.name'
    """
    #: Username parsing regex.  Stripping out the "~" might be a
    #: Freenode peculiarity...
    REGEX = re.compile(r'(?P<raw>(?P<nick>[^!]+)(!~*(?P<user>[^@]+))?(@(?P<host>.+))?)')

    @classmethod
    def parse(cls, raw):
        """Create an :class:`IRCUser` from a raw user string."""
        return cls(**cls.REGEX.match(raw).groupdict())


class IRCCodec(codecs.Codec):
    """The encoding scheme to use for IRC messages.

    IRC messages are "just bytes" with no encoding made explicit in the
    protocol definition or the messages.  Ideally we'd like to handle IRC
    messages as proper strings.
    """
    def encode(self, input, errors='strict'):
        """Encode a message as UTF-8."""
        return codecs.encode(input, 'utf-8', errors)

    def decode(self, input, errors='strict'):
        """Decode a message.

        IRC messages could pretty much be in any encoding.  Here we just try
        the two most likely candidates: UTF-8, falling back to CP1252.
        Unfortunately, any encoding where every byte is valid (e.g. CP1252)
        makes it impossible to detect encoding errors - if *input* isn't UTF-8
        or CP1252-compatible, the result might be a bit odd.
        """
        try:
            return codecs.decode(input, 'utf-8', errors)
        except UnicodeDecodeError:
            return codecs.decode(input, 'cp1252', errors)


class IRCClient(asyncio.Protocol):
    """Internet Relay Chat client protocol.

    A line-oriented protocol for communicating with IRC servers.  It handles
    receiving data at several layers of abstraction:

    * :meth:`data_received`: raw bytes
    * :meth:`line_received`: decoded line
    * :meth:`message_received`: parsed :class:`IRCMessage`
    * ``irc_<COMMAND>(msg)``: called when ``msg.command == '<COMMAND>'``
    * ``on_<event>(...)``: specific events with specific arguments,
      e.g. ``on_quit(user, message)``

    It also handles sending data at several layers of abstraction:

    * :meth:`send_raw`: raw IRC command, e.g. ``self.send_raw('JOIN #cs-york-dev')``
    * :meth:`send`: :class:`IRCMessage`, e.g.
      ``self.send(IRCMessage.create('JOIN', params=['#cs-york-dev']))``
    * ``<action>(...)``: e.g. ``self.join('#cs-york-dev')``.

    The API and implementation is inspired by irc3_ and Twisted_.

    .. _irc3: https://github.com/gawel/irc3
    .. _Twisted: http://twistedmatrix.com/documents/14.0.0/api/twisted.words.protocols.irc.IRCClient.html

    * TODO: limit send rate
    * TODO: limit PRIVMSG/NOTICE send length
    * TODO: NAMES
    * TODO: MODE
    * TODO: More sophisticated CTCP? (see Twisted_)
    * TODO: MOTD?
    * TODO: SSL
    """
    #: Codec for encoding/decoding IRC messages.
    codec = IRCCodec()
    #: Event loop the client is running on.
    loop = asyncio.get_event_loop()

    #: Generate a default configuration.  Easier to call this and update the
    #: result than relying on ``dict.copy()``.
    DEFAULTS = staticmethod(lambda: dict(
        nick='csbot',
        username=None,
        host='irc.freenode.net',
        port=6667,
        password=None,
    ))

    def __init__(self, *configs, **more_config):
        self.config = self.DEFAULTS()
        for config in configs:
            self.config.update(config)
        self.config.update(**more_config)

        self.transport = None
        self._buffer = b''
        self._exiting = False

        self.nick = None

    def connect(self):
        """Connect to the IRC server."""
        LOG.debug('connecting to {host}:{port}...'.format(**self.config))
        return asyncio.Task(self.loop.create_connection(
            lambda: self, self.config['host'], self.config['port']))

    def disconnect(self):
        """Disconnect from the IRC server.

        Use :meth:`quit` for a more graceful disconnect.
        """
        self._exiting = True
        if self.transport is not None:
            self.transport.close()

    def connection_made(self, transport):
        """Callback for successful connection.

        Register with the IRC server.
        """
        LOG.debug('connection made')
        self.transport = transport

        if self.config['password']:
            self.send_raw('PASS {}'.format(self.config['password']))

        nick = self.config['nick']
        username = self.config['username'] or nick
        self.set_nick(nick)
        self.send_raw('USER {} * * :{}'.format(username, nick))

    def connection_lost(self, exc):
        """Handle a broken connection by attempting to reconnect.

        Won't reconnect if the broken connection was deliberate (i.e.
        :meth:`close` was called).
        """
        LOG.debug('connection lost: %r', exc)
        self.transport = None
        if not self._exiting:
            self.loop.call_later(2, self.connect)

    def data_received(self, data):
        """Callback for received bytes."""
        data = self._buffer + data
        lines = data.split(b'\r\n')
        self._buffer = lines.pop()
        for line in lines:
            self.line_received(self.codec.decode(line))

    def line_received(self, line):
        """Callback for received raw IRC message."""
        msg = IRCMessage.parse(line)
        LOG.debug('>>> %s', msg.pretty)
        self.message_received(msg)

    def message_received(self, msg):
        """Callback for received parsed IRC message."""
        self._dispatch_method('irc_' + msg.command_name, msg)

    def send_raw(self, data):
        """Send a raw IRC message to the server.

        Encodes, terminates and sends *data* to the server.
        """
        LOG.debug('<<< %s', data)
        data = self.codec.encode(data) + b'\r\n'
        self.transport.write(data)

    def send(self, msg):
        """Send an :class:`IRCMessage`."""
        self.send_raw(msg.raw)

    # Specific commands for sending messages

    def set_nick(self, nick):
        """Ask the server to set our nick."""
        self.send_raw('NICK {}'.format(nick))
        self.nick = nick
        self.on_nick_changed(nick)

    def join(self, channel):
        """Join a channel."""
        self.send_raw('JOIN {}'.format(channel))

    def leave(self, channel, message=None):
        """Leave a channel, with an optional message."""
        self.send_raw('PART {} :{}'.format(channel, message or ''))

    def quit(self, message=None, reconnect=False):
        """Leave the server.

        If *reconnect* is False, then the client will not attempt to reconnect
        after the server closes the connection.
        """
        self._exiting = not reconnect
        self.send_raw('QUIT :{}'.format(message or ''))

    def msg(self, to, message):
        """Send *message* to a channel/nick."""
        self.send_raw('PRIVMSG {} :{}'.format(to, message))

    def act(self, to, action):
        """Send *action* as a CTCP ACTION to a channel/nick."""
        self.ctcp_query(to, 'ACTION', action)

    def notice(self, to, message):
        """Send *message* as a NOTICE to a channel/nick."""
        self.send_raw('NOTICE {} :{}'.format(to, message))

    def set_topic(self, channel, topic):
        """Try and set a channel's topic."""
        self.send_raw('TOPIC {} :{}'.format(channel, topic))

    def get_topic(self, channel):
        """Ask server to send the topic for *channel*.

        Will cause :meth:`on_topic_changed` at some point in the future.
        """
        self.send_raw('TOPIC {}'.format(channel))

    def ctcp_query(self, to, command, data=None):
        """Send CTCP query."""
        msg = command
        if data:
            msg += ' ' + data
        self.msg(to, '\x01' + msg + '\x01')

    def ctcp_reply(self, to, command, data=None):
        """Send CTCP reply."""
        msg = command
        if data:
            msg += ' ' + data
        self.notice(to, '\x01' + msg + '\x01')

    # Messages received from the server

    def irc_RPL_WELCOME(self, msg):
        """Received welcome from server, now we can start communicating.

        Welcome should include the accepted nick as the first parameter.  This
        may be different to the nick we requested (e.g. truncated to a maximum
        length); if this is the case we store the new nick and fire the
        :meth:`on_nick_changed` event.
        """
        nick = msg.params[0]
        if nick != self.nick:
            self.nick = nick
            self.on_nick_changed(self.nick)
        self.on_welcome()

    def irc_ERR_NICKNAMEINUSE(self, msg):
        """Attempted nick is in use, try another.

        Adds an underscore to the end of the current nick.  If the server
        truncated the nick, replaces the last non-underscore with an underscore.
        """
        _, nick = msg.params[:2]

        # If the failed nick doesn't match the one we tried, it was probably
        # truncated and just adding more characters will leave us stuck in a
        # loop.  To avoid this we start replacing non-underscores at the end of
        # the nick with underscores.
        if nick != self.nick:
            stripped = nick.rstrip('_')[:-1]
            new_nick = stripped + '_' * (len(nick) - len(stripped))
        else:
            new_nick = nick + '_'

        self.set_nick(new_nick)

    def irc_PING(self, msg):
        """IRC PING/PONG keepalive."""
        self.send_raw('PONG :{}'.format(msg.params[-1]))

    def irc_NICK(self, msg):
        """Somebody's nick changed."""
        user = IRCUser.parse(msg.prefix)
        new_nick = msg.params[-1]
        if user.nick == self.nick:
            self.nick = new_nick
            self.on_nick_changed(new_nick)
        else:
            self.on_user_renamed(user.nick, new_nick)

    def irc_JOIN(self, msg):
        """Somebody joined a channel."""
        user = IRCUser.parse(msg.prefix)
        channel = msg.params[0]
        if user.nick == self.nick:
            self.on_joined(channel)
        else:
            self.on_user_joined(user, channel)

    def irc_PART(self, msg):
        """Somebody left a channel."""
        user = IRCUser.parse(msg.prefix)
        channel, message = msg.pad_params(2)
        if user.nick == self.nick:
            self.on_left(channel)
        else:
            self.on_user_left(user, channel, message)

    def irc_KICK(self, msg):
        """Somebody was kicked from a channel."""
        user = IRCUser.parse(msg.prefix)
        channel, nick, reason = msg.pad_params(3)
        if nick == self.nick:
            self.on_kicked(channel, user, reason)
        else:
            self.on_user_kicked(IRCUser.parse(nick), channel, user, reason)

    def irc_QUIT(self, msg):
        """Somebody quit the server."""
        (message,) = msg.pad_params(1)
        self.on_user_quit(IRCUser.parse(msg.prefix), message)

    def irc_TOPIC(self, msg):
        """A channel's topic changed."""
        user = IRCUser.parse(msg.prefix)
        channel, new_topic = msg.pad_params(2)
        self.on_topic_changed(user, channel, new_topic)

    def irc_RPL_TOPIC(self, msg):
        """Topic notification, usually after joining a channel."""
        user = IRCUser.parse(msg.prefix)
        _, channel, topic = msg.pad_params(3)
        self.on_topic_changed(user, channel, topic)

    def irc_PRIVMSG(self, msg):
        """Received a ``PRIVMSG``.

        TODO: Implement CTCP queries.
        """
        user = IRCUser.parse(msg.prefix)
        channel, message = msg.params

        if message.startswith('\x01') and message.endswith('\x01'):
            command, _, data = message[1:-1].partition(' ')
            self._dispatch_method('on_ctcp_query_' + command,
                                  user, channel, data or None)

        self.on_privmsg(user, channel, message)

    def irc_NOTICE(self, msg):
        """Received a ``NOTICE``.

        TODO: Implement CTCP replies.
        """
        user = IRCUser.parse(msg.prefix)
        channel, message = msg.params

        if message.startswith('\x01') and message.endswith('\x01'):
            command, _, data = message[1:-1].partition(' ')
            self._dispatch_method('on_ctcp_reply_' + command,
                                  user, channel, data or None)

        self.on_notice(user, channel, message)

    # TODO: on_mode_changed

    # Events regarding self

    def on_welcome(self):
        """Successfully signed on to the server."""
        pass

    def on_nick_changed(self, nick):
        """Changed nick."""
        pass

    def on_joined(self, channel):
        """Joined a channel."""
        pass

    def on_left(self, channel):
        """Left a channel."""
        pass

    def on_kicked(self, channel, by, reason):
        """Kicked from a channel."""
        pass

    def on_privmsg(self, user, to, message):
        """Received a message, either directly or in a channel."""
        pass

    def on_notice(self, user, to, message):
        """Received a notice, either directly or in a channel."""
        pass

    def on_action(self, user, to, action):
        """Received CTCP ACTION.  Common enough to deserve its own event."""
        pass

    def on_ctcp_query_ACTION(self, user, to, data):
        """Turn CTCP ACTION into :meth:`on_action` event."""
        self.on_action(user, to, data)

    # Events regarding other users

    def on_user_renamed(self, oldnick, newnick):
        """User changed nick."""
        pass

    def on_user_joined(self, user, channel):
        """User joined a channel."""
        pass

    def on_user_left(self, user, channel, message):
        """User left a channel."""
        pass

    def on_user_kicked(self, user, channel, by, reason):
        """User kicked from a channel."""
        pass

    def on_user_quit(self, user, message):
        """User disconnected."""
        pass

    # Events regarding channels

    def on_topic_changed(self, user, channel, topic):
        """*user* changed the topic of *channel* to *topic*."""
        pass

    def _dispatch_method(self, method_name, *args, **kwargs):
        """Dispatch to *method* only if it exists."""
        method = getattr(self, method_name, None)
        if method is not None:
            method(*args, **kwargs)


def main():
    logging.basicConfig(format='[%(levelname).1s:%(name)s] %(message)s',
                        level=logging.DEBUG)
    logging.getLogger('asyncio').setLevel(logging.INFO)

    loop = asyncio.get_event_loop()

    bot = IRCClient(nick='csbot_py3')
    import types
    def on_welcome(self):
        self.join('#cs-york-dev')
        self.act('#cs-york-dev', 'arrives')
    bot.on_welcome = types.MethodType(on_welcome, bot)
    bot.connect()

    def stop():
        bot.disconnect()
        loop.stop()
    loop.add_signal_handler(signal.SIGINT, stop)

    loop.run_forever()
    loop.close()


if __name__ == '__main__':
    main()
