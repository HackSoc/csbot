# coding=utf-8
from lxml.etree import LIBXML_VERSION
import unittest.mock as mock

import pytest
import requests

from csbot.util import simple_http_get


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
    [@bot]
    plugins = linkinfo
    """)


@pytest.fixture
def irc_client(irc_client):
    irc_client.connection_made()
    return irc_client


@pytest.mark.parametrize("url, content_type, body, expected_title", encoding_test_cases,
                         ids=[_[0] for _ in encoding_test_cases])
def test_encoding_handling(bot_helper, responses, url, content_type, body, expected_title):
    responses.add(responses.GET, url, body=body, content_type=content_type, stream=True)
    result = bot_helper['linkinfo'].get_link_info(url)
    assert result.text == expected_title


@pytest.mark.parametrize("url, content_type, body", error_test_cases,
                         ids=[_[0] for _ in error_test_cases])
def test_html_title_errors(bot_helper, responses, url, content_type, body):
    responses.add(responses.GET, url, body=body,
                  content_type=content_type, stream=True)
    result = bot_helper['linkinfo'].get_link_info(url)
    assert result.is_error


def test_connection_error(bot_helper, responses):
    # Check our assumptions: should be connection error because "responses" library is mocking the internet
    with pytest.raises(requests.ConnectionError):
        simple_http_get('http://example.com/foo/bar')
    # Should result in an error message from linkinfo (and implicitly no exception raised)
    result = bot_helper['linkinfo'].get_link_info('http://example.com/foo/bar')
    assert result.is_error


@pytest.mark.usefixtures("run_client")
@pytest.mark.asyncio
@pytest.mark.parametrize("msg, urls", [('http://example.com', ['http://example.com'])])
def test_scan_privmsg(bot_helper, msg, urls):
    with mock.patch.object(bot_helper['linkinfo'], 'get_link_info') as get_link_info:
        yield from bot_helper.client.line_received(':nick!user@host PRIVMSG #channel :' + msg)
        get_link_info.assert_has_calls([mock.call(url) for url in urls])


@pytest.mark.usefixtures("run_client")
@pytest.mark.asyncio
def test_scan_privmsg_rate_limit(bot_helper):
    """Test that we won't respond too frequently to URLs in messages.

    Unfortunately we can't currently test the passage of time, so the only
    element that can be tested is that URLs stop getting processed after so
    many URL-like strings and not enough (zero) time passing.
    """
    linkinfo = bot_helper['linkinfo']
    count = int(linkinfo.config_get('rate_limit_count'))
    for i in range(count):
        with mock.patch.object(linkinfo, 'get_link_info') as get_link_info:
            yield from bot_helper.client.line_received(':nick!user@host PRIVMSG #channel :http://example.com/{}'.format(i))
            get_link_info.assert_called_once_with('http://example.com/{}'.format(i))
    with mock.patch.object(linkinfo, 'get_link_info') as get_link_info:
        yield from bot_helper.client.line_received(':nick!user@host PRIVMSG #channel :http://example.com/12345')
        assert not get_link_info.called
