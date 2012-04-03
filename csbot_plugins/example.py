from csbot import Plugin


class EmptyPlugin(Plugin):
    pass


class Example(Plugin):
    def setup(self):
        self.bot.register_command('test', self.test_command)

    def test_command(self, user, channel, data):
        self.bot.reply(user, channel,
                       'test invoked: {}'.format((user, channel, data)))

    def privmsg(self, user, channel, msg):
        print ">>>", msg

    def action(self, user, channel, action):
        print "*", action
