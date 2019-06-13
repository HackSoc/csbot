import os.path
import re
from urllib.parse import urlparse
import collections
from collections import namedtuple
import datetime
from functools import partial

import aiohttp
import lxml.etree
import lxml.html

from ..plugin import Plugin
from ..util import Struct, simple_http_get_async, maybe_future_result
from .. import config


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
    @config.config
    class Config:
        scan_limit = config.option(int, default=1, help="Maximum number of parts of a PRIVMSG to scan for URLs")
        minimum_slug_length = config.option(int, default=10, help="Minimum slug length in 'title in URL' filter")
        max_file_ext_length = config.option(
            int, default=6, help="Maximum file extension length (including the dot) for 'title in URL' filter")
        minimum_path_match = config.option(
            float, default=0.5,
            help="Minimum match (fraction) between path component and title to be considered 'title in URL'")
        rate_limit_time = config.option(int, default=60, help="Number of seconds for rolling rate limit period")
        rate_limit_count = config.option(int, default=5, help="maximum rate of URL responses over rate limiting period")
        max_response_size = config.option(int, default=1048576, help="Maximum HTTP response size (in bytes)")

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
    async def link_command(self, e):
        """Handle the "link" command.

        Fetch information about a specified URL, e.g.
        ``!link http://google.com``.  The link can be explicitly marked as NSFW
        by including the string anywhere in the trailing string, e.g.
        ``!link http://lots-of-porn.com nsfw``.
        """
        # Split command data into the URL and any trailing information
        parts = e['data'].split(None, 1)
        if len(parts) < 1:
            e.reply('No URL supplied')
            return
        url = parts[0]
        rest = parts[1] if len(parts) > 1 else ''

        if '://' not in url:
            url = 'http://' + url

        # Get info for the URL
        result = await self.get_link_info(url)
        self._log_if_error(result)
        # See if it was marked as NSFW in the command text
        result.nsfw |= 'nsfw' in rest.lower()
        # Tell the user
        e.reply(result.get_message())

    @Plugin.hook('core.message.privmsg')
    async def scan_privmsg(self, e):
        """Scan the data of PRIVMSG events for URLs and respond with
        information about them.
        """
        # Don't want to be scanning URLs inside commands,
        # especially because we'd show information twice when the "link"
        # command is invoked...
        if e['message'].startswith(self.bot.config_get('command_prefix')):
            return

        parts = e['message'].split()
        for i, part in enumerate(parts[:self.config.scan_limit]):
            # Skip parts that don't look like URLs
            if '://' not in part:
                continue

            # Skip rest of message if we've auto-replied to URLs too frequently
            if self._rate_limited():
                break

            # Get info for the URL
            result = await self.get_link_info(part)
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
                    e.reply(result.get_message())
                # ... and since we got a useful result, stop processing the message
                break

    async def get_link_info(self, original_url):
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
                result = await maybe_future_result(h.handler(url, match), log=self.log)
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
                try:
                    return await self.scrape_html_title(url)
                except aiohttp.ClientConnectionError:
                    return make_error('Connection error')

    async def scrape_html_title(self, url):
        """Scrape the ``<title>`` tag contents from the HTML page at *url*.

        Returns a :class:`LinkInfoResult`.
        """
        make_error = partial(LinkInfoResult, url.geturl(), is_error=True)

        # Let's see what's on the other end...
        async with simple_http_get_async(url.geturl()) as r:
            # Only bother with 200 OK
            if r.status != 200:
                return make_error('HTTP request failed: {} {}'
                                  .format(r.status, r.reason))
            # Only process HTML-ish responses
            if 'Content-Type' not in r.headers:
                return make_error('No Content-Type header')
            elif 'html' not in r.headers['Content-Type']:
                return make_error('Content-Type not HTML-ish: {}'
                                  .format(r.headers['Content-Type']))
            # Don't try to process massive responses
            if 'Content-Length' in r.headers:
                max_size = self.config.max_response_size
                if int(r.headers['Content-Length']) > max_size:
                    return make_error('Content-Length too large: {} bytes, >{}'
                                      .format(r.headers['Content-Length'], max_size))

            # Get the correct parser
            # If present, charset attribute in HTTP Content-Type header takes
            # precedence, but fallback to default if encoding isn't recognised
            parser = lxml.html.html_parser
            if r.charset is not None:
                encoding = r.charset
                try:
                    parser = lxml.html.HTMLParser(encoding=encoding)
                except LookupError:
                    pass    # Oh well

            # In case Content-Length is absent on a massive file, get only a
            # reasonable chunk instead. We don't just get the first chunk
            # because chunk-encoded responses iterate over chunks rather than
            # the size we request...
            chunk = b''
            async for next_chunk in r.content.iter_chunked(self.config.max_response_size):
                chunk += next_chunk
                if len(chunk) >= self.config.max_response_size:
                    break
            # Try to trim chunk to a tag end to help the HTML parser out
            try:
                chunk = chunk[:chunk.rindex(b'>') + 1]
            except ValueError:
                pass

            # Attempt to parse as an HTML document
            html = lxml.etree.fromstring(chunk, parser)
            if html is None:
                return make_error('Response not usable as HTML')

            # Attempt to get the <title> tag
            title = html.findtext('.//title') or ''
            # Normalise title whitespace
            title = ' '.join(title.strip().split())

            if not title:
                return make_error('Missing or empty <title> tag')

            # Build result
            result = LinkInfoResult(url, title,
                                    nsfw=url.netloc.endswith('.xxx'))
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
            if len(ext) <= self.config.max_file_ext_length:
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
        slug_length = self.config.minimum_slug_length
        for part in path.split('/'):
            ratio = float(len(part)) / float(len(title))
            if (len(part) >= slug_length and title.startswith(part) and
                    ratio >= self.config.minimum_path_match):
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
            seconds=self.config.rate_limit_time)
        count = self.config.rate_limit_count

        if len(self.rate_limit_list) < count:
            self.rate_limit_list.append(now)
            return False

        if self.rate_limit_list[0] + delta < now:
            self.rate_limit_list.popleft()
            self.rate_limit_list.append(now)
            return False

        self.log.debug('rate limiting URL responses')
        return True
