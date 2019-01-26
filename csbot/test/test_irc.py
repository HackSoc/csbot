from unittest import mock

import pytest

from csbot.irc import *


# Test IRC client line protocol

@pytest.mark.asyncio
async def test_buffer(run_client):
    """Check that incoming data is converted to a line-oriented protocol."""
    with run_client.patch('line_received') as m:
        await run_client.receive_bytes(b':nick!user@host PRIVMSG')
        assert not m.called
        await run_client.receive_bytes(b' #channel :hello\r\nPING')
        m.assert_has_calls([
            mock.call(':nick!user@host PRIVMSG #channel :hello'),
        ])
        await run_client.receive_bytes(b' :server.name\r\n')
        m.assert_has_calls([
            mock.call(':nick!user@host PRIVMSG #channel :hello'),
            mock.call('PING :server.name'),
        ])
        await run_client.receive_bytes(b':nick!user@host JOIN #foo\r\n'
                                 b':nick!user@host JOIN #bar\r\n')
        m.assert_has_calls([
            mock.call(':nick!user@host PRIVMSG #channel :hello'),
            mock.call('PING :server.name'),
            mock.call(':nick!user@host JOIN #foo'),
            mock.call(':nick!user@host JOIN #bar'),
        ])


@pytest.mark.asyncio
async def test_decode_ascii(run_client):
    """Check that plain ASCII ends up as a (unicode) string."""
    with run_client.patch('line_received') as m:
        await run_client.receive_bytes(b':nick!user@host PRIVMSG #channel :hello\r\n')
        m.assert_called_once_with(':nick!user@host PRIVMSG #channel :hello')


@pytest.mark.asyncio
async def test_decode_utf8(run_client):
    """Check that incoming UTF-8 is properly decoded."""
    with run_client.patch('line_received') as m:
        await run_client.receive_bytes(b':nick!user@host PRIVMSG #channel :\xe0\xb2\xa0\r\n')
        m.assert_called_once_with(':nick!user@host PRIVMSG #channel :ಠ')


@pytest.mark.asyncio
async def test_decode_cp1252(run_client):
    """Check that incoming CP1252 is properly decoded.

    This tests a CP1252 sequences which is definitely illegal in UTF-8, to
    check that the fallback decoding works.
    """
    with run_client.patch('line_received') as m:
        await run_client.receive_bytes(b':nick!user@host PRIVMSG #channel :\x93\x94\r\n')
        m.assert_called_once_with(':nick!user@host PRIVMSG #channel :“”')


@pytest.mark.asyncio
async def test_decode_invalid_sequence(run_client):
    """Check that incoming invalid byte sequence is properly handled.

    This tests invalid byte sequences which are definitely illegal in
    UTF-8 and CP1252, to check that nothing breaks and that it correctly
    replaces the character.
    """
    with run_client.patch('line_received') as m:
        await run_client.receive_bytes(b':nick!user@host PRIVMSG #channel : ono\x81\r\n')
        m.assert_called_once_with(':nick!user@host PRIVMSG #channel : ono�')


def test_encode(irc_client_helper):
    """Check that outgoing data is encoded as UTF-8."""
    irc_client_helper.client.send_line('PRIVMSG #channel :ಠ_ಠ')
    irc_client_helper.assert_bytes_sent(b'PRIVMSG #channel :\xe0\xb2\xa0_\xe0\xb2\xa0\r\n')


# Test IRC client behaviour

@pytest.mark.asyncio
async def test_auto_reconnect(run_client):
    with run_client.patch('connect') as m:
        assert not m.called
        run_client.client.reader.feed_eof()
        await run_client.client.disconnected.wait()
        m.assert_called_once_with()


@pytest.mark.asyncio
async def test_disconnect(run_client):
    with run_client.patch('connect') as m:
        run_client.client.disconnect()
        await run_client.client.disconnected.wait()
        assert not m.called


def test_PING_PONG(irc_client_helper):
    irc_client_helper.receive('PING :i.am.a.server')
    irc_client_helper.assert_sent('PONG :i.am.a.server')


def test_RPL_WELCOME_nick_truncated(irc_client_helper):
    """IRC server might truncate the requested nick at sign-on, this should
    be reflected by the client's behaviour."""
    with irc_client_helper.patch('on_nick_changed') as m:
        irc_client_helper.client.set_nick('foo_bar')
        assert irc_client_helper.client.nick == 'foo_bar'
        irc_client_helper.receive(':a.server 001 foo_b :Welcome to the server')
        assert irc_client_helper.client.nick == 'foo_b'
        # Check events were fired for both nick changes (the initial request
        # and the truncated nick)
        m.assert_has_calls([mock.call('foo_bar'), mock.call('foo_b')])


