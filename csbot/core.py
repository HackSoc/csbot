import logging
import collections

from twisted.words.protocols import irc
from twisted.internet import reactor, protocol
from twisted.python import log
import configparser
import straight.plugin

from csbot.plugin import Plugin, SpecialPlugin
from csbot.plugin import build_plugin_dict, PluginManager
import csbot.events as events
from csbot.events import Event, CommandEvent
from csbot.util import nick


class Bot(SpecialPlugin):
    """The IRC bot.

    Handles plugins, command dispatch, hook dispatch, etc.  Persistent across
    losing and regaining connection.

    *config* is an optional file-like object to read configuration from, which
    is parsed with :mod:`configparser`.
    """

    #: Default configuration values
    CONFIG_DEFAULTS = {
        'nickname': 'csyorkbot',
        'password': None,
        'username': 'csyorkbot',
        'realname': 'cs-york bot',
        'sourceURL': 'http://github.com/csyork/csbot/',
        'lineRate': '1',
        'irc_host': 'irc.freenode.net',
        'irc_port': '6667',
        'command_prefix': '!',
        'channels': ' '.join([
            '#cs-york-dev',
        ]),
        'plugins': ' '.join([
            'example',
        ]),
    }

    #: Environment variable fallbacks
    CONFIG_ENVVARS = {
        'password': ['IRC_PASS'],
    }

    #: Dictionary containing available plugins for loading, using
    #: straight.plugin to discover plugin classes under a namespace.
    available_plugins = build_plugin_dict(straight.plugin.load(
        'csbot.plugins', subclasses=Plugin))

    def __init__(self, config=None):
        super(Bot, self).__init__(self)

        # Load configuration
        self.config_root = configparser.ConfigParser(interpolation=None,
                                                     allow_no_value=True)
        self.config_root.optionxform = str  # No lowercase option names
        if config is not None:
            self.config_root.read_file(config)

        # Plugin management
        self.plugins = PluginManager([self], self.available_plugins,
                                     self.config_get('plugins').split(),
                                     [self])
        self.commands = {}

        # Event runner
        self.events = events.ImmediateEventRunner(self.plugins.fire_hooks)

    def bot_setup(self):
        """Load plugins defined in configuration and run setup methods.
        """
        self.plugins.setup()

    def bot_teardown(self):
        """Run plugin teardown methods.
        """
        self.plugins.teardown()

    def post_event(self, event):
        self.events.post_event(event)

    def register_command(self, cmd, metadata, f, tag=None):
        # Bail out if the command already exists
        if cmd in self.commands:
            self.log.warn('tried to overwrite command: {}'.format(cmd))
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
        for c in self.config_get('channels').split():
            event.protocol.join(c)

    @Plugin.hook('core.message.privmsg')
    def privmsg(self, event):
        """Handle commands inside PRIVMSGs."""
        # See if this is a command
        command = CommandEvent.parse_command(
            event, self.config_get('command_prefix'))
        if command is not None:
            self.post_event(command)

    @Plugin.hook('core.command')
    def fire_command(self, event):
        """Dispatch a command event to its callback.
        """
        # Ignore unknown commands
        if event['command'] not in self.commands:
            return

        f, _, _ = self.commands[event['command']]
        f(event)

    @Plugin.command('help', help=('help [command]: show help for command, or '
                                  'show available commands'))
    def show_commands(self, e):
        args = e.arguments()
        if len(args) > 0:
            cmd = args[0]
            if cmd in self.commands:
                f, meta, tag = self.commands[cmd]
                e.protocol.msg(e['reply_to'],
                               meta.get('help', cmd + ': no help string'))
            else:
                e.protocol.msg(e['reply_to'], cmd + ': no such command')
        else:
            e.protocol.msg(e['reply_to'], ', '.join(sorted(self.commands)))

    @Plugin.command('plugins')
    def show_plugins(self, event):
        event.protocol.msg(event['reply_to'],
                           'loaded plugins: ' + ', '.join(self.plugins))


class PluginError(Exception):
    pass


