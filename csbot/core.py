from functools import wraps
import types
import shlex
import ConfigParser

from twisted.words.protocols import irc
from twisted.internet import reactor, protocol
from twisted.python import log
import pymongo


def hook(f):
    """Create a plugin hook.

    Used as a method decorator this will cause the hook of the same name to be
    fired after the method.  Used to create a new method, *f* names the hook
    that will be fired by the method.
    """
    if callable(f):
        @wraps(f)
        def newf(self, *args, **kwargs):
            f(self, *args, **kwargs)
            self.bot.fire_hook(f.__name__, *args, **kwargs)
    else:
        def newf(self, *args, **kwargs):
            self.bot.fire_hook(f, *args, **kwargs)
        newf.__doc__ = "Generated hook trigger for ``{}``".format(f)
    return newf


def nick(user):
    """Get nick from user string.

    >>> nick('csyorkbot!~csbot@example.com')
    'csyorkbot'
    """
    return user.split('!', 1)[0]


def username(user):
    """Get username from user string.

    >>> username('csyorkbot!~csbot@example.com')
    'csbot'
    """
    return user.rsplit('@', 1)[0].rsplit('~', 1)[1]


def host(user):
    """Get hostname from user string.

    >>> host('csyorkbot!~csbot@example.com')
    'example.com'
    """
    return user.rsplit('@', 1)[1]


def is_channel(channel):
    """Check if *channel* is a channel or private chat.

    >>> is_channel('#cs-york')
    True
    >>> is_channel('csyorkbot')
    False
    """
    return channel.startswith('#')


class Bot(object):
    """The IRC bot.

    Handles plugins, command dispatch, hook dispatch, etc.  Persistent across
    losing and regaining connection.
    """

    #: Default configuration values
    DEFAULTS = {
            'nickname': 'csyorkbot',
            'username': 'csyorkbot',
            'realname': 'cs-york bot',
            'sourceURL': 'http://github.com/csyork/csbot/',
            'lineRate': '1',
            'keyvalfile': 'keyval.cfg',
            'irc_host': 'irc.freenode.net',
            'irc_port': '6667',
            'command_prefix': '!',
            'channels': ' '.join([
                '#cs-york-dev',
            ]),
            'plugins': ' '.join([
                'example.Example',
            ]),
            'mongodb_host': 'localhost',
            'mongodb_port': '27017',
    }

    def __init__(self, configpath, plugins):
        # Load the configuration file
        self.configpath = configpath
        self.config = ConfigParser.SafeConfigParser(defaults=self.DEFAULTS,
                                                    allow_no_value=True)
        self.config.read(self.configpath)

        # Load plugin "key-value" store
        self.plugindata = ConfigParser.SafeConfigParser(allow_no_value=True)
        self.plugindata.read(self.config.get('DEFAULT', 'keyvalfile'))

        # Make mongodb connection
        self.mongodb = pymongo.Connection(
                self.config.get('DEFAULT', 'mongodb_host'),
                self.config.getint('DEFAULT', 'mongodb_port'))


        self.available_plugins = dict((P.plugin_name(), P) for P in plugins)
        self.plugins = dict()
        self.commands = dict()

    def setup(self):
        """Load plugins defined in configuration.
        """
        map(self.load_plugin, self.config.get('DEFAULT', 'plugins').split())

    def teardown(self):
        """Unload plugins and save data.
        """
        for name in self.plugins.keys():
            self.unload_plugin(name)

        # Save the plugin data
        with open(self.config.get('DEFAULT', 'keyvalfile'), 'wb') as kvf:
            self.plugindata.write(kvf)

    def load_plugin(self, name):
        """Load a named plugin and register all of its commands.

        When a plugin is loaded, it is added to the bot, all of its defined
        commands are registered, and then its :meth:`Plugin.setup` is run.

        .. todo: use :py:func:`reload` to update plugin first
        """
        if name not in self.available_plugins:
            self.log_err('Plugin {} does not exist'.format(name))
            return

        if name in self.plugins:
            self.log_err('Plugin {} already loaded'.format(name))
            return

        p = self.available_plugins[name](self)
        self.plugins[name] = p
        self.log_msg('Loaded plugin {}'.format(name))

        for command, handler in p.features.commands.iteritems():
            if command in self.commands:
                self.log_err('Command {} already provided by plugin {}'.format(
                             command,
                             self.commands[command].im_class.plugin_name()))
            else:
                self.log_msg('Registering command {}'.format(command))
                self.commands[command] = handler

        p.setup()

    def unload_plugin(self, name):
        """Unload a named plugin and unregister all of its commands.

        When a plugin is unloaded, its :meth:'Plugin.teardown' method is run,
        all of its commands are unregistered, and then the plugin itself is
        removed from the :class:`Bot`.
        """
        if name not in self.plugins:
            self.log_err('Plugin {} not loaded'.format(name))
            return

        p = self.plugins[name]
        p.teardown()

        delcmds = [n for n, h in self.commands.iteritems()
                   if h.im_class.plugin_name() == name]
        for cmd in delcmds:
            self.log_msg('Unregistering command {}'.format(cmd))
            del self.commands[cmd]

        del self.plugins[name]
        self.log_msg('Unloaded plugin {}'.format(name))

    def fire_command(self, command):
        """Dispatch *command* to its callback.
        """
        if command.command not in self.commands:
            command.error('Command "{0.command}" not found'.format(command))
            return

        handler = self.commands[command.command]
        handler(command)

    def fire_hook(self, hook, *args, **kwargs):
        """Fire *hook* on every plugin.
        """
        for plugin in self.plugins.itervalues():
            plugin.features.fire_hook(hook, *args, **kwargs)

    def log_msg(self, msg):
        """Convenience wrapper around ``twisted.python.log.msg`` for plugins"""
        log.msg(msg)

    def log_err(self, err):
        """Convenience wrapper around ``twisted.python.log.err`` for plugins"""
        log.err(err)


