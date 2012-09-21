import logging
import collections

from twisted.words.protocols import irc
from twisted.internet import reactor, protocol
from twisted.python import log
import pymongo
import configparser

from csbot.plugin import Plugin, PluginManager
import csbot.events as events
from csbot.events import Event, CommandEvent
from csbot.util import nick


class Bot(Plugin):
    """The IRC bot.

    Handles plugins, command dispatch, hook dispatch, etc.  Persistent across
    losing and regaining connection.
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
            'mongodb_uri': 'mongodb://localhost:27017',
            'mongodb_prefix': 'csbot__',
    }

    #: Environment variable fallbacks
    CONFIG_ENVVARS = {
            'password': ['IRC_PASS'],
            'mongodb_uri': ['MONGOLAB_URI', 'MONGODB_URI'],
    }

    #: The top-level package for all bot plugins
    PLUGIN_PACKAGE = 'csbot.plugins'

    def __init__(self, configpath):
        super(Bot, self).__init__(self)

        # Load the configuration file
        self.config_path = configpath
        self.config_root = configparser.ConfigParser(interpolation=None,
                                                     allow_no_value=True)
        with open(self.config_path, 'r') as cfg:
            self.config_root.read_file(cfg)

        # Make mongodb connection
        self.log.info('connecting to mongodb: ' +
                      self.config_get('mongodb_uri'))
        self.mongodb = pymongo.Connection(self.config_get('mongodb_uri'))

        # Plugin management
        self.plugins = PluginManager(self.PLUGIN_PACKAGE, Plugin,
                                     self.config_get('plugins').split(),
                                     [self], [self])
        self.commands = {}

        # Event runner
        self.events = events.ImmediateEventRunner(
            lambda e: self.plugins.broadcast('fire_hooks', (e,)))

    @classmethod
    def plugin_name(cls):
        """Special plugin name that can't clash with real plugin classes.
        """
        return '@' + super(Bot, cls).plugin_name()

    def setup(self):
        """Load plugins defined in configuration.
        """
        super(Bot, self).setup()
        self.plugins.broadcast('setup', static=False)

    def teardown(self):
        """Unload plugins and save data.
        """
        super(Bot, self).teardown()
        self.plugins.broadcast('teardown', static=False)

    def post_event(self, event):
        self.events.post_event(event)

    def register_command(self, cmd, f, tag=None):
        # Bail out if the command already exists
        if cmd in self.commands:
            oldf, oldtag = self.commands[cmd]
            self.log.warn('tried to overwrite command: {}'.format(cmd))
            return False

        self.commands[cmd] = (f, tag)
        self.log.info('registered command: ({}, {})'.format(cmd, tag))
        return True

    def unregister_command(self, cmd, tag=None):
        if cmd in self.commands:
            f, t = self.commands[cmd]
            if t == tag:
                del self.commands[cmd]
                self.log.info('unregistered command: ({}, {})'
                              .format(cmd, tag))
            else:
                self.log.error(('tried to remove command {} ' +
                                'with wrong tag {}').format(cmd, tag))

    def unregister_commands(self, tag):
        delcmds = [c for c, (f, t) in self.commands.iteritems() if t == tag]
        for cmd in delcmds:
            f, tag = self.commands[cmd]
            del self.commands[cmd]
            self.log.info('unregistered command: ({}, {})'.format(cmd, tag))

    @Plugin.hook('core.self.connected')
    def signedOn(self, event):
        map(event.protocol.join, self.config_get('channels').split())

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

        f, _ = self.commands[event['command']]
        f(event)

    @Plugin.command('help')
    def show_commands(self, event):
        event.protocol.msg(event['reply_to'], ', '.join(sorted(self.commands)))

    @Plugin.command('plugins')
    def show_plugins(self, event):
        event.protocol.msg(event['reply_to'],
                           'loaded plugins: ' + ', '.join(self.plugins))


class PluginError(Exception):
    pass


class BotProtocol(irc.IRCClient):
    log = logging.getLogger('csbot.protocol')

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
        self.emit_new('core.raw.connected')

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)
        self.emit_new('core.raw.disconnected', {'reason': reason})

    def sendLine(self, line):
        # Encode unicode strings with utf-8
        if isinstance(line, unicode):
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

    def userJoined(self, user, channel):
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
        inverse_prefixes = dict((v[0], k) for k, v in prefixes.iteritems())

        # Get mode characters from name prefix
        def f(name):
            if name[0] in inverse_prefixes:
                return (name[1:], set(inverse_prefixes[name[0]]))
            else:
                return (name, set())
        names = map(f, raw_names)

        # Fire the event
        self.names(channel, names, raw_names)

    def topicUpdated(self, user, channel, newtopic):
        self.emit_new('core.channel.topic', {
            'channel': channel,
            'author': user,     # might be server name or nick
            'topic': newtopic,
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


class ColorLogFilter(logging.Filter):
    """Add ``color`` attribute with severity-relevant ANSI color code to log
    records.
    """
    def filter(self, record):
        formats = {
            logging.DEBUG: '1;30',
            logging.INFO: '',
            logging.WARNING: '33',
            logging.ERROR: '31',
            logging.CRITICAL: '7;31',
        }
        record.color = formats.get(record.levelno, '')
        return record


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
    handler = logging.StreamHandler()
    handler.setLevel(args.loglevel)
    handler.addFilter(ColorLogFilter())
    handler.setFormatter(logging.Formatter(
        '\x1b[%(color)sm[%(asctime)s] (%(name)s) %(message)s\x1b[0m',
        '%Y/%m/%d %H:%M:%S'))
    rootlogger = logging.getLogger('')
    rootlogger.setLevel(args.loglevel)
    rootlogger.addHandler(handler)

    # Create bot and run setup functions
    bot = Bot(args.config)
    bot.setup()

    # Connect and enter the reactor loop
    reactor.connectTCP(bot.config_get('irc_host'),
                       int(bot.config_get('irc_port')),
                       BotFactory(bot))
    reactor.run()

    # Run teardown functions before exiting
    bot.teardown()
