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


class IRCProtocol(asyncio.Protocol):
    """IRC streaming protocol.

    A line-oriented protocol for communicating with IRC servers.  Uses
    :class:`IRCCodec` to attempt to gloss over encoding issues,  Calls
    :meth:`IRCClient.line_received` on *client* when a full decoded line has
    been received, and the client should use :meth:`write_line` to send messages
    to the server.
    """
    def __init__(self, client):
        self.client = client
        self.buffer = b''
        self.codec = IRCCodec()
        self.transport = None
        self.exiting = False

    def connection_made(self, transport):
        """Callback for successful connection.

        Save the transport object for sending data later.
        """
        LOG.debug('connection made')
        self.transport = transport

    def data_received(self, data):
        """Callback for received data.

        Turn received data into a sequence of un-terminated, decoded strings,
        which are passed to the :class:`IRCClient`.
        """
        LOG.debug('data received: %s', data)
        data = self.buffer + data
        lines = data.split(b'\r\n')
        self.buffer = lines.pop()
        for line in lines:
            self.client.line_received(self.codec.decode(line))

    def write_line(self, data):
        """Send a message to the server.

        Encodes, terminates and sends *data* to the server.
        """
        data = self.codec.encode(data) + b'\r\n'
        self.transport.write(data)
        LOG.debug('data sent: %s', data)

    def connection_lost(self, exc):
        """Handle a broken connection by attempting to reconnect.

        Won't reconnect if the broken connection was deliberate (i.e.
        :meth:`close` was called).
        """
        self.transport = None
        if not self.exiting:
            self.client.loop.call_later(5, self.client.create_connection)
        LOG.debug('connection lost: %r', exc)

    def close(self):
        """Deliberately close the connection."""
        self.exiting = True
        if self.transport is not None:
            self.transport.close()


class IRCClient(object):
    nick = ['csbot_irc']
    realname = 'csbot'
    userinfo = 'https://github.com/HackSoc/csbot'
    host = 'irc.freenode.net'

    def __init__(self, config=None):
        self.loop = asyncio.get_event_loop()
        self.protocol = None

    def start(self, run_forever=True):
        LOG.info('starting bot')
        # Run bot setup()
        self.create_connection()
        self.loop.add_signal_handler(signal.SIGINT, self.stop)
        if run_forever:
            self.loop.run_forever()

    def stop(self):
        LOG.info('stopping bot')
        # Run bot teardown()
        self.protocol.close()
        self.loop.stop()

    def create_connection(self):
        create_protocol = lambda: IRCProtocol(self)
        t = asyncio.Task(self.loop.create_connection(create_protocol,
                                                     'chat.freenode.net',
                                                     6667))
        t.add_done_callback(self.connection_made)

    def connection_made(self, f):
        if self.protocol is not None:
            self.protocol.close()
            self.protocol = None

        # Get result of create_connection from Future
        transport, self.protocol = f.result()

        self.send_raw('USER csbot * * :csbot')
        self.send_raw('NICK not_really_csbot')
        self.send_raw('JOIN #cs-york-dev')

    def line_received(self, line):
        LOG.debug('line received: %s', line)
        msg = IRCMessage.parse(line)
        LOG.debug('command parsed: %r', msg)
        self.message_received(msg)

    def message_received(self, msg):
        method_name = 'irc_' + msg.command_name
        method = getattr(self, method_name, None)
        if method is not None:
            method(msg)

    def irc_PING(self, msg):
        self.send(IRCMessage.create('PONG', trailing=msg.trailing))

    def send(self, msg):
        self.send_raw(msg.raw)

    def send_raw(self, line):
        self.protocol.write_line(line)


def main():
    logging.basicConfig(format='[%(levelname).1s:%(name)s] %(message)s',
                        level=logging.DEBUG)
    logging.getLogger('asyncio').setLevel(logging.INFO)

    loop = asyncio.get_event_loop()
    bot = IRCClient()
    bot.start()
    loop.close()


if __name__ == '__main__':
    main()