import collections
from collections import abc
from functools import partial
import logging
import os
from typing import (
    Any,
    Callable,
    List,
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
    Set,
    Type,
)

import attr
import straight.plugin

from . import config


def find_plugins():
    """Find available plugins.

    Returns a list of discovered plugin classes.
    """
    return list(straight.plugin.load('csbot.plugins', subclasses=Plugin))


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


class LazyMethod:
    def __init__(self, obj, name):
        self.obj = obj
        self.name = name

    def __call__(self, *args, **kwargs):
        return getattr(self.obj, self.name)(*args, **kwargs)


class PluginDuplicate(Exception):
    pass


class PluginDependencyUnmet(Exception):
    pass


class PluginFeatureError(Exception):
    pass


class PluginConfigError(Exception):
    pass


class PluginManager(abc.Mapping):
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

    The :class:`~collections.abc.Mapping` interface is implemented to provide easy
    querying and access to the loaded plugins.  All attributes that do not
    start with a ``_`` are treated as methods that will be proxied through to
    every plugin in the order they were loaded (*loaded* before *plugins*) with
    the same arguments.
    """

    #: Loaded plugins.
    plugins: MutableMapping[str, "Plugin"]

    def __init__(self, loaded, available, plugins, args):
        self.log = logging.getLogger(__name__)
        self.plugins = collections.OrderedDict()

        # Register already-loaded plugins
        for p in loaded:
            self.plugins[p.plugin_name()] = p

        # Attempt to load other plugins
        for p in plugins:
            if p in self.plugins:
                self.log.warning('not loading duplicate plugin:  ' + p)
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

        Returns a list of the return value from each plugin.
        """
        if name.startswith('_'):
            raise AttributeError

        def f(*args):
            return [getattr(p, name)(*args) for p in self.plugins.values()]
        return f

    # Implement abstract "read-only" Mapping interface

    def __getitem__(self, key):
        return self.plugins[key]

    def __len__(self):
        return len(self.plugins)

    def __iter__(self):
        return iter(self.plugins)


@attr.s
class ProvidedByPlugin:
    """Descriptor for plugin attributes that get (and cache) a value from another plugin.

    See :meth:`Plugin.use`.
    """
    plugin: str = attr.ib()
    kwargs: Mapping[str, Any] = attr.ib()
    name: str = attr.ib(default=None)

    def __set_name__(self, owner: Type["Plugin"], name: str):
        if not issubclass(owner, Plugin):
            raise PluginFeatureError("Can only Plugin.use() inside a Plugin subclass")
        self.name = name

    def __get__(self, instance: "Plugin", owner: Type["Plugin"]):
        if instance is None:
            raise AttributeError("Plugin.use() attributes only work on instances")
        attribute = f"_{self.__class__.__name__}__{self.name}"
        if not hasattr(instance, attribute):
            other = instance.bot.plugins[self.plugin]
            setattr(instance, attribute, other.provide(instance.plugin_name(), **self.kwargs))
        return getattr(instance, attribute)


@attr.s
class _PluginData:
    dependencies: Set[str] = attr.ib(factory=set)
    hooks: MutableMapping[str, MutableSequence[str]] = attr.ib(factory=lambda: collections.defaultdict(list))
    commands = attr.ib(factory=list)
    integrations = attr.ib(factory=list)
    uses: MutableSequence[ProvidedByPlugin] = attr.ib(factory=list)

    def depends(self, *dependencies):
        self.dependencies.update(dependencies)

    def hook(self, name, f=None):
        if f is None:
            return partial(self.hook, name)
        else:
            if f.__name__ not in self.hooks[name]:
                self.hooks[name].append(f.__name__)
            return f

    def command(self, name, f=None, **metadata):
        if f is None:
            return partial(self.command, name, **metadata)
        else:
            self.commands.append((name, metadata, f.__name__))
            return f

    def integrate_with(self, *otherplugins):
        if len(otherplugins) == 0:
            raise PluginFeatureError("no plugins specified in Plugin .integrate_with()")

        def decorate(f):
            self.integrations.append((otherplugins, f.__name__))
            return f
        return decorate

    def use(self, other, kwargs):
        self.depends(other)
        descriptor = ProvidedByPlugin(other, kwargs)
        self.uses.append(descriptor)
        return descriptor


class PluginMeta(type):
    """Metaclass for :class:`Plugin` that collects methods tagged with plugin
    feature decorators.
    """
    _plugin_data_stack: MutableSequence[_PluginData] = []

    @classmethod
    def __prepare__(mcs, name, bases, **kwargs):
        """Prepare "plugin data" context.

        The plugin data object is put on the top of a stack, so is "current" for the lifetime of creating a new
        :class:`Plugin` class, except if a nested class is being created.
        """
        data = _PluginData()
        mcs._plugin_data_stack.append(data)
        return dict(
            __plugin_data=data,
        )

    def __new__(mcs, name, bases, attrs, **kwargs):
        mcs._plugin_data_stack.pop()
        return super().__new__(mcs, name, bases, attrs)

    def __init__(cls, name, bases, attrs):
        super(PluginMeta, cls).__init__(name, bases, attrs)

        # Initialise plugin features
        cls._Plugin__plugin_data = data = attrs.pop("__plugin_data")
        data.depends(*cls.PLUGIN_DEPENDS)

    @classmethod
    def current(mcs):
        if len(mcs._plugin_data_stack) == 0:
            raise TypeError("attempting to use plugin features outside of a Plugin subclass")
        return mcs._plugin_data_stack[-1]


