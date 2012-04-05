from csbot.core import Plugin, command
from time import localtime, strftime


class Tell(Plugin):
    messages = {}   # This is a dict, storing nickname -> [messages] pairs
                    # Messages are dicts with message, time and from attributes.

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
        (to_user, message) = event.data.split(" ", 1)[0]
        from_user = event.user
        time = localtime()  # TODO: this should probably do some i18n but
                            # being as the channel is largely in the UK...
        if (user_is_here):
                # TODO: implement this
        msg = {'message': message, 'from': from_user, 'time': time}
        if (messages.has_key(to_user)):
            messages[to_user].append(msg)
        else:
            messages[to_user] = [msg]

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

    def getMessages(self, user):
        if (messages.has_key(user)):
            return messages.get(user)
        else:
            return []

    def hasMessages(self, user):
        return (messages.has_key(user))

    def action(self, user, channel, action):
        print "*", action