class BotProtocol(irc.IRCClient):
    log = logging.getLogger('csbot.protocol')

    _WHO_IDENTIFY = ('1', '%na')

    def __init__(self, bot):
        self.bot = bot
        # Get IRCClient configuration from the Bot
        self.nickname = bot.config_get('nickname')
        self.password = bot.config_get('password')
        self.username = bot.config_get('username')
        self.realname = bot.config_get('realname')
        self.sourceURL = bot.config_get('sourceURL')
        self.lineRate = int(bot.config_get('lineRate'))

        # Keeps partial name lists between RPL_NAMREPLY and
        # RPL_ENDOFNAMES events
        self.names_accumulator = collections.defaultdict(list)

    def emit_new(self, event_type, data=None):
        """Shorthand for firing a new event; the new event is returned.
        """
        event = Event(self, event_type, data)
        self.bot.post_event(event)
        return event

    def emit(self, event):
        """Shorthand for firing an existing event.
        """
        self.bot.post_event(event)

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        self.sendLine('CAP REQ :account-notify extended-join')
        self.emit_new('core.raw.connected')

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)
        self.emit_new('core.raw.disconnected', {'reason': reason})

    def sendLine(self, line):
        # Encode unicode strings with utf-8
        if isinstance(line, str):
            line = line.encode('utf-8')
        irc.IRCClient.sendLine(self, line)
        self.emit_new('core.raw.sent', {'message': line})

    def lineReceived(self, line):
        # Attempt to decode incoming strings; if they are neither UTF-8 or
        # CP1252 they will get mangled as whatever CP1252 thinks they are.
        try:
            line = line.decode('utf-8')
        except UnicodeDecodeError:
            line = line.decode('cp1252')
        self.emit_new('core.raw.received', {'message': line})
        irc.IRCClient.lineReceived(self, line)

    def signedOn(self):
        self.emit_new('core.self.connected')

    def joined(self, channel):
        self.identify(channel)
        self.emit_new('core.self.joined', {'channel': channel})

    def left(self, channel):
        self.emit_new('core.self.left', {'channel': channel})

    def privmsg(self, user, channel, message):
        self.emit_new('core.message.privmsg', {
            'channel': channel,
            'user': user,
            'message': message,
            'is_private': channel == self.nickname,
            'reply_to': nick(user) if channel == self.nickname else channel,
        })

    def noticed(self, user, channel, message):
        self.emit_new('core.message.notice', {
            'channel': channel,
            'user': user,
            'message': message,
            'is_private': channel == self.nickname,
            'reply_to': nick(user) if channel == self.nickname else channel,
        })

    def action(self, user, channel, message):
        self.emit_new('core.message.action', {
            'channel': channel,
            'user': user,
            'message': message,
            'is_private': channel == self.nickname,
            'reply_to': nick(user) if channel == self.nickname else channel,
        })

    def irc_JOIN(self, prefix, params):
        """Re-implement ``JOIN`` handler to account for ``extended-join`` info.
        """
        user = prefix
        nick_ = nick(user)
        channel, account, _ = params

        if nick_ == self.nickname:
            self.joined(channel)
        else:
            self.emit_new('core.user.identified', {
                'user': user,
                'account': None if account == '*' else account,
            })
            self.emit_new('core.channel.joined', {
                'channel': channel,
                'user': user,
            })

    def userLeft(self, user, channel):
        self.emit_new('core.channel.left', {
            'channel': channel,
            'user': user,
        })

    def names(self, channel, names, raw_names):
        """Called when the NAMES list for a channel has been received.
        """
        self.emit_new('core.channel.names', {
            'channel': channel,
            'names': names,
            'raw_names': raw_names,
        })

    def userQuit(self, user, message):
        self.emit_new('core.user.quit', {
            'user': user,
            'message': message,
        })

    def userRenamed(self, oldnick, newnick):
        self.emit_new('core.user.renamed', {
            'oldnick': oldnick,
            'newnick': newnick,
        })

    def irc_RPL_NAMREPLY(self, prefix, params):
        channel = params[2]
        self.names_accumulator[channel].extend(params[3].split())

    def irc_RPL_ENDOFNAMES(self, prefix, params):
        # Get channel and raw names list
        channel = params[1]
        raw_names = self.names_accumulator.pop(channel, [])

        # Get a mapping from status characters to mode flags
        prefixes = self.supported.getFeature('PREFIX')
        inverse_prefixes = dict((v[0], k) for k, v in prefixes.items())

        # Get mode characters from name prefix
        def f(name):
            if name[0] in inverse_prefixes:
                return (name[1:], set(inverse_prefixes[name[0]]))
            else:
                return (name, set())
        names = list(map(f, raw_names))

        # Fire the event
        self.names(channel, names, raw_names)

    def topicUpdated(self, user, channel, newtopic):
        self.emit_new('core.channel.topic', {
            'channel': channel,
            'author': user,     # might be server name or nick
            'topic': newtopic,
        })

    def identify(self, target):
        """Find the account for a user or all users in a channel."""
        tag, query = self._WHO_IDENTIFY
        self.sendLine('WHO {} {}t,{}'.format(target, query, tag))
        pass

    def irc_354(self, prefix, params):
        """Handle "formatted WHO" responses."""
        tag = params[1]
        if tag == self._WHO_IDENTIFY[0]:
            self.emit_new('core.user.identified', {
                'user': params[2],
                'account': None if params[3] == '0' else params[3],
            })

    def irc_ACCOUNT(self, prefix, params):
        """Account change notification from ``account-notify`` capability."""
        self.emit_new('core.user.identified', {
            'user': prefix,
            'account': None if params[0] == '*' else params[0],
        })


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


