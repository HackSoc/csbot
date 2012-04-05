from csbot.core import Plugin, command
from time import localtime, strftime


class Tell(Plugin):
    # Messages are stored in a dict, storing nickname -> [messages] pairs
    # Each message is a dict with message, time and from attributes.

    def __init__(self, bot):
        super(Tell, self).__init__(bot)
        self.messages = {}

    @command('printmsgs')
    """
    This is just for debugging so I can get it to print the currently known messages
    to check things are working. I'll remove it when private messages get added probably.
    """
    def print_messages_command(self, event):
        for user in self.messages:
            messages = self.messages[user]
            for message in messages:
                print(message)

    @command('tell')
    def tell_command(self, event):
        """
        Stores a message for a user to be delivered when the user is next in the channel.

        Usage:
        !tell <user> <message>

        Example:
        > TestUser  [13:37] | !tell Haegin You are awesome.
        > Bot       [13:37] | TestUser, I'll let Haegin know.

        If Haegin is already in the channel the bot should let the user know.
        > Bot       [13:37] | TestUser, Haegin is here, you can tell them yourself!

        When Haegin next connects to the channel the bot will send him a message of the following form:
        > Haegin, "You are awesome." - TestUser (at 13:37)

        TODO:
        - It should be possible to leave a long message (how long is long?).
        - Long messages should be announced in the channel but sent as a PM
        - Implement a private message feature that won't be announced in the channel
        - We need to handle messages which are just long enough to fit in one message when
            saved but too long when the citation and time is added.
        """
        print(event.data)
        to_user = event.data[0]
        message = " ".join(event.data[1:])
        from_user = event.user
        time = localtime()  # TODO: this should probably do some i18n but
                            # being as the channel is largely in the UK...
        user_is_here = False
        if (user_is_here):
            # TODO: implement the check
            event.reply("{}, {} is here, you can tell them yourself.".format(from_user, to_user))
        else:
            msg = {'message': message, 'from': from_user, 'time': time}
            if (self.messages.has_key(to_user)):
                self.messages[to_user].append(msg)
            else:
                self.messages[to_user] = [msg]

            event.reply("{}, I'll let {} know.".format(from_user, to_user))

        #event.reply(('test invoked: {0.user}, {0.channel}, '
        #             '{0.data}').format(event))
        #event.reply('raw data: ' + event.raw_data, is_verbose=True)

    @command('messages')
    def messages_command(self, event):
        """
        Notifies a user if they have received any messages recently

        Example Usage:
        > TestUser  [13:37] | !messages
        > Bot       [13:37] | You have 2 messages, please check your PM.

        If the user has no messages it will tell them
        > Bot       [13:37] | You have no messages. Sorry.
        """
        # TODO: implement

    def on_join(event):
        if (hasMessages(event.user)):
            messages = getMessages(event.user)
            if (len(messages) <= 1):
                # If there is only one message we can tell them in the channel
                sendMessage(event, messages[0])
            for msg in messages:
                # If there is more than one message we need to PM them and tell
                # to check their PM.
                sendMessage(event, msg, isPM=True)
            event.reply("{}, several people left messages for you. Please check the PM I sent you.".format(event.user))

    def sendMessage(event, message, isPM=False):
        from_user = message['from']
        to_user = message['to']
        message = message['message']
        time = message['time']
        event.reply("{}, \"{}\" - {} (at {})".format(to_user, message, from_user, time))

    def getMessages(self, user):
        if (self.messages.has_key(user)):
            return self.messages.get(user)
        else:
            return []

    def hasMessages(self, user):
        return (self.messages.has_key(user))

    def action(self, user, channel, action):
        print "*", action
