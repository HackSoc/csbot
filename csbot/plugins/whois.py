from csbot.plugin import Plugin
from csbot.util import nick


class Whois(Plugin):
    """Associate data with a user and a channel. Users can update their own
    data, and it persists over nick changes."""

    PLUGIN_DEPENDS = ['usertrack']

    whoisdb = Plugin.use('mongodb', collection='whois')

    def whois_lookup(self, nick, channel, db=None):
        """Performs a whois lookup for a nick on a specific channel"""
        db = db or self.whoisdb

        ident = self.identify_user(nick, channel)
        user = db.find_one(ident)

        if user is None:
            return None
        else:
            return user['data']

    def whois_set(self, nick, channel, whois_str, db=None):
        db = db or self.whoisdb

        ident = self.identify_user(nick, channel)
        db.remove(ident)

        ident['data'] = whois_str
        db.insert(ident)

    @Plugin.command('whois', help=('whois [nick]: show whois data for'
                                   ' a nick, or for yourself if omitted'))
    def whois(self, e):
        """Look up a user by nick, and return what data they have set for
        themselves (or an error message if there is no data)"""
        nick_ = e['data'] or nick(e['user'])
        res = self.whois_lookup(nick_, e['channel'])

        if res is None:
            e.reply('No data for {}'.format(nick_))
        else:
            e.reply('{}: {}'.format(nick_, str(res)))

    @Plugin.command('whois.set')
    def set(self, e):
        """Allow a user to associate data with themselves for this channel."""
        self.whois_set(nick(e['user']), e['channel'], e['data'])

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
