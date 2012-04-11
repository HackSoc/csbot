from csbot.core import Plugin, PluginFeatures
from csbot.util import nick


class EmptyPlugin(Plugin):
    pass


class Example(Plugin):
    features = PluginFeatures()

    @features.command('test')
    def test_command(self, event):
        event.reply(('test invoked: {0.user}, {0.channel}, '
                     '{0.data}').format(event))
        event.reply('raw data: ' + event.raw_data, is_verbose=True)

    @features.command('cfg')
    def test_cfg(self, event):
        if len(event.data) == 0:
            event.error("You need to tell me what to look for!")
        else:
            try:
                event.reply("{} = {}".format(event.data[0],
                                             self.cfg(event.data[0])))
            except KeyError:
                event.error("I don't know a {}".format(event.data[0]))

    @features.command('set')
    def test_set(self, event):
        try:
            key = event.data[0]
            val = event.data[1]

            self.set(key, val)

            event.reply("{} has been set to {}.".format(key, val))
        except IndexError:
            event.error("You need to tell me the name and the value to store!")

    @features.command('get')
    def test_get(self, event):
        key = event.data[0]

        try:
            event.reply("{} is {}.".format(key, self.get(key)))
        except KeyError:
            event.error("I don't know the meaning of {}.".format(key))

    @features.hook('privmsg')
    def privmsg(self, event):
        print '[{timestamp}][{event.channel}] <{nick}> {event.message}'.format(
                event=event,
                nick=nick(event.user),
                timestamp=event.datetime.strftime('%Y/%m/%d %H:%M'))

    @features.hook('action')
    def action(self, event):
        print '[{timestamp}][{event.channel}] * {nick} {event.message}'.format(
                event=event,
                nick=nick(event.user),
                timestamp=event.datetime.strftime('%Y/%m/%d %H:%M'))

    @features.hook('userJoined')
    def userJoined(self, event):
        print '[{timestamp}][{event.channel}] {event.user} has joined'.format(
                event=event,
                timestamp=event.datetime.strftime('%Y/%m/%d %H:%M'))

    @features.hook('userLeft')
    def userLeft(self, event):
        print '[{timestamp}][{event.channel}] {event.user} has left'.format(
                event=event,
                timestamp=event.datetime.strftime('%Y/%m/%d %H:%M'))

    @features.hook('userQuit')
    def userQuit(self, event):
        print '[{timestamp}] {event.user} quit ({event.message})'.format(
                event=event,
                timestamp=event.datetime.strftime('%Y/%m/%d %H:%M'))

    @features.hook('names')
    def names(self, event):
        print '[{timestamp}][{event.channel}] NAMES: {event.raw_names}'.format(
                event=event,
                timestamp=event.datetime.strftime('%Y/%m/%d %H:%M'))