def test_ERR_NICKNAMEINUSE(irc_client_helper):
    """If nick is in use, try another one."""
    original_nick = 'MrRoboto'
    irc_client_helper.client.set_nick(original_nick)
    irc_client_helper.assert_sent('NICK {}'.format(original_nick))
    irc_client_helper.receive(':a.server 433 * {} :Nickname is already in use.'.format(original_nick))
    new_nick = original_nick + '_'
    irc_client_helper.assert_sent('NICK {}'.format(new_nick))
    assert irc_client_helper.client.nick == new_nick


def test_ERR_NICKNAMEINUSE_truncated(irc_client_helper):
    """IRC server might truncate requested nicks, so we should use a
    different strategy to resolve nick collisions if that happened."""
    irc_client_helper.client.set_nick('a_very_long_nick')
    irc_client_helper.receive(':a.server 433 * a_very_long_nick :Nickname is already in use.')
    # Should have triggered the same behaviour as above, appending _
    assert irc_client_helper.client.nick == 'a_very_long_nick_'
    # Except oops, server truncated it to the same in-use nick!
    irc_client_helper.receive(':a.server 433 * a_very_long_nick :Nickname is already in use.')
    # Next nick tried should be the same length with some _ replacements
    assert irc_client_helper.client.nick == 'a_very_long_nic_'
    # Not stateful, so if this in use it'll try append first
    irc_client_helper.receive(':a.server 433 * a_very_long_nic_ :Nickname is already in use.')
    assert irc_client_helper.client.nick == 'a_very_long_nic__'
    # But yet again, if that request got truncated, it'll replace a character
    irc_client_helper.receive(':a.server 433 * a_very_long_nic_ :Nickname is already in use.')
    assert irc_client_helper.client.nick == 'a_very_long_ni__'


# Test IRC messages trigger client events

@pytest.mark.parametrize("raw,method,args,kwargs", [
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
])
def test_routing(irc_client_helper, raw, method, args, kwargs):
    """Run every routing test case."""
    # Patch the expected method (creating it if necessary)
    with irc_client_helper.patch(method, create=True) as m:
        # Handle the raw IRC message
        irc_client_helper.receive(raw)
        # Check for the call
        m.assert_called_once_with(*args, **kwargs)


ME = IRCUser.parse('csbot!bot@robot.land')
USER = IRCUser.parse('nick!person@their.server')


@pytest.mark.parametrize("raw,method,args,kwargs", [
    # Welcome/signed on
    (f':a.server 001 {ME.nick} :Welcome to the server', 'on_welcome', [], {}),
    # Our nick changed by the server
    (f':{ME.raw} NICK :csbot2', 'on_nick_changed', ['csbot2'], {}),
    # Somebody else's nick changed
    (f':{USER.raw} NICK :nick2', 'on_user_renamed', [USER.nick, 'nick2'], {}),
    # We joined a channel
    (f':{ME.raw} JOIN #channel', 'on_joined', ['#channel'], {}),
    # Somebody else joined a channel
    (f':{USER.raw} JOIN #channel', 'on_user_joined', [USER, '#channel'], {}),
    # We left a channel
    (f':{ME.raw} PART #channel :"goodbye"', 'on_left', ['#channel'], {}),
    # Somebody else left a channel
    (f':{USER.raw} PART #channel :"goodbye"', 'on_user_left', [USER, '#channel', '"goodbye"'], {}),
    (f':{USER.raw} PART #channel', 'on_user_left', [USER, '#channel', None], {}),
    # We were kicked from a channel
    (f':{USER.raw} KICK #channel {ME.nick} :reason', 'on_kicked', ['#channel', USER, 'reason'], {}),
    (f':{USER.raw} KICK #channel {ME.nick}', 'on_kicked', ['#channel', USER, None], {}),
    # Somebody else was kicked from a channel
    (f':{USER.raw} KICK #channel somebody :reason',
     'on_user_kicked', [IRCUser.parse('somebody'), '#channel', USER, 'reason'], {}),
    (f':{USER.raw} KICK #channel somebody',
     'on_user_kicked', [IRCUser.parse('somebody'), '#channel', USER, None], {}),
    # Somebody quit the server
    (f':{USER.raw} QUIT :goodbye', 'on_user_quit', [USER, 'goodbye'], {}),
    (f':{USER.raw} QUIT', 'on_user_quit', [USER, None], {}),
    # Received a message
    (f':{USER.raw} PRIVMSG #channel :hello', 'on_privmsg', [USER, '#channel', 'hello'], {}),
    # Received a notice
    (f':{USER.raw} NOTICE #channel :hello', 'on_notice', [USER, '#channel', 'hello'], {}),
    # Received an action
    (f':{USER.raw} PRIVMSG #channel :\x01ACTION bounces\x01',
     'on_action', [USER, '#channel', 'bounces'], {}),
    # Channel topic reported after JOIN
    (f':a.server 332 {ME.nick} #channel :channel topic',
     'on_topic_changed', [IRCUser.parse('a.server'), '#channel', 'channel topic'], {}),
    # Channel topic changed
    (f':{USER.raw} TOPIC #channel :new topic',
     'on_topic_changed', [USER, '#channel', 'new topic'], {}),
    # Channel topic unset
    (f':{USER.raw} TOPIC #channel',
     'on_topic_changed', [USER, '#channel', None], {}),
], )
def test_events(irc_client_helper, raw, method, args, kwargs):
    """Run every event test case."""
    # Patch the expected method
    with irc_client_helper.patch(method) as m:
        # Handle the raw IRC message
        irc_client_helper.receive(raw)
        # Check for the call
        m.assert_called_once_with(*args, **kwargs)


