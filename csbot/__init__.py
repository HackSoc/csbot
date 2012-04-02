from twisted.words.protocols import irc
from twisted.internet import reactor, protocol
from twisted.python import log


class Bot(irc.IRCClient):

    nickname = "csyorkbot"
    username = "csyorkbot"
    realname = "cs-york bot"
    sourceURL = 'http://github.com/csyork/csbot/'
    lineRate = 1

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        print "[Connected]"

    def connectionLost(self, reason):
        irc.IRCClient.connectionMade(self)
        print "[Disconnected because {}]".format(reason)

    def signedOn(self):
        map(self.join, self.factory.channels)

    def privmsg(self, user, channel, msg):
        print ">>>", msg


class Plugin(object):
    def __init__(self, bot):
        raise NotImplementedError


class BotFactory(protocol.ClientFactory):
    def __init__(self, plugins, channels):
        self.plugins = plugins
        self.channels = channels

    def buildProtocol(self, addr):
        p = Bot()
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        reactor.stop()


if __name__ == '__main__':
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
