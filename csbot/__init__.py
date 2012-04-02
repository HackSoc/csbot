from twisted.words.protocols import irc
from twisted.internet import reactor, protocol
from twisted.python import log


class Bot(irc.IRCClient):

    nickname = "csyorkbot"
    username = "csyorkbot"
    realname = "cs-york bot"
    sourceURL = 'http://github.com/csyork/csbot/'
    lineRate = 1

    def __init__(self, plugins):
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
        self.fire_hook('signedOn')

    def privmsg(self, user, channel, msg):
        print ">>>", msg
        self.fire_hook('privmsg', user, channel, msg)


class Plugin(object):
    """Bot plugin base class.

    All plugins should subclass this class to be automatically detected and
    loaded.
    """
    def __init__(self, bot):
        self.bot = bot


class BotFactory(protocol.ClientFactory):
    def __init__(self, plugins, channels):
        self.plugins = plugins
        self.channels = channels

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
    f = BotFactory(plugins=plugins, channels=['#cs-york-dev'])
    reactor.connectTCP('irc.freenode.net', 6667, f)
    reactor.run()