def test_parse_failure(irc_client_helper):
    """Test something that doesn't parse as a message.

    Most things will parse as a message, technically speaking, but the
    empty string won't!
    """
    with pytest.raises(IRCParseError):
        irc_client_helper.receive('')


# Test that calling various commands causes the appropriate messages to be sent to the server

def test_set_nick(irc_client_helper):
    with irc_client_helper.patch('on_nick_changed') as m:
        irc_client_helper.client.set_nick('new_nick')
        irc_client_helper.assert_sent('NICK new_nick')
        assert irc_client_helper.client.nick == 'new_nick'
        m.assert_called_once_with('new_nick')


def test_join(irc_client_helper):
    irc_client_helper.client.join('#foo')
    irc_client_helper.assert_sent('JOIN #foo')


def test_leave(irc_client_helper):
    irc_client_helper.client.leave('#foo')
    irc_client_helper.assert_sent('PART #foo :')
    irc_client_helper.client.leave('#foo', 'just because')
    irc_client_helper.assert_sent('PART #foo :just because')


def test_quit(irc_client_helper):
    irc_client_helper.client.quit()
    irc_client_helper.assert_sent('QUIT :')
    irc_client_helper.client.quit('reason')
    irc_client_helper.assert_sent('QUIT :reason')


@pytest.mark.asyncio
async def test_quit_no_reconnect(run_client):
    with run_client.patch('connect') as m:
        run_client.client.quit(reconnect=False)
        run_client.client.reader.feed_eof()
        await run_client.client.disconnected.wait()
        assert not m.called


@pytest.mark.asyncio
async def test_quit_reconnect(run_client):
    with run_client.patch('connect') as m:
        run_client.client.quit(reconnect=True)
        run_client.client.reader.feed_eof()
        await run_client.client.disconnected.wait()
        assert m.called


def test_msg(irc_client_helper):
    irc_client_helper.client.msg('#channel', 'a message')
    irc_client_helper.assert_sent('PRIVMSG #channel :a message')
    irc_client_helper.client.msg('a_nick', 'another message')
    irc_client_helper.assert_sent('PRIVMSG a_nick :another message')


def test_act(irc_client_helper):
    irc_client_helper.client.act('#channel', 'bounces')
    irc_client_helper.assert_sent('PRIVMSG #channel :\x01ACTION bounces\x01')


def test_notice(irc_client_helper):
    irc_client_helper.client.notice('#channel', 'a notice')
    irc_client_helper.assert_sent('NOTICE #channel :a notice')


def test_set_topic(irc_client_helper):
    irc_client_helper.client.set_topic('#channel', 'new topic')
    irc_client_helper.assert_sent('TOPIC #channel :new topic')
    irc_client_helper.client.set_topic('#channel', '')
    irc_client_helper.assert_sent('TOPIC #channel :')


def test_get_topic(irc_client_helper):
    irc_client_helper.client.get_topic('#channel')
    irc_client_helper.assert_sent('TOPIC #channel')


def test_ctcp_query(irc_client_helper):
    irc_client_helper.client.ctcp_query('#channel', 'VERSION')
    irc_client_helper.assert_sent('PRIVMSG #channel :\x01VERSION\x01')
    irc_client_helper.client.ctcp_query('a_nick', 'FOO', 'bar')
    irc_client_helper.assert_sent('PRIVMSG a_nick :\x01FOO bar\x01')


def test_ctcp_reply(irc_client_helper):
    irc_client_helper.client.ctcp_reply('a_nick', 'PONG')
    irc_client_helper.assert_sent('NOTICE a_nick :\x01PONG\x01')
    irc_client_helper.client.ctcp_reply('a_nick', 'VERSION', '1.0')
    irc_client_helper.assert_sent('NOTICE a_nick :\x01VERSION 1.0\x01')


# Test IRC message parsing

def test_PING():
    """Parse a simple message."""
    m = IRCMessage.parse('PING :i.am.a.server')
    assert m.raw == 'PING :i.am.a.server'
    assert m.prefix == None
    assert m.command == 'PING'
    assert m.command_name == 'PING'
    assert m.params == ['i.am.a.server']


def test_RPL_WELCOME():
    """Parse a more complex command, which also involves a numeric reply."""
    m = IRCMessage.parse(':a.server 001 nick :Welcome to the server')
    assert m.prefix == 'a.server'
    assert m.command == '001'
    assert m.command_name == 'RPL_WELCOME'
    assert m.params, ['nick' == 'Welcome to the server']
