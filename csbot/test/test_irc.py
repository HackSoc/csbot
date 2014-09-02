import unittest
from unittest import mock

from . import mock_client
from ..irc import *


class IRCClientTestCase(unittest.TestCase):
    CLIENT_CONFIG = {}

    def setUp(self):
        self.client = mock_client(IRCClient, self.CLIENT_CONFIG)

    def patch(self, attrs, create=False):
        """Shortcut for patching attribute(s) of the client."""
        if isinstance(attrs, str):
            return mock.patch.object(self.client, attrs, create=create)
        else:
            return mock.patch.multiple(self.client, create=create,
                                       **{k: mock.DEFAULT for k in attrs})

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
            self.client.reset_mock()

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


class TestIRCClientBehaviour(IRCClientTestCase):
    def test_auto_reconnect(self):
        with self.patch('connect') as m:
            self.client.connection_lost(None)
            m.assert_called_once_with()

    def test_disconnect(self):
        with self.patch('connect') as m:
            self.client.disconnect()
            self.assertFalse(m.called)

    def test_PING_PONG(self):
        self.connect()
        self.receive('PING :i.am.a.server')
        self.assert_sent('PONG :i.am.a.server')

    def test_RPL_WELCOME_nick_truncated(self):
        """IRC server might truncate the requested nick at sign-on, this should
        be reflected by the client's behaviour."""
        self.connect()
        with self.patch('on_nick_changed') as m:
            self.client.set_nick('foo_bar')
            self.assertEqual(self.client.nick, 'foo_bar')
            self.receive(':a.server 001 foo_b :Welcome to the server')
            self.assertEqual(self.client.nick, 'foo_b')
            # Check events were fired for both nick changes (the initial request
            # and the truncated nick)
            m.assert_has_calls([mock.call('foo_bar'), mock.call('foo_b')])

    def test_ERR_NICKNAMEINUSE(self):
        """If nick is in use, try another one."""
        self.connect()
        nick = self.client.nick
        new_nick = nick + '_'
        self.receive(':a.server 433 * {} :Nickname is already in use.'.format(nick))
        self.assert_sent('NICK {}'.format(new_nick))
        self.assertEqual(self.client.nick, new_nick)

    def test_ERR_NICKNAMEINUSE_truncated(self):
        """IRC server might truncate requested nicks, so we should use a
        different strategy to resolve nick collisions if that happened."""
        self.connect()
        self.client.set_nick('a_very_long_nick')
        self.receive(':a.server 433 * a_very_long_nick :Nickname is already in use.')
        # Should have triggered the same behaviour as above, appending _
        self.assertEqual(self.client.nick, 'a_very_long_nick_')
        # Except oops, server truncated it to the same in-use nick!
        self.receive(':a.server 433 * a_very_long_nick :Nickname is already in use.')
        # Next nick tried should be the same length with some _ replacements
        self.assertEqual(self.client.nick, 'a_very_long_nic_')
        # Not stateful, so if this in use it'll try append first
        self.receive(':a.server 433 * a_very_long_nic_ :Nickname is already in use.')
        self.assertEqual(self.client.nick, 'a_very_long_nic__')
        # But yet again, if that request got truncated, it'll replace a character
        self.receive(':a.server 433 * a_very_long_nic_ :Nickname is already in use.')
        self.assertEqual(self.client.nick, 'a_very_long_ni__')


