import os.path
import re
from urlparse import urlparse
import collections
import datetime

import requests
import lxml.etree
import lxml.html

from csbot.plugin import Plugin


class LinkInfo(Plugin):
    CONFIG_DEFAULTS = {
        # Maximum number of parts of a PRIVMSG to scan for URLs.
        'scan_limit': 1,
        # Minimum slug length in "title in URL" filter
        'minimum_slug_length': 10,
        # Maximum file extension length (including the dot) for "title in URL"
        'max_file_ext_length': 6,
        # Minimum match (fraction) between path component and title for title
        # to be considered present in the URL
        'minimum_path_match': 0.5,
        # Number of seconds for rolling rate limiting period
        'rate_limit_time': 60,
        # Maximum rate of URL responses over rate limiting period
        'rate_limit_count': 5,
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

        # Timestamps of recently handled URLs for cooldown timer
        self.rate_limit_list = collections.deque()

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
                if reply is not None and not self._rate_limited():
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
        if 'charset=' in r.headers['content-type']:
            # If present, HTTP Content-Type header charset takes precedence
            parser = lxml.html.HTMLParser(
                encoding=r.headers['content-type'].rsplit('=', 1)[1])
        else:
            parser = lxml.html.html_parser
        html = lxml.etree.fromstring(r.content, parser)
        title = html.find('.//title')

        if title is None:
            self.log.debug(u'failed to find <title>: ' + url.geturl())
            return None

        # Normalise title whitespace
        title = ' '.join(title.text.strip().split())
        nsfw = url.netloc.endswith('.xxx')

        # See if the title is in the URL
        if self._filter_title_in_url(url, title):
            return None

        # Return the scraped title
        return 'Title', nsfw, u'"{}"'.format(title)

    def _filter_title_in_url(self, url, title):
        """See if *title* is represented in *url*.
        """
        # Only match based on the path
        path = url.path
        # Ignore case
        path = path.lower()
        title = title.lower()
        # Strip file extension if present
        if not path.endswith('/'):
            path_noext, ext = os.path.splitext(path)
            if len(ext) <= int(self.config_get('max_file_ext_length')):
                path = path_noext
        # Strip characters that are unlikely to end up in a slugified URL
        strip_pattern = r'[^a-z/]'
        path = re.sub(strip_pattern, '', path)
        title = re.sub(strip_pattern, '', title)

        # Attempt 0: is the title actually just the domain name?
        if title in url.netloc.lower():
            self.log.debug(u'title "{}" matches domain name "{}"'.format(
                title, url.netloc))
            return True

        # Attempt 1: is the slugified title entirely within the URL path?
        if title in path:
            self.log.debug(u'title "{}" in "{}"'.format(title, path))
            return True

        # Attempt 2: is some part of the URL path the start of the title?
        slug_length = int(self.config_get('minimum_slug_length'))
        for part in path.split('/'):
            ratio = float(len(part)) / float(len(title))
            if (len(part) >= slug_length and title.startswith(part) and
                    ratio >= float(self.config_get('minimum_path_match'))):
                self.log.debug(u'path part "{}" matches title "{}"'.format(
                    part, title))
                return True

        # Didn't match
        return False

    def _respond(self, e, prefix, nsfw, message):
        """A helper function for responding to link information requests in a
        consistent format.
        """
        e.protocol.msg(e['reply_to'], u'{}: {}{}'.format(
            prefix, '[NSFW] ' if nsfw else '', message,
        ))

    def _rate_limited(self):
        """Find out if the current call is subject to rate limiting.

        Somewhat self-policing, this function returns True if it's being
        called too often.  "Too often" is defined as more than
        ``rate_limit_count`` calls in a ``rate_limit_time`` second period.
        """
        now = datetime.datetime.now()
        delta = datetime.timedelta(
            seconds=int(self.config_get('rate_limit_time')))
        count = int(self.config_get('rate_limit_count'))

        if len(self.rate_limit_list) < count:
            self.rate_limit_list.append(now)
            return False

        if self.rate_limit_list[0] + delta < now:
            self.rate_limit_list.popleft()
            self.rate_limit_list.append(now)
            return False

        self.log.debug('rate limiting URL responses')
        return True
