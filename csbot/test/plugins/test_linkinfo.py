# coding=utf-8
from StringIO import StringIO

from twisted.trial import unittest
from httpretty import httprettified, HTTPretty
from lxml.etree import LIBXML_VERSION

from csbot.core import Bot
from csbot.plugins.linkinfo import LinkInfo


bot_config = """
[@bot]
plugins = linkinfo
"""

#: Test encoding handling; tests are (url, content-type, body, expected_title)
encoding_test_cases = [
    # (These test case are synthetic, to test various encoding scenarios)

    # UTF-8 with Content-Type header encoding only
    (
        "http://example.com/utf8-content-type-only",
        "text/html; charset=utf-8",
        "<html><head><title>EM DASH \xe2\x80\x94 &mdash;</title></head><body></body></html>",
        u'"EM DASH \u2014 \u2014"'
    ),
    # UTF-8 with meta http-equiv encoding only
    (
        "http://example.com/utf8-meta-http-equiv-only",
        "text/html",
        ('<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
         '<title>EM DASH \xe2\x80\x94 &mdash;</title></head><body></body></html>'),
        u'"EM DASH \u2014 \u2014"'
    ),
    # UTF-8 with XML encoding declaration only
    (
        "http://example.com/utf8-xml-encoding-only",
        "text/html",
        ('<?xml version="1.0" encoding="UTF-8"?><html><head>'
         '<title>EM DASH \xe2\x80\x94 &mdash;</title></head><body></body></html>'),
        u'"EM DASH \u2014 \u2014"'
    ),

    # (The following are real test cases the bot has barfed on in the past)

    # Content-Type encoding, XML encoding declaration *and* http-equiv are all
    # present (but no UTF-8 in title).  If we give lxml a decoded string with
    # the XML encoding declaration it complains.
    (
        "http://www.w3.org/TR/REC-xml/",
        "text/html; charset=utf-8",
        """
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
        u'"Extensible Markup Language (XML) 1.0 (Fifth Edition)"'
    ),
    # No Content-Type encoding, but has http-equiv encoding.  Has a mix of
    # UTF-8 literal em-dash and HTML entity em-dash - both should be output as
    # unicode em-dash.
    (
        "http://docs.python.org/2/library/logging.html",
        "text/html",
        """
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
        u'"15.7. logging \u2014 Logging facility for Python \u2014 Python v2.7.3 documentation"'
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
            ('<html><head><meta charset="UTF-8">'
             '<title>EM DASH \xe2\x80\x94 &mdash;</title></head><body></body></html>'),
            u'"EM DASH \u2014 \u2014"'
        ),
    ]


class TestLinkInfoPlugin(unittest.TestCase):
    def setUp(self):
        self.bot = Bot(StringIO(bot_config))
        self.linkinfo = self.bot.plugins['linkinfo']

    @httprettified
    def test_encoding_handling(self):
        for url, content_type, body, _ in encoding_test_cases:
            HTTPretty.register_uri(HTTPretty.GET, url, body=body,
                                   content_type=content_type)

        for url, _, _, expected_title in encoding_test_cases:
            _, _, title = self.linkinfo.get_link_info(url)
            self.assertEqual(title, expected_title, url)
