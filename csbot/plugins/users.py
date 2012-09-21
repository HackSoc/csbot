from csbot.core import Plugin
from datetime import datetime


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
        # Clear out any previous records as the may be out of date and can't be
        # trusted any more
        self.db.offline_users.remove()
        self.db.online_users.remove()
        super(Users, self).setup()

    def is_online(self, user):
        """
        This checks to see if a user is known to be online.

        If they have not done anything since the bot joined it will return a
        false negative.  This is a known limitation that will be overcome when
        it becomes possible to query the list of users in the channel.
        """
        return self.db.online_users.find({'user': user}).count() > 0

    def get_online_users(self):
        """
        This returns a list of all the users currently known to be online.

        This is known to be incomplete at the moment as we can not currently
        get the list of users in the channel.
        """
        return [u['user'] for u in self.db.online_users.find()]

    @Plugin.command('spoke')
    def spoke(self, event):
        """
        Tells the user who asked when the last time the user they asked about
        spoke.
        """
        data = event.arguments()
        usr = self.db.online_users.find_one({'user': data[0]})
        if usr:
            if 'time_last_spoke' in usr:
                event.reply("{} last said something {}".format(
                    usr['user'], usr['time_last_spoke']))
            else:
                event.reply("I don't remember {} saying anything.".format(
                    usr['user']))
        else:
            event.reply("I've never even heard of {}".format(data[0]))

    @Plugin.command('seen')
    def seen(self, event):
        """
        Tells the user who asked when the last time the user they asked about
        was online.
        """
        data = event.arguments()
        usr = self.db.offline_users.find_one({'user': data[0]})
        if usr:
            event.reply("{} was last seen at {}".format(usr['user'],
                usr['time']))
        else:
            usr = self.db.online_users.find_one({'user': data[0]})
            if usr:
                event.reply("{} is here.".format(usr['user']))
            else:
                event.reply("I haven't seen {}".format(data[0]))

    @Plugin.hook('core.channel.joined')
    def userJoined(self, event):
        usr_matcher = {'user': event['user']}
        # Delete any records of them being offline
        self.db.offline_users.remove(usr_matcher)
        # Update any existing records.
        records = self.db.online_users.find(usr_matcher)
        if records.count > 1:
            # if there is more than one record, remove them and re-add them to
            # be sure we only have one record of it
            self.db.online_users.remove(usr_matcher)
            usr_matcher['join_time'] = event.datetime
            self.db.online_users.insert(usr_matcher)
            # if there is one record update it
        elif records.count == 1:
            usr = records.next()
            usr['join_time'] = event.datetime
            self.db.online_users.update({'_id': usr['_id']}, usr)
        else:
            # if there is no record create a new one
            usr_matcher['join_time'] = event.datetime
            self.db.online_users.insert(usr_matcher)

    @Plugin.hook('core.channel.names')
    def names(self, event):
        """
        When we connect to a channel we get a list of the names. This handles
        that list and updates the lists of users.
        """
        # Remove everyone in the db
        self.db.online_users.remove()
        self.db.offline_users.remove()
        for nick, mode in event['names']:
            self.db.online_users.insert({
                'user': nick,
                'join_time': event.datetime,
                })

    @Plugin.hook('core.message.privmsg')
    def privmsg(self, event):
        self.bot.log.info('Called privmsg')
        usr = self.db.online_users.find_one({'user': event['user']})
        self.bot.log.info('event: ' + str(event))
        if usr:
            self.bot.log.info('Found a user')
            usr['last_said'] = event['message']
            usr['time_last_spoke'] = event.datetime
            self.db.online_users.update({'_id': usr['_id']}, usr)
        else:
            self.bot.log.info('Didn\'t find a user')
#            usr = {'user': event.user,
#                    'time_last_spoke': event.datetime,
#                    'join_time': event.datetime}
#            self.db.online_users.insert(usr)

    @Plugin.hook('core.user.renamed')
    def userRenamed(self, event):
        usrs = self.db.online_users.find({'user': event['oldnick']})
        if usrs.count() > 1:
            self.db.online_users.remove({'user': event['oldnick']})
        elif usrs.count() < 1:
            usr = {'user': event['newnick'], 'join_time': event.datetime}
            self.db.online_users.insert(usr)
        else:
            usr = usrs.next()
            usrs['user'] = event['newnick']
            self.db.online_users.update({'_id': usr['_id']}, usr)

    def userOffline(self, event):
        # Remove any record of being online or offline
        self.db.online_users.remove({'user': event['user']})
        self.db.offline_users.remove({'user': event['user']})
        # Be offline
        self.db.offline_users.insert({
            'user': event['user'],
            'time': datetime.now()
            })

    @Plugin.hook('core.channel.left')
    def userLeft(self, event):
        self.userOffline(event)

    @Plugin.hook('core.channel.quit')
    def userQuit(self, event):
        self.userOffline(event)

    @Plugin.hook('core.user.quit')
    def userKicked(self, event):
        self.userOffline(event)
