import re
from urlparse import urlparse

import requests
import lxml.html

from csbot.plugin import Plugin


class LinkInfo(Plugin):
    CONFIG_DEFAULTS = {
        # Maximum number of parts of a PRIVMSG to scan for URLs.
        'scan_limit': 1,
    }

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

    @Plugin.command('link')
    def link_command(self, e):
        """Handle the "link" command.

        Fetch information about a specified URL, e.g.
        ``!link http://google.com``.  The link can be explicitly marked as NSFW
        by including the string anywhere in the trailing string, e.g.
        ``!link http://lots-of-porn.com nsfw``.
        """
        # Split command data into the URL and any trailing information
        parts = e['data'].split(None, 1)
        url = parts[0]
        rest = parts[1] if len(parts) > 1 else ''
        # See if the command data was marked as NSFW
        nsfw = 'nsfw' in rest.lower()

        if '://' not in url:
            url = 'http://' + url

        reply = self.get_link_info(url)
        if reply is not None:
            prefix, link_nsfw, message = reply
            self._respond(e, prefix, nsfw or link_nsfw, message)
        else:
            e.protocol.msg(e['reply_to'], u"Couldn't fetch info for " + url)

    @Plugin.hook('core.message.privmsg')
    def scan_privmsg(self, e):
        """Scan the data of PRIVMSG events for URLs and respond with
        information about them.
        """
        # Don't want to be scanning URLs inside commands,
        # especially because we'd show information twice when the "link"
        # command is invoked...
        if e['message'].startswith(self.bot.config_get('command_prefix')):
            return

        parts = e['message'].split()
        for i, part in enumerate(parts[:int(self.config_get('scan_limit'))]):
            if '://' in part:
                # See if "NSFW" appears anywhere else in the message
                nsfw = 'nsfw' in ''.join(parts[:i] + parts[i + 1:]).lower()
                reply = self.get_link_info(part)
                if reply is not None:
                    prefix, link_nsfw, message = reply
                    self._respond(e, prefix, nsfw or link_nsfw, message)
                    break

    def get_link_info(self, original_url):
        """Get information about a URL, returning either None or a tuple of
        ``(prefix, nsfw, message)``.
        """
        url = urlparse(original_url)

        # Skip non-HTTP(S) URLs
        if url.scheme not in ('http', 'https'):
            return None

        # Try handlers in registration order
        for f, h in self.handlers:
            match = f(url)
            if match:
                reply = h(url, match)
                # "None" replies fall through to the next handler
                if reply is not None:
                    return reply
        # If no handlers gave a response, use the default handler
        else:
            # Check that the URL hasn't been excluded
            for f in self.excludes:
                if f(url):
                    self.log.debug(u'ignored URL: ' + original_url)
                    return None
            # Invoke the default handler
            else:
                reply = self.scrape_html_title(url)
                if reply is None:
                    self.log.debug(u'URL not handled: ' + original_url)
                return reply

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
            # Normalise title whitespace
            title = ' '.join(title.text.strip().split())
            return ('Title', url.netloc.endswith('.xxx'),
                    u'"{}"'.format(title))
        else:
            self.log.debug(u'failed to find <title>: ' + url)
            return None

    def _respond(self, e, prefix, nsfw, message):
        """A helper function for responding to link information requests in a
        consistent format.
        """
        e.protocol.msg(e['reply_to'], u'{}: {}{}'.format(
            prefix, '[NSFW] ' if nsfw else '', message,
        ))