class BotProtocol(irc.IRCClient):
    def __init__(self, bot):
        self.bot = bot
        # Get IRCClient configuration from the Bot
        self.nickname = bot.config.get('DEFAULT', 'nickname')
        self.username = bot.config.get('DEFAULT', 'username')
        self.realname = bot.config.get('DEFAULT', 'realname')
        self.sourceURL = bot.config.get('DEFAULT', 'sourceURL')
        self.lineRate = bot.config.getint('DEFAULT', 'lineRate')

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        print "[Connected]"

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)
        print "[Disconnected because {}]".format(reason)

    def signedOn(self):
        map(self.join, self.bot.config.get('DEFAULT', 'channels').split())

    @hook
    def privmsg(self, user, channel, msg):
        """Handle commands in channel messages.
        """
        command = CommandEvent.create(self.bot, self, user, channel, msg)
        if command is not None:
            self.bot.fire_command(command)

    action = hook('action')
    userJoined = hook('userJoined')


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

    def fire_hook(self, hook, *args, **kwargs):
        """Run all handlers for *hook*.

        The handlers are run in the order they were registered for *hook*,
        which should correspond to the order they were defined in.  All
        extra arguments are passed through to every handler.
        """
        if hook in self.hooks:
            for f in self.hooks[hook]:
                f(*args, **kwargs)


class Plugin(object):
    """Bot plugin base class.
    """

    features = PluginFeatures()

    def __init__(self, bot):
        self.bot = bot
        self.features = self.features.instantiate(self)
        self.db = self.bot.mongodb[self.plugin_name().replace('.', '__')]

    @classmethod
    def plugin_name(cls):
        """Get the plugin's name.

        A plugin's name is its fully qualified path, excluding the leading
        component (which will always be ``csbot.plugins``).

        >>> from csbot.plugins.example import EmptyPlugin
        >>> EmptyPlugin.plugin_name()
        'example.EmptyPlugin'
        >>> p = EmptyPlugin(None)
        >>> p.plugin_name()
        'example.EmptyPlugin'
        """
        return cls.__module__.split('.', 2)[2] + '.' + cls.__name__

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
        pass

    def teardown(self):
        pass


