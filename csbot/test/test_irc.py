import unittest
from unittest import mock

from ..irc import *


class IRCClientMock(IRCClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.send_raw = mock.Mock(wraps=self.send_raw)

    def connect(self):
        self.connection_made(mock.Mock())


class IRCClientTestCase(unittest.TestCase):
    CLIENT_CONFIG = {}

    def setUp(self):
        self.client = IRCClientMock(self.CLIENT_CONFIG)

    def patch(self, attrs):
        """Shortcut for patching attribute(s) of the client."""
        if isinstance(attrs, str):
            return mock.patch.object(self.client, attrs)
        else:
            return mock.patch.multiple(self.client, **{k: mock.DEFAULT for k in attrs})

    def receive_bytes(self, bytes):
        """Shortcut for pushing received data to the client."""
        self.client.data_received(bytes)

    def assert_bytes_sent(self, bytes):
        """Check the raw bytes that have been sent via the transport.

        Compares *bytes* to the collection of everything sent to
        ``transport.write(...)``.  Resets the mock so the next call will not
        contain what was checked by this call.
        """
        sent = b''.join(args[0] for args, _ in self.client.transport.write.call_args_list)
        self.assertEqual(sent, bytes)
        self.client.transport.write.reset_mock()

    def receive(self, lines):
        """Shortcut to push a series of lines to the client."""
        if isinstance(lines, str):
            lines = [lines]
        for l in lines:
            self.client.line_received(l)

    def assert_sent(self, lines):
        """Check that a list of (unicode) strings have been sent.

        Resets the mock so the next call will not contain what was checked by
        this call.
        """
        if isinstance(lines, str):
            lines = [lines]
        self.client.send_raw.assert_has_calls([mock.call(l) for l in lines])
        self.client.send_raw.reset_mock()

    def connect(self, silent=True):
        """Make the client "connect" to a fake transport, optionally removing
        traces of the on-connect messages."""
        self.client.connect()
        if silent:
            self.client.transport.write.reset_mock()
            self.client.send_raw.reset_mock()


class TestIRCClientLineProtocol(IRCClientTestCase):
    def test_buffer(self):
        """Check that incoming data is converted to a line-oriented protocol."""
        with self.patch('line_received') as m:
            self.receive_bytes(b':nick!user@host PRIVMSG')
            self.assertFalse(m.called)
            self.receive_bytes(b' #channel :hello\r\nPING')
            m.assert_has_calls([
                mock.call(':nick!user@host PRIVMSG #channel :hello'),
            ])
            self.receive_bytes(b' :server.name\r\n')
            m.assert_has_calls([
                mock.call(':nick!user@host PRIVMSG #channel :hello'),
                mock.call('PING :server.name'),
            ])
            self.receive_bytes(b':nick!user@host JOIN #foo\r\n'
                               b':nick!user@host JOIN #bar\r\n')
            m.assert_has_calls([
                mock.call(':nick!user@host PRIVMSG #channel :hello'),
                mock.call('PING :server.name'),
                mock.call(':nick!user@host JOIN #foo'),
                mock.call(':nick!user@host JOIN #bar'),
            ])

    def test_decode_ascii(self):
        """Check that plain ASCII ends up as a (unicode) string."""
        with self.patch('line_received') as m:
            self.receive_bytes(b':nick!user@host PRIVMSG #channel :hello\r\n')
            m.assert_called_once_with(':nick!user@host PRIVMSG #channel :hello')

    def test_decode_utf8(self):
        """Check that incoming UTF-8 is properly decoded."""
        with self.patch('line_received') as m:
            self.receive_bytes(b':nick!user@host PRIVMSG #channel :\xe0\xb2\xa0\r\n')
            m.assert_called_once_with(':nick!user@host PRIVMSG #channel :ಠ')

    def test_decode_cp1252(self):
        """Check that incoming CP1252 is properly decoded.

        This tests a CP1252 sequences which is definitely illegal in UTF-8, to
        check that the fallback decoding works.
        """
        with self.patch('line_received') as m:
            self.receive_bytes(b':nick!user@host PRIVMSG #channel :\x93\x94\r\n')
            m.assert_called_once_with(':nick!user@host PRIVMSG #channel :“”')

    def test_encode(self):
        """Check that outgoing data is encoded as UTF-8."""
        self.connect()
        self.client.send_raw('PRIVMSG #channel :ಠ_ಠ')
        self.assert_bytes_sent(b'PRIVMSG #channel :\xe0\xb2\xa0_\xe0\xb2\xa0\r\n')


class TestIRCClientAutoRespond(IRCClientTestCase):
    def test_PING_PONG(self):
        self.connect()
        self.receive('PING :i.am.a.server')
        self.assert_sent('PONG :i.am.a.server')

    def test_ERR_NICKNAMEINUSE(self):
        self.connect()
        nick = self.client.nick
        new_nick = nick + '_'
        self.receive(':a.server 433 * {} :Nickname is already in use.'.format(nick))
        self.assert_sent('NICK {}'.format(new_nick))
        self.assertEqual(self.client.nick, new_nick)


class TestIRCClientEvents(IRCClientTestCase):
    """Test that particular methods are run as a consequence of messages."""
    def test_message_routing(self):
        """Test that a message gets routed to ``irc_COMMAND``."""
        with self.patch('irc_PRIVMSG') as m:
            msg = ':nick!user@host PRIVMSG #channel :hello'
            self.receive(msg)
            m.assert_called_once_with(IRCMessage.parse(msg))

    def test_message_routing_numeric(self):
        """Test that a message with a numeric comamnd gets routed correctly."""
        with self.patch('irc_RPL_WELCOME') as m:
            msg = ':a.server 001 nick :Welcome to the server'
            self.receive(msg)
            m.assert_called_once_with(IRCMessage.parse(msg))

    TEST_EVENTS = [
        (':nick!user@host PRIVMSG #channel :hello',
         'on_privmsg', [IRCUser.parse('nick!user@host'), '#channel', 'hello'], {}),
        (':csbot!user@host NICK :csbot2', 'on_nick_changed', ['csbot2'], {}),
        (':nick!user@host NICK :nick2', 'on_user_renamed', ['nick', 'nick2'], {}),
    ]

    def test_all_events(self):
        """Run every event test case."""
        self.connect()
        # Iterate over test cases
        for raw, method, args, kwargs in self.TEST_EVENTS:
            # Inform unittest which test case we're running
            with self.subTest(raw=raw, method=method):
                # Patch the expected method
                with self.patch(method) as m:
                    # Handle the raw IRC message
                    self.receive(raw)
                    # Check for the call
                    m.assert_called_once_with(*args, **kwargs)


class TestIRCMessage(unittest.TestCase):
    def test_PING(self):
        """Parse a simple message."""
        m = IRCMessage.parse('PING :i.am.a.server')
        self.assertEqual(m.raw, 'PING :i.am.a.server')
        self.assertEqual(m.prefix, None)
        self.assertEqual(m.command, 'PING')
        self.assertEqual(m.command_name, 'PING')
        self.assertEqual(m.params, [])
        self.assertEqual(m.trailing, 'i.am.a.server')

    def test_RPL_WELCOME(self):
        """Parse a more complex command, which also involves a numeric reply."""
        m = IRCMessage.parse(':a.server 001 nick :Welcome to the server')
        self.assertEqual(m.prefix, 'a.server')
        self.assertEqual(m.command, '001')
        self.assertEqual(m.command_name, 'RPL_WELCOME')
        self.assertEqual(m.params, ['nick'])
        self.assertEqual(m.trailing, 'Welcome to the server')
