import functools
import unittest
import unittest.mock

import mongomock

from csbot.util import subdict
from csbot.test import BotTestCase, run_client


def failsafe(f):
    """forces the test to fail if not using a mock
    this prevents the tests from accidentally polluting a real database in the event of failure"""
    @functools.wraps(f)
    def decorator(self, *args, **kwargs):
        assert isinstance(self.quote.quotedb,
                          mongomock.Collection), 'Not mocking MongoDB -- may be writing to actual database (!) (aborted test)'
        return f(self, *args, **kwargs)
    return decorator

class TestQuotePlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = mongodb usertrack quote

    [mongodb]
    mode = mock
    """

    PLUGINS = ['quote']

    def setUp(self):
        super().setUp()

        if not isinstance(self.quote.paste_quotes, unittest.mock.Mock):
            self.quote.paste_quotes = unittest.mock.MagicMock(wraps=self.quote.paste_quotes, return_value='N/A')

        self.quote.paste_quotes.reset_mock()

    def _recv_privmsg(self, name, channel, msg):
        yield from self.client.line_received(':{} PRIVMSG {} :{}'.format(name, channel, msg))

    @failsafe
    def test_quote_empty(self):
        assert list(self.quote.find_quotes('noQuotesForMe', '#anyChannel')) == []

    @failsafe
    @run_client
    def test_client_quote_add(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!quote Nick')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quotes Nick')
        self.assert_sent('NOTICE {} :{}'.format('#First', '<Nick> test data'))

    @failsafe
    @run_client
    def test_client_quote_add_pattern_find(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data#1')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!quote Nick')

        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data#2')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!quote Nick')

        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quotes Nick data#2')
        self.assert_sent('NOTICE {} :{}'.format('#First', '<Nick> test data#2'))


    @failsafe
    @run_client
    def test_client_quotes_not_exist(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quotes Nick')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'No quotes recorded for Nick'))

    @failsafe
    @run_client
    def test_client_quote_add_multi(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'other data')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!quote Nick test')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quotes Nick')
        self.assert_sent('NOTICE {} :{}'.format('#First', '<Nick> test data'))

    @failsafe
    @run_client
    def test_client_quote_channel_specific_logs(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'other data')

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!quote Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'Unknown nick Nick'))

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!quotes Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Second', 'No quotes recorded for Nick'))

    @failsafe
    @run_client
    def test_client_quote_channel_specific_quotes(self):
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data')
        yield from self._recv_privmsg('Nick!~user@host', '#Second', 'other data')

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!quote Nick')
        yield from self._recv_privmsg('Other!~user@host', '#Second', '!quotes Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Second', '<Nick> other data'))

        yield from self._recv_privmsg('Another!~user@host', '#First', '!quote Nick')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!quotes Nick')
        self.assert_sent('NOTICE {} :{}'.format('#First', '<Nick> test data'))

    @failsafe
    @run_client
    def test_client_quote_channel_fill_logs(self):
        for i in range(150):
            yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data#{}'.format(i))
            yield from self._recv_privmsg('Nick!~user@host', '#Second', 'other data#{}'.format(i))

        yield from self._recv_privmsg('Other!~user@host', '#Second', '!quote Nick data#135')
        yield from self._recv_privmsg('Other!~user@host', '#Second', '!quotes Nick')
        self.assert_sent('NOTICE {} :{}'.format('#Second', '<Nick> other data#135'))

    @failsafe
    @run_client
    def test_client_quotes_format(self):
        """make sure the format !quotes.list yields is readable and goes to the right place
        """
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'data test')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!quote Nick')

        yield from self._recv_privmsg('Other!~user@host', '#First', '!quotes.list')
        self.assert_sent('NOTICE Other :0 - #First - <Nick> data test')

    @failsafe
    @run_client
    def test_client_quotes_list(self):
        """ensure the list !quotes.list sends is short and redirects to pastebin
        """
        # stick some quotes in a thing
        data = ['test data#{}'.format(i) for i in range(10)]
        for msg in data:
            yield from self._recv_privmsg('Nick!~user@host', '#First', msg)
            yield from self._recv_privmsg('Other!~user@host', '#First', '!quote Nick')

        yield from self._recv_privmsg('Other!~user@host', '#First', '!quotes.list')

        quotes = [{'nick': 'Nick', 'channel': '#First', 'message': d, 'quoteId': i} for i, d in enumerate(data)]
        msgs = ['NOTICE {channel} :{msg}'.format(channel='Other', msg=self.quote.format_quote(q)) for q in quotes]
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
        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data#1')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!quote Nick')

        yield from self._recv_privmsg('Nick!~user@host', '#First', 'test data#2')
        yield from self._recv_privmsg('Other!~user@host', '#First', '!quote Nick')

        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quotes.remove -1')
        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quotes.remove 0')

        yield from self._recv_privmsg('Nick!~user@host', '#First', '!quotes Nick')
        self.assert_sent('NOTICE {} :{}'.format('#First', 'No quotes recorded for Nick'))

