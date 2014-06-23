from functools import partial
import collections
import logging
import os


def build_plugin_dict(plugins):
    """Build a dictionary mapping the value of :meth:`~Plugin.plugin_name` to
    each plugin class in *plugins*.  :exc:`PluginDuplicate` is raised if more
    than one plugin has the same name.
    """
    mapping = {}
    for P in plugins:
        name = P.plugin_name()
        if name in mapping:
            raise PluginDuplicate(name, P.qualified_name(),
                                  mapping[name].qualified_name())
        else:
            mapping[name] = P
    return mapping


class PluginDuplicate(Exception):
    pass


class PluginDependencyUnmet(Exception):
    pass


class PluginFeatureError(Exception):
    pass


class PluginManager(collections.Mapping):
    """A simple plugin manager and proxy.

    The plugin manager is responsible for loading plugins and proxying method
    calls to all plugins.  In addition to accepting *loaded*, a list of
    existing plugin objects, it will attempt to load each of *plugins* from
    *available* (a mapping of plugin name to plugin class), passing *args* to
    the constructors.

    Attempting to load missing or duplicate plugins will log errors and
    warnings respectively, but will not result in an exception or any change of
    state.  A plugin class' dependencies are checked before loading and a
    :exc:`PluginDependencyUnmet` is raised if any are missing.

    The :class:`~collections.Mapping` interface is implemented to provide easy
    querying and access to the loaded plugins.  All attributes that do not
    start with a ``_`` are treated as methods that will be proxied through to
    every plugin in the order they were loaded (*loaded* before *plugins*) with
    the same arguments.
    """

    #: Loaded plugins.
    plugins = {}

    def __init__(self, loaded, available, plugins, args):
        self.log = logging.getLogger(__name__)
        self.plugins = collections.OrderedDict()

        # Register already-loaded plugins
        for p in loaded:
            self.plugins[p.plugin_name()] = p

        # Attempt to load other plugins
        for p in plugins:
            if p in self.plugins:
                self.log.warn('not loading duplicate plugin:  ' + p)
            elif p not in available:
                self.log.error('plugin not found: ' + p)
            else:
                P = available[p]
                missing = P.missing_dependencies(self.plugins)
                if len(missing) > 0:
                    raise PluginDependencyUnmet(
                        "{} has unmet dependencies: {}".format(
                            p, ', '.join(missing)))
                self.plugins[p] = P(*args)
                self.log.info('plugin loaded: ' + p)

    def __getattr__(self, name):
        """Treat all undefined public attributes as proxy methods.

        It is assumed that the invoked method exists on all plugins, so this
        should probably only be used when the method call is part of the
        :class:`Plugin` base class.
        """
        if name.startswith('_'):
            raise AttributeError

        def f(*args):
            for p in self.plugins.values():
                getattr(p, name)(*args)
        return f

    # Implement abstract "read-only" Mapping interface

    def __getitem__(self, key):
        return self.plugins[key]

    def __len__(self):
        return len(self.plugins)

    def __iter__(self):
        return iter(self.plugins)


ProvidedByPlugin = collections.namedtuple('ProvidedByPlugin', ['plugin', 'kwargs'])


class PluginMeta(type):
    """Metaclass for :class:`Plugin` that collects methods tagged with plugin
    feature decorators.
    """
    def __init__(cls, name, bases, dict):
        super(PluginMeta, cls).__init__(name, bases, dict)

        # Initialise plugin features
        cls.PLUGIN_DEPENDS = set(cls.PLUGIN_DEPENDS)
        cls.plugin_hooks = collections.defaultdict(list)
        cls.plugin_cmds = []
        cls.plugin_integrations = []
        cls.plugin_provide = []

        # Scan for decorated methods
        for name, attr in dict.items():
            for h in getattr(attr, 'plugin_hooks', ()):
                cls.plugin_hooks[h].append(attr)
            for cmd, metadata in getattr(attr, 'plugin_cmds', ()):
                cls.plugin_cmds.append((cmd, metadata, attr))
            if len(getattr(attr, 'plugin_integrate_with', [])) > 0:
                cls.plugin_integrations.append((attr.plugin_integrate_with, attr))
            if isinstance(attr, ProvidedByPlugin):
                cls.PLUGIN_DEPENDS.add(attr.plugin)
                cls.plugin_provide.append((name, attr))


