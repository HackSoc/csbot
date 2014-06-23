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

    def last(self, nick, channel=None):
        """Get the last thing said (including actions) by a given
        nick, optionally filtering by channel.
        """

        if channel is None:
            return self.db.find_one({'nick': nick},
                                    sort=[('when', pymongo.DESCENDING)])
        else:
            return self.db.find_one({'nick': nick,
                                     'channel': channel},
                                    sort=[('when', pymongo.DESCENDING)])

    def last_message(self, nick, channel=None):
        """Get the last message sent by a nick, optionally filtering
        by channel.
        """

        if channel is None:
            return self.db.find_one({'nick': nick,
                                     'type': 'message'},
                                    sort=[('when', pymongo.DESCENDING)])
        else:
            return self.db.find_one({'nick': nick,
                                     'channel': channel,
                                     'type': 'message'},
                                    sort=[('when', pymongo.DESCENDING)])

    def last_action(self, nick, channel=None):
        """Get the last action sent by a nick, optionally filtering
        by channel.
        """

        if channel is None:
            return self.db.find_one({'nick': nick,
                                     'type': 'action'},
                                    sort=[('when', pymongo.DESCENDING)])
        else:
            return self.db.find_one({'nick': nick,
                                     'channel': channel,
                                     'type': 'action'},
                                    sort=[('when', pymongo.DESCENDING)])

    @Plugin.hook('core.message.privmsg')
    def record_message(self, event):
        """Record the receipt of a new message.
        """

        # Check if this is an action
        if event['message'][:7] == '\x01ACTION':
            print("Action")
            return

        self.db.remove({'nick': nick(event['user']),
                        'channel': event['channel'],
                        'type': 'message'})

        self.db.insert({'nick': nick(event['user']),
                        'channel': event['channel'],
                        'type': 'message',
                        'when': datetime.now(),
                        'message': event['message']})

    @Plugin.hook('core.message.action')
    def record_action(self, event):
        """Record the receipt of a new action.
        """

        self.db.remove({'nick': nick(event['user']),
                        'channel': event['channel'],
                        'type': 'action'})

        self.db.insert({'nick': nick(event['user']),
                        'channel': event['channel'],
                        'type': 'action',
                        'when': datetime.now(),
                        'message': event['message']})

    @Plugin.command('last', help=('last nick: show the last thing'
                                  ' said by a nick in this channel'))
    def show_last(self, event):
        thenick = event['data']
        message = self.last(thenick, channel=event['channel'])

        if message is None:
            event.protocol.msg(event['reply_to'],
                               'Nothing recorded for {}'.format(thenick))
        elif message['type'] == 'message':
            event.protocol.msg(event['reply_to'],
                               '[{}] <{}> {}'.format(message['when'],
                                                     thenick,
                                                     message['message']))
        else:
            event.protocol.msg(event['reply_to'],
                               '[{}] * {} {}'.format(message['when'],
                                                     thenick,
                                                     message['message']))
