from itertools import chain
from functools import partial
import collections
import logging
import os

import straight.plugin


class PluginBase(object):
    """Minimal plugin base class to work with :class:`PluginManager`."""
    #: Plugins which *must* be loaded before this plugin.
    PLUGIN_DEPENDS = []

    @classmethod
    def plugin_name(cls):
        """Get the name of the plugin, by default the class name in lowercase.
        """
        return cls.__name__.lower()

    @classmethod
    def qualified_name(cls):
        """Get the fully qualified class name, most useful when complaining
        about duplicate plugins names.
        """
        return '{}.{}'.format(cls.__module__, cls.__name__)


class PluginDuplicate(Exception):
    pass


class PluginDependencyUnmet(Exception):
    pass


class PluginFeatureError(Exception):
    pass


class PluginManager(collections.Mapping):
    """A simple plugin manager based on `straight.plugin`_.

    The plugin manager will discover plugins under *namespace* that subclass
    *baseclass*.  Each of *plugins* will be loaded by name, passing *args* as
    arguments to the constructor.

    Optionally, *static* can be used to supply a list of plugins that have
    already been loaded.  These do not have to subclass *baseclass*, but are
    still assumed to follow the same interface.  The :class:`PluginBase` class
    demonstrates the minimum interface that :class:`PluginManager` requires.

    Methods are invoked across all plugins by using :meth:`broadcast`.

    .. _straight.plugin: https://github.com/ironfroggy/straight.plugin
    """

    #: Plugins loaded outside of the plugin manager.
    static = []
    #: Plugins loaded by the plugin manager
    plugins = {}

    def __init__(self, namespace, baseclass, plugins, static=None, args=None):
        self.log = logging.getLogger(__name__)
        self.static = static or []
        self.plugins = collections.OrderedDict()

        args = args or []
        available = self.discover(namespace, baseclass)

        for p in plugins:
            if p in self.plugins:
                self.log.warn('not loading duplicate plugin:  ' + p)
            elif p not in available:
                self.log.error('plugin not found: ' + p)
            else:
                P = available[p]
                for dep in P.PLUGIN_DEPENDS:
                    if dep not in self.plugins:
                        raise PluginDependencyUnmet(
                            "{} depends on {}, which isn't loaded yet"
                            .format(p, dep))
                self.plugins[p] = P(*args)
                self.log.info('plugin loaded: ' + p)

    @staticmethod
    def discover(namespace, baseclass):
        """Discover plugins under *namespace* subclassing *baseclass*.

        Return a dict mapping plugin names to plugin classes.  A
        :exc:`PluginDuplicate` is raised if multiple plugins have the same
        name.
        """
        # Use straight.plugin to discover classes
        plugins = straight.plugin.load(namespace,
                                       subclasses=baseclass)

        # Build available plugins dict, checking for duplicates
        available = {}
        for P in plugins:
            name = P.plugin_name()
            if name in available:
                raise PluginDuplicate(name, P.qualified_name(),
                                      available[name].qualified_name())
            else:
                available[name] = P
        return available

    def broadcast(self, method, args=()):
        """Call ``p.method(*args)`` on every plugin.

        Plugins are always called in the order they were loaded, with static
        plugins being called before loaded plugins.
        """
        for p in chain(self.static, self.plugins.itervalues()):
            getattr(p, method)(*args)

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
        cls.plugin_hooks = collections.defaultdict(list)
        cls.plugin_cmds = []
        cls.plugin_integrations = []

        # Scan for decorated methods
        for f in dict.itervalues():
            for h in getattr(f, 'plugin_hooks', ()):
                cls.plugin_hooks[h].append(f)
            for cmd, metadata in getattr(f, 'plugin_cmds', ()):
                cls.plugin_cmds.append((cmd, metadata, f))
            if len(getattr(f, 'plugin_integrate_with', [])) > 0:
                cls.plugin_integrations.append((f.plugin_integrate_with, f))