class Plugin(object, metaclass=PluginMeta):
    """Bot plugin base class.

    All bot plugins should inherit from this class.  It provides convenience
    methods for hooking events, registering commands, accessing MongoDB and
    manipulating the configuration file.
    """

    #: Default configuration values, used automatically by :meth:`config_get`.
    CONFIG_DEFAULTS: Mapping[str, Any] = {}
    #: Configuration environment variables, used automatically by
    #: :meth:`config_get`.
    CONFIG_ENVVARS: Mapping[str, Sequence[str]] = {}
    #: Plugins that :meth:`missing_dependencies` should check for.
    PLUGIN_DEPENDS: Sequence[str] = []

    #: The plugin's logger, created by default using the plugin class'
    #: containing module name as the logger name.
    log = None

    __plugin_data: _PluginData

    def __init__(self, bot):
        # Get the logger for the module the actual plugin is defined in, not
        # this base class; using __name__ would make every plugin log to
        # 'csbot.plugin' instead.
        self.log = logging.getLogger(self.__class__.__module__)
        self.bot = bot
        self.__config = self._get_config(bot)

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
        return [p for p in cls.__plugin_data.dependencies if p not in plugins]

    @staticmethod
    def hook(hook):
        return PluginMeta.current().hook(hook)

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
        return PluginMeta.current().command(cmd, **metadata)

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
        return PluginMeta.current().integrate_with(*otherplugins)

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
        return PluginMeta.current().use(other, kwargs)

    def get_hooks(self, hook: str) -> List[Callable]:
        """Get a list of this plugin's handlers for *hook*.
        """
        return [getattr(self, name) for name in self.__plugin_data.hooks.get(hook, ())]

    def provide(self, plugin_name, **kwarg):
        """Provide a value for a :meth:`Plugin.use` usage."""
        raise PluginFeatureError('{} plugin does not support Plugin.use()'.format(self.plugin_name()))

    def setup(self):
        """Plugin setup.

        * Replace all :class:`ProvidedByPlugin` attributes.
        * Fire all plugin integration methods.
        * Register all commands provided by the plugin.
        """
        # Preserve old behaviour of provide() being called during setup()
        for descriptor in self.__plugin_data.uses:
            getattr(self, descriptor.name)

        for plugin_names, name in self.__plugin_data.integrations:
            plugins = [self.bot.plugins[p] for p in plugin_names
                       if p in self.bot.plugins]
            # Only fire integration method if all named plugins were loaded
            if len(plugins) == len(plugin_names):
                f = getattr(self, name)
                f(*plugins)

        for cmd, meta, name in self.__plugin_data.commands:
            self.bot.register_command(
                cmd,
                meta,
                LazyMethod(self, name),
                tag=self)

    def teardown(self):
        """Plugin teardown.

        * Unregister all commands provided by the plugin.
        """
        self.bot.unregister_commands(tag=self)

    @classmethod
    def _get_config(cls, bot):
        # Get dict-like access to config
        plugin = cls.plugin_name()
        if plugin in bot.config_root:
            cfg = bot.config_root[plugin]
        else:
            cfg = {}

        # Upgrade to structure-based config if defined
        config_cls = getattr(cls, 'Config', None)
        if config.is_config(config_cls):
            try:
                cfg = config.structure(cfg, config_cls)
            except config.ConfigError as e:
                raise PluginConfigError(f"error in config for plugin '{cls.plugin_name()}': {e}") from e

        return cfg

    @property
    def config(self):
        """Get the configuration section for this plugin.

        Uses the ``[plugin_name]`` section of the configuration file, creating
        an empty section if it doesn't exist.

        .. seealso:: :mod:`configparser`
        """
        if self.__config is None:
            self.__config = self._get_config(self.bot)
        return self.__config

    def subconfig(self, subsection):
        """Get a configuration subsection for this plugin.

        Uses the ``[plugin_name/subsection]`` section of the configuration file,
        creating an empty section if it doesn't exist.
        """
        if config.is_config(self.config):
            raise PluginFeatureError("subconfig() incompatible with plugin.Config, "
                                     "use config.option_map()")
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
        if config.is_config(self.config):
            raise PluginFeatureError("config_get('<key>') incompatible with plugin.Config, "
                                     "use self.config.<key>")

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
        if config.is_config(self.config):
            raise PluginFeatureError("config_getboolean('<key>') incompatible with plugin.Config, "
                                     "use self.config.<key>")

        if key in self.CONFIG_DEFAULTS:
            value = self.config.get(key, self.CONFIG_DEFAULTS[key])
        else:
            value = self.config[key]

        if isinstance(value, bool):
            return value
        elif value.lower() in {"true", "yes", "1"}:
            return True
        elif value.lower() in {"false", "no", "0"}:
            return False
        else:
            raise ValueError("unrecognised boolean: %s" % (value,))


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
