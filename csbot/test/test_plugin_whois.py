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

    @run_client
    def test_whois_set_singlechannel(self):
        yield from self._recv_privmsg('Nick!~user@host', '#channel', '!whois.set test')
        self._assert_whois('Nick', '#channel', 'test')

    @run_client
    def test_whois_set_multichannel(self):
        yield from self._recv_privmsg('Nick!~user@host', '#channel1', '!whois.set test1')
        yield from self._recv_privmsg('Nick!~user@host', '#channel2', '!whois.set test2')

        self._assert_whois('Nick', '#channel1', 'test1')
        self._assert_whois('Nick', '#channel2', 'test2')