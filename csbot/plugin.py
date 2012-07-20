import types


class PluginFeatures(object):
    """Utility class to simplify defining plugin features.

    Plugins can define hooks and commands.  This class provides a
    decorator-based approach to creating these features.
    """
    def __init__(self):
        self.commands = dict()
        self.hooks = dict()

    def instantiate(self, inst):
        """Create a duplicate :class:`PluginFeatures` bound to *inst*.

        Returns an exact duplicate of this object, but every method that has
        been registered with a decorator is bound to *inst* so when it's called
        it acts like a normal method call.
        """
        cls = inst.__class__
        features = PluginFeatures()
        features.commands = dict((c, types.MethodType(f, inst, cls))
                                 for c, f in self.commands.iteritems())
        features.hooks = dict((h, [types.MethodType(f, inst, cls) for f in fs])
                              for h, fs in self.hooks.iteritems())
        return features

    def hook(self, hook):
        """Create a decorator to register a handler for *hook*.
        """
        if hook not in self.hooks:
            self.hooks[hook] = list()

        def decorate(f):
            self.hooks[hook].append(f)
            return f
        return decorate

    def command(self, command, help=None):
        """Create a decorator to register a handler for *command*.

        Raises a :class:`KeyError` if this class has already registered a
        handler for *command*.
        """
        if command in self.commands:
            raise KeyError('Duplicate command: {}'.format(command))

        def decorate(f):
            f.help = help
            self.commands[command] = f
            return f
        return decorate

    def fire_hooks(self, event):
        """Fire plugin hooks associated with ``event.event_type``.

        Hook handlers are run in the order they were registered, which should
        correspond to the order they were defined if decorators were used.
        """
        hooks = self.hooks.get(event.event_type, list())
        for h in hooks:
            h(event)


class Plugin(object):
    """Bot plugin base class.
    """

    features = PluginFeatures()

    def __init__(self, bot):
        self.bot = bot
        self.features = self.features.instantiate(self)
        self.db_ = None

    @classmethod
    def plugin_name(cls):
        """Get the plugin's name.

        A plugin's name is its class name in lowercase.  Duplicate plugin names
        are not permitted and plugin names should be handled case-insensitively
        as ``name.lower()``.

        >>> from csbot.plugins.example import EmptyPlugin
        >>> EmptyPlugin.plugin_name()
        'emptyplugin'
        >>> p = EmptyPlugin(None)
        >>> p.plugin_name()
        'emptyplugin'
        """
        return cls.__name__.lower()

    @property
    def db(self):
        if self.db_ is None:
            self.db_ = self.bot.mongodb['csbot__' + self.plugin_name()]
        return self.db_

    def cfg(self, name):
        plugin = self.plugin_name()

        # Check plugin config
        if self.bot.config.has_section(plugin):
            if self.bot.config.has_option(plugin, name):
                return self.bot.config.get(plugin, name)

        # Check default config
        if self.bot.config.has_option("DEFAULT", name):
            return self.bot.config.get("DEFAULT", name)

        # Raise an exception
        raise KeyError("{} is not a valid option.".format(name))

    def get(self, key):
        """Get a value from the plugin key/value store by key. If the key
        is not found, a KeyError is raised.
        """

        plugin = self.plugin_name()

        if self.bot.plugindata.has_section(plugin):
            if self.bot.plugindata.has_option(plugin, key):
                return self.bot.plugindata.get(plugin, key)

        raise KeyError("{} is not defined.".format(key))

    def set(self, key, value):
        """Set a value in the plugin key/value store by key.
        """

        plugin = self.plugin_name()

        if not self.bot.plugindata.has_section(plugin):
            self.bot.plugindata.add_section(plugin)

        self.bot.plugindata.set(plugin, key, value)

    def setup(self):
        """Run setup actions for the plugin.

        This should be overloaded in plugins to perform actions that need to
        happen before receiving any events.

        .. note:: Plugin setup order is not guaranteed to be consistent, so do
                  not rely on it.
        """
        pass

    def teardown(self):
        """Run teardown actions for the plugin.

        This should be overloaded in plugins to perform teardown actions, for
        example writing stuff to file/database, before the bot is destroyed.

        .. note:: Plugin teardown order is not guaranteed to be consistent, so
                  do not rely on it.
        """
        pass
