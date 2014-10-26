import os.path
import re
from urllib.parse import urlparse
import collections
from collections import namedtuple
import datetime
from functools import partial

import requests
import lxml.etree
import lxml.html

from ..plugin import Plugin
from ..util import simple_http_get, Struct


LinkInfoHandler = namedtuple('LinkInfoHandler', ['filter', 'handler', 'exclusive'])


class LinkInfoResult(Struct):
    #: The URL requested
    url = Struct.REQUIRED
    #: Information about the URL
    text = Struct.REQUIRED
    #: Is an error?
    is_error = False
    #: URL is not safe for work?
    nsfw = False
    #: URL information is redundant? (e.g. duplicated in URL string)
    is_redundant = False

    def get_message(self):
        if self.is_error:
            return 'Error: {} ({})'.format(self.text, self.url)
        else:
            return ('[NSFW] ' if self.nsfw else '') + self.text


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

    def register_handler(self, filter, handler, exclusive=False):
        """Add a URL handler.

        *filter* should be a function that returns a True-like or False-like
        value to indicate whether *handler* should be run for a particular URL.
        The URL is supplied as a :class:`urlparse:ParseResult` instance.

        If *handler* is called, it will be as ``handler(url, filter(url))``.
        The filter result is useful for accessing the results of a regular
        expression filter, for example.  The result should be a
        :class:`LinkInfoResult` instance.  If the result is None instead, the
        processing will fall through to the next handler; this is the best way
        to signal that a handler doesn't know what to do with a particular URL.

        If *exclusive* is True, the fall-through behaviour will not happen,
        instead terminating the handling with the result of calling *handler*.
        """
        self.handlers.append(LinkInfoHandler(filter, handler, exclusive))

    def register_exclude(self, filter):
        """Add a URL exclusion filter.

        *filter* should be a function that returns a True-like or False-like
        value to indicate whether or not a URL should be excluded from the
        default title-scraping behaviour (after all registered handlers have
        been tried).  The URL is supplied as a :class:`urlparse.ParseResult`
        instance.
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

        if '://' not in url:
            url = 'http://' + url

        # Get info for the URL
        result = self.get_link_info(url)
        self._log_if_error(result)
        # See if it was marked as NSFW in the command text
        result.nsfw |= 'nsfw' in rest.lower()
        # Tell the user
        e.protocol.msg(e['reply_to'], result.get_message())

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
            # Skip parts that don't look like URLs
            if '://' not in part:
                continue

            # Get info for the URL
            result = self.get_link_info(part)
            self._log_if_error(result)

            if result.is_error:
                # Try next bit if this one didn't work - might have not really
                # been a valid URL, and we're only guessing after all...
                continue
            else:
                # See if "NSFW" appears anywhere else in the message
                result.nsfw |= 'nsfw' in ''.join(parts[:i] + parts[i + 1:]).lower()
                # Send message only if it was interesting enough
                if not result.is_redundant:
                    e.protocol.msg(e['reply_to'], result.get_message())
                # ... and since we got a useful result, stop processing the message
                break

    def get_link_info(self, original_url):
        """Get information about a URL.

        Using the *original_url* string, run the chain of URL handlers and
        excludes to get a :class:`LinkInfoResult`.
        """
        make_error = partial(LinkInfoResult, original_url, is_error=True)

        url = urlparse(original_url)

        # Skip non-HTTP(S) URLs
        if url.scheme not in ('http', 'https'):
            return make_error('not a recognised URL scheme: {}'.format(url.scheme))

        # Try handlers in registration order
        for h in self.handlers:
            match = h.filter(url)
            if match:
                result = h.handler(url, match)
                if result is not None:
                    # Useful result, return it
                    return result
                elif h.exclusive:
                    # No result, and exclusive handler
                    return make_error('exclusive handler gave no result')
                else:
                    # No result, fall through to next handler
                    pass
        # If no handlers gave a response, use the default handler
        else:
            # Check that the URL hasn't been excluded
            for f in self.excludes:
                if f(url):
                    return make_error('URL excluded')
            # Invoke the default handler if not excluded
            else:
                return self.scrape_html_title(url)

    def scrape_html_title(self, url):
        """Scrape the ``<title>`` tag contents from the HTML page at *url*.

        Returns a :class:`LinkInfoResult`.
        """
        make_error = partial(LinkInfoResult, url.geturl(), is_error=True)

        # Let's see what's on the other end...
        r = simple_http_get(url.geturl())
        # Only bother with 200 OK
        if r.status_code != requests.codes.ok:
            return make_error('HTTP request failed: {}'.format(r.status_code))
        if 'html' not in r.headers['Content-Type']:
            return make_error('Content-Type not HTML-ish: {}'
                              .format(r.headers['Content-Type']))

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
            return make_error('failed to find <title>')

        # Normalise title whitespace
        title = ' '.join(title.text.strip().split())
        # Build result
        result = LinkInfoResult(url, title, nsfw=url.netloc.endswith('.xxx'))
        # See if the title is redundant, i.e. appears in the URL
        result.is_redundant = self._filter_title_in_url(url, title)
        return result

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
            self.log.debug('title "{}" matches domain name "{}"'.format(
                title, url.netloc))
            return True

        # Attempt 1: is the slugified title entirely within the URL path?
        if title in path:
            self.log.debug('title "{}" in "{}"'.format(title, path))
            return True

        # Attempt 2: is some part of the URL path the start of the title?
        slug_length = int(self.config_get('minimum_slug_length'))
        for part in path.split('/'):
            ratio = float(len(part)) / float(len(title))
            if (len(part) >= slug_length and title.startswith(part) and
                    ratio >= float(self.config_get('minimum_path_match'))):
                self.log.debug('path part "{}" matches title "{}"'.format(
                    part, title))
                return True

        # Didn't match
        return False

    def _log_if_error(self, result):
        """If *result* represents an error, log it.
        """
        if result is not None and result.is_error:
            self.log.debug(result.text + ' (' + result.url + ')')

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
