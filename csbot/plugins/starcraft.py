from csbot.core import Plugin
from csbot.util import nick


class Starcraft(Plugin):
    """
    This plugin allows people to request starcraft games, notifying
    anyone who has registered for a game.
    """

    @Plugin.command('starcraft')
    def starcraft(self, event):
        if 'users' in event.bot.plugins:
            requestor = nick(event['user'])
            users = event.bot.plugins['users'].get_users_by_tag('starcraft')
            names = [usr['user'] for usr in users]
            if requestor in names:
                names.remove(requestor)
            if len(names) > 0:
                message = ", ".join(names)
                message += ", {} wants to play StarCraft".format(requestor)
                event.reply(message)
            else:
                event.reply("Sorry, nobody else wants to play.")
        else:
            event.reply("Sorry, without the users plugin loaded I'm useless.")

