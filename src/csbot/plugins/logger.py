import logging

from csbot.core import Plugin
from csbot.util import nick


class Logger(Plugin):
    raw_log = logging.getLogger('csbot.raw_log')
    pretty_log = logging.getLogger('csbot.pretty_log')

    @Plugin.hook('core.raw.received')
    def raw_received(self, event):
        self.raw_log.debug('>>> ' + repr(event['message']))

    @Plugin.hook('core.raw.sent')
    def raw_sent(self, event):
        self.raw_log.debug('<<< ' + repr(event['message']))

    @Plugin.hook('core.raw.connected')
    def connected(self, event):
        self.pretty_log.info('[Connected]')

    @Plugin.hook('core.raw.disconnected')
    def disconnected(self, event):
        self.pretty_log.info('[Disconnected: {}]'.format(event['reason']))

    @Plugin.hook('core.self.connected')
    def signedon(self, event):
        self.pretty_log.info('[Signed on]')

    @Plugin.hook('core.self.joined')
    def joined(self, event):
        self.pretty_log.info('[Joined {0}]'.format(event['channel']))

    @Plugin.hook('core.self.left')
    def left(self, event):
        self.pretty_log.info('[Left {0}]'.format(event['channel']))

    @Plugin.hook('core.channel.joined')
    def user_joined(self, event):
        self.pretty_log.info('[{channel}] {user} has joined'.format(
            channel=event['channel'], user=event['user']))

    @Plugin.hook('core.channel.left')
    def user_left(self, event):
        self.pretty_log.info('[{channel}] {user} has left'.format(
            channel=event['channel'], user=event['user']))

    @Plugin.hook('core.channel.names')
    def names(self, event):
        self.pretty_log.info('[{channel}] Users: {names}'.format(
            channel=event['channel'], names=', '.join(event['raw_names'])))

    @Plugin.hook('core.channel.topic')
    def topic(self, event):
        self.pretty_log.info('[{channel}] Topic: {topic}'.format(
            channel=event['channel'], topic=event['topic']))

    @Plugin.hook('core.message.privmsg')
    def privmsg(self, event):
        self.pretty_log.info('[{channel}] <{nick}> {message}'.format(
            channel=event['channel'],
            nick=nick(event['user']),
            message=event['message']))

    @Plugin.hook('core.message.notice')
    def notice(self, event):
        self.pretty_log.info('[{channel}] -{nick}- {message}'.format(
            channel=event['channel'],
            nick=nick(event['user']),
            message=event['message']))

    @Plugin.hook('core.message.action')
    def action(self, event):
        self.pretty_log.info('[{channel}] * {nick} {message}'.format(
            channel=event['channel'],
            nick=nick(event['user']),
            message=event['message']))

    @Plugin.hook('core.user.quit')
    def quit(self, event):
        self.pretty_log.info('{user} has quit'.format(user=event['user']))

    @Plugin.hook('core.user.renamed')
    def renamed(self, event):
        self.pretty_log.info('{oldnick} is now {newnick}'.format(
            oldnick=event['oldnick'], newnick=event['newnick']))

    @Plugin.hook('core.command')
    def command(self, event):
        self.pretty_log.info(
            'Command {command} fired by {nick} in channel {channel}'.format(
                command=(event['command'], event['data']),
                nick=nick(event['user']),
                channel=event['channel']))
