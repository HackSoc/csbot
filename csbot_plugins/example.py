from csbot import Plugin


class Example(Plugin):
    HOOKS = ['privmsg']

    def privmsg(self, user, channel, msg):
        pass
