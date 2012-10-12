from csbot.core import Plugin
from csbot.util import nick, sensible_time
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
        """
        return self.db.online_users.find({'user': user}).count() > 0

    def is_op(self, nick):
        """
        This checks to see if the given nick has operator privilages.
        """
        user = self.get_user_by_nick(nick)
        return user['op'] == True

    def get_online_users(self):
        """
        This returns a list of all the users currently known to be online.

        This is known to be incomplete at the moment as we can not currently
        get the list of users in the channel.
        """
        return [u['user'] for u in self.db.online_users.find()]

    def get_user_by_nick(self, nick):
        """
        This finds a user in the database with the given nick. Only one
        result will be returned.
        """
        return self.db.online_users.find_one({'user': nick})

    def save_user(self, user):
        """
        This takes a user that has been modified and saves it to the database.
        If the user doesn't already exist in the db it should fail.
        """
        self.db.online_users.update({'_id': user['_id']}, user)

    def save_or_update_user(self, user):
        """
        This takes a user that has been modified and saves it to the database.
        If the user doesn't already exist in the db it will be created.
        """
        self.db.online_users.update({'_id': user['_id']}, user, True)

    def get_users_by_tag(self, tag):
        return self.db.online_users.find({tag: True})

    @Plugin.command('ops')
    def ops(self, event):
        """
        Lists the current channel ops
        """
        ops = []
        for user in self.db.online_users.find():
            if 'op' in user and user['op'] == True:
                ops.append(user['user'])
        event.reply("Current ops: {}".format(", ".join(ops)))

    @Plugin.command('spoke')
    def spoke(self, event):
        """
        Tells the user who asked when the last time the user they asked about
        spoke.
        """
        data = event.arguments()
        usr = self.get_user_by_nick(data[0])
        if usr:
            if 'time_last_spoke' in usr:
                event.reply("{} last said something {}".format(
                    usr['user'], sensible_time(self.bot, usr['time_last_spoke'], True)))
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
                sensible_time(self.bot, usr['time'], True)))
        else:
            usr = self.db.online_users.find_one({'user': data[0]})
            if usr:
                event.reply("{} is here.".format(usr['user']))
            else:
                event.reply("I haven't seen {}".format(data[0]))

    @Plugin.command('register')
    def register(self, event):
        """
        Allows users to register themselves against a tag. Other plugins can then
        use this tag to retrieve users.
        """
        tags = event.arguments()
        usr = self.get_user_by_nick(nick(event['user']))
        if usr:
            for tag in tags:
                usr[tag] = True
            self.save_user(usr)

    @Plugin.command('unregister')
    def unregister(self, event):
        """
        Allows users to unregister themselves from a tag.
        """
        tags = event.arguments()
        usr = self.get_user_by_nick(nick(event['user']))
        if usr:
            modified = False
            for tag in tags:
                if usr[tag]:
                    usr[tag] = False
                    modified = True
            self.save_user(usr)

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
        usr = self.db.online_users.find_one({'user': nick(event['user'])})
        if usr:
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
        # TODO: can this actually happen or will there only ever be one user with a nick?
        usrs = self.db.online_users.find({'user': event['oldnick']})
        if usrs.count() > 1:
            self.db.online_users.remove({'user': event['oldnick']})
        elif usrs.count() < 1:
            usr = {'user': event['newnick'], 'join_time': event.datetime}
            self.db.online_users.insert(usr)
        else:
            usr = usrs.next()
            usr['user'] = event['newnick']
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

    @Plugin.hook('core.channel.modeChanged')
    def modeChanged(self, event):
        # all users in the args tuple have been affected
        if event['mode'] == 'o':
            if event['set']:
                for nick in event['args']:
                    user = self.get_user_by_nick(nick)
                    user['op'] = True
                    self.save_user(user)
            else:
                for nick in event['args']:
                    user = self.get_user_by_nick(nick)
                    del user['op']
                    self.save_user(user)