class TestIRCClientEvents(IRCClientTestCase):
    """Test that particular methods are run as a consequence of messages."""
    TEST_ROUTING = [
        # Generic message routing to irc_COMMAND
        (':nick!user@host PRIVMSG #channel :hello',
         'irc_PRIVMSG', [IRCMessage.parse(':nick!user@host PRIVMSG #channel :hello')], {}),
        # Generic message routing for known numeric commands
        (':a.server 001 nick :Welcome to the server',
         'irc_RPL_WELCOME', [IRCMessage.parse(':a.server 001 nick :Welcome to the server')], {}),
        # Generic message routing for unknown numeric commands
        (':a.server 999 arg1 :trailing',
         'irc_999', [IRCMessage.parse(':a.server 999 arg1 :trailing')], {}),
        # Routing for CTCP queries
        (':nick!user@host PRIVMSG #channel :\x01FOO bar\x01',
         'on_ctcp_query_FOO', [IRCUser.parse('nick!user@host'), '#channel', 'bar'], {}),
        # Routing for CTCP replies
        (':nick!user@host NOTICE #channel :\x01FOO bar\x01',
         'on_ctcp_reply_FOO', [IRCUser.parse('nick!user@host'), '#channel', 'bar'], {}),
    ]

    def test_routing(self):
        """Run every routing test case."""
        self.connect()
        # Iterate over test cases
        for raw, method, args, kwargs in self.TEST_ROUTING:
            # Inform unittest which test case we're running
            with self.subTest(raw=raw, method=method):
                # Patch the expected method (creating it if necessary)
                with self.patch(method, create=True) as m:
                    # Handle the raw IRC message
                    self.receive(raw)
                    # Check for the call
                    m.assert_called_once_with(*args, **kwargs)

    ME = IRCUser.parse('csbot!bot@robot.land')
    USER = IRCUser.parse('nick!person@their.server')
    #: Some common test parameters for substituting in test cases
    VALUES = {
        'me': ME,
        'user': USER,
    }

    TEST_EVENTS = [
        # Welcome/signed on
        (':a.server 001 {me.nick} :Welcome to the server', 'on_welcome', [], {}),
        # Our nick changed by the server
        (':{me.raw} NICK :csbot2', 'on_nick_changed', ['csbot2'], {}),
        # (Change our nick back for the rest of the tests)
        (':csbot2!user@host NICK :{me.nick}', 'on_nick_changed', [ME.nick], {}),
        # Somebody else's nick changed
        (':{user.raw} NICK :nick2', 'on_user_renamed', [USER.nick, 'nick2'], {}),
        # We joined a channel
        (':{me.raw} JOIN #channel', 'on_joined', ['#channel'], {}),
        # Somebody else joined a channel
        (':{user.raw} JOIN #channel', 'on_user_joined', [USER, '#channel'], {}),
        # We left a channel
        (':{me.raw} PART #channel :"goodbye"', 'on_left', ['#channel'], {}),
        # Somebody else left a channel
        (':{user.raw} PART #channel :"goodbye"', 'on_user_left', [USER, '#channel', '"goodbye"'], {}),
        (':{user.raw} PART #channel', 'on_user_left', [USER, '#channel', None], {}),
        # We were kicked from a channel
        (':{user.raw} KICK #channel {me.nick} :reason', 'on_kicked', ['#channel', USER, 'reason'], {}),
        (':{user.raw} KICK #channel {me.nick}', 'on_kicked', ['#channel', USER, None], {}),
        # Somebody else was kicked from a channel
        (':{user.raw} KICK #channel somebody :reason',
         'on_user_kicked', [IRCUser.parse('somebody'), '#channel', USER, 'reason'], {}),
        (':{user.raw} KICK #channel somebody',
         'on_user_kicked', [IRCUser.parse('somebody'), '#channel', USER, None], {}),
        # Somebody quit the server
        (':{user.raw} QUIT :goodbye', 'on_user_quit', [USER, 'goodbye'], {}),
        (':{user.raw} QUIT', 'on_user_quit', [USER, None], {}),
        # Received a message
        (':{user.raw} PRIVMSG #channel :hello', 'on_privmsg', [USER, '#channel', 'hello'], {}),
        # Received a notice
        (':{user.raw} NOTICE #channel :hello', 'on_notice', [USER, '#channel', 'hello'], {}),
        # Received an action
        (':{user.raw} PRIVMSG #channel :\x01ACTION bounces\x01',
         'on_action', [USER, '#channel', 'bounces'], {}),
        # Channel topic reported after JOIN
        (':a.server 332 {me.nick} #channel :channel topic',
         'on_topic_changed', [IRCUser.parse('a.server'), '#channel', 'channel topic'], {}),
        # Channel topic changed
        (':{user.raw} TOPIC #channel :new topic',
         'on_topic_changed', [USER, '#channel', 'new topic'], {}),
        # Channel topic unset
        (':{user.raw} TOPIC #channel',
         'on_topic_changed', [USER, '#channel', None], {}),
    ]

    def test_events(self):
        """Run every event test case."""
        self.connect()
        # Iterate over test cases
        for raw, method, args, kwargs in self.TEST_EVENTS:
            # Perform substitutions
            raw = raw.format(**self.VALUES)
            # Inform unittest which test case we're running
            with self.subTest(raw=raw, method=method):
                # Patch the expected method
                with self.patch(method) as m:
                    # Handle the raw IRC message
                    self.receive(raw)
                    # Check for the call
                    m.assert_called_once_with(*args, **kwargs)