class Plugin(object, metaclass=PluginMeta):
    """Bot plugin base class.

    All bot plugins should inherit from this class.  It provides convenience
    methods for hooking events, registering commands, accessing MongoDB and
    manipulating the configuration file.
    """

    #: Default configuration values, used automatically by :meth:`config_get`.
    CONFIG_DEFAULTS = {}
    #: Configuration environment variables, used automatically by
    #: :meth:`config_get`.
    CONFIG_ENVVARS = {}
    #: Plugins that :meth:`missing_dependencies` should check for.
    PLUGIN_DEPENDS = []

    #: The plugin's logger, created by default using the plugin class'
    #: containing module name as the logger name.
    log = None

    def __init__(self, bot):
        # Get the logger for the module the actual plugin is defined in, not
        # this base class; using __name__ would make every plugin log to
        # 'csbot.plugin' instead.
        self.log = logging.getLogger(self.__class__.__module__)
        self.bot = bot
        self._db = None

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

    @classmethod
    def missing_dependencies(cls, plugins):
        """Return elements from :attr:`PLUGIN_DEPENDS` that are not in the
        container *plugins*.

        This should be used with some container of already loaded plugin names
        (e.g. a dictionary or set) to find out which dependencies are missing.
        """
        return [p for p in cls.PLUGIN_DEPENDS if p not in plugins]

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

    @staticmethod
    def use(other, **kwargs):
        """Create a property that will be provided by another plugin.

        Returns a :class:`ProvidedByPlugin` instance.  :class:`PluginMeta` will
        collect attributes of this type, and add *other* as an implicit plugin
        dependency.  :meth:`setup` will replace it with a value acquired from
        the plugin named by *other*.  For example::

            class Foo(Plugin):
                stuff = Plugin.use('mongodb', collection='stuff')

        will cause :meth:`setup` to replace the ``stuff`` attribute with::

            self.bot.plugins[other].provide(self.plugin_name(), **kwargs)
        """
        return ProvidedByPlugin(other, kwargs)

    def fire_hooks(self, event):
        """Execute all of this plugin's handlers for *event*."""
        for f in self.plugin_hooks.get(event.event_type, ()):
            f(self, event)

    def provide(self, plugin_name, **kwarg):
        """Provide a value for a :meth:`Plugin.use` usage."""
        raise NotImplementedError

    def setup(self):
        """Plugin setup.

        * Replace all :class:`ProvidedByPlugin` attributes.
        * Fire all plugin integration methods.
        * Register all commands provided by the plugin.
        """
        for name, provided_by in self.plugin_provide:
            other = self.bot.plugins[provided_by.plugin]
            new_value = other.provide(self.plugin_name(), **provided_by.kwargs)
            setattr(self, name, new_value)

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

    @property
    def config(self):
        """Get the configuration section for this plugin.

        Uses the ``[plugin_name]`` section of the configuration file, creating
        an empty section if it doesn't exist.

        .. seealso:: :mod:`configparser`
        """
        plugin = self.plugin_name()
        if plugin not in self.bot.config_root:
            self.bot.config_root[plugin] = {}
        return self.bot.config_root[plugin]

    def subconfig(self, subsection):
        """Get a configuration subsection for this plugin.

        Uses the ``[plugin_name/subsection]`` section of the configuration file,
        creating an empty section if it doesn't exist.
        """
        section = self.plugin_name() + '/' + subsection
        if section not in self.bot.config_root:
            self.bot.config_root[section] = {}
        return self.bot.config_root[section]

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


class SpecialPlugin(Plugin):
    """A special plugin with a special name that expects to be handled
    specially.  Probably shouldn't have too many of these or they won't feel
    special anymore.
    """
    @classmethod
    def plugin_name(cls):
        """Change the plugin name to something that can't possibly result from
        a class name by prepending a ``@``.
        """
        return '@' + super(SpecialPlugin, cls).plugin_name()
