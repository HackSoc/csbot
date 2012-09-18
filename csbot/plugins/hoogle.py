import json
import logging
import requests

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
        hoogleurl = 'http://www.haskell.org/hoogle/?mode=json&hoogle=' + query
        hoogleresp = requests.get(hoogleurl)

        if hoogleresp.status_code != requests.codes.ok:
            self.log.warn(u'request failed for ' + hoogleurl)
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

        try:
            allresults = json.loads(hoogleresp.text)[u'results']
            totalresults = len(allresults)
            results = allresults[0:maxresults]

            e.protocol.msg(e['reply_to'], u'Showing {} of {} results:'.format(
                maxresults if maxresults < totalresults else totalresults,
                totalresults))

            for result in results:
                e.protocol.msg(e['reply_to'], result[u'self'])
        except ValueError:
            self.log.warn(u'invalid JSON received from Hoogle')
