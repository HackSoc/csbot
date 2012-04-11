from csbot.core import Plugin, PluginFeatures
from csbot.util import nick
from datetime import datetime


class Tell(Plugin):
    features = PluginFeatures()

    @features.command('printmsgs')
    def print_messages_command(self, event):
        """
        This is just for debugging so I can get it to print the currently known
        messages to check things are working. I'll remove it when private
        messages get added probably.
        """
        for msg in self.db.messages.find():
            print(msg)

    @features.command('tell')
    def tell_command(self, event):
        """
        Stores a message for a user to be delivered when the user is next in
        the channel.

        Usage:
        !tell <user> <message>

        Example:
        > TestUser  [13:37] | !tell Haegin You are awesome.
        > Bot       [13:37] | TestUser, I'll let Haegin know.

        If Haegin is already in the channel the bot should let the user know.
        > Bot       [13:37] | TestUser, Haegin is here, you can tell them
        > yourself!

        When Haegin next connects to the channel the bot will send him a
        message of the following form:
        > Haegin, "You are awesome." - TestUser (at 13:37)

        TODO:
        - It should be possible to leave a long message (how long is long?).
        - Long messages should be announced in the channel but sent as a PM
        - Implement a private message feature that won't be announced in the
          channel
        - We need to handle messages which are just long enough to fit in one
          message when saved but too long when the citation and time is added.
        """
        print(event.data)
        to_user = event.data[0]
        message = " ".join(event.data[1:])
        from_user = nick(event.user)
        # TODO: this should probably do some i18n but being as the channel is
        # largely in the UK...
        time = datetime.now()
        if (self.bot.get_plugin("users.Users").is_online(to_user)):
            event.reply("{} is here, you can tell them yourself."
                    .format(to_user))
        else:
            msg = {'message': message,
                   'from': from_user,
                   'to': to_user,
                   'time': time}
            self.db.messages.insert(msg)
            event.reply("{}, I'll let {} know.".format(from_user, to_user))

    @features.hook('userJoined')
    def userJoined(self, event):
        print("user {} has joined the channel {}".format(event.user,
            event.channel))
        msgs = self.getMessages(event.user)
        if msgs.count() > 1:
            deliver_to = event.user
            event.protocol.msg(event.channel,
                    "{}, several people left messages for you. \
                    Please check the PMs I'm sending you.".format(event.user))
        else:
            deliver_to = event.channel
        for msg in msgs:
            from_user = msg['from']
            time = msg['time'].strftime('%H:%M')
            message = msg['message']
            self.sendMessage(event.protocol, deliver_to, from_user, event.user, message, time)
            # Remove the message now we've delivered it
            self.db.messages.remove(msg['_id'])

    def sendMessage(self, bot, channel, from_user, to_user, message, time):
        msg = "{}, \"{}\" - {} (at {})".format(
                to_user, message, from_user, time)
        bot.msg(channel, msg)

    def getMessages(self, user):
        """
        Gets a mongodb cursor to allow iterating over all the messages for a
        user
        """
        return self.db.messages.find({'to': user})

    def hasMessages(self, user):
        return (self.db.messages.find({'to': user}).count() > 0)

    def action(self, user, channel, action):
        print "*", action

    @features.command('messages')
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