class CommandEvent(object):
    #: The :class:`Bot` this command was received by
    bot = None
    #: The :class:`BotProtocol` this event was received by
    protocol = None
    #: The command invoked (minus any trigger characters)
    command = None
    #: User string for the source of the command
    user = None
    #: Channel that the command was received on
    channel = None
    #: False if the command was triggered by the command prefix, True otherwise
    direct = False
    #: The rest of the line after the command name
    raw_data = None
    #: Cached argument list, see :attr:`data`
    data_ = None

    def __init__(self, bot, protocol, user, channel, command, direct, raw_data):
        self.bot = bot
        self.protocol = protocol
        self.command = command
        self.user = user
        self.channel = channel
        self.direct = direct
        self.raw_data = raw_data
        self.data_ = None

    @staticmethod
    def create(bot, protocol, user, channel, msg):
        """Attempt to create an event from *msg*.

        Returns None if *msg* is not a command, otherwise returns a new
        :class:`CommandEvent`.
        """
        command_prefix = bot.config.get('DEFAULT', 'command_prefix')

        command = None
        direct = False

        if is_channel(channel):
            # In channel, must be triggered explicitly
            if msg.startswith(command_prefix):
                # Triggered by command prefix: "<prefix><cmd> <args>"
                command = msg[len(command_prefix):]
            elif msg.startswith(protocol.nickname):
                # Addressing the bot by name: "<nick>, <cmd> <args>"
                msg = msg[len(protocol.nickname):].lstrip()
                # Check that the bot was specifically addressed, rather than
                # a similar nick or just talking about the bot
                if len(msg) > 0 and msg[0] in ',:;.':
                    command = msg.lstrip(',:;.')
                    direct = True
        else:
            command = msg
            direct = True

        if command is None or command.strip() == '':
            return None

        command = command.split(None, 1)
        cmd = command[0]
        data = command[1] if len(command) == 2 else ''
        return CommandEvent(bot, protocol, user, channel, cmd, direct, data)

    @property
    def data(self):
        """Command data as an argument list.

        On first access, the argument list is processed from :attr:`raw_data`
        using :py:mod:`shlex`.  The lexer is customised to only use `"` for
        argument quoting, allowing `'` to be used naturally within arguments.

        If the lexer fails to process the argument list, :meth:`error` is
        called and :py:class:`ValueError` is raised.
        """
        if self.data_ is None:
            try:
                # Create a shlex instance just like shlex.split does
                lex = shlex.shlex(self.raw_data, posix=True)
                lex.whitespace_split = True
                # Don't treat ' as a quote character, so it can be used
                # naturally in words
                lex.quotes = '"'
                self.data_ = list(lex)
            except ValueError as e:
                self.error('Unmatched quotation marks')
                raise e
        return self.data_

    def reply(self, msg, is_verbose=False):
        """Send a reply message.

        All plugin responses should be via this method.  The :attr:`user` is
        addressed by name if the response is in a channel rather than a private
        chat.  If *is_verbose* is True, the reply is suppressed unless the bot
        was addressed directly, i.e. in private chat or by name in a channel.
        """
        if self.channel == self.protocol.nickname:
            self.protocol.msg(nick(self.user), msg)
        elif self.direct or not is_verbose:
            self.protocol.msg(self.channel, msg)

    def error(self, err):
        """Send an error message."""
        self.reply('Error: ' + err, is_verbose=True)


class BotFactory(protocol.ClientFactory):
    def __init__(self, bot):
        self.bot = bot

    def buildProtocol(self, addr):
        p = BotProtocol(self.bot)
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        reactor.stop()


def main(argv):
    import sys
    import argparse
    from straight.plugin import load

    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', default='csbot.cfg',
                        help='Configuration file [default: %(default)s]')
    args = parser.parse_args(argv[1:])

    # Start twisted logging
    log.startLogging(sys.stdout)

    # Find plugins
    plugins = load('csbot.plugins', subclasses=Plugin)
    print "Plugins found:", plugins

    # Create bot and run setup functions
    bot = Bot(args.config, plugins)
    bot.setup()

    # Connect and enter the reactor loop
    reactor.connectTCP(bot.config.get('DEFAULT', 'irc_host'),
                       bot.config.getint('DEFAULT', 'irc_port'),
                       BotFactory(bot))
    reactor.run()

    # Run teardown functions before exiting
    bot.teardown()
