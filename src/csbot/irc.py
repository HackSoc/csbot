import asyncio
import logging
import signal
import re
import codecs
import base64
import types
from typing import (
    Any,
    Awaitable,
    Callable,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
)

import attr

from ._rfc import NUMERIC_REPLIES
from . import util


LOG = logging.getLogger('csbot.irc')


class IRCParseError(Exception):
    """Raised by :meth:`IRCMessage.parse` when a message can't be parsed."""


@attr.s(frozen=True, slots=True)
class IRCMessage:
    """Represents an IRC message.

    The IRC message format, paraphrased and simplified from RFC2812, is::

        message = [":" prefix " "] command {" " parameter} [" :" trailing]

    Has the following attributes:

    :param raw: The raw IRC message
    :type raw: str
    :param prefix: Prefix part of the message, usually the origin
    :type prefix: str or None
    :param command: IRC command
    :type command: str
    :param params: List of command parameters (including trailing)
    :type params: list of str
    :param command_name: Name of IRC command (see below)
    :type command_name: str

    The *command_name* attribute is intended to be the "readable" form of the
    *command*.  Usually it will be the same as *command*, but numeric replies
    recognised in RFC2812 will have their corresponding name instead.
    """
    raw: str = attr.ib(validator=util.type_validator)
    prefix: Optional[str] = attr.ib(validator=util.type_validator)
    command: str = attr.ib(validator=util.type_validator)
    params: List[str] = attr.ib(validator=attr.validators.deep_iterable(attr.validators.instance_of(str), None))
    command_name: str = attr.ib(validator=util.type_validator)

    #: Regular expression to extract message components from a message.
    REGEX = re.compile(r'(:(?P<prefix>\S+) )?(?P<command>\S+)'
                       r'(?P<params>( (?!:)\S+)*)( :(?P<trailing>.*))?')
    #: Commands to force trailing parameter (``:blah``) for
    FORCE_TRAILING = {'USER', 'QUIT', 'PRIVMSG'}

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
                cls._raw_params(params or [], command in cls.FORCE_TRAILING),
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
            self._raw_params(self.params, self.command in self.FORCE_TRAILING),
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
    def _raw_params(params, force_trailing):
        if len(params) > 0 and (force_trailing or ' ' in params[-1]):
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


@attr.s(frozen=True, slots=True)
class IRCUser:
    """Provide access to the parts of an IRC user string.

    The following parts of the user string are available, set to *None* if that
    part of the string is absent:

    :param raw: Raw user string
    :param nick: Nick of the user
    :param user: Username of the user (excluding leading ``~``)
    :param host: Hostname of the user

    >>> IRCUser.parse('my_nick!some_user@host.name')
    IRCUser(raw='my_nick!some_user@host.name', nick='my_nick', user='some_user', host='host.name')
    """
    raw: str = attr.ib(validator=util.type_validator)
    nick: str = attr.ib(validator=util.type_validator)
    user: Optional[str] = attr.ib(validator=util.type_validator)
    host: Optional[str] = attr.ib(validator=util.type_validator)

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
            return codecs.decode(input, 'cp1252', 'replace')


class IRCClientError(Exception):
    pass


