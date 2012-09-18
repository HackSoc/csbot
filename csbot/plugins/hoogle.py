import logging
import requests
import urllib

from csbot.plugin import Plugin


class Hoogle(Plugin):
    CONFIG_DEFAULTS = {
        'results': 5,
    }

    log = logging.getLogger(__name__)

    def setup(self):
        super(Hoogle, self).setup()

    @Plugin.command('hoogle')
    def search_hoogle(self, e):
        """Search Hoogle with a given string and return the first few
        (exact number configurable) results.
        """

        query = e['data']
        hurl = 'http://www.haskell.org/hoogle/?mode=json&hoogle=' + query
        hresp = requests.get(hurl)

        if hresp.status_code != requests.codes.ok:
            self.log.warn(u'request failed for ' + hurl)
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

        maxresults = 0

        try:
            maxresults = int(self.config_get('results'))
        except ValueError:
            self.log.warn(u'"results" is not an integer!')

        if hresp.json is None:
            self.log.warn(u'invalid JSON received from Hoogle')
            return

        allresults = hresp.json[u'results']
        totalresults = len(allresults)
        results = allresults[0:maxresults]
        niceresults = []

        for result in results:
            niceresults.append(result[u'self'])

        encqry = urllib.quote(query.encode('utf-8'))
        fullurl = 'http://www.haskell.org/hoogle/?hoogle=' + encqry

        e.protocol.msg(
            e['reply_to'], u'Showing {} of {} results: {} ({})'.format(
                maxresults if maxresults < totalresults else totalresults,
                totalresults,
                '; '.join(niceresults),
                fullurl))
