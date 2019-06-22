import collections
import itertools

from csbot.plugin import Plugin, SpecialPlugin, find_plugins
from csbot.plugin import build_plugin_dict, PluginManager, PluginConfigError
import csbot.events as events
from csbot.events import Event, CommandEvent
from csbot.util import maybe_future_result

from .irc import IRCClient, IRCUser
from . import config


class PluginError(Exception):
    pass


class Bot(SpecialPlugin, IRCClient):
    # TODO: use IRCUser instances instead of raw user string

    class Config(config.Config):
        ircv3 = config.option(bool, default=False, help="Enable IRCv3 features (i.e. 'client capabilities')")
        nickname = config.option(str, required=True, example="csyorkbot", help="IRC nick")
        username = config.option(str, default="csyorkbot", help="IRC user")
        realname = config.option(str, default="", example="cs-york bot", help="IRC 'real name'")
        auth_method = config.option(str, default="pass", help="Authentication method: 'pass' or 'sasl_plain")
        password = config.option(str, env="IRC_PASS", example="password123", help="Authentication password")
        irc_host = config.option(str, required=True, example="irc.freenode.net", help="IRC server hostname")
        irc_port = config.option(int, default=6667, help="IRC server port")
        command_prefix = config.option(str, default="!", help="Prefix for invoking commands")
        channels = config.option(config.WordList, example=["#cs-york-dev"], help="Channels to join")
        plugins = config.option(config.WordList, example=["logger", "linkinfo"], help="Plugins to load")
        use_notice = config.option(int, default=True, help="Use NOTICE instead of PRIVMSG to send messages")
        client_ping = config.option(int, default=0, help="Send PING if no messages for this many seconds (0=disabled)")
        bind_addr = config.option(str, example="192.168.1.111", help="Bind to specific local address")

    #: Dictionary containing available plugins for loading, using
    #: straight.plugin to discover plugin classes under a namespace.
    available_plugins = build_plugin_dict(find_plugins())

    _WHO_IDENTIFY = ('1', '%na')

    def __init__(self, config=None, loop=None):
        self.config_root = config
        if self.config_root is None:
            self.config_root = {}
        if not isinstance(self.config_root, collections.abc.Mapping):
            raise TypeError("expected 'config' to be a dict-like object")

        # Initialise plugin
        SpecialPlugin.__init__(self, self)

        # Initialise IRCClient from Bot configuration
        IRCClient.__init__(
            self,
            loop=loop,
            ircv3=self.config.ircv3,
            nick=self.config.nickname,
            username=self.config.username,
            host=self.config.irc_host,
            port=self.config.irc_port,
            password=self.config.password,
            auth_method=self.config.auth_method,
            bind_addr=self.config.bind_addr,
            client_ping_enabled=(self.config.client_ping > 0),
            client_ping_interval=self.config.client_ping,
        )

        self._recent_messages = collections.deque(maxlen=10)

        # Plumb in reply(...) method
        if self.config.use_notice:
            self.reply = self.notice
        else:
            self.reply = self.msg

        # Plugin management
        self.plugins = PluginManager([self], self.available_plugins,
                                     self.config.plugins,
                                     [self])
        self.commands = {}

        # Event runner
        self.events = events.HybridEventRunner(self._get_hooks, self.loop)

        # Keeps partial name lists between RPL_NAMREPLY and
        # RPL_ENDOFNAMES events
        self.names_accumulator = collections.defaultdict(list)

    def bot_setup(self):
        """Load plugins defined in configuration and run setup methods.
        """
        self.plugins.setup()

    def bot_teardown(self):
        """Run plugin teardown methods.
        """
        self.plugins.teardown()

    def _get_hooks(self, event):
        return itertools.chain(*self.plugins.get_hooks(event.event_type))

    def post_event(self, event):
        return self.events.post_event(event)

    def register_command(self, cmd, metadata, f, tag=None):
        # Bail out if the command already exists
        if cmd in self.commands:
            self.log.warning('tried to overwrite command: {}'.format(cmd))
            return False

        self.commands[cmd] = (f, metadata, tag)
        self.log.info('registered command: ({}, {})'.format(cmd, tag))
        return True

    def unregister_command(self, cmd, tag=None):
        if cmd in self.commands:
            f, m, t = self.commands[cmd]
            if t == tag:
                del self.commands[cmd]
                self.log.info('unregistered command: ({}, {})'
                              .format(cmd, tag))
            else:
                self.log.error(('tried to remove command {} ' +
                                'with wrong tag {}').format(cmd, tag))

    def unregister_commands(self, tag):
        delcmds = [c for c, (_, _, t) in self.commands.items() if t == tag]
        for cmd in delcmds:
            f, _, tag = self.commands[cmd]
            del self.commands[cmd]
            self.log.info('unregistered command: ({}, {})'.format(cmd, tag))

    @Plugin.hook('core.self.connected')
    def signedOn(self, event):
        for c in self.config.channels:
            event.bot.join(c)

    @Plugin.hook('core.message.privmsg')
    def privmsg(self, event):
        """Handle commands inside PRIVMSGs."""
        # See if this is a command
        command = CommandEvent.parse_command(
            event, self.config.command_prefix, event.bot.nick)
        if command is not None:
            self.post_event(command)

    @Plugin.hook('core.command')
    async def fire_command(self, event):
        """Dispatch a command event to its callback.
        """
        # Ignore unknown commands
        if event['command'] not in self.commands:
            return

        f, _, _ = self.commands[event['command']]
        await maybe_future_result(f(event), log=self.log)

    @Plugin.command('help', help=('help [command]: show help for command, or '
                                  'show available commands'))
    def show_commands(self, e):
        args = e.arguments()
        if len(args) > 0:
            cmd = args[0]
            if cmd in self.commands:
                f, meta, tag = self.commands[cmd]
                e.reply(meta.get('help', cmd + ': no help string'))
            else:
                e.reply(cmd + ': no such command')
        else:
            e.reply(', '.join(sorted(self.commands)))

    @Plugin.command('plugins')
    def show_plugins(self, e):
        e.reply('loaded plugins: ' + ', '.join(self.plugins))

    # Implement IRCClient events

    def emit_new(self, event_type, data=None):
        """Shorthand for firing a new event.
        """
        event = Event(self, event_type, data)
        return self.bot.post_event(event)

    def emit(self, event):
        """Shorthand for firing an existing event.
        """
        self.bot.post_event(event)

    async def connection_made(self):
        await super().connection_made()
        if self.config.ircv3:
            await self.request_capabilities(enable={'account-notify', 'extended-join'})
        self.emit_new('core.raw.connected')

    async def connection_lost(self, exc):
        await super().connection_lost(exc)
        self.emit_new('core.raw.disconnected', {'reason': repr(exc)})

    def send_line(self, line):
        super().send_line(line)
        self.emit_new('core.raw.sent', {'message': line})

    def line_received(self, line):
        self._recent_messages.append(line)
        fut = self.emit_new('core.raw.received', {'message': line})
        super().line_received(line)
        return fut

    @property
    def recent_messages(self):
        return list(self._recent_messages)

    def on_welcome(self):
        self.emit_new('core.self.connected')

    def on_joined(self, channel):
        self.identify(channel)
        self.emit_new('core.self.joined', {'channel': channel})

    def on_left(self, channel):
        self.emit_new('core.self.left', {'channel': channel})

    def on_privmsg(self, user, channel, message):
        self.emit_new('core.message.privmsg', {
            'channel': channel,
            'user': user.raw,
            'message': message,
            'is_private': channel == self.nick,
            'reply_to': user.nick if channel == self.nick else channel,
        })

    def on_notice(self, user, channel, message):
        self.emit_new('core.message.notice', {
            'channel': channel,
            'user': user.raw,
            'message': message,
            'is_private': channel == self.nick,
            'reply_to': user.nick if channel == self.nick else channel,
        })

    def on_action(self, user, channel, message):
        self.emit_new('core.message.action', {
            'channel': channel,
            'user': user.raw,
            'message': message,
            'is_private': channel == self.nick,
            'reply_to': user.nick if channel == self.nick else channel,
        })

    def on_user_joined(self, user, channel):
        self.emit_new('core.channel.joined', {
            'channel': channel,
            'user': user.raw,
        })

    def on_user_left(self, user, channel, message):
        self.emit_new('core.channel.left', {
            'channel': channel,
            'user': user.raw,
        })

    def on_user_quit(self, user, message):
        self.emit_new('core.user.quit', {
            'user': user.raw,
            'message': message,
        })

    def on_user_renamed(self, oldnick, newnick):
        self.emit_new('core.user.renamed', {
            'oldnick': oldnick,
            'newnick': newnick,
        })

    def on_topic_changed(self, user, channel, topic):
        self.emit_new('core.channel.topic', {
            'channel': channel,
            'author': user.raw,     # might be server name or nick
            'topic': topic,
        })

    # Implement NAMES handling

    def irc_RPL_NAMREPLY(self, msg):
        channel = msg.params[2]
        self.names_accumulator[channel].extend(msg.params[3].split())

    def irc_RPL_ENDOFNAMES(self, msg):
        # Get channel and raw names list
        channel = msg.params[1]
        raw_names = self.names_accumulator.pop(channel, [])

        # TODO: restore this functionality
        # Get a mapping from status characters to mode flags
        # prefixes = self.supported.getFeature('PREFIX')
        # inverse_prefixes = dict((v[0], k) for k, v in prefixes.items())

        # Get mode characters from name prefix
        # def f(name):
        #     if name[0] in inverse_prefixes:
        #         return (name[1:], set(inverse_prefixes[name[0]]))
        #     else:
        #         return (name, set())
        def f(name):
            return name.lstrip('@+'), set()
        names = list(map(f, raw_names))

        # Fire the event
        self.on_names(channel, names, raw_names)

    def on_names(self, channel, names, raw_names):
        """Called when the NAMES list for a channel has been received.
        """
        self.emit_new('core.channel.names', {
            'channel': channel,
            'names': names,
            'raw_names': raw_names,
        })

    # Implement active account discovery via "formatted WHO"

    def identify(self, target):
        """Find the account for a user or all users in a channel."""
        tag, query = self._WHO_IDENTIFY
        self.send_line('WHO {} {}t,{}'.format(target, query, tag))

    def irc_354(self, msg):
        """Handle "formatted WHO" responses."""
        tag = msg.params[1]
        if tag == self._WHO_IDENTIFY[0]:
            user, account = msg.params[2:]
            self.on_user_identified(user, None if account == '0' else account)

    def on_user_identified(self, user, account):
        self.emit_new('core.user.identified', {
            'user': user,
            'account': account,
        })

    # Implement passive account discovery via "Client Capabilities"

    def irc_ACCOUNT(self, msg):
        """Account change notification from ``account-notify`` capability."""
        account = msg.params[0]
        self.on_user_identified(msg.prefix, None if account == '*' else account)

    def irc_JOIN(self, msg):
        """Re-implement ``JOIN`` handler to account for ``extended-join`` info.
        """
        # Only do special handling if extended-join was enabled
        if 'extended-join' not in self.enabled_capabilities:
            return super().irc_JOIN(msg)

        user = IRCUser.parse(msg.prefix)
        nick = user.nick
        channel, account, _ = msg.params

        if nick == self.nick:
            self.on_joined(channel)
        else:
            self.on_user_identified(user.raw, None if account == '*' else account)
            self.on_user_joined(user, channel)

    def reply(self, to, message):
        """Reply to a nick/channel.

        This is not implemented because it should be replaced in the constructor
        with a reference to a real method, e.g. ``self.reply = self.msg``.
        """
        raise NotImplementedError

    @classmethod
    def write_example_config(cls, f, commented=False):
        plugins = [cls]
        plugins.extend(cls.available_plugins[k] for k in sorted(cls.available_plugins.keys()))
        generator = config.TomlExampleGenerator(commented=commented)
        for P in plugins:
            config_cls = getattr(P, 'Config', None)
            if config.is_config(config_cls):
                try:
                    generator.generate(config_cls, f, prefix=[P.plugin_name()])
                except config.ConfigError as e:
                    raise PluginConfigError(f"error in example config for plugin '{P.plugin_name()}': {e}") from e
                f.write("\n\n")
