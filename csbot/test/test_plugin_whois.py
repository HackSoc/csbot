import pytest
import mongomock


@pytest.fixture(autouse=True)
def failsafe(bot_helper):
    """forces the test to fail if not using a mock
    this prevents the tests from accidentally polluting a real database in the event of failure"""
    assert isinstance(bot_helper['whois'].whoisdb,
                      mongomock.Collection), 'Not mocking MongoDB -- may be writing to actual database (!) (aborted test)'


@pytest.fixture
def bot_helper_class(bot_helper_class):
    class Helper(bot_helper_class):
        async def recv_privmsg(self, name, channel, msg):
            await self.client.line_received(':{} PRIVMSG {} :{}'.format(name, channel, msg))

    return Helper


pytestmark = pytest.mark.bot(config="""\
    [@bot]
    plugins = mongodb usertrack whois

    [mongodb]
    mode = mock
    """)


class TestWhoisAPI:
    @pytest.fixture
    def whois(self, bot_helper):
        return bot_helper['whois']

    def test_whois_empty(self, whois):
        assert whois.whois_lookup('this_nick_doesnt_exist', '#anyChannel') is None

    def test_whois_insert(self, whois):
        whois.whois_set('Nick', channel='#First', whois_str='test data')
        assert whois.whois_lookup('Nick', '#First') == 'test data'

    def test_whois_unset(self, whois):
        whois.whois_set('Nick', channel='#First', whois_str='test data')
        assert whois.whois_lookup('Nick', '#First') == 'test data'
        whois.whois_unset('Nick', '#First')
        assert whois.whois_lookup('Nick', '#First') is None

    def test_whois_set_overwrite(self, whois):
        whois.whois_set('Nick', channel='#First', whois_str='test data')
        whois.whois_set('Nick', channel='#First', whois_str='overwritten data')
        assert whois.whois_lookup('Nick', '#First') == 'overwritten data'

    def test_whois_multi_user(self, whois):
        whois.whois_set('Nick', channel='#First', whois_str='test1')
        whois.whois_set('OtherNick', channel='#First', whois_str='test2')
        assert whois.whois_lookup('Nick', '#First') == 'test1'
        assert whois.whois_lookup('OtherNick', '#First') == 'test2'

    def test_whois_multi_channel(self, whois):
        whois.whois_set('Nick', channel='#First', whois_str='first data')
        whois.whois_set('Nick', channel='#Second', whois_str='second data')
        assert whois.whois_lookup('Nick', '#First') == 'first data'
        assert whois.whois_lookup('Nick', '#Second') == 'second data'

    def test_whois_channel_specific(self, whois):
        whois.whois_set('Nick', channel='#First', whois_str='first data')
        assert whois.whois_lookup('Nick', '#AnyOtherChannel') is None

    def test_whois_setdefault(self, whois):
        whois.whois_set('Nick', 'test default data')
        assert whois.whois_lookup('Nick', '#First') == 'test default data'
        assert whois.whois_lookup('Nick', '#Other') == 'test default data'
        whois.whois_unset('Nick', '#First')
        assert whois.whois_lookup('Nick', '#First') == 'test default data'

    def test_whois_channel_before_setdefault(self, whois):
        whois.whois_set('Nick', 'test default data')
        whois.whois_set('Nick', channel='#First', whois_str='test first data')
        assert whois.whois_lookup('Nick', '#First') == 'test first data'
        assert whois.whois_lookup('Nick', '#Other') == 'test default data'
        whois.whois_unset('Nick', '#First')
        assert whois.whois_lookup('Nick', '#First') == 'test default data'

    def test_whois_setdefault_unset(self, whois):
        whois.whois_set('Nick', 'test default data')
        assert whois.whois_lookup('Nick', '#First') == 'test default data'
        assert whois.whois_lookup('Nick', '#Other') == 'test default data'
        whois.whois_unset('Nick', '#First')
        assert whois.whois_lookup('Nick', '#First') == 'test default data'
        whois.whois_unset('Nick')
        assert whois.whois_lookup('Nick', '#First') is None
        assert whois.whois_lookup('Nick', '#Second') is None


@pytest.mark.usefixtures("run_client")
@pytest.mark.asyncio
class TestWhoisBehaviour:
    async def test_client_reply_whois_after_set(self, bot_helper):
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois.set test1')
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test1'))

    async def test_client_reply_whois_different_channel(self, bot_helper):
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois.set test1')
        await bot_helper.recv_privmsg('Nick!~user@host', '#Second', '!whois')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#Second', 'No data for Nick'))

    async def test_client_reply_whois_multiple_users_channels(self, bot_helper):
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois.set test1')
        await bot_helper.recv_privmsg('Nick!~user@host', '#Second', '!whois.set test2')
    
        await bot_helper.recv_privmsg('Other!~other@otherhost', '#First', '!whois Nick')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test1'))
    
        await bot_helper.recv_privmsg('Other!~user@host', '#Second', '!whois Nick')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test2'))

    async def test_client_reply_whois_self(self, bot_helper):
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois.set test1')
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test1'))

    async def test_client_reply_whois_setdefault_then_set_channel(self, bot_helper):
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois.setdefault test data')
    
        await bot_helper.recv_privmsg('Nick!~user@host', '#Second', '!whois')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test data'))
        await bot_helper.recv_privmsg('Other!~other@otherhost', '#Third', '!whois Nick')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#Third', 'Nick: test data'))
    
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois.set test first')
    
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test first'))
        await bot_helper.recv_privmsg('Other!~other@otherhost', '#Second', '!whois Nick')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test data'))

    async def test_client_reply_whois_setdefault_then_unset_channel(self, bot_helper):
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois.setdefault test data')
        await bot_helper.recv_privmsg('Nick!~user@host', '#Second', '!whois')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test data'))
    
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois.set test first')
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test first'))
    
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois.unset')
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#First', 'Nick: test data'))

    async def test_client_reply_whois_setdefault_then_unsetdefault(self, bot_helper):
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois.setdefault test data')
    
        await bot_helper.recv_privmsg('Nick!~user@host', '#Second', '!whois')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#Second', 'Nick: test data'))
        await bot_helper.recv_privmsg('Other!~other@otherhost', '#Third', '!whois Nick')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#Third', 'Nick: test data'))
    
        await bot_helper.recv_privmsg('Nick!~user@host', '#First', '!whois.unsetdefault')
    
        await bot_helper.recv_privmsg('Nick!~user@host', '#Second', '!whois')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#Second', 'No data for Nick'))
        await bot_helper.recv_privmsg('Other!~other@otherhost', '#Third', '!whois Nick')
        bot_helper.assert_sent('NOTICE {} :{}'.format('#Third', 'No data for Nick'))
