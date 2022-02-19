import asyncio
from unittest import mock

import mongomock
import pytest

from csbot.plugins.quote import QuoteRecord
from csbot.util import subdict


class TestQuoteRecord:
    def test_quote_formatter(self):
        quote = QuoteRecord(quote_id=0, channel='#First', nick='Nick', message='test')
        assert quote.format() == '[0] <Nick> test'
        assert quote.format(show_id=False) == '<Nick> test'
        assert quote.format(show_channel=True) == '[0] - #First - <Nick> test'
        assert quote.format(show_channel=True, show_id=False) == '#First - <Nick> test'

    def test_quote_deserialise(self):
        udict = {'quoteId': 0, 'channel': '#First', 'message': 'test', 'nick': 'Nick'}
        qr = QuoteRecord(quote_id=0, channel='#First', nick='Nick', message='test')
        assert QuoteRecord.from_udict(udict) == qr

    def test_quote_serialise(self):
        udict = {'quoteId': 0, 'channel': '#First', 'message': 'test', 'nick': 'Nick'}
        qr = QuoteRecord(quote_id=0, channel='#First', nick='Nick', message='test')
        assert qr.to_udict() == udict


class TestQuotePlugin:
    pytestmark = [
        pytest.mark.bot(config="""
            ["@bot"]
            plugins = ["mongodb", "usertrack", "auth", "quote"]
            
            [auth]
            nickaccount  = "#First:quote"
            otheraccount = "#Second:quote"
            
            [mongodb]
            mode = "mock"
        """),
        pytest.mark.usefixtures("run_client"),
    ]

    @pytest.fixture(autouse=True)
    def quote_plugin(self, bot_helper):
        self.bot_helper = bot_helper
        self.quote = self.bot_helper['quote']

        # Force the test to fail if not using a mock database. This prevents the tests from accidentally
        # polluting a real database in the evnet of failure.
        assert isinstance(self.quote.quotedb, mongomock.Collection), \
            'Not mocking MongoDB -- may be writing to actual database (!) (aborted test)'

        self.mock_paste_quotes = mock.MagicMock(wraps=self.quote.paste_quotes, return_value='N/A')
        with mock.patch.object(self.quote, 'paste_quotes', self.mock_paste_quotes):
            yield

    async def _recv_line(self, line):
        return await asyncio.wait(self.bot_helper.receive(line))

    async def _recv_privmsg(self, name, channel, msg):
        return await self._recv_line(f':{name} PRIVMSG {channel} :{msg}')

    def assert_sent_quote(self, channel, quote_id, quoted_user, quoted_channel, quoted_text, show_channel=False):
        quote = QuoteRecord(quote_id=quote_id,
                            channel=quoted_channel,
                            nick=quoted_user,
                            message=quoted_text)
        self.bot_helper.assert_sent('NOTICE {} :{}'.format(channel, quote.format()))

    def test_quote_empty(self):
        assert list(self.quote.find_quotes('noQuotesForMe', '#anyChannel')) == []

    async def test_client_quote_add(self):
        await self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        await self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')
        await self._recv_privmsg('Nick!~user@host', '#First', '!quote Nick')
        self.assert_sent_quote('#First', 0, 'Nick', '#First', 'test data')

    async def test_client_quote_remember_send_privmsg(self):
        await self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        await self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')
        self.bot_helper.assert_sent('NOTICE Other :remembered "<Nick> test data"')

    async def test_client_quote_add_pattern_find(self):
        await self._recv_privmsg('Nick!~user@host', '#First', 'test data#1')
        await self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')

        await self._recv_privmsg('Nick!~user@host', '#First', 'test data#2')
        await self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')

        await self._recv_privmsg('Nick!~user@host', '#First', '!quote Nick data#2')
        self.assert_sent_quote('#First', 1, 'Nick', '#First', 'test data#2')

    async def test_client_quotes_not_exist(self):
        await self._recv_privmsg('Nick!~user@host', '#First', '!quote Nick')
        self.bot_helper.assert_sent('NOTICE {} :{}'.format('#First', 'No data for Nick'))

    async def test_client_quote_add_multi(self):
        await self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        await self._recv_privmsg('Nick!~user@host', '#First', 'other data')
        await self._recv_privmsg('Other!~user@host', '#First', '!remember Nick test')
        await self._recv_privmsg('Nick!~user@host', '#First', '!quote Nick')
        self.assert_sent_quote('#First', 0, 'Nick', '#First', 'test data')

    async def test_client_quote_channel_specific_logs(self):
        await self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        await self._recv_privmsg('Nick!~user@host', '#First', 'other data')

        await self._recv_privmsg('Other!~user@host', '#Second', '!remember Nick')
        self.bot_helper.assert_sent('NOTICE {} :{}'.format('#Second', 'No data for Nick'))

        await self._recv_privmsg('Other!~user@host', '#Second', '!quote Nick')
        self.bot_helper.assert_sent('NOTICE {} :{}'.format('#Second', 'No data for Nick'))

    async def test_client_quote_channel_specific_quotes(self):
        await self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        await self._recv_privmsg('Nick!~user@host', '#Second', 'other data')

        await self._recv_privmsg('Other!~user@host', '#Second', '!remember Nick')
        await self._recv_privmsg('Other!~user@host', '#Second', '!quote Nick')
        self.assert_sent_quote('#Second', 0, 'Nick', '#Second', 'other data')

        await self._recv_privmsg('Another!~user@host', '#First', '!remember Nick')
        await self._recv_privmsg('Other!~user@host', '#First', '!quote Nick')
        self.assert_sent_quote('#First', 1, 'Nick', '#First', 'test data')

    async def test_client_quote_channel_fill_logs(self):
        for i in range(150):
            await self._recv_privmsg('Nick!~user@host', '#First', 'test data#{}'.format(i))
            await self._recv_privmsg('Nick!~user@host', '#Second', 'other data#{}'.format(i))

        await self._recv_privmsg('Other!~user@host', '#Second', '!remember Nick data#135')
        await self._recv_privmsg('Other!~user@host', '#Second', '!quote Nick')
        self.assert_sent_quote('#Second', 0, 'Nick', '#Second', 'other data#135')

    async def test_client_quotes_format(self):
        """make sure the format !quote.list yields is readable and goes to the right place
        """
        await self._recv_line(":Other!~other@otherhost ACCOUNT otheraccount")

        await self._recv_privmsg('Nick!~user@host', '#Second', 'data test')
        await self._recv_privmsg('Other!~user@host', '#Second', '!remember Nick')

        await self._recv_privmsg('Other!~user@host', '#Second', '!quote.list')
        self.bot_helper.assert_sent('NOTICE Other :[0] - #Second - <Nick> data test')

    async def test_client_quotes_list(self):
        """ensure the list !quote.list sends is short and redirects to pastebin
        """
        await self._recv_line(":Nick!~user@host ACCOUNT nickaccount")
        await self._recv_line(":Other!~other@otherhost ACCOUNT otheraccount")

        # stick some quotes in a thing
        data = ['test data#{}'.format(i) for i in range(10)]
        for msg in data:
            await self._recv_privmsg('Nick!~user@host', '#Second', msg)
            await self._recv_privmsg('Other!~user@host', '#Second', '!remember Nick')

        await self._recv_privmsg('Other!~user@host', '#Second', '!quote.list')

        quotes = [QuoteRecord(quote_id=i, channel='#Second', nick='Nick', message=d) for i, d in enumerate(data)]
        quotes = reversed(quotes)
        msgs = ['NOTICE {channel} :{msg}'.format(channel='Other',
                                                 msg=q.format(show_channel=True)) for q in quotes]
        self.bot_helper.assert_sent(msgs[:5])

        # manually unroll the call args to map subdict over it
        # so we can ignore the cruft mongo inserts
        quote_calls = self.quote.paste_quotes.call_args
        qarg, = quote_calls[0]  # args
        for quote, document in zip(quotes, qarg):
            assert subdict(quote, document)

    async def test_client_quote_remove(self):
        await self._recv_line(":Nick!~user@host ACCOUNT nickaccount")

        await self._recv_privmsg('Nick!~user@host', '#First', 'test data#1')
        await self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')

        await self._recv_privmsg('Nick!~user@host', '#First', 'test data#2')
        await self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')

        await self._recv_privmsg('Nick!~user@host', '#First', '!quote.remove -1')
        await self._recv_privmsg('Nick!~user@host', '#First', '!quote.remove 0')

        await self._recv_privmsg('Nick!~user@host', '#First', '!quote Nick')
        self.bot_helper.assert_sent('NOTICE {} :{}'.format('#First', 'No data for Nick'))

    async def test_client_quote_remove_no_permission(self):
        await self._recv_line(":Other!~other@otherhost ACCOUNT otheraccount")

        await self._recv_privmsg('Nick!~user@host', '#First', 'test data#1')
        await self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')
        await self._recv_privmsg('Other!~user@host', '#First', '!quote.remove -1')

        self.bot_helper.assert_sent('NOTICE {} :{}'.format('#First', 'error: otheraccount not authorised for #First:quote'))

    async def test_client_quote_remove_no_quotes(self):
        await self._recv_line(":Nick!~user@host ACCOUNT nickaccount")
        await self._recv_privmsg('Nick!~user@host', '#First', '!quote.remove -1')

        self.bot_helper.assert_sent('NOTICE {} :{}'.format('#First', 'Error: could not remove quote(s) with ID: -1'))

    async def test_client_quote_list_no_permission(self):
        await self._recv_line(":Other!~other@otherhost ACCOUNT otheraccount")

        await self._recv_privmsg('Nick!~user@host', '#First', 'test data#1')
        await self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')
        await self._recv_privmsg('Other!~user@host', '#First', '!quote.list')

        self.bot_helper.assert_sent('NOTICE {} :{}'.format('#First', 'error: otheraccount not authorised for #First:quote'))

    async def test_client_quote_channelwide(self):
        await self._recv_privmsg('Nick!~user@host', '#First', 'test data!')
        await self._recv_privmsg('Other!~other@host', '#First', '!remember Nick')
        await self._recv_privmsg('Other!~other@host', '#First', '!quote')
        self.assert_sent_quote('#First', 0, 'Nick', '#First', 'test data!')

    async def test_client_quote_channelwide_with_pattern(self):
        await self._recv_privmsg('Nick!~user@host', '#First', 'test data!')
        await self._recv_privmsg('Other!~other@host', '#First', '!remember Nick')

        await self._recv_privmsg('Other!~other@host', '#First', 'other data')
        await self._recv_privmsg('Nick!~user@host', '#First', '!remember Other')

        await self._recv_privmsg('Other!~other@host', '#First', '!quote * other')
        self.assert_sent_quote('#First', 1, 'Other', '#First', 'other data')
