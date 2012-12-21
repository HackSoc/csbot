from csbot.plugin import Plugin
from csbot.util import nick


class Auth(Plugin):
    def setup(self):
        super(Auth, self).setup()
        self.accounts = {}

    @Plugin.hook('core.user.identified')
    def _user_identified(self, e):
        nick_ = nick(e['user'])
        self.accounts[nick_] = e['account']

    @Plugin.hook('core.user.renamed')
    def _user_renamed(self, e):
        """Keep account information across nick changes."""
        if e['oldnick'] in self.accounts:
            self.accounts[e['newnick']] = self.accounts[e['oldnick']]
            del self.accounts[e['oldnick']]

    @Plugin.hook('core.user.quit')
    def _user_quit(self, e):
        self.accounts.pop(nick(e['user']), None)

    def account(self, nick):
        """Get the account associated with *nick*, or return None."""
        return self.accounts.get(nick, None)

    @Plugin.command('account', help=('account [nick]: show Freenode account for'
                                     ' a nick, or for yourself if omitted'))
    def account_command(self, e):
        nick_ = e['data'] or nick(e['user'])
        account = self.account(nick_)
        if account is None:
            e.protocol.msg(e['reply_to'],
                           u'{} is not authenticated'.format(nick_))
        else:
            e.protocol.msg(e['reply_to'],
                           u'{} is authenticated as {}'.format(nick_, account))
