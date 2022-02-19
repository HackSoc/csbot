# coding=utf-8
from lxml.etree import LIBXML_VERSION
import unittest.mock as mock
import asyncio

import pytest
import asynctest.mock
import aiohttp
from aioresponses import CallbackResult

from csbot.plugin import Plugin, find_plugins


#: Test encoding handling; tests are (url, content-type, body, expected_title)
encoding_test_cases = [
    # (These test case are synthetic, to test various encoding scenarios)

    # UTF-8 with Content-Type header encoding only
    (
        "http://example.com/utf8-content-type-only",
        "text/html; charset=utf-8",
        b"<html><head><title>EM DASH \xe2\x80\x94 &mdash;</title></head><body></body></html>",
        'EM DASH \u2014 \u2014'
    ),
    # UTF-8 with meta http-equiv encoding only
    (
        "http://example.com/utf8-meta-http-equiv-only",
        "text/html",
        (b'<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
         b'<title>EM DASH \xe2\x80\x94 &mdash;</title></head><body></body></html>'),
        'EM DASH \u2014 \u2014'
    ),
    # UTF-8 with XML encoding declaration only
    (
        "http://example.com/utf8-xml-encoding-only",
        "text/html",
        (b'<?xml version="1.0" encoding="UTF-8"?><html><head>'
         b'<title>EM DASH \xe2\x80\x94 &mdash;</title></head><body></body></html>'),
        'EM DASH \u2014 \u2014'
    ),

    # (The following are real test cases the bot has barfed on in the past)

    # Content-Type encoding, XML encoding declaration *and* http-equiv are all
    # present (but no UTF-8 in title).  If we give lxml a decoded string with
    # the XML encoding declaration it complains.
    (
        "http://www.w3.org/TR/REC-xml/",
        "text/html; charset=utf-8",
        b"""
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html
  PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="EN">
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
        <title>Extensible Markup Language (XML) 1.0 (Fifth Edition)</title>
        <!-- snip -->
    </head>
    <body>
    <!-- snip -->
    </body>
</html>
        """,
        'Extensible Markup Language (XML) 1.0 (Fifth Edition)'
    ),
    # No Content-Type encoding, but has http-equiv encoding.  Has a mix of
    # UTF-8 literal em-dash and HTML entity em-dash - both should be output as
    # unicode em-dash.
    (
        "http://docs.python.org/2/library/logging.html",
        "text/html",
        b"""
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    <title>15.7. logging \xe2\x80\x94 Logging facility for Python &mdash; Python v2.7.3 documentation</title>
    <!-- snip -->
  </head>
  <body>
  <!-- snip -->
  </body>
</html>
        """,
        '15.7. logging \u2014 Logging facility for Python \u2014 Python v2.7.3 documentation'
    ),
    (
        "http://example.com/invalid-charset",
        "text/html; charset=utf-flibble",
        b'<html><head><title>Flibble</title></head><body></body></html>',
        'Flibble'
    ),
]

# Add HTML5 test-cases if libxml2 is new enough (<meta charset=...> encoding
# detection was added in 2.8.0)
if LIBXML_VERSION >= (2, 8, 0):
    encoding_test_cases += [
        # UTF-8 with meta charset encoding only
        (
            "http://example.com/utf8-meta-charset-only",
            "text/html",
            (b'<html><head><meta charset="UTF-8">'
             b'<title>EM DASH \xe2\x80\x94 &mdash;</title></head><body></body></html>'),
            'EM DASH \u2014 \u2014'
        ),
    ]


error_test_cases = [
    (
        "http://example.com/empty-title-tag",
        "text/html",
        b'<html><head><title></title></head><body></body></html>',
    ),
    (
        "http://example.com/whitespace-title-tag",
        "text/html",
        b'<html><head><title>   </title></head><body></body></html>',
    ),
    (
        "http://example.com/no-root-element",
        "text/html",
        b'<!DOCTYPE html><html ',
    ),
]


pytestmark = pytest.mark.bot(config="""\
    ["@bot"]
    plugins = ["linkinfo"]
    """)


@pytest.fixture
async def irc_client(irc_client):
    await irc_client.connection_made()
    return irc_client


@pytest.mark.parametrize("url, content_type, body, expected_title", encoding_test_cases,
                         ids=[_[0] for _ in encoding_test_cases])
async def test_encoding_handling(bot_helper, aioresponses, url, content_type, body, expected_title):
    aioresponses.get(url, status=200, body=body, headers={'Content-Type': content_type})
    result = await bot_helper['linkinfo'].get_link_info(url)
    assert result.text == expected_title


@pytest.mark.parametrize("url, content_type, body", error_test_cases,
                         ids=[_[0] for _ in error_test_cases])
async def test_html_title_errors(bot_helper, aioresponses, url, content_type, body):
    aioresponses.get(url, status=200, body=body, headers={'Content-Type': content_type})
    result = await bot_helper['linkinfo'].get_link_info(url)
    assert result.is_error


