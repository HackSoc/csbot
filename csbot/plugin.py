import types
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
        # Follow "static" plugins with dynamic plugins - using .values() instead
        # of .itervalues() because plugin loading/unloading would invalidate the
        # iterator, and these are valid things to happen at any time.
        for p in chain(self.static, self.plugins.values()):
            getattr(p, method)(*args, **kwargs)

    # Implement abstract "read-only" Mapping interface
    
    def __getitem__(self, key):
        return self.plugins[key]

    def __len__(self):
        return len(self.plugins)

    def __iter__(self):
        return iter(self.plugins)


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
    """Bot plugin base class."""
    __metaclass__ = PluginMeta

    def __init__(self, bot):
        self.bot = bot
        self.db_ = None

    def fire_hooks(self, event):
        """Execute all of this plugin's handlers for *event*."""
        for f in self.plugin_hooks.get(event.event_type, ()):
            f(self, event)

    def setup(self):
        for cmd, f in self.plugin_cmds:
            self.bot.register_command(cmd, partial(f, self), tag=self)

    def teardown(self):
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

    # Methods copied from old Plugin class
    # TODO: tidy these up

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
