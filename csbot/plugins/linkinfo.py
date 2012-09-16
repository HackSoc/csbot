import logging

import requests
import lxml.html

from csbot.plugin import Plugin


class LinkInfo(Plugin):
    log = logging.getLogger(__name__)

    @Plugin.hook('core.message.privmsg')
    def entry_point(self, e):
        # Attempt to grab a URL and protocol
        url = e['message'].split(None, 1)[0]
        protocol = url.split('://', 1)[0]

        # We probably can't do anything useful with non-HTTP URLs
        if protocol not in ('http', 'https'):
            return

        # Let's see what's on the other end...
        r = requests.get(url)
        # Only bother with 200 OK
        if r.status_code != requests.codes.ok:
            return
        # Also only bother with HTML responses
        if 'html' not in r.headers['Content-Type']:
            return

        # Attempt to scrape the HTML for a <title>
        html = lxml.html.document_fromstring(r.text)
        title = html.find('.//title')

        if title is not None:
            e.protocol.msg(e['reply_to'], u'Title: "{}"'.format(title.text))
        else:
            self.log.warn('failed to find <title> at ' + url)
