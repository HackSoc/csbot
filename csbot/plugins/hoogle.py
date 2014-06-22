import requests
import urllib.parse

from csbot.plugin import Plugin
from csbot.util import simple_http_get


class Hoogle(Plugin):
    CONFIG_DEFAULTS = {
        'results': 5,
    }

    def setup(self):
        super(Hoogle, self).setup()

    @Plugin.command('hoogle')
    def search_hoogle(self, e):
        """Search Hoogle with a given string and return the first few
        (exact number configurable) results.
        """

        query = e['data']
        hurl = 'http://www.haskell.org/hoogle/?mode=json&hoogle=' + query
        hresp = simple_http_get(hurl)

        if hresp.status_code != requests.codes.ok:
            self.log.warn('request failed for ' + hurl)
            return

        # The Hoogle response JSON is of the following format:
        # {
        #  "version": "<hoogle version>"
        #  "results": [
        #    {
        #      "location": "<link to docs>"
        #      "self":     "<name> :: <type>"
        #      "docs":     "<short description>"
        #    },
        #    ...
        #  ]
        # }

        maxresults = int(self.config_get('results'))

        if hresp.json is None:
            self.log.warn('invalid JSON received from Hoogle')
            return

        allresults = hresp.json()['results']
        totalresults = len(allresults)
        results = allresults[0:maxresults]
        niceresults = []

        for result in results:
            niceresults.append(result['self'])

        encqry = urllib.parse.quote(query.encode('utf-8'))
        fullurl = 'http://www.haskell.org/hoogle/?hoogle=' + encqry

        e.protocol.msg(
            e['reply_to'], 'Showing {} of {} results: {} ({})'.format(
                maxresults if maxresults < totalresults else totalresults,
                totalresults,
                '; '.join(niceresults),
                fullurl))
