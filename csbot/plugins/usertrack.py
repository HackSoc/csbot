from collections import defaultdict
from copy import deepcopy

from csbot.plugin import Plugin
from csbot.util import nick


class UserDict(defaultdict):
    def __missing__(self, key):
        user = self.create_user(key)
        self[key] = user
        return user

    @staticmethod
    def create_user(nick):
        return {
            'nick': nick,
            'account': None,
            'channels': set(),
        }

    def copy_or_create(self, nick):
        if nick in self:
            return deepcopy(self[nick])
        else:
            return self.create_user(nick)


class UserTrack(Plugin):
    def setup(self):
        super(UserTrack, self).setup()
        self._users = UserDict()

    @Plugin.hook('core.channel.joined')
    def _channel_joined(self, e):
        user = self._users[nick(e['user'])]
        user['channels'].add(e['channel'])

    @Plugin.hook('core.channel.left')
    def _channel_left(self, e):
        user = self._users[nick(e['user'])]
        user['channels'].discard(e['channel'])
        # Lost sight of the user, can't reliably track them any more
        if len(user['channels']) == 0:
            del self._users[nick(e['user'])]

    @Plugin.hook('core.channel.names')
    def _channel_names(self, e):
        for name, prefixes in e['names']:
            user = self._users[name]
            user['channels'].add(e['channel'])

    @Plugin.hook('core.user.identified')
    def _user_identified(self, e):
        user = self._users[nick(e['user'])]
        user['account'] = e['account']

    @Plugin.hook('core.user.renamed')
    def _user_renamed(self, e):
        # Retrieve user record
        user = self._users[e['oldnick']]
        # Remove old nick entry
        del self._users[user['nick']]
        # Rename user
        user['nick'] = e['newnick']
        # Add under new nick
        self._users[user['nick']] = user

    @Plugin.hook('core.user.quit')
    def _user_quit(self, e):
        # User is gone, remove record
        del self._users[nick(e['user'])]

    def get_user(self, nick):
        """Get a copy of the user record for *nick*.
        """
        return self._users.copy_or_create(nick)

    @Plugin.command('account', help=('account [nick]: show Freenode account for'
                                     ' a nick, or for yourself if omitted'))
    def account_command(self, e):
        nick_ = e['data'] or nick(e['user'])
        account = self.get_user(nick_)['account']
        if account is None:
            e.protocol.msg(e['reply_to'],
                           '{} is not authenticated'.format(nick_))
        else:
            e.protocol.msg(e['reply_to'],
                           '{} is authenticated as {}'.format(nick_, account))