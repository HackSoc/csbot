from csbot.plugin import Plugin
from csbot.util import nick
from csbot.events import Event
from datetime import datetime
import pymongo


class Last(Plugin):
    """Utility plugin to record the last message (and time said) of a
    user. Records both messages and actions individually, and allows
    querying on either.
    """
    db = Plugin.use('mongodb', collection='last')

    def last(self, nick, channel=None, msgtype=None):
        """Get the last thing said (including actions) by a given
        nick, optionally filtering by channel.
        """
        search = {'nick': nick}

        if channel is not None:
            search['channel'] = channel

        if msgtype is not None:
            search['type'] = msgtype

        # Additional sorting by _id to make sort order stable for messages that arrive in the same millisecond
        # (which sometimes happens during tests).
        return self.db.find_one(search, sort=[('when', pymongo.DESCENDING), ('_id', pymongo.DESCENDING)])

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
        if event['message'].startswith('\x01ACTION'):
            return

        # Check if this is a command
        if event['message'].startswith(self.bot.config.command_prefix):
            return

        self.record(event,
                    nick(event['user']),
                    event['channel'],
                    'message',
                    event['message'])

    @Plugin.hook('core.message.privmsg')
    def record_command(self, event):
        """Record the receipt of a new command.
        """
        if not event['message'].startswith(self.bot.config.command_prefix):
            return

        self.record(event,
                    nick(event['user']),
                    event['channel'],
                    'command',
                    event['message'])

    @Plugin.hook('core.message.action')
    def record_action(self, event):
        """Record the receipt of a new action.
        """
        self.record(event,
                    nick(event['user']),
                    event['channel'],
                    'action',
                    event['message'])

    def record(self, event, nick, channel, msgtype, msg):
        """Record a new message, of a given type.
        """
        self._schedule_update(event,
                              {'nick': nick,
                               'channel': channel,
                               'type': msgtype},
                              {'nick': nick,
                               'channel': channel,
                               'type': msgtype,
                               'when': datetime.now(),
                               'message': msg})

    def _schedule_update(self, e, query, update):
        self.bot.post_event(Event.extend(e, 'last.update',
                                         {'query': query, 'update': update}))

    @Plugin.hook('last.update')
    def _apply_update(self, e):
        self.db.remove(e['query'])
        self.db.insert(e['update'])

    @Plugin.command('seen', help=('seen nick [type]: show the last thing'
                                  ' said by a nick in this channel, optionally'
                                  ' filtering by type: message, action,'
                                  ' or command.'))
    def show_seen(self, event):
        splitted = event['data'].split()
        thenick = splitted[0]
        msgtype = splitted[1] if len(splitted) > 1 else None

        if msgtype not in ['message', 'command', 'action', None]:
            event.reply('Bad filter: {}. Accepted are "message", "command", and "action".'.format(msgtype))
            return

        message = self.last(thenick, channel=event['channel'], msgtype=msgtype)

        if message is None:
            event.reply('Nothing recorded for {}'.format(thenick))
        elif message['type'] in ['message', 'command']:
            event.reply('[{}] <{}> {}'.format(message['when'].strftime("%Y-%m-%d %H:%M:%S"),
                                              thenick,
                                              message['message']))
        else:
            event.reply('[{}] * {} {}'.format(message['when'].strftime("%Y-%m-%d %H:%M:%S"),
                                              thenick,
                                              message['message']))