async def test_not_found(bot_helper, aioresponses):
    # Test our assumptions: direct request should raise connection error, because aioresponses
    # is mocking the internet
    with pytest.raises(aiohttp.ClientConnectionError):
        async with aiohttp.ClientSession() as session, session.get('http://example.com/'):
            pass

    # Should result in an error message from linkinfo (and implicitly no exception raised)
    result = await bot_helper['linkinfo'].get_link_info('http://example.com/')
    assert result.is_error


@pytest.mark.parametrize("msg, urls", [('http://example.com', ['http://example.com'])])
async def test_scan_privmsg(event_loop, bot_helper, aioresponses, msg, urls):
    with asynctest.mock.patch.object(bot_helper['linkinfo'], 'get_link_info') as get_link_info:
        await bot_helper.client.line_received(':nick!user@host PRIVMSG #channel :' + msg)
        get_link_info.assert_has_calls([mock.call(url) for url in urls])


@pytest.mark.parametrize("msg, urls", [('http://example.com', ['http://example.com'])])
async def test_command(event_loop, bot_helper, aioresponses, msg, urls):
    with asynctest.mock.patch.object(bot_helper['linkinfo'], 'get_link_info') as get_link_info, \
        asynctest.mock.patch.object(bot_helper['linkinfo'], 'link_command',
                                    wraps=bot_helper['linkinfo'].link_command) as link_command:
        await bot_helper.client.line_received(':nick!user@host PRIVMSG #channel :!link ' + msg)
        get_link_info.assert_has_calls([mock.call(url) for url in urls])
        assert link_command.call_count == 1


async def test_scan_privmsg_rate_limit(bot_helper, aioresponses):
    """Test that we won't respond too frequently to URLs in messages.

    Unfortunately we can't currently test the passage of time, so the only
    element that can be tested is that URLs stop getting processed after so
    many URL-like strings and not enough (zero) time passing.
    """
    linkinfo = bot_helper['linkinfo']
    count = linkinfo.config.rate_limit_count
    for i in range(count):
        with asynctest.mock.patch.object(linkinfo, 'get_link_info', ) as get_link_info:
            await bot_helper.client.line_received(
                ':nick!user@host PRIVMSG #channel :http://example.com/{}'.format(i))
            get_link_info.assert_called_once_with('http://example.com/{}'.format(i))
    with asynctest.mock.patch.object(linkinfo, 'get_link_info') as get_link_info:
        await bot_helper.client.line_received(':nick!user@host PRIVMSG #channel :http://example.com/12345')
        assert not get_link_info.called


class TestNonBlocking:
    class MockPlugin(Plugin):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.handler_mock = mock.Mock(spec=callable)

        @Plugin.hook('core.message.privmsg')
        def privmsg(self, event):
            self.handler_mock(event['message'])

    CONFIG = """\
    ["@bot"]
    plugins = ["mockplugin", "linkinfo"]
    """

    pytestmark = pytest.mark.bot(plugins=find_plugins() + [MockPlugin], config=CONFIG)

    async def test_non_blocking_privmsg(self, event_loop, bot_helper, aioresponses):
        bot_helper.reset_mock()

        event = asyncio.Event()

        async def handler(url, **kwargs):
            await event.wait()
            return CallbackResult(status=200, content_type='text/html',
                                  body=b'<html><head><title>foo</title></head><body></body></html>')
        aioresponses.get('http://example.com/', callback=handler)

        futures = bot_helper.receive([
            ':nick!user@host PRIVMSG #channel :a',
            ':nick!user@host PRIVMSG #channel :http://example.com/',
            ':nick!user@host PRIVMSG #channel :b',
        ])
        await asyncio.wait(futures, timeout=0.1)
        assert bot_helper['mockplugin'].handler_mock.mock_calls == [
            mock.call('a'),
            mock.call('http://example.com/'),
            mock.call('b'),
        ]
        bot_helper.client.send_line.assert_not_called()

        event.set()
        await asyncio.wait(futures, timeout=0.1)
        assert all(f.done() for f in futures)
        bot_helper.assert_sent('NOTICE #channel :foo')

    async def test_non_blocking_command(self, event_loop, bot_helper, aioresponses):
        bot_helper.reset_mock()

        event = asyncio.Event()

        async def handler(url, **kwargs):
            await event.wait()
            return CallbackResult(status=200, content_type='application/octet-stream',
                                  body=b'<html><head><title>foo</title></head><body></body></html>')

        aioresponses.get('http://example.com/', callback=handler)

        futures = bot_helper.receive([
            ':nick!user@host PRIVMSG #channel :a',
            ':nick!user@host PRIVMSG #channel :!link http://example.com/',
            ':nick!user@host PRIVMSG #channel :b',
        ])
        await asyncio.wait(futures, timeout=0.1)
        assert bot_helper['mockplugin'].handler_mock.mock_calls == [
            mock.call('a'),
            mock.call('!link http://example.com/'),
            mock.call('b'),
        ]
        bot_helper.client.send_line.assert_not_called()

        event.set()
        await asyncio.wait(futures, timeout=0.1)
        assert all(f.done() for f in futures)
        bot_helper.assert_sent('NOTICE #channel :Error: Content-Type not HTML-ish: '
                               'application/octet-stream (http://example.com/)')
