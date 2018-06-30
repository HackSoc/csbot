from csbot.plugin import Plugin
from csbot.util import nick


class Whois(Plugin):
    """Associate data with a user and a channel. Users can update their own
    data, and it persists over nick changes."""

    PLUGIN_DEPENDS = ['usertrack']

    whoisdb = Plugin.use('mongodb', collection='whois')

    def whois_lookup(self, nick, channel, db=None):
        """Performs a whois lookup for a nick"""
        db = db or self.whoisdb

        for ident in (self.identify_user(nick, channel),  # lookup channel specific first
                      self.identify_user(nick)):          # default fallback
            user = db.find_one(ident)
            if user:
                return user['data']

    def whois_set(self, nick, whois_str, channel=None, db=None):
        db = db or self.whoisdb

        ident = self.whois_unset(nick, channel=channel)
        ident['data'] = whois_str
        db.insert(ident)

    def whois_unset(self, nick, channel=None, db=None):
        db = db or self.whoisdb

        ident = self.identify_user(nick, channel=channel)
        db.remove(ident)

        return ident

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

    @Plugin.command('whois.setlocal', help=('whois.setlocal [whois_text]: sets the whois text'
                                            ' for the user, but only for the current channel'))
    def setlocal(self, e):
        """Allow a user to associate data with themselves for this channel."""
        self.whois_set(nick(e['user']), e['data'], channel=e['channel'])

    set_help = ('whois.setdefault [default_whois]: sets the default'
                ' whois text for the user, used when no channel-specific'
                ' one is set')
    @Plugin.command('whois.set', help=set_help)
    @Plugin.command('whois.setdefault', help=set_help)
    def setdefault(self, e):
        self.whois_set(nick(e['user']), e['data'], channel=None)
        e.reply('Set global whois for {}'.format(nick(e['user'])))

    @Plugin.command('whois.unsetlocal', help=('whois.unsetlocal: unsets the local whois text for the user'
                                              ' but only for this channel'
                                              ' (the global whois for the user is unaffected'))
    def unsetlocal(self, e):
        self.whois_unset(nick(e['user']), channel=e['channel'])

    unset_help = ('whois.unsetdefault: unsets the global whois text for the user.'
                  ' Locally set whois texts will be unaffected')
    @Plugin.command('whois.unset', help=unset_help)
    @Plugin.command('whois.unsetdefault', help=unset_help)
    def unsetdefault(self, e):
        nick_ = nick(e['user'])
        whois = self.whois_lookup(nick_, e['channel'])
        self.whois_unset(nick_)
        if whois:
            e.reply('Unset global whois for {} (was: {})'.format(nick_, str(whois)))
        else:
            e.reply('Unset global whois for {}')

    def identify_user(self, nick, channel=None):
        """Identify a user: by account if authed, if not, by nick. Produces a dict
        suitable for throwing at mongo."""

        user = self.bot.plugins['usertrack'].get_user(nick)

        if user['account'] is not None:
            return {'account': user['account'],
                    'channel': channel}
        else:
            return {'nick': nick,
                    'channel': channel}