class TestIRCClientCommands(IRCClientTestCase):
    """Test that calling various commands causes the appropriate messages to be
    sent to the server."""
    def setUp(self):
        super().setUp()
        # All of these tests send things, so connect the mock transport
        self.client.connect()

    def test_set_nick(self):
        with self.patch('on_nick_changed') as m:
            self.client.set_nick('new_nick')
            self.assert_sent('NICK new_nick')
            self.assertEqual(self.client.nick, 'new_nick')
            m.assert_called_once_with('new_nick')

    def test_join(self):
        self.client.join('#foo')
        self.assert_sent('JOIN #foo')

    def test_leave(self):
        self.client.leave('#foo')
        self.assert_sent('PART #foo :')
        self.client.leave('#foo', 'just because')
        self.assert_sent('PART #foo :just because')

    def test_quit(self):
        self.client.quit()
        self.assert_sent('QUIT :')
        self.client.quit('reason')
        self.assert_sent('QUIT :reason')

    def test_quit_no_reconnect(self):
        with self.patch('connect') as m:
            self.client.quit(reconnect=False)
            self.client.connection_lost(None)
            self.assertFalse(m.called)

    def test_quit_reconnect(self):
        with self.patch('connect') as m:
            self.client.quit(reconnect=True)
            self.client.connection_lost(None)
            self.assertTrue(m.called)

    def test_msg(self):
        self.client.msg('#channel', 'a message')
        self.assert_sent('PRIVMSG #channel :a message')
        self.client.msg('a_nick', 'another message')
        self.assert_sent('PRIVMSG a_nick :another message')

    def test_act(self):
        self.client.act('#channel', 'bounces')
        self.assert_sent('PRIVMSG #channel :\x01ACTION bounces\x01')

    def test_notice(self):
        self.client.notice('#channel', 'a notice')
        self.assert_sent('NOTICE #channel :a notice')

    def test_set_topic(self):
        self.client.set_topic('#channel', 'new topic')
        self.assert_sent('TOPIC #channel :new topic')
        self.client.set_topic('#channel', '')
        self.assert_sent('TOPIC #channel :')

    def test_get_topic(self):
        self.client.get_topic('#channel')
        self.assert_sent('TOPIC #channel')

    def test_ctcp_query(self):
        self.client.ctcp_query('#channel', 'VERSION')
        self.assert_sent('PRIVMSG #channel :\x01VERSION\x01')
        self.client.ctcp_query('a_nick', 'FOO', 'bar')
        self.assert_sent('PRIVMSG a_nick :\x01FOO bar\x01')

    def test_ctcp_reply(self):
        self.client.ctcp_reply('a_nick', 'PONG')
        self.assert_sent('NOTICE a_nick :\x01PONG\x01')
        self.client.ctcp_reply('a_nick', 'VERSION', '1.0')
        self.assert_sent('NOTICE a_nick :\x01VERSION 1.0\x01')


class TestIRCMessage(unittest.TestCase):
    def test_PING(self):
        """Parse a simple message."""
        m = IRCMessage.parse('PING :i.am.a.server')
        self.assertEqual(m.raw, 'PING :i.am.a.server')
        self.assertEqual(m.prefix, None)
        self.assertEqual(m.command, 'PING')
        self.assertEqual(m.command_name, 'PING')
        self.assertEqual(m.params, ['i.am.a.server'])

    def test_RPL_WELCOME(self):
        """Parse a more complex command, which also involves a numeric reply."""
        m = IRCMessage.parse(':a.server 001 nick :Welcome to the server')
        self.assertEqual(m.prefix, 'a.server')
        self.assertEqual(m.command, '001')
        self.assertEqual(m.command_name, 'RPL_WELCOME')
        self.assertEqual(m.params, ['nick', 'Welcome to the server'])
