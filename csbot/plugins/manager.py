from csbot.core import Plugin, PluginError


class PluginManager(Plugin):
    @Plugin.command('plugins')
    def plugins(self, event):
        names = sorted(event.bot.plugins)
        event.protocol.msg(event['reply_to'], ', '.join(names))

    @Plugin.command('plugins.available')
    def available(self, event):
        names = sorted(event.bot.plugins.discover().keys())
        event.protocol.msg(event['reply_to'], ', '.join(names))

    @Plugin.command('plugins.load')
    def load(self, event):
        available = event.bot.plugins.discover()
        self.plugin_loader_helper(event, 'loaded',
                lambda x: (x not in available) or x in event.bot.plugins,
                event.bot.plugins.load)

    @Plugin.command('plugins.unload')
    def unload(self, event):
        self.plugin_loader_helper(event, 'unloaded',
                lambda x: x not in event.bot.plugins,
                event.bot.plugins.unload)

    def plugin_loader_helper(self, event, verb, ignore, operation):
        success = list()
        failure = list()
        ignored = list()

        for name in event.arguments():
            if ignore(name):
                ignored.append(name)
                continue
            try:
                operation(name)
                success.append(name)
            except PluginError as e:
                failure.append(name)
                event.protocol.msg(event['reply_to'],
                                   'Error: ' + str(e))

        reply = list()
        for group, members in zip((verb, 'failed', 'ignored'),
                                  (success, failure, ignored)):
            if len(members) > 0:
                reply.append(group + ': ' + ', '.join(members))
        reply = '; '.join(reply)

        if reply:
            event.protocol.msg(event['reply_to'], reply)
