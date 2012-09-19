import re
from urlparse import urlparse

import requests
import lxml.html

from csbot.plugin import Plugin


class LinkInfo(Plugin):
    def __init__(self, *args, **kwargs):
        super(LinkInfo, self).__init__(*args, **kwargs)

        # URL handlers
        self.handlers = []

        # URL exclusion filters, with defaults
        self.excludes = [
            # Ignore media links, they'll just waste time and bandwidth
            lambda url: re.search(r'\.(png|jpg|jpeg|gif|mp3|mp4|wav|avi|mkv'
                                  r'|mov)$', url.path, re.I),
        ]

    def register_handler(self, filter, handler):
        """Add a URL handler.

        If ``filter(url)`` returns a True-like value, then
        ``handler(url, filter(url))`` will be called.  The the URL is provided
        as a :class:`urlparse.ParseResult`.  Including the filter result is
        useful for accessing the results of a regular expression filter.

        *handler* should return a ``(prefix, nsfw, message)`` tuple.  If it
        returns None instead, the processing will fall through to the next
        handler: this is the best way to signal that a handler doesn't know
        what to do with a URL it has matched.
        """
        self.handlers.append((filter, handler))

    def register_exclude(self, filter):
        """Add a URL exclusion filter.

        URL exclusions are applied after all handlers have been tried without
        getting a response, and before the the default title-scraping handler
        is invoked.  If ``filter(url)`` returns a True-like value, then the URL
        will be ignored.
        """
        self.excludes.append(filter)

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
        # Skip non-HTTP(S) URLs
        if url.scheme not in ('http', 'https'):
            return

        def respond(prefix, nsfw, message):
            e.protocol.msg(e['reply_to'], u'{}: {}{}'.format(
                prefix, '[NSFW] ' if nsfw else '', message,
            ))

        # Try handlers in registration order
        for f, h in self.handlers:
            match = f(url)
            if match:
                reply = h(url, match)
                # "None" replies fall through to the next handler
                if reply is not None:
                    respond(*reply)
                    break
        # If no handlers gave a response, use the default handler
        else:
            # Check that the URL hasn't been excluded
            for f in self.excludes:
                if f(url):
                    self.log.debug(u'ignored URL: ' + original_url)
                    break
            # Invoke the default handler
            else:
                reply = self.scrape_html_title(url)
                if reply is not None:
                    respond(*reply)
                else:
                    self.log.debug(u'URL not handled: ' + original_url)

    def scrape_html_title(self, url):
        """Scrape the ``<title>`` tag contents from an HTML page.
        """
        # Let's see what's on the other end...
        r = requests.get(url.geturl())
        # Only bother with 200 OK
        if r.status_code != requests.codes.ok:
            self.log.debug(u'request failed for ' + url.geturl())
            return None
        if 'html' not in r.headers['Content-Type']:
            self.log.debug(u'Content-Type not HTML-ish ({}): {}'
                           .format(r.headers['Content-Type'], url.geturl()))
            return None

        # Attempt to scrape the HTML for a <title>
        html = lxml.html.document_fromstring(r.text)
        title = html.find('.//title')

        if title is not None:
            return ('Title', url.netloc.endswith('.xxx'),
                    u'"{}"'.format(title.text))
        else:
            self.log.debug(u'failed to find <title>: ' + url)
            return None
