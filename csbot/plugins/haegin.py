from csbot.core import Plugin, command


class TellPlugin(Plugin):
    @command('tell')
    def test_command(self, event):
        if (event)
        event.reply(('test invoked: {0.user}, {0.channel}, '
                     '{0.data}').format(event))
        event.reply('raw data: ' + event.raw_data, is_verbose=True)

    @command('cfg')
    def test_cfg(self, event):
        if len(event.data) == 0:
            event.error("You need to tell me what to look for!")
        else:
            try:
                event.reply("{} = {}".format(event.data[0],
                                             self.cfg(event.data[0])))
            except KeyError:
                event.error("I don't know a {}".format(event.data[0]))

    def privmsg(self, user, channel, msg):
        print ">>>", msg

    def action(self, user, channel, action):
        print "*", action
