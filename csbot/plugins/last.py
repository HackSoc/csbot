from csbot.plugin import Plugin
from csbot.util import nick
from datetime import datetime
import pymongo


class Last(Plugin):
    """Utility plugin to record the last message (and time said) of a
    user. Records both messages and actions individually, and allows
    querying on either.
    """

    db = Plugin.use('mongodb', collection='last')

    def provide(self):
        """Return a reference to the plugin, allowing other plugins to
        use it."""

        return self

    def last(self, nick, channel=None, msgtype=None):
        """Get the last thing said (including actions) by a given
        nick, optionally filtering by channel.
        """

        search = {'nick': nick}

        if channel is not None:
            search['channel'] = channel

        if msgtype is not None:
            search['type'] = msgtype

        return self.db.find_one(search, sort=[('when', pymongo.DESCENDING)])

    def last_message(self, nick, channel=None):
        """Get the last message sent by a nick, optionally filtering
        by channel.
        """

        return self.last(nick, channel=channel, msgtype='message')

    def last_action(self, nick, channel=None):
        """Get the last action sent by a nick, optionally filtering
        by channel.
        """

        return self.last(nick, channel=channel, msgtype='action')

    def last_command(self, nick, channel=None):
        """Get the last command sent by a nick, optionally filtering
        by channel.
        """

        return self.last(nick, channel=channel, msgtype='command')

    @Plugin.hook('core.message.privmsg')
    def record_message(self, event):
        """Record the receipt of a new message.
        """

        # Check if this is an action
        if event['message'][:7] == '\x01ACTION':
            return

        # Check if this is a command
        if event['message'][0] == self.bot.config_get('command_prefix'):
            return

        self.record(nick(event['user']), event['channel'], 'message',
                    event['message'])

    @Plugin.hook('core.message.privmsg')
    def record_command(self, event):
        """Record the receipt of a new command.
        """

        if event['message'][0] != self.bot.config_get('command_prefix'):
            return

        self.record(nick(event['user']), event['channel'], 'command',
                    event['message'])

    @Plugin.hook('core.message.action')
    def record_action(self, event):
        """Record the receipt of a new action.
        """

        self.record(nick(event['user']), event['channel'], 'action',
                    event['message'])

    def record(self, nick, channel, msgtype, msg):
        """Record a new message, of a given type.
        """

        self.db.remove({'nick': nick,
                        'channel': channel,
                        'type': msgtype})

        self.db.insert({'nick': nick,
                        'channel': channel,
                        'type': msgtype,
                        'when': datetime.now(),
                        'message': msg})

    @Plugin.command('last', help=('last nick [type]: show the last thing'
                                  ' said by a nick in this channel, optionally'
                                  ' filtering by type: message, action,'
                                  ' or command.'))
    def show_last(self, event):
        splitted = event['data'].split()
        thenick = splitted[0]
        msgtype = splitted[1] if len(splitted) > 1 else None
        message = self.last(thenick, channel=event['channel'], msgtype=msgtype)

        if message is None:
            event.protocol.msg(event['reply_to'],
                               'Nothing recorded for {}'.format(thenick))
        elif message['type'] in ['message', 'command']:
            event.protocol.msg(event['reply_to'],
                               '[{}] <{}> {}'.format(message['when'].strftime("%Y-%m-%d %H:%M:%S"),
                                                     thenick,
                                                     message['message']))
        else:
            event.protocol.msg(event['reply_to'],
                               '[{}] * {} {}'.format(message['when'].strftime("%Y-%m-%d %H:%M:%S"),
                                                     thenick,
                                                     message['message']))
