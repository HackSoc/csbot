from csbot.core import Plugin
from csbot.util import nick


class Tags(Plugin):

    PLUGIN_DEPENDS = ['users']

    """
    This plugin allows people to request games, notifying
    anyone who has registered for a game.
    """
    @Plugin.command('play')
    def play(self, event):
        game = event.arguments()[0]
        if 'users' in event.bot.plugins:
            requestor = nick(event['user'])
            users = event.bot.plugins['users'].find_users_by_tag(game)
            nicks = map(str, users)
            if requestor in nicks:
                nicks.remove(requestor)
            if len(nicks) > 0:
                message = ", ".join(nicks)
                message += ": {} wants to play {}".format(requestor, game.title())
                event.reply(message)
            else:
                event.reply("Sorry, nobody else wants to play {}.".format(game.title()))
        else:
            event.reply("Sorry, without the users plugin loaded I'm useless.")