class PrettyStreamHandler(logging.StreamHandler):
    """A :class:`logging.StreamHandler` that wraps log messages with
    severity-dependent ANSI colours."""
    #: Mapping from logging levels to ANSI colours.
    COLOURS = {
        logging.DEBUG: '\033[36m',      # Cyan
        logging.WARNING: '\033[33m',    # Yellow foreground
        logging.ERROR: '\033[31m',      # Red foreground
        logging.CRITICAL: '\033[31;7m'  # Red foreground, inverted
    }
    #: ANSI code for resetting the terminal to default colour.
    COLOUR_END = '\033[0m'

    def format(self, record):
        """Call :meth:`logging.StreamHandler.format`, and apply a colour to the
        message if output stream is a TTY."""
        msg = super(PrettyStreamHandler, self).format(record)
        if self.stream.isatty():
            colour = self.COLOURS.get(record.levelno, '')
            return colour + msg + self.COLOUR_END
        else:
            return msg


def main(argv):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', default='csbot.cfg',
                        help='Configuration file [default: %(default)s]')
    parser.add_argument('-d', '--debug', dest='loglevel', default=logging.INFO,
                        action='store_const', const=logging.DEBUG,
                        help='Debug output [default: off]')
    args = parser.parse_args(argv[1:])

    # Connect Twisted logging to Python logging
    observer = log.PythonLoggingObserver('twisted')
    observer.start()

    # Log to stdout with ANSI color codes to indicate level
    handler = PrettyStreamHandler()
    handler.setLevel(args.loglevel)
    handler.setFormatter(logging.Formatter(
        '[%(asctime)s] (%(levelname).1s:%(name)s) %(message)s',
        '%Y/%m/%d %H:%M:%S'))
    rootlogger = logging.getLogger('')
    rootlogger.setLevel(args.loglevel)
    rootlogger.addHandler(handler)

    # Create bot and run setup functions
    try:
        config = open(args.config, 'r')
    except IOError:
        config = None

    bot = Bot(config)

    if config is not None:
        config.close()

    bot.bot_setup()

    # Connect and enter the reactor loop
    reactor.connectTCP(bot.config_get('irc_host'),
                       int(bot.config_get('irc_port')),
                       BotFactory(bot))
    reactor.run()

    # Run teardown functions before exiting
    bot.bot_teardown()
