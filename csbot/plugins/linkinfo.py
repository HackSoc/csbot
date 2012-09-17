import logging
import re
from urlparse import urlparse

import requests
import lxml.html

from csbot.plugin import Plugin


class LinkInfo(Plugin):
    log = logging.getLogger(__name__)

    def setup(self):
        """Create exclusion and handler filters.
        """
        super(LinkInfo, self).setup()

        # URL exclusion filters; if a test(url) returns a True-ish value then
        # the URL will be ignored.
        self.excludes = [
            lambda url: url.scheme not in ('http', 'https'),
            lambda url: re.match(r'\.(png|jpg|jpeg|gif)$', url.path, re.I),
        ]

        # Special URL handlers as (test, handler) pairs; if test(url) returns
        # a True-ish value, then handler(e, url, test(url)) is called and no
        # further handlers are tried.
        self.handlers = [
            (lambda url: url.netloc in ('reddit.com', 'www.reddit.com'),
                self.handle_reddit),
            # Fallback handler
            (lambda url: True, self.handle_html_title),
        ]

    @Plugin.hook('core.message.privmsg')
    def entry_point(self, e):
        """Receive messages and pass discovered URLs to the appropriate
        handler.
        """
        # Attempt to parse a URL at the beginning of the message
        original_url = e['message'].split(None, 1)[0]
        if '://' not in original_url:
            return
        url = urlparse(original_url)

        # Check the exclude filters
        for f in self.excludes:
            if f(url):
                self.log.debug(u'ignored URL: ' + original_url)
                return

        # Check for special handlers
        for test, handler in self.handlers:
            match = test(url)
            if match:
                self.log.debug(u'handling URL with ' + repr(handler))
                handler(e, url, match)
                return

        self.log.warn(u'URL not handled: ' + original_url)

    def handle_html_title(self, e, url, match):
        """Scrape the ``<title>`` tag contents from an HTML page.
        """
        # Let's see what's on the other end...
        r = requests.get(url.geturl())
        # Only bother with 200 OK
        if r.status_code != requests.codes.ok:
            self.log.warn(u'request failed for ' + url.geturl())
            return
        if 'html' not in r.headers['Content-Type']:
            self.log.debug(u'Content-Type not HTML-ish ({}): {}'
                           .format(r.headers['Content-Type'], url.geturl()))
            return

        # Attempt to scrape the HTML for a <title>
        html = lxml.html.document_fromstring(r.text)
        title = html.find('.//title')

        if title is not None:
            e.protocol.msg(e['reply_to'], u'Title: "{}"'.format(title.text))
        else:
            self.log.warn('failed to find <title> at ' + url)

    def handle_reddit(self, e, url, match):
        # TODO: implement this
        self.handle_html_title(e, url, match)
