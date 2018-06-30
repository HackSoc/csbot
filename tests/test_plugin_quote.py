import functools
import unittest
import unittest.mock

import mongomock

from csbot.util import subdict
from csbot.test import BotTestCase, run_client

from csbot.plugins.quote import QuoteRecord


def failsafe(f):
    """forces the test to fail if not using a mock
    this prevents the tests from accidentally polluting a real database in the event of failure"""
    @functools.wraps(f)
    def decorator(self, *args, **kwargs):
        assert isinstance(self.quote.quotedb,
                          mongomock.Collection), 'Not mocking MongoDB -- may be writing to actual database (!) (aborted test)'
        return f(self, *args, **kwargs)
    return decorator

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


class TestQuotePlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = mongodb usertrack auth quote

    [auth]
    nickaccount  = #First:quote
    otheraccount = #Second:quote

    [mongodb]
    mode = mock
    """

    PLUGINS = ['quote']

    def setUp(self):
        super().setUp()

        if not isinstance(self.quote.paste_quotes, unittest.mock.Mock):
            self.quote.paste_quotes = unittest.mock.MagicMock(wraps=self.quote.paste_quotes, return_value='')

        self.quote.paste_quotes.reset_mock()

    def _recv_privmsg(self, name, channel, msg):
        yield from self.client.line_received(':{} PRIVMSG {} :{}'.format(name, channel, msg))

    def assert_sent_quote(self, channel, quote_id, quoted_user, quoted_channel, quoted_text, show_channel=False):
        quote = QuoteRecord(quote_id=quote_id,
                            channel=quoted_channel,
                            nick=quoted_user,
                            message=quoted_text)
        self.assert_sent('NOTICE {} :{}'.format(channel, quote.format()))

    @failsafe
    def test_quote_empty(self):
        assert list(self.quote.find_quotes('noQuotesForMe', '#anyChannel')) == []

    @failsafe
    @run_client
    def test_client_quote_add(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quote Nick')
        self.assert_sent_quote('#First', 0, 'Nick', '#First', 'test data')

    @failsafe
    @run_client
    def test_client_quote_remember_send_privmsg(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')
        self.assert_sent('NOTICE Other :remembered "<Nick> test data"')

    @failsafe
    @run_client
    def test_client_quote_add_pattern_find(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data#1')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')

        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data#2')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')

        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quote Nick data#2')
        self.assert_sent_quote('#First', 1, 'Nick', '#First', 'test data#2')

    @failsafe
    @run_client
    def test_client_quotes_not_exist(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quote Nick')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'No data for Nick'))

    @failsafe
    @run_client
    def test_client_quote_add_multi(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'other data')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!remember Nick test')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quote Nick')
        self.assert_sent_quote('#First', 0, 'Nick', '#First', 'test data')

    @failsafe
    @run_client
    def test_client_quote_channel_specific_logs(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'other data')

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!remember Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'No data for Nick'))

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!quote Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'No data for Nick'))

    @failsafe
    @run_client
    def test_client_quote_channel_specific_quotes(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        yield from self._recv_privmsg('Nick!~user@host', '#Second', 'other data')

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!remember Nick')
        yield from self._recv_privmsg('Other!~user@host', '#Second', '!quote Nick')
        self.assert_sent_quote('#Second', 0, 'Nick', '#Second', 'other data')

        yield from self._recv_privmsg('Another!~user@host', '#First', '!remember Nick')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!quote Nick')
        self.assert_sent_quote('#First', 1, 'Nick', '#First', 'test data')

    @failsafe
    @run_client
    def test_client_quote_channel_fill_logs(self):
        for i in range(150):
            yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data#{}'.format(i))
            yield from self._recv_privmsg('Nick!~user@host', '#Second', 'other data#{}'.format(i))

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!remember Nick data#135')
        yield from self._recv_privmsg('Other!~user@host', '#Second', '!quote Nick')
        self.assert_sent_quote('#Second', 0, 'Nick', '#Second', 'other data#135')

    @failsafe
    @run_client
    def test_client_quotes_format(self):
        """make sure the format !quote.list yields is readable and goes to the right place
        """
        yield from self.client.line_received(":Other!~other@otherhost ACCOUNT otheraccount")

        yield from self._recv_privmsg('Nick!~user@host', '#Second', 'data test')
        yield from self._recv_privmsg('Other!~user@host', '#Second', '!remember Nick')

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!quote.list')
        self.assert_sent('NOTICE Other :[0] - #Second - <Nick> data test')

    @failsafe
    @run_client
    def test_client_quotes_list(self):
        """ensure the list !quote.list sends is short and redirects to pastebin
        """
        yield from self.client.line_received(":Nick!~user@host ACCOUNT nickaccount")
        yield from self.client.line_received(":Other!~other@otherhost ACCOUNT otheraccount")

        # stick some quotes in a thing
        data = ['test data#{}'.format(i) for i in range(10)]
        for msg in data:
            yield from self._recv_privmsg('Nick!~user@host', '#Second', msg)
            yield from self._recv_privmsg('Other!~user@host', '#Second', '!remember Nick')

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!quote.list')

        quotes = [QuoteRecord(quote_id=i, channel='#Second', nick='Nick', message=d) for i, d in enumerate(data)]
        quotes = reversed(quotes)
        msgs = ['NOTICE {channel} :{msg}'.format(channel='Other',
                                                 msg=q.format(show_channel=True)) for q in quotes]
        self.assert_sent(msgs[:5])

        # manually unroll the call args to map subdict over it
        # so we can ignore the cruft mongo inserts
        quote_calls = self.quote.paste_quotes.call_args
        qarg, = quote_calls[0]  # args
        for quote, document in zip(quotes, qarg):
            assert subdict(quote, document)

    @failsafe
    @run_client
    def test_client_quote_remove(self):
        yield from self.client.line_received(":Nick!~user@host ACCOUNT nickaccount")

        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data#1')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')

        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data#2')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')

        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quote.remove -1')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quote.remove 0')

        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quote Nick')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'No data for Nick'))

    @failsafe
    @run_client
    def test_client_quote_remove_no_permission(self):
        yield from self.client.line_received(":Other!~other@otherhost ACCOUNT otheraccount")

        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data#1')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!quote.remove -1')

        self.assert_sent('NOTICE {} :{}'.format('#First', 'error: otheraccount not authorised for #First:quote'))

    @failsafe
    @run_client
    def test_client_quote_remove_no_quotes(self):
        yield from self.client.line_received(":Nick!~user@host ACCOUNT nickaccount")
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quote.remove -1')

        self.assert_sent('NOTICE {} :{}'.format('#First', 'Error: could not remove quote(s) with ID: -1'))

    @failsafe
    @run_client
    def test_client_quote_list_no_permission(self):
        yield from self.client.line_received(":Other!~other@otherhost ACCOUNT otheraccount")

        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data#1')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!remember Nick')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!quote.list')

        self.assert_sent('NOTICE {} :{}'.format('#First', 'error: otheraccount not authorised for #First:quote'))

    @run_client
    def test_client_quote_channelwide(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data!')
        yield from self._recv_privmsg('Other!~other@host', '#First', '!remember Nick')
        yield from self._recv_privmsg('Other!~other@host', '#First', '!quote')
        self.assert_sent_quote('#First', 0, 'Nick', '#First', 'test data!')

    @failsafe
    @run_client
    def test_client_quote_channelwide_with_pattern(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data!')
        yield from self._recv_privmsg('Other!~other@host', '#First', '!remember Nick')

        yield from self._recv_privmsg('Other!~other@host', '#First', 'other data')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!remember Other')

        yield from self._recv_privmsg('Other!~other@host', '#First', '!quote * other')
        self.assert_sent_quote('#First', 1, 'Other', '#First', 'other data')
