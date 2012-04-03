from functools import wraps
import shlex

from twisted.words.protocols import irc
from twisted.internet import reactor, protocol
from twisted.python import log


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
            self.fire_hook(f.__name__, *args, **kwargs)
    else:
        def newf(self, *args, **kwargs):
            self.fire_hook(f, *args, **kwargs)
        newf.__doc__ = "Generated hook trigger for ``{}``".format(f)
    return newf


def nick(user):
    return user.split('!', 1)[0]


def host(user):
    return user.rsplit('@', 1)[1]


def is_channel(channel):
    return channel.startswith('#')


class Bot(irc.IRCClient):

    nickname = "csyorkbot"
    username = "csyorkbot"
    realname = "cs-york bot"
    sourceURL = 'http://github.com/csyork/csbot/'
    lineRate = 1

    def __init__(self, plugins):
        self.commands = dict()
        self.plugins = [P(self) for P in plugins]
        self.plugin_lookup = dict()
        for p in self.plugins:
            if hasattr(p.__class__, 'NAME'):
                if p.__class__.NAME in self.plugin_lookup:
                    self.log_err('Plugin name ' + p.__class__.NAME +
                                 ' already in use')
                else:
                    self.plugin_lookup[p.__class__.NAME] = p

    def fire_hook(self, hook, *args, **kwargs):
        """Call *hook* on every plugin that has implemented it"""
        for plugin in self.plugins:
            f = getattr(plugin, hook, None)
            if callable(f):
                f(*args, **kwargs)

    def register_command(self, command, f, raw=False):
        """Register *f* as the callback for *command*.

        The callback will be called as ``f(user, channel, data)``.  If *raw* is
        False (default) then ``data`` will be a list of arguments split with
        :func:`shlex.split`.  If *raw* is True then ``data`` will be the entire
        trailing string.

        Returns False if the command already exists, otherwise returns True.
        """
        if command in self.commands:
            self.log_err('Command {} already registered'.format(command))
            return False
        self.commands[command] = {'f': f, 'raw': raw}
        return True

    def fire_command(self, command, user, channel, data, direct):
        """Dispatch *command* to its callback."""
        if command not in self.commands:
            self.error(user, channel,
                       'Command "{}" not found'.format(command),
                       direct)
            return

        cmd = self.commands[command]
        if not cmd['raw']:
            try:
                data = shlex.split(data, posix=False)
            except ValueError:
                self.error(user, channel, 'Unmatched quotation marks', direct)
                return

        cmd['f'](user, channel, data)

    def reply(self, user, channel, msg):
        if nick(user) != channel:
            msg = nick(user) + ': ' + msg
        self.msg(channel, msg)

    def error(self, user, channel, msg, direct):
        self.log_err(msg)
        if direct:
            self.reply(user, channel, "Error: " + msg)

    def log_msg(self, msg):
        """Convenience wrapper around ``twisted.python.log.msg`` for plugins"""
        log.msg(msg)

    def log_err(self, err):
        """Convenience wrapper around ``twisted.python.log.err`` for plugins"""
        log.err(err)

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        print "[Connected]"

    def connectionLost(self, reason):
        irc.IRCClient.connectionMade(self)
        print "[Disconnected because {}]".format(reason)

    def signedOn(self):
        map(self.join, self.factory.channels)

    @hook
    def privmsg(self, user, channel, msg):
        """Handle commands in channel messages.

        Figure out if the message is a user trying to trigger a command, and
        fire that command if it is.  Also figure out if the bot was addressed
        directly (by nick in a channel, or in a private chat) - this will
        decide whether or not the bot shows errors for a failed command.
        """
        # TODO: need a cleaner way to handle this "direct/indirect" thing
        command = None
        direct = False
        if is_channel(channel):
            # In channel, must be triggered explicitly
            if msg.startswith(self.factory.command_prefix):
                # Triggered by command prefix: "<prefix><cmd> <args>"
                command = msg[len(self.factory.command_prefix):]
            elif msg.startswith(self.nickname):
                # Addressing the bot by name: "<nick>, <cmd> <args>"
                msg = msg[len(self.nickname):].lstrip()
                # Check that the bot was specifically addressed, rather than
                # a similar nick or just talking about the bot
                if len(msg) > 0 and msg[0] in ',:;.':
                    command = msg.lstrip(',:;.')
                    direct = True
        elif channel == self.nickname:
            channel = nick(user)
            command = msg
            direct = True

        if command:
            cmd = command.split(None, 1)
            if len(cmd) == 1:
                self.fire_command(cmd[0], user, channel, "", direct)
            elif len(cmd) == 2:
                self.fire_command(cmd[0], user, channel, cmd[1], direct)

    action = hook('action')


class Plugin(object):
    """Bot plugin base class.

    All plugins should subclass this class to be automatically detected and
    loaded.
    """
    def __init__(self, bot):
        self.bot = bot


class BotFactory(protocol.ClientFactory):
    def __init__(self, plugins, channels, command_prefix):
        self.plugins = plugins
        self.channels = channels
        self.command_prefix = command_prefix

    def buildProtocol(self, addr):
        p = Bot(self.plugins)
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        reactor.stop()


def main(argv):
    import sys
    from straight.plugin import load

    # Start twisted logging
    log.startLogging(sys.stdout)

    # Find plugins
    plugins = load('csbot_plugins', subclasses=Plugin)
    print "Plugins found:", plugins

    # Start client
    f = BotFactory(plugins=plugins,
                   channels=['#cs-york-dev'],
                   command_prefix='!')
    reactor.connectTCP('irc.freenode.net', 6667, f)
    reactor.run()
