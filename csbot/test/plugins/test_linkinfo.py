# coding=utf-8
from StringIO import StringIO

from twisted.trial import unittest
from httpretty import httprettified, HTTPretty

from csbot.core import Bot
from csbot.plugins.linkinfo import LinkInfo


bot_config = """
[@bot]
plugins = linkinfo
"""

#: Test encoding handling; tests are (url, content-type, body, expected_title)
encoding_test_cases = (
    # (The following are real test cases the bot has barfed on in the past)

    # Content-Type encoding, XML encoding declaration *and* http-equiv are all
    # present (but no UTF-8 in title).  If we give lxml a decoded string with
    # the XML encoding declaration it complains.
    (
        "http://www.w3.org/TR/REC-xml/",
        "text/html; charset=utf-8",
        u"""
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
        u"""
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    <title>15.7. logging — Logging facility for Python &mdash; Python v2.7.3 documentation</title>
    <!-- snip -->
  </head>
  <body>
  <!-- snip -->
  </body>
</html>
        """,
        u'"15.7. logging \u2014 Logging facility for Python \u2014 Python v2.7.3 documentation"'
    ),
)

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
            self.assertEqual(title, expected_title)
