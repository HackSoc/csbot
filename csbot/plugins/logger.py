import logging

from csbot.core import Plugin, PluginFeatures
from csbot.util import nick


class Logger(Plugin):
    features = PluginFeatures()
    raw_log = logging.getLogger('csbot.raw_log')
    pretty_log = logging.getLogger('csbot.pretty_log')

    @features.hook('core.raw.received')
    def raw_received(self, event):
        self.raw_log.debug('>>> ' + repr(event['message']))

    @features.hook('core.raw.sent')
    def raw_sent(self, event):
        self.raw_log.debug('<<< ' + repr(event['message']))

    @features.hook('core.raw.connected')
    def connected(self, event):
        self.pretty_log.info('[Connected]')

    @features.hook('core.raw.disconnected')
    def connected(self, event):
        self.pretty_log.info('[Disconnected: {}]'.format(event['reason']))

    @features.hook('core.self.connected')
    def connected(self, event):
        self.pretty_log.info('[Signed on]')

    @features.hook('core.self.joined')
    def joined(self, event):
        self.pretty_log.info('[Joined {0}]'.format(event['channel']))

    @features.hook('core.self.left')
    def joined(self, event):
        self.pretty_log.info('[Left {0}]'.format(event['channel']))

    @features.hook('core.message.privmsg')
    def privmsg(self, event):
        self.pretty_log.info(
            '[{channel}] <{nick}> {message}'.format(
                channel=event['channel'],
                nick=nick(event['user']),
                message=event['message']))

    @features.hook('core.message.action')
    def action(self, event):
        self.pretty_log.info(
            '[{channel}] * {nick} {message}'.format(
                channel=event['channel'],
                nick=nick(event['user']),
                message=event['message']))

    @features.hook('core.command')
    def command(self, event):
        self.pretty_log.info(
            'Command {command} fired by {nick} in channel {channel}'.format(
                command=(event['command'], event['data']),
                nick=nick(event['user']),
                channel=event['channel']))