class Plugin(PluginBase):
    """Bot plugin base class.

    All bot plugins should inherit from this class.  It provides convenience
    methods for hooking events, registering commands, accessing MongoDB and
    manipulating the configuration file.
    """
    __metaclass__ = PluginMeta

    #: Default configuration values, used automatically by :meth:`config_get`.
    CONFIG_DEFAULTS = {}
    #: Configuration environment variables, used automatically by
    #: :meth:`config_get`.
    CONFIG_ENVVARS = {}

    #: The plugin's logger, created by default using the plugin class'
    #: containing module name as the logger name.
    log = None

    def __init__(self, bot):
        self.log = logging.getLogger(self.__class__.__module__)
        self.bot = bot
        self._db = None

    def fire_hooks(self, event):
        """Execute all of this plugin's handlers for *event*."""
        for f in self.plugin_hooks.get(event.event_type, ()):
            f(self, event)

    def setup(self):
        """Plugin setup.

        * Fire all plugin integration methods.
        * Register all commands provided by the plugin.
        """
        for plugin_names, f in self.plugin_integrations:
            plugins = [self.bot.plugins[p] for p in plugin_names
                       if p in self.bot.plugins]
            # Only fire integration method if all named plugins were loaded
            if len(plugins) == len(plugin_names):
                f(self, *plugins)

        for cmd, meta, f in self.plugin_cmds:
            self.bot.register_command(cmd, meta, partial(f, self), tag=self)

    def teardown(self):
        """Plugin teardown.

        * Unregister all commands provided by the plugin.
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
    def command(cmd, **metadata):
        """Tag a command to be registered by :meth:`setup`.

        Additional keyword arguments are added to a metadata dictionary that
        gets stored with the command.  This is a good place to put, for
        example, the help string for the command::

            @Plugin.command('foo', help='foo: does something amazing')
            def foo_command(self, e):
                pass
        """
        def decorate(f):
            if hasattr(f, 'plugin_cmds'):
                f.plugin_cmds.append((cmd, metadata))
            else:
                f.plugin_cmds = [(cmd, metadata)]
            return f
        return decorate

    @staticmethod
    def integrate_with(*otherplugins):
        """Tag a method as providing integration with *otherplugins*.

        During :meth:`.setup`, all methods tagged with this decorator will be
        run if all of the named plugins are loaded.  The actual plugin
        objects will be passed as arguments to the method in the same order.

        .. note:: The order that integration methods are called in cannot be
                  guaranteed, because attribute order is not preserved during
                  class creation.
        """
        if len(otherplugins) == 0:
            raise PluginFeatureError('no plugins specified in Plugin'
                                     '.integrate_with()')

        def decorate(f):
            f.plugin_integrate_with = otherplugins
            return f
        return decorate

    @property
    def config(self):
        """Get the configuration section for this plugin.

        If the config section doesn't exist yet, it is created empty.

        .. seealso:: :mod:`py3k:configparser`
        """
        plugin = self.plugin_name()
        if plugin not in self.bot.config_root:
            self.bot.config_root[plugin] = {}
        return self.bot.config_root[plugin]

    def config_get(self, key):
        """Convenience wrapper proxying ``get()`` on :attr:`config`.

        Given a key, this method tries the following in order::

            self.config[key]
            for v in self.CONFIG_ENVVARS[key]:
                os.environ[v]
            self.CONFIG_DEFAULTS[key]

        :exc:`KeyError` is raised if none of the methods succeed.
        """
        if key in self.config:
            return self.config[key]

        for envvar in self.CONFIG_ENVVARS.get(key, []):
            if envvar in os.environ:
                return os.environ[envvar]

        # Fallback which will raise KeyError if they key wasn't found anywhere
        return self.CONFIG_DEFAULTS[key]

    def config_getboolean(self, key):
        """Identical to :meth:`config_get`, but proxying ``getboolean``.
        """
        if key in self.CONFIG_DEFAULTS:
            return self.config.getboolean(key, self.CONFIG_DEFAULTS[key])
        else:
            return self.config.getboolean(key)

    @property
    def db(self):
        """Get a MongoDB database for the plugin, based on the plugin name."""
        if self._db is None:
            self._db = self.bot.mongodb[self.bot.config_get('mongodb_prefix') +
                                        self.plugin_name()]
        return self._db
