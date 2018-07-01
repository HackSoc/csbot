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

        for d in (self.whois_lookup_channel(nick, channel),
                  self.whois_lookup_global(nick)):
            if d:
                return d

    def whois_lookup_channel(self, nick, channel):
        return self._lookup(self.identify_user(nick, channel))

    def whois_lookup_global(self, nick):
        return self._lookup(self.identify_user(nick))

    def _lookup(self, ident):
        user = self.whoisdb.find_one(ident)
        if user:
            return user['data']

        return None

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
    @Plugin.command('whois.setdefault', help=set_help)
    def setdefault(self, e):
        self.whois_set(nick(e['user']), e['data'], channel=None)

    @Plugin.command('whois.set', help='sets the whois text for this channel')
    def set(self, e):
        nick_ = nick(e['user'])
        channel = e['channel']
        old_whois = self.whois_lookup_global(nick_)
        local_whois = self.whois_lookup_channel(nick_, channel)

        if local_whois:
            self.setlocal(e)
            fmt = 'set new local whois for {} (was: "{}"). use whois.setdefault to set for all channels'
            self.bot.reply(nick_, fmt.format(channel, str(local_whois)))
        elif old_whois:
            self.setlocal(e)
            fmt = 'set new local whois for {}. use whois.setdefault to set for all channels'
            self.bot.reply(nick_, fmt.format(channel))
        else:
            self.setdefault(e)
            self.bot.reply(nick_, 'set default whois for all channels')

    @Plugin.command('whois.unsetlocal', help=('whois.unsetlocal: unsets the local whois text for the user'
                                              ' but only for this channel'))
    def unsetlocal(self, e):
        self.whois_unset(nick(e['user']), channel=e['channel'])

    unset_help = ('whois.unsetdefault: unsets the default whois text for the user.'
                  ' local, channel-specific, whois text is unaffected')
    @Plugin.command('whois.unsetdefault', help=unset_help)
    def unsetdefault(self, e):
        self.whois_unset(nick(e['user']))

    @Plugin.command('whois.unset', help='unsets the currently set whois for this channel')
    def unset(self, e):
        nick_ = nick(e['user'])
        old_local_whois = self.whois_lookup_channel(nick_, e['channel'])
        old_global_whois = self.whois_lookup_global(nick_)

        if old_local_whois:
            self.unsetlocal(e)
            fmt = 'unset local whois for {} (was: "{}"), use whois.unsetdefault to unset the global default'
            self.bot.reply(nick_, fmt.format(e['channel'], str(old_local_whois)))
        elif old_global_whois:
            self.unsetdefault(e)
            fmt = 'unset default whois for all channels (was: {}). use whois.setdefault to re-set it'
            self.bot.reply(nick_, fmt.format(str(old_global_whois)))

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
