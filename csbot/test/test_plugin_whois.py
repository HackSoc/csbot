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
        self.whois.whois_set('nick1', '#First', 'test data')
        assert self.whois.whois_lookup('nick1', '#First') == 'test data'
        assert self.whois.whois_lookup('nick1', '#otherChannel') is None

    def test_whois_multi_user(self):
        self.whois.whois_set('nick1', '#First', 'test1')
        self.whois.whois_set('nick2', '#First', 'test2')
        assert self.whois.whois_lookup('nick1', '#First') == 'test1'
        assert self.whois.whois_lookup('nick2', '#First') == 'test2'

    def test_whois_multi_channel(self):
        self.whois.whois_set('nick1', '#First', 'test data1')
        self.whois.whois_set('nick1', '#Second', 'test data2')
        assert self.whois.whois_lookup('nick1', '#First') == 'test data1'
        assert self.whois.whois_lookup('nick1', '#Second') == 'test data2'

    @run_client
    def test_client_set_single_channel(self):
        yield from self._recv_privmsg('Nick!~user@host', '#channel', '!whois.set test')
        self._assert_whois('Nick', '#channel', 'test')

    @run_client
    def test_client_set_multi_channel(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!whois.set test1')
        yield from self._recv_privmsg('Nick!~user@host', '#Second', '!whois.set test2')

        self._assert_whois('Nick', '#First', 'test1')
        self._assert_whois('Nick', '#Second', 'test2')

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

        yield from self._recv_privmsg('Other!~user@host', '#First', '!whois Nick')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test1'))

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!whois Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test2'))