from csbot.test import BotTestCase, run_client
from mongomock import MongoClient

class TestWhoisPlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = mongodb usertrack whois
    """

    PLUGINS = ['whois']

    def _assert_whois(self, nick, channel, whois_data):
        assert self.whois.whoisdb.find_one({'nick': nick, 'channel': channel})['data'] == whois_data

    def _recv_privmsg(self, name, channel, msg):
        yield from self.client.line_received(':{} PRIVMSG {} :{}'.format(name, channel, msg))

    def setUp(self):
        super().setUp()
        collection = MongoClient().db.collection
        self.whois.whoisdb = collection

    def test_whois_empty(self):
        assert self.whois.whois_lookup('this_nick_doesnt_exist', '#anyChannel') is None

    def test_whois_insert(self):
        self.whois.whois_set('Nick', '#First', 'test data')
        assert self.whois.whois_lookup('Nick', '#First') == 'test data'

    def test_whois_set_overwrite(self):
        self.whois.whois_set('Nick', '#First', 'test data')
        self.whois.whois_set('Nick', '#First', 'overwritten data')
        assert self.whois.whois_lookup('Nick', '#First') == 'overwritten data'

    def test_whois_multi_user(self):
        self.whois.whois_set('Nick', '#First', 'test1')
        self.whois.whois_set('OtherNick', '#First', 'test2')
        assert self.whois.whois_lookup('Nick', '#First') == 'test1'
        assert self.whois.whois_lookup('OtherNick', '#First') == 'test2'

    def test_whois_multi_channel(self):
        self.whois.whois_set('Nick', '#First', 'first data')
        self.whois.whois_set('Nick', '#Second', 'second data')
        assert self.whois.whois_lookup('Nick', '#First') == 'first data'
        assert self.whois.whois_lookup('Nick', '#Second') == 'second data'

    def test_whois_channel_specific(self):
        self.whois.whois_set('Nick', '#First', 'first data')
        assert self.whois.whois_lookup('Nick', '#AnyOtherChannel') is None

    @run_client
    def test_client_reply_whois_after_set(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.set test1')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test1'))

    @run_client
    def test_client_reply_whois_different_channel(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.set test1')
        yield from self._recv_privmsg('Nick!~user@host', '#Second', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'No data for Nick'))

    @run_client
    def test_client_reply_whois_multiple_users_channels(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.set test1')
        yield from self._recv_privmsg('Nick!~user@host', '#Second', '!whois.set test2')

        yield from self._recv_privmsg('Other!~other@otherhost', '#First', '!whois Nick')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test1'))

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!whois Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test2'))

    @run_client
    def test_client_reply_whois_self(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.set test1')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test1'))