import functools

import mongomock

from csbot.test import BotTestCase, run_client


def failsafe(f):
    """forces the test to fail if not using a mock
    this prevents the tests from accidentally polluting a real database in the event of failure"""
    @functools.wraps(f)
    def decorator(self, *args, **kwargs):
        assert isinstance(self.whois.whoisdb,
                          mongomock.Collection), 'Not mocking MongoDB -- may be writing to actual database (!) (aborted test)'
        return f(self, *args, **kwargs)
    return decorator

class TestWhoisPlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = mongodb usertrack whois

    [mongodb]
    mode = mock
    """

    PLUGINS = ['whois']

    def _recv_privmsg(self, name, channel, msg):
        yield from self.client.line_received(':{} PRIVMSG {} :{}'.format(name, channel, msg))

    @failsafe
    def test_whois_empty(self):
        assert self.whois.whois_lookup('this_nick_doesnt_exist', '#anyChannel') is None

    @failsafe
    def test_whois_insert(self):
        self.whois.whois_set('Nick', channel='#First', whois_str='test data')
        assert self.whois.whois_lookup('Nick', '#First') == 'test data'

    @failsafe
    def test_whois_unset(self):
        self.whois.whois_set('Nick', channel='#First', whois_str='test data')
        assert self.whois.whois_lookup('Nick', '#First') == 'test data'
        self.whois.whois_unset('Nick', '#First')
        assert self.whois.whois_lookup('Nick', '#First') is None

    @failsafe
    def test_whois_set_overwrite(self):
        self.whois.whois_set('Nick', channel='#First', whois_str='test data')
        self.whois.whois_set('Nick', channel='#First', whois_str='overwritten data')
        assert self.whois.whois_lookup('Nick', '#First') == 'overwritten data'

    @failsafe
    def test_whois_multi_user(self):
        self.whois.whois_set('Nick', channel='#First', whois_str='test1')
        self.whois.whois_set('OtherNick', channel='#First', whois_str='test2')
        assert self.whois.whois_lookup('Nick', '#First') == 'test1'
        assert self.whois.whois_lookup('OtherNick', '#First') == 'test2'

    @failsafe
    def test_whois_multi_channel(self):
        self.whois.whois_set('Nick', channel='#First', whois_str='first data')
        self.whois.whois_set('Nick', channel='#Second', whois_str='second data')
        assert self.whois.whois_lookup('Nick', '#First') == 'first data'
        assert self.whois.whois_lookup('Nick', '#Second') == 'second data'

    @failsafe
    def test_whois_channel_specific(self):
        self.whois.whois_set('Nick', channel='#First', whois_str='first data')
        assert self.whois.whois_lookup('Nick', '#AnyOtherChannel') is None

    @failsafe
    def test_whois_setdefault(self):
        self.whois.whois_set('Nick', 'test default data')
        assert self.whois.whois_lookup('Nick', '#First') == 'test default data'
        assert self.whois.whois_lookup('Nick', '#Other') == 'test default data'
        self.whois.whois_unset('Nick', '#First')
        assert self.whois.whois_lookup('Nick', '#First') == 'test default data'

    @failsafe
    def test_whois_channel_before_setdefault(self):
        self.whois.whois_set('Nick', 'test default data')
        self.whois.whois_set('Nick', channel='#First', whois_str='test first data')
        assert self.whois.whois_lookup('Nick', '#First') == 'test first data'
        assert self.whois.whois_lookup('Nick', '#Other') == 'test default data'
        self.whois.whois_unset('Nick', '#First')
        assert self.whois.whois_lookup('Nick', '#First') == 'test default data'

    @failsafe
    def test_whois_setdefault_unset(self):
        self.whois.whois_set('Nick', 'test default data')
        assert self.whois.whois_lookup('Nick', '#First') == 'test default data'
        assert self.whois.whois_lookup('Nick', '#Other') == 'test default data'
        self.whois.whois_unset('Nick', '#First')
        assert self.whois.whois_lookup('Nick', '#First') == 'test default data'
        self.whois.whois_unset('Nick')
        assert self.whois.whois_lookup('Nick', '#First') is None
        assert self.whois.whois_lookup('Nick', '#Second') is None

    @failsafe
    @run_client
    def test_client_reply_whois_after_set(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.setlocal test1')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test1'))

    @failsafe
    @run_client
    def test_client_reply_whois_different_channel(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.setlocal test1')
        yield from self._recv_privmsg('Nick!~user@host', '#Second', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'No data for Nick'))

    @failsafe
    @run_client
    def test_client_reply_whois_multiple_users_channels(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.setlocal test1')
        yield from self._recv_privmsg('Nick!~user@host', '#Second', '!whois.setlocal test2')

        yield from self._recv_privmsg('Other!~other@otherhost', '#First', '!whois Nick')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test1'))

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!whois Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test2'))

    @failsafe
    @run_client
    def test_client_reply_whois_self(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.setlocal test1')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test1'))

    @failsafe
    @run_client
    def test_set_alias(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.set test1')
        yield from self._recv_privmsg('Nick!~user@host', '#Second', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test1'))

    @failsafe
    @run_client
    def test_unset_alias(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.set test1')
        yield from self._recv_privmsg('Nick!~user@host', '#Second', '!whois.unset')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'No data for Nick'))

    @failsafe
    @run_client
    def test_client_reply_whois_setdefault_then_set_channel(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.setdefault test data')

        yield from self._recv_privmsg('Nick!~user@host', '#Second', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test data'))
        yield from self._recv_privmsg('Other!~other@otherhost', '#Third', '!whois Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Third', 'Nick: test data'))

        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.setlocal test first')

        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test first'))
        yield from self._recv_privmsg('Other!~other@otherhost', '#Second', '!whois Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test data'))

    @failsafe
    @run_client
    def test_client_reply_whois_setdefault_then_unset_channel(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.setdefault test data')
        yield from self._recv_privmsg('Nick!~user@host', '#Second', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test data'))

        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.setlocal test first')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test first'))

        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.unsetlocal')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test data'))


    @failsafe
    @run_client
    def test_client_reply_whois_setdefault_then_unsetdefault(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.setdefault test data')

        yield from self._recv_privmsg('Nick!~user@host', '#Second', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test data'))
        yield from self._recv_privmsg('Other!~other@otherhost', '#Third', '!whois Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Third', 'Nick: test data'))

        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.unset')

        yield from self._recv_privmsg('Nick!~user@host', '#Second', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'No data for Nick'))
        yield from self._recv_privmsg('Other!~other@otherhost', '#Third', '!whois Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Third', 'No data for Nick'))