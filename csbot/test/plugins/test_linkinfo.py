# coding=utf-8
from twisted.trial import unittest
from httpretty import httprettified, HTTPretty

from csbot.core import Bot
from csbot.plugins.linkinfo import LinkInfo

example_python_doc = u"""
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    <title>15.7. logging — Logging facility for Python &mdash; Python v2.7.3 documentation</title>
  </head>
  <body>
  </body>
</html>
"""

class TestLinkInfoPlugin(unittest.TestCase):
    def setUp(self):
        self.bot = Bot()
        self.linkinfo = LinkInfo(self.bot)

    def tearDown(self):
        self.bot = None
        self.linkinfo = None

    @httprettified
    def test_unicode_handling(self):
        HTTPretty.register_uri(HTTPretty.GET,
                               "http://docs.python.org/2/library/logging.html",
                               body=example_python_doc,
                               content_type="text/html")
        prefix, nsfw, title = self.linkinfo.get_link_info(
            "http://docs.python.org/2/library/logging.html")
        self.assertEqual(title, u'"15.7. logging \u2014 Logging facility for '
                                u'Python \u2014 Python v2.7.3 documentation"')