class IRCClient:
    """Internet Relay Chat client protocol.

    A line-oriented protocol for communicating with IRC servers.  It handles
    receiving data at several layers of abstraction:

    * :meth:`line_received`: decoded line
    * :meth:`message_received`: parsed :class:`IRCMessage`
    * ``irc_<COMMAND>(msg)``: called when ``msg.command == '<COMMAND>'``
    * ``on_<event>(...)``: specific events with specific arguments,
      e.g. ``on_quit(user, message)``

    It also handles sending data at several layers of abstraction:

    * :meth:`send_line`: raw IRC command, e.g. ``self.send_line('JOIN #cs-york-dev')``
    * :meth:`send`: :class:`IRCMessage`, e.g.
      ``self.send(IRCMessage.create('JOIN', params=['#cs-york-dev']))``
    * ``<action>(...)``: e.g. ``self.join('#cs-york-dev')``.

    The API and implementation is inspired by irc3_ and Twisted_.

    .. _irc3: https://github.com/gawel/irc3
    .. _Twisted: http://twistedmatrix.com/documents/14.0.0/api/twisted.words.protocols.irc.IRCClient.html

    * TODO: NAMES
    * TODO: MODE
    * TODO: More sophisticated CTCP? (see Twisted_)
    * TODO: MOTD?
    * TODO: SSL
    """
    #: Codec for encoding/decoding IRC messages.
    codec = IRCCodec()

    #: Generate a default configuration.  Easier to call this and update the
    #: result than relying on ``dict.copy()``.
    DEFAULTS = staticmethod(lambda: dict(
        ircv3=False,
        nick='csbot',
        username=None,
        host='irc.freenode.net',
        port=6667,
        password=None,
        auth_method='pass',
        bind_addr=None,
        client_ping_enabled=False,
        client_ping_interval=60,
        rate_limit_enabled=False,
        rate_limit_period=5,
        rate_limit_count=5,
    ))

    #: Available client capabilities
    available_capabilities: Set[str]
    #: Enabled client capabilities
    enabled_capabilities: Set[str]

    def __init__(self, *, loop=None, **kwargs):
        self.loop = loop or asyncio.get_event_loop()

        self.__config = self.DEFAULTS()
        self.__config.update(**kwargs)

        self.reader, self.writer = None, None
        self._exiting = False
        self.connected = asyncio.Event(loop=self.loop)
        self.connected.clear()
        self.disconnected = asyncio.Event(loop=self.loop)
        self.disconnected.set()
        self._last_message_received = self.loop.time()
        self._client_ping = None
        self._client_ping_counter = 0
        if self.__config['rate_limit_enabled']:
            self._send_line = util.RateLimited(self._send_line,
                                               period=self.__config['rate_limit_period'],
                                               count=self.__config['rate_limit_count'],
                                               loop=self.loop,
                                               log=LOG)

        self._message_waiters = set()

        self.nick = self.__config['nick']
        self.available_capabilities = set()
        self.enabled_capabilities = set()

    async def run(self, run_once=False):
        """Run the bot, reconnecting when the connection is lost."""
        self._exiting = run_once
        while True:
            await self.connect()
            self.connected.set()
            self.disconnected.clear()
            # Need to start read_loop() first so that connection_made() can await messages
            read_loop_fut = self.loop.create_task(self.read_loop())
            await self.connection_made()
            await read_loop_fut
            await self.connection_lost(self.reader.exception())
            self.connected.clear()
            self.disconnected.set()
            if self._exiting:
                break

    async def connect(self):
        """Connect to the IRC server."""
        LOG.debug('connecting to {host}:{port}...'.format(**self.__config))

        # Optionally bind to specific local address
        local_addr = None
        bind = self.__config['bind_addr']
        if bind is not None:
            local_addr = (bind, None)

        self.reader, self.writer = await asyncio.open_connection(self.__config['host'],
                                                                 self.__config['port'],
                                                                 loop=self.loop,
                                                                 local_addr=local_addr)

    def disconnect(self):
        """Disconnect from the IRC server.

        Use :meth:`quit` for a more graceful disconnect.
        """
        self._exiting = True
        if self.writer is None:
            LOG.warning("disconnect() when not connected")
        else:
            self.writer.close()

    async def read_loop(self):
        """Read and dispatch lines until the connection closes."""
        while True:
            try:
                line = await self.reader.readline()
                if not line.endswith(b'\r\n'):
                    break
            except ConnectionError:
                break
            self.line_received(self.codec.decode(line[:-2]))

    async def connection_made(self):
        """Callback for successful connection.

        Register with the IRC server.
        """
        LOG.debug('connection made')
        if self.__config['rate_limit_enabled']:
            self._send_line.start()

        nick = self.__config['nick']
        username = self.__config['username'] or nick
        user_msg = IRCMessage.create('USER', [username, '*', '*', nick])
        password = self.__config['password']
        auth_method = self.__config['auth_method']

        if self.__config['ircv3']:
            # Discover available capabilities
            self.send(IRCMessage.create('CAP', ['LS']))
            await self.wait_for_message(lambda m: (m.command == 'CAP' and m.params[1] == 'LS', m))

        if auth_method == 'pass':
            if password:
                self.send(IRCMessage.create('PASS', [password]))
            self.set_nick(nick)
            self.send(user_msg)
        elif auth_method == 'sasl_plain':
            sasl_enabled = await self.request_capabilities(enable={'sasl'})
            self.set_nick(nick)
            self.send(user_msg)
            if sasl_enabled:
                self.send(IRCMessage.create('AUTHENTICATE', ['PLAIN']))
                # SASL PLAIN authentication message (https://tools.ietf.org/html/rfc4616)
                # (assuming authzid = authcid = nick)
                sasl_plain = '{}\0{}\0{}'.format(nick, nick, password)
                # Well this is awkward... password string encoded to bytes as utf-8,
                # base64-encoded to different bytes, converted back to string for
                # use in the IRCMessage (which later encodes it as utf-8...)
                sasl_plain_b64 = base64.b64encode(sasl_plain.encode('utf-8')).decode('ascii')
                self.send(IRCMessage.create('AUTHENTICATE', [sasl_plain_b64]))
                sasl_success = await self.wait_for_message(lambda m: (m.command in ('903', '904'), m.command == '903'))
                if not sasl_success:
                    LOG.error('SASL authentication failed')
            else:
                LOG.error('could not enable "sasl" capability, skipping authentication')
        else:
            raise ValueError('unknown auth_method: {}'.format(auth_method))

        if self.__config['ircv3']:
            self.send(IRCMessage.create('CAP', ['END']))

        self._start_client_pings()

    async def connection_lost(self, exc):
        """Handle a broken connection by attempting to reconnect.

        Won't reconnect if the broken connection was deliberate (i.e.
        :meth:`close` was called).
        """
        LOG.debug('connection lost: %r', exc)
        if self.__config['rate_limit_enabled']:
            cancelled = self._send_line.stop()
            if cancelled:
                LOG.warning(f"{len(cancelled)} outgoing message(s) discarded")
        self.reader, self.writer = None, None
        self._stop_client_pings()

    def line_received(self, line: str):
        """Callback for received raw IRC message."""
        self._last_message_received = self.loop.time()
        msg = IRCMessage.parse(line)
        LOG.debug('>>> %s', msg.pretty)
        self.message_received(msg)

    def line_sent(self, line: str):
        """Callback for sent raw IRC message.

        Subclasses can implement this to get access to the actual message that was sent (which may
        have been truncated from what was passed to :meth:`send_line`).
        """
        LOG.debug('<<< %s', line)

    def message_received(self, msg):
        """Callback for received parsed IRC message."""
        self.process_wait_for_message(msg)
        self._dispatch_method('irc_' + msg.command_name, msg)

    def send_line(self, data: str):
        """Send a raw IRC message to the server.

        Encodes, terminates and sends *data* to the server. If the line would be longer than the
        maximum allowed by the IRC specification, it is trimmed to fit (without breaking UTF-8
        sequences).

        If rate limiting is enabled, the message may not be sent immediately.
        """
        encoded = self.codec.encode(data)
        trimmed = util.truncate_utf8(encoded, 510)  # RFC line length is 512 including \r\n
        if len(trimmed) < len(encoded):
            LOG.warning(f"outgoing message trimmed from {len(encoded)} to {len(trimmed)} bytes")
        self._send_line(trimmed)

    def _send_line(self, data: bytes):
        """Actually send the message to the server."""
        self.writer.write(data + b"\r\n")
        self.line_sent(self.codec.decode(data))

    def send(self, msg):
        """Send an :class:`IRCMessage`."""
        self.send_line(msg.raw)

    def _start_client_pings(self):
        self._stop_client_pings()

        if not self.__config['client_ping_enabled']:
            return

        interval = self.__config['client_ping_interval']
        self._client_ping = asyncio.ensure_future(self._send_client_pings(interval), loop=self.loop)

    def _stop_client_pings(self):
        if self._client_ping is not None:
            self._client_ping.cancel()
            self._client_ping = None

    async def _send_client_pings(self, interval):
        """Send a client ``PING`` if no messages have been received for *interval* seconds."""
        self._client_ping_counter = 0
        delay = interval
        while True:
            await asyncio.sleep(delay)
            now = self.loop.time()
            remaining = self._last_message_received + interval - now

            if remaining <= 0:
                # Send the PING
                self._client_ping_counter += 1
                self.send_line(f'PING {self._client_ping_counter}')
                # Wait for another interval
                delay = interval
            else:
                # Wait until interval has elapsed since last message
                delay = remaining

    class Waiter:
        PredicateType = Callable[[IRCMessage], Tuple[bool, Any]]

        def __init__(self, predicate: PredicateType, future: asyncio.Future):
            self.predicate = predicate
            self.future = future

    def wait_for_message(self, predicate: Waiter.PredicateType) -> asyncio.Future:
        """Wait for a message that matches *predicate*.

        *predicate* should return a `(did_match, result)` tuple, where *did_match* is a boolean
        indicating if the message is a match, and *result* is the value to return.

        Returns a future that is resolved with *result* on the first matching message.
        """
        waiter = self.Waiter(predicate, self.loop.create_future())
        self._message_waiters.add(waiter)
        return waiter.future

    def process_wait_for_message(self, msg):
        done = set()
        for w in self._message_waiters:
            if not w.future.done():
                matched, result = False, None
                try:
                    matched, result = w.predicate(msg)
                except Exception as e:
                    w.future.set_exception(e)
                if matched:
                    w.future.set_result(result)
            if w.future.done():
                done.add(w)
        self._message_waiters.difference_update(done)

    # Specific commands for sending messages

    def request_capabilities(self, *, enable: Iterable[str] = None, disable: Iterable[str] = None) -> Awaitable[bool]:
        """Request a change to the enabled IRCv3 capabilities.

        *enable* and *disable* are sets of capability names, with *disable* taking precedence.

        Returns a future which resolves with True if the request is successful, or False otherwise.
        """
        if not self.__config['ircv3']:
            raise IRCClientError('configured with ircv3=False, cannot use capability negotiation')

        enable_set = set(enable or ())
        disable_set = set(disable or ())
        enable_set.difference_update(disable_set)
        unknown = enable_set.union(disable_set).difference(self.available_capabilities)
        if unknown:
            LOG.warning('attempting to request unknown capabilities: %r', unknown)

        request = ' '.join(sorted(enable_set) + [f'-{c}' for c in sorted(disable_set)])
        if len(request) == 0:
            LOG.warning('no capabilities requested, not sending CAP REQ')
            fut = self.loop.create_future()
            fut.set_result(True)
            return fut
        else:
            message = IRCMessage.create('CAP', ['REQ', request])
            self.send(message)
            return self._wait_for_capability_response(request)

    def _wait_for_capability_response(self, request):
        def predicate(msg):
            if msg.command == 'CAP':
                _, subcommand, response = msg.params
                response = response.strip()
                if subcommand == 'ACK' and response == request:
                    return True, True
                elif subcommand == 'NAK' and response == request:
                    return True, False
            return False, None
        return self.wait_for_message(predicate)

    def set_nick(self, nick):
        """Ask the server to set our nick."""
        self.send_line('NICK {}'.format(nick))
        self.nick = nick
        self.on_nick_changed(nick)

    def join(self, channel):
        """Join a channel."""
        self.send_line('JOIN {}'.format(channel))

    def leave(self, channel, message=None):
        """Leave a channel, with an optional message."""
        self.send_line('PART {} :{}'.format(channel, message or ''))

    def quit(self, message=None, reconnect=False):
        """Leave the server.

        If *reconnect* is False, then the client will not attempt to reconnect
        after the server closes the connection.
        """
        self._exiting = not reconnect
        self.send_line('QUIT :{}'.format(message or ''))

    def msg(self, to, message):
        """Send *message* to a channel/nick."""
        self.send_line('PRIVMSG {} :{}'.format(to, message))

    def act(self, to, action):
        """Send *action* as a CTCP ACTION to a channel/nick."""
        self.ctcp_query(to, 'ACTION', action)

    def notice(self, to, message):
        """Send *message* as a NOTICE to a channel/nick."""
        self.send_line('NOTICE {} :{}'.format(to, message))

    def set_topic(self, channel, topic):
        """Try and set a channel's topic."""
        self.send_line('TOPIC {} :{}'.format(channel, topic))

    def get_topic(self, channel):
        """Ask server to send the topic for *channel*.

        Will cause :meth:`on_topic_changed` at some point in the future.
        """
        self.send_line('TOPIC {}'.format(channel))

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
        self.send_line('PONG :{}'.format(msg.params[-1]))

    def irc_CAP(self, msg):
        """Dispatch ``CAP`` subcommands to their own methods."""
        self._dispatch_method('irc_{}_{}'.format(msg.command_name, msg.params[1]), msg)

    def irc_CAP_LS(self, msg):
        """Response to ``CAP LS``, giving list of available capabilities."""
        _, _, data = msg.params
        data = data.split()
        self.available_capabilities = set(data)
        self.on_capabilities_available(self.available_capabilities)

    def irc_CAP_ACK(self, msg):
        """Response to ``CAP REQ``, acknowledging capability changes."""
        _, _, data = msg.params
        data = data.split()
        for name in data:
            if name.startswith('-'):
                name = name[1:]
                try:
                    self.enabled_capabilities.remove(name)
                except KeyError:
                    pass
                self.on_capability_disabled(name)
            else:
                self.enabled_capabilities.add(name)
                self.on_capability_enabled(name)

    def irc_CAP_NAK(self, msg):
        """Response to ``CAP REQ``, rejecting capability changes."""
        _, _, data = msg.params
        data = data.split()
        LOG.error('Client capability change(s) rejected: {}'.format(data))

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

    def on_capabilities_available(self, capabilities):
        """Client capabilities are available.

        Called with a set of client capability names when we get a response to
        ``CAP LS``.
        """
        LOG.debug('capabilities available: {}'.format(capabilities))
        pass

    def on_capability_enabled(self, name):
        """Client capability enabled.

        Called when enabling client capability *name* has been acknowledged.
        """
        LOG.debug('capability enabled: {}'.format(name))
        pass

    def on_capability_disabled(self, name):
        """Client capability disabled.

        Called when disabling client capability *name* has been acknowledged.
        """
        LOG.debug('capability disabled: {}'.format(name))
        pass

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


def main():  # pragma: no cover
    logging.basicConfig(format='[%(levelname).1s:%(name)s] %(message)s',
                        level=logging.DEBUG)
    logging.getLogger('asyncio').setLevel(logging.INFO)

    loop = asyncio.get_event_loop()

    bot = IRCClient(nick='csbot_py3')

    def on_welcome(self):
        self.join('#cs-york-dev')
        self.act('#cs-york-dev', 'arrives')
    bot.on_welcome = types.MethodType(on_welcome, bot)

    def stop():
        bot.disconnect()
        # Give the client a chance to exit cleanly before forcing a stop
        loop.call_soon(loop.stop)
    loop.add_signal_handler(signal.SIGINT, stop)

    loop.run_until_complete(bot.run())
    loop.close()


if __name__ == '__main__':  # pragma: no cover
    main()
