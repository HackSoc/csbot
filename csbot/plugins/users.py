from csbot.core import Plugin
from csbot.util import sensible_time
from csbot.plugins.user.user import User


class Users(Plugin):
    """
    This class provides various utility functions for other plugins to use when
    keeping track of users and nicks.
    It also provides !seen and !spoke functionality.

    To do this it gets a list of logged in users when it joins the channel and
    then updates this list when users change nick, leave the channel or join
    the channel.
    """

    def setup(self):
        # Mark any previous records as untrustworth as the may be out of date
        for user in User.all_users():
            user.set_offline()
        super(Users, self).setup()

    @Plugin.command('ops')
    def ops(self, event):
        """
        Lists the current channel ops
        """
        ops = []
        for user in User.online_users():
            if 'op' in user and user['op']:
                ops.append(user['user'])
        event.reply("Current ops: {}".format(", ".join(ops)))

    @Plugin.command('spoke')
    def spoke(self, event):
        """
        Tells the user who asked when the last time the user they asked about
        spoke.
        """
        nck = event.arguments()[0]
        try:
            usr = User.find_user_by_nick(nck)
            if 'last_spoke' in usr:
                event.reply("{} last said something at {}".format(
                    usr.nick, sensible_time(self.bot, usr.last_spoke, True)))
            else:
                event.reply("I don't remember {} saying anything.".format(
                    usr.nick))
        except User.NotFound:
            event.reply("I've never even heard of {}".format(nck))

    @Plugin.command('seen')
    def seen(self, event):
        """
        Tells the user who asked when the last time the user they asked about
        was online.
        """
        nck = event.arguments()[0]
        try:
            usr = User.find_user_by_nick(nck)
            if usr.is_offline:
                if 'is_connected' in usr:
                    time = sensible_time(self.bot,
                                         usr.disconnection_time, True)
                    event.reply("{} was last seen at {}".format(usr.nick,
                                                                time))
                else:
                    event.reply("{} left when I wasn't \
                            around to see, sorry.".format(usr.nick))
            else:
                event.reply("{} is here.".format(usr.nick))
        except User.NotFound:
            event.reply("I don't know {}".format(nck))

    @Plugin.hook('core.channel.joined')
    def userJoined(self, event):
        user = User.find_user_by_nick(event['user'])
        try:
            user.load_from_database()
        except User.NotFound:
            pass
            # User hasn't been seen before
        user.set_connected(event.datetime)

    @Plugin.hook('core.channel.names')
    def names(self, event):
        """
        When we connect to a channel we get a list of the names. This handles
        that list and updates the lists of users.
        """
        for nck, mode in event['names']:
            try:
                usr = User.find_user_by_nick(nck)
                usr.set_online()
            except User.NotFound:
                pass
                # FIXME: fire off a whois
            # if they exist, yay, if not, fire off a whois and set up
            # a handler to register the user and host information etc.

    @Plugin.hook('core.message.privmsg')
    def privmsg(self, event):
        try:
            usr = User.find_user_by_nick(event['user'])
            usr.said(event['message'], event.datetime)
        except User.NotFound:
            self.bot.log.info('Didn\'t find a user')

    @Plugin.hook('core.user.renamed')
    def userRenamed(self, event):
        usr = User.find_user_by_nick(event['oldnick'])
        usr.set_nick(event['newnick'])

    def userOffline(self, event):
        usr = User.find_user_by_nick(event['nick'])
        usr.set_disconnected()

    @Plugin.hook('core.channel.left')
    def userLeft(self, event):
        self.userOffline(event)

    @Plugin.hook('core.channel.quit')
    def userQuit(self, event):
        self.userOffline(event)

    @Plugin.hook('core.user.quit')
    def userKicked(self, event):
        self.userOffline(event)

    @Plugin.hook('core.channel.modeChanged')
    def modeChanged(self, event):
        # all users in the args tuple have been affected
        if event['mode'] == 'o':
            if event['set']:
                for nck in event['args']:
                    user = User.find_user_by_nick(nck)
                    user.set_op(True)
            else:
                for nck in event['args']:
                    user = User.find_user_by_nick(nck)
                    user.set_op(False)
