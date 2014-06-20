from csbot.plugin import Plugin
from csbot.util import nick


class Whois(Plugin):
    """Associate data with a user and a channel. Users can update their own
    data, and it persists over nick changes."""

    PLUGIN_DEPENDS = ['usertrack']

    whoisdb = Plugin.use('mongodb', collection='whois')

    @Plugin.command('whois', help=('whois [nick]: show whois data for'
                                   ' a nick, or for yourself if omitted'))
    def whois(self, e):
        """Look up a user by nick, and return what data they have set for
        themselves (or an error message if there is no data)"""

        nick_ = e['data'] or nick(e['user'])
        ident = self.identify_user(nick_, e['channel'])
        user = self.whoisdb.find_one(ident)

        if user is None:
            e.protocol.msg(e['reply_to'], 'No data for {}'.format(nick_))
        else:
            e.protocol.msg(e['reply_to'], '{}: {}'.format(nick_, user['data']))

    @Plugin.command('whois.set')
    def set(self, e):
        """Allow a user to associate data with themselves for this channel."""

        ident = self.identify_user(nick(e['user']), e['channel'])
        self.whoisdb.remove(ident)

        ident['data'] = e['data']
        self.whoisdb.insert(ident)

    def identify_user(self, nick, channel):
        """Identify a user: by account if authed, if not, by nick. Produces a dict
        suitable for throwing at mongo."""

        user = self.bot.plugins['usertrack'].get_user(nick)

        if user['account'] is not None:
            return {'account': user['account'],
                    'channel': channel}
        else:
            return {'nick': nick,
                    'channel': channel}
