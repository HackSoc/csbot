from itertools import chain
from functools import partial
import collections
import logging

import straight.plugin


class PluginError(Exception):
    pass


class PluginBase(object):
    """Minimal plugin base class to work with :class:`PluginManager`."""
    @classmethod
    def plugin_name(cls):
        """Get the short name of the plugin, by default the class name in
        lowercase."""
        return cls.__name__.lower()

    @classmethod
    def qualified_plugin_name(cls):
        """Get the fully qualified class name, most useful when dealing with
        ambiguous (non-unique) short names.
        """
        return '{}.{}'.format(cls.__module__, cls.__name)

    def setup(self):
        """Called after the plugin is loaded.  This is where a plugin should
        perform its own setup.

        .. note:: Plugin loading order is unlikely to be consistent, so
                  interaction with other plugins in this method is discouraged.
        """
        pass

    def teardown(self):
        """Called before the plugin is unloaded.  This is where a plugin should
        perform its own cleanup.

        .. note:: Plugin unloading order is unlikely to be consistent, so
                  interaction with other plugins in this method is discouraged.
        """
        pass


class PluginManager(collections.Mapping):
    """A generic plugin manager based on :mod:`straight.plugin`.

    The plugin manager will discover and manage plugins under *namespace* that
    subclass *baseclass*.  When creating a new plugin instance, *args* is
    passed as arguments to the constructor.

    The :class:`PluginBase` class demonstrates the minimum interface that the
    plugin manager expects from plugin classes.

    Optionally *static* can be used to supply a list of plugins that are always
    loaded, and are called by :meth:`broadcast` before any other.  They are not
    managed by the plugin manager, so :meth:`~PluginBase.setup` and
    :meth:`~PluginBase.teardown` are not called.
    """

    #: Plugins that are always loaded.
    static = []
    #: Currently loaded plugins.
    plugins = {}

    def __init__(self, namespace, baseclass, args=None, static=None):
        self.__namespace = namespace
        self.__baseclass = baseclass
        self.__args = args or []
        self.static = static or []
        self.plugins = {}
        self.log = logging.getLogger(__name__)

    def discover(self):
        """Discover available plugins.

        Return a dict mapping plugin names to plugin classes.  A
        :exc:`PluginError` is raised if multiple plugins have the same short
        name.
        """
        plugins = straight.plugin.load(self.__namespace,
                                       subclasses=self.__baseclass)
        available = {}

        for P in plugins:
            name = P.plugin_name()
            if name in available:
                raise PluginError('name conflict "{}":  {} and {}'.format(
                        P.plugin_name(),
                        available[name].qualified_plugin_name(),
                        P.qualified_plugin_name()))
            else:
                available[name] = P

        return available

    def load(self, name):
        """Load a plugin, returning True if the plugin exists, otherwise
        returning False.
        """
        if name in self.plugins:
            self.log.warn('plugin already loaded: {}'.format(name))
            return True

        available = self.discover()
        if name not in available:
            self.log.error('plugin not found: {}'.format(name))
            return False

        p = available[name](*self.__args)
        self.plugins[name] = p
        self.log.info('plugin loaded: {}'.format(name))
        p.setup()
        return True

    def unload(self, name):
        """Unload a plugin."""
        if name not in self.plugins:
            self.log.warn('plugin not loaded: {}'.format(name))

        p = self.plugins.pop(name)
        p.teardown()
        self.log.info('plugin unloaded: {}'.format(name))

    def broadcast(self, method, *args, **kwargs):
        """Call ``p.method(*args, **kwargs)`` on every plugin."""
        # Follow "static" plugins with dynamic plugins - using .values()
        # instead of .itervalues() because plugin loading/unloading would
        # invalidate the iterator, and these are valid things to happen at any
        # time.
        for p in chain(self.static, self.plugins.values()):
            getattr(p, method)(*args, **kwargs)

    # Implement abstract "read-only" Mapping interface

    def __getitem__(self, key):
        return self.plugins[key]

    def __len__(self):
        return len(self.plugins)

    def __iter__(self):
        return iter(self.plugins)


class PluginMeta(type):
    """Metaclass for :class:`Plugin` that collects methods tagged with plugin
    feature decorators.
    """
    def __init__(cls, name, bases, dict):
        super(PluginMeta, cls).__init__(name, bases, dict)

        # Initialise plugin features
        cls.plugin_hooks = {}
        cls.plugin_cmds = []

        # Scan for callables decorated with Plugin.hook, Plugin.command
        for f in dict.itervalues():
            for h in getattr(f, 'plugin_hooks', ()):
                if h in cls.plugin_hooks:
                    cls.plugin_hooks[h].append(f)
                else:
                    cls.plugin_hooks[h] = [f]
            for cmd in getattr(f, 'plugin_cmds', ()):
                cls.plugin_cmds.append((cmd, f))


class Plugin(PluginBase):
    """Bot plugin base class.

    All bot plugins should inherit from this class.  It provides convenience
    methods for hooking events, registering commands, accessing MongoDB and
    manipulating the configuration file.
    """
    __metaclass__ = PluginMeta

    CONFIG_DEFAULTS = {}

    def __init__(self, bot):
        self.bot = bot
        self.db_ = None

    def fire_hooks(self, event):
        """Execute all of this plugin's handlers for *event*."""
        for f in self.plugin_hooks.get(event.event_type, ()):
            f(self, event)

    def setup(self):
        """Plugin setup; register all commands provided by the plugin.
        """
        for cmd, f in self.plugin_cmds:
            self.bot.register_command(cmd, partial(f, self), tag=self)

    def teardown(self):
        """Plugin teardown; unregister all commands provided by the plugin.
        """
        self.bot.unregister_commands(tag=self)

    @staticmethod
    def hook(hook):
        def decorate(f):
            if hasattr(f, 'plugin_hooks'):
                f.plugin_hooks.add(hook)
            else:
                f.plugin_hooks = set((hook,))
            return f
        return decorate

    @staticmethod
    def command(cmd):
        def decorate(f):
            if hasattr(f, 'plugin_cmds'):
                f.plugin_cmds.add(cmd)
            else:
                f.plugin_cmds = set((cmd,))
            return f
        return decorate

    @property
    def config(self):
        """Get the configuration section for this plugin.

        If the config section doesn't exist yet, it is created empty.
        """
        plugin = self.plugin_name()
        if plugin not in self.bot.config_root:
            self.bot.config_root[plugin] = {}
        return self.bot.config_root[plugin]

    def config_get(self, key):
        """Convenience wrapper proxying ``get()`` on :attr:`config`.

        It's common to want to get a configuration value with a fallback to
        some default.  This method simplifies the ugly syntax of

            foo = self.config.get(key, self.CONFIG_DEFAULTS[key])

        by making the fallback value implied if *key* exists in
        :attr:`CONFIG_DEFAULTS`.  If there is no default for *key* then this
        method acts just like ``self.config[key]``, and will throw a KeyError
        if *key* isn't present in the configuration.
        """
        if key in self.CONFIG_DEFAULTS:
            return self.config.get(key, self.CONFIG_DEFAULTS[key])
        else:
            return self.config[key]

    def config_getboolean(self, key):
        """Identical to :meth:`config_get`, but proxying ``getboolean``.
        """
        if key in self.CONFIG_DEFAULTS:
            return self.config.getboolean(key, self.CONFIG_DEFAULTS[key])
        else:
            return self.config.getboolean(key)

    # Methods copied from old Plugin class
    # TODO: tidy these up

    @property
    def db(self):
        if self.db_ is None:
            self.db_ = self.bot.mongodb['csbot__' + self.plugin_name()]
        return self.db_
