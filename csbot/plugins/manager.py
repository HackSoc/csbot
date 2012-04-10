from csbot.core import Plugin, PluginFeatures, PluginError


class PluginManager(Plugin):
    features = PluginFeatures()

    @features.command('plugins.available')
    def available(self, event):
        names = sorted(event.bot.discover_plugins())
        event.reply(', '.join(names))

    @features.command('plugins.load')
    def load(self, event):
        available = event.bot.discover_plugins()
        self.plugin_loader_helper(event, 'loaded',
                lambda x: (x not in available) or event.bot.has_plugin(x),
                event.bot.load_plugin)

    @features.command('plugins.unload')
    def unload(self, event):
        self.plugin_loader_helper(event, 'unloaded',
                lambda x: not event.bot.has_plugin(x),
                event.bot.unload_plugin)

    @features.command('plugins.reload')
    def reload(self, event):
        self.plugin_loader_helper(event, 'reloaded',
                lambda x: not event.bot.has_plugin(x),
                event.bot.reload_plugin)

    def plugin_loader_helper(self, event, verb, ignore, operation):
        success = list()
        failure = list()
        ignored = list()

        for name in event.data:
            if ignore(name):
                ignored.append(name)
                continue
            try:
                operation(name)
                success.append(name)
            except PluginError as e:
                failure.append(name)
                event.error(str(e))

        reply = list()
        for group, members in zip((verb, 'failed', 'ignored'),
                                  (success, failure, ignored)):
            if len(members) > 0:
                reply.append(group + ': ' + ', '.join(members))
        reply = '; '.join(reply)

        if reply:
            event.reply(reply)
