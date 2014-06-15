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
                            'prefix command params trailing command_name raw')):
    """Represents an IRC message.

    The IRC message format, paraphrased and simplified from RFC2812, is::

        message = [":" prefix " "] command {" " parameter} [" :" trailing]

    This is represented as a :class:`namedtuple` with the following attributes:

    :param prefix: Prefix part of the message, usually the origin
    :type prefix: str or None
    :param command: IRC command
    :type command: str
    :param params: List of command parameters
    :type params: list of str
    :param trailing: Trailing data
    :type trailing: str or None
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
            # Create command_name, which is either the RFC2812 name for a
            # numeric command, or just the received command.
            groups['command_name'] = NUMERIC_REPLIES.get(groups['command'],
                                                         groups['command'])
            return cls(**groups)

    @classmethod
    def create(cls, command, params=None, trailing=None, prefix=None):
        """Create an :class:`IRCMessage` from its core components.

        The *raw* and *command_name* attributes will be generated based on the
        message details.
        """
        args = {
            'prefix': prefix or None,
            'command': command,
            'params': params or [],
            'trailing': trailing or None,
            'command_name': NUMERIC_REPLIES.get(command, command),
            'raw': ''.join([
                (':' + prefix + ' ') if prefix else '',
                command,
                (' ' + ' '.join(params)) if params else '',
                (' :' + trailing) if trailing else '',
            ]),
        }
        return cls(**args)


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
    """
    #: Codec for encoding/decoding IRC messages.
    codec = IRCCodec()
    #: Event loop the client is running on.
    loop = asyncio.get_event_loop()

    #: Generate a default configuration.  Easier to call this and update the
    #: result than relying on ``dict.copy()``.
    DEFAULTS = staticmethod(lambda: dict(
        nick='csbot',
        host='irc.freenode.net',
        port=6667,
    ))

    def __init__(self, *configs, **more_config):
        self.config = dict(self.DEFAULTS(), *configs, **more_config)
        self.transport = None
        self._buffer = b''
        self._exiting = False

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
        """Callback for successful connection."""
        LOG.debug('connection made')
        self.transport = transport
        self.send_raw('USER {nick} * * :{nick}'.format(**self.config))
        self.send_raw('NICK {nick}'.format(**self.config))
        self.send_raw('JOIN #cs-york-dev')

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
        LOG.debug('data received: %s', data)
        data = self._buffer + data
        lines = data.split(b'\r\n')
        self._buffer = lines.pop()
        for line in lines:
            self.line_received(self.codec.decode(line))

    def line_received(self, line):
        """Callback for received raw IRC message."""
        LOG.debug('line received: %s', line)
        msg = IRCMessage.parse(line)
        LOG.debug('command parsed: %r', msg)
        self.message_received(msg)

    def message_received(self, msg):
        """Callback for received parsed IRC message."""
        method_name = 'irc_' + msg.command_name
        method = getattr(self, method_name, None)
        if method is not None:
            method(msg)

    def send_raw(self, data):
        """Send a raw IRC message to the server.

        Encodes, terminates and sends *data* to the server.
        """
        data = self.codec.encode(data) + b'\r\n'
        self.transport.write(data)
        LOG.debug('data sent: %s', data)

    def send(self, msg):
        """Send an :class:`IRCMessage`."""
        self.send_raw(msg.raw)

    def irc_PING(self, msg):
        """IRC PING/PONG keepalive."""
        self.send(IRCMessage.create('PONG', trailing=msg.trailing))


def main():
    logging.basicConfig(format='[%(levelname).1s:%(name)s] %(message)s',
                        level=logging.DEBUG)
    logging.getLogger('asyncio').setLevel(logging.INFO)

    loop = asyncio.get_event_loop()

    bot = IRCClient(nick='not_really_csbot')
    bot.connect()

    def stop():
        bot.disconnect()
        loop.stop()
    loop.add_signal_handler(signal.SIGINT, stop)

    loop.run_forever()
    loop.close()


if __name__ == '__main__':
    main()
