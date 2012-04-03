from csbot.core import Plugin, command


class EmptyPlugin(Plugin):
    pass


class Example(Plugin):
    @command('test')
    def test_command(self, user, channel, data):
        self.bot.reply(user, channel,
                       'test invoked: {}'.format((user, channel, data)))

    @command('cfg')
    def test_cfg(self, user, channel, data):
        msg = "You need to tell me what to look for!"

        if len(data) > 0:
            try:
                msg = "{} = {}".format(data[0], self.cfg(data[0]))
            except Exception:
                msg = "I don't know a {}".format(data[0])

        self.bot.reply(user, channel, msg)

    def privmsg(self, user, channel, msg):
        print ">>>", msg

    def action(self, user, channel, action):
        print "*", action
