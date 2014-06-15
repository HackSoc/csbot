from csbot.plugin import Plugin


class Whois(Plugin):
    """Associate data with a user and a channel. Users can update their own
    data, and it persists over nick changes."""

    whoisdb = Plugin.use('mongodb', collection='whois')

    def setup(self):
        super(Whois, self).setup()

    @Plugin.command('whois', help=('whois [nick]: show whois data for'
                                   ' a nick, or for yourself if omitted'))
    def whois(self, e):
        """Look up a user by nick, and return what data they have set for
        themselves (or an error message if there is no data)"""

        nick = e['data'] or e['user'].split('!', 1)[0]
        user = self.whoisdb.find_one({'nick': nick,
                                      'channel': e['channel']})

        if user is None:
            e.protocol.msg(e['reply_to'], u'No data for {}'.format(nick))
        else:
            e.protocol.msg(e['reply_to'], u'{}: {}'.format(nick, user['data']))

    @Plugin.command('whois.set')
    def set(self, e):
        """Allow a user to associate data with themselves for this channel."""

        self.whoisdb.remove({'nick': e['user'].split('!', 1)[0],
                             'channel': e['channel']})
        self.whoisdb.insert({'nick': e['user'].split('!', 1)[0],
                             'channel': e['channel'],
                             'data': e['data']})
