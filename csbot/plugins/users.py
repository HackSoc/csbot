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
        super(Users, self).setup()
        # Setup the db
        self.userdb = UserDB(self.db)
        # Mark any previous records as untrustworth as the may be out of date
        users = self.userdb.all_users()
        for user in users:
            user.set_offline()

    def get_users_by_tag(self, tag):
        return self.db.online_users.find({tag: True})

    @Plugin.command('ops')
    def ops(self, event):
        """
        Lists the current channel ops
        """
        ops = map(str, self.userdb.ops())
        if len(ops) > 0:
            event.reply("Current ops: {}".format(", ".join(ops)))
        else:
            event.reply("Sorry, there don't appear to be any ops here.")

    @Plugin.command('spoke')
    def spoke(self, event):
        """
        Tells the user who asked when the last time the user they asked about
        spoke.
        """
        nck = event.arguments()[0]
        try:
            usr = self.userdb.find_user_by_nick(nck)
            try:
                event.reply("{} last said something at {}".format(
                    usr.dbdict['nick'], sensible_time(self.bot, usr.dbdict['last_spoke'], True)))
            except KeyError:
                event.reply("I don't remember {} saying anything.".format(
                    usr.dbdict['nick']))
        except UserNotFound:
            event.reply("I've never even heard of {}".format(nck))

    @Plugin.command('seen')
    def seen(self, event):
        """
        Tells the user who asked when the last time the user they asked about
        was online.
        """
        nck = event.arguments()[0]
        try:
            usr = self.userdb.find_user_by_nick(nck)
            if usr.is_offline():
                if hasattr(usr, 'disconnection_time'):
                    time = sensible_time(self.bot,
                                         usr.disconnection_time, True)
                    event.reply("{} was last seen at {}".format(usr.dbdict['nick'],
                                                                time))
                else:
                    event.reply("{} left when I wasn't around to see, sorry.".format(usr.dbdict['nick']))
            else:
                event.reply("{} is here.".format(usr.dbdict['nick']))
        except UserNotFound:
            event.reply("I don't know {}".format(nck))

    @Plugin.command('register')
    def register(self, event):
        """
        Allows users to register themselves against a tag. Other plugins can then
        use this tag to retrieve users.
        """
        tags = event.arguments()
        usr = self.userdb.find_user_by_nick(event['user'])
        for tag in tags:
            usr.add_tag(tag)
        usr.save()

    @Plugin.command('unregister')
    def unregister(self, event):
        """
        Allows users to unregister themselves from a tag.
        """
        tags = event.arguments()
        usr = self.userdb.find_user_by_nick(event['user'])
        for tag in tags:
            usr.remove_tag(tag)
        usr.save()

    @Plugin.command('register')
    def register(self, event):
        """
        Allows users to register themselves against a tag. Other plugins can then
        use this tag to retrieve users.
        """
        tags = event.arguments()
        usr = self.userdb.find_user_by_nick(event['user'])
        if usr:
            for tag in tags:
                usr.add_tag(tag)
            usr.save()

    @Plugin.command('unregister')
    def unregister(self, event):
        """
        Allows users to unregister themselves from a tag.
        """
        tags = event.arguments()
        usr = self.userdb.find_user_by_nick(event['user'])
        if usr:
            for tag in tags:
                usr.remove_tag(tag)
            usr.save()

    @Plugin.hook('core.channel.joined')
    def userJoined(self, event):
        try:
            user = self.userdb.find_user_by_nick(event['user'])
            user.set_connected(event.datetime)
        except UserNotFound:
            nick, user, host = User.split_username(event['user'])
            usr = User(self.userdb, nick, user, host)
            if (user is None or host is None):
                event.protocol.whois(nick)
            usr.set_connected(event.datetime)

    @Plugin.hook('core.channel.names')
    def names(self, event):
        """
        When we connect to a channel we get a list of the names. This handles
        that list and updates the lists of users.
        """
        # mode is an array of mode characters, e.g. [u'o']
        for nck, mode in event['names']:
            try:
                usr = self.userdb.find_user_by_nick(nck)
                usr.set_op('o' in mode)
                usr.set_online()
            except UserNotFound:
                event.protocol.whois(nck)

    @Plugin.hook('core.user.whois')
    def whois(self, event):
        try:
            user = self.userdb.find_user_by_nick(event['nick'])
            user.user = event['user']
            user.host = event['host']
        except UserNotFound:
            user = User(self.userdb, event['nick'], event['user'], event['host'])
        user.save_or_create()
        user.set_online()

    @Plugin.hook('core.message.privmsg')
    def privmsg(self, event):
        try:
            usr = self.userdb.find_user_by_nick(event['user'])
            usr.said(event['message'], event.datetime)
        except UserNotFound:
            self.bot.log.info('Didn\'t find a user')

    @Plugin.hook('core.user.renamed')
    def userRenamed(self, event):
        usr = self.userdb.find_user_by_nick(event['oldnick'])
        usr.set_nick(event['newnick'])

    def userOffline(self, event):
        usr = self.userdb.find_user_by_nick(event['nick'])
        usr.set_disconnected()

    @Plugin.hook('core.channel.left')
    def userLeft(self, event):
        self.userOffline(event)

    @Plugin.hook('core.user.quit')
    def userQuit(self, event):
        self.userOffline(event)

    @Plugin.hook('core.channel.kicked')
    def userKicked(self, event):
        kickee = self.userdb.find_user_by_nick(event['kickee'])
        kicker = self.userdb.find_user_by_nick(event['kicker'])
        kickee.set_kicked(event.datetime, kicker, event['message'])

    @Plugin.hook('core.channel.modeChanged')
    def modeChanged(self, event):
        # all users in the args tuple have been affected
        if event['mode'] == 'o':
            if event['set']:
                for nck in event['args']:
                    user = self.userdb.find_user_by_nick(nck)
                    user.set_op(True)
            else:
                for nck in event['args']:
                    user = self.userdb.find_user_by_nick(nck)
                    user.set_op(False)

    def find_users_by_tag(self, tag):
        return self.userdb.find_users_by_tag(tag)


class User(object):
    """
    This class represents a user in the channel. It is backed by the mongo database.

    In the database the basic user looks similar to this:
    {
        'nick': 'Haegin',
        'user': 'HJMills',
        'host': 'unaffiliated/hjmills',
        'online: True,
    }

    They may have extra attributes such as connection/disconnection times,
    last spoke time, last utterance, or tags.
    """

    ONLINE  = 'online'
    OFFLINE = 'offline'
    UNKNOWN = 'unknown'

    def __init__(self, userdb, nick, user, host):
        """
        Creates a new user object by passing nick, user and host separately to skip
        any validation.
        """
        self.userdb = userdb
        self.dbdict = {}
        self.dbdict['nick'] = nick
        self.dbdict['user'] = user
        self.dbdict['host'] = host
        self.save_or_create()

    def __str__(self):
        return self.dbdict['nick']

    def is_online(self):
        """
        This checks to see if the user is known to be online.
        """
        try:
            return self.dbdict['connection_status'] == User.ONLINE
        except KeyError:
            return False

    def is_offline(self):
        """
        This checks to see if the user is known to be offline.
        """
        try:
            return self.dbdict['connection_status'] == User.OFFLINE
        except KeyError:
            return False

    def is_op(self):
        """
        This checks to see if the user has operator privilages.
        """
        try:
            return self.dbdict['op'] == True
        except KeyError:
            return False

    def set_op(self, is_op = True):
        """
        This can set the user to be, or not be, an operator. If the
        is_op parameter is not specified, it sets the user to be an
        operator.
        """
        self.dbdict['op'] = is_op
        self.save()

    def has_tag(self, tag):
        return 'tags' in self.dbdict and tag in self.dbdict['tags']

    def add_tag(self, tag):
        """
        Adds a tag to the user that can be used for a variety of purposes.
        """
        if 'tags' in self.dbdict:
            if tag not in self.dbdict['tags']:
                self.dbdict['tags'].append(tag)
        else:
            self.dbdict['tags'] = [tag]
        self.save()

    def remove_tag(self, tag):
        """
        Removes the given tag from the list of tags associated with the user.
        If the tag isn't in the users tag list, nothing happens.
        """
        if tag in self.dbdict['tags']:
            self.dbdict['tags'].remove(tag)
            self.save()

    def save(self):
        """
        This saves the current user to the database.
        If the user doesn't already exist in the db it should fail.
        """
        self.userdb.update_user(self.dbdict)

    def save_or_create(self):
        """
        This saves the current user to the database.
        If the user doesn't already exist in the db it should create it.
        """
        try:
            self.userdb.update_user(self.dbdict)
        except KeyError: # because the _id is not set
            self.userdb.add_user(self.dbdict)

    def set_online(self):
        """
        Sets the user as online without updating the connection_time.
        """
        self.dbdict['connection_status'] = User.ONLINE
        self.save()

    def set_offline(self):
        """
        Sets the user as offline, without updating the disconnection_time.
        """
        self.dbdict['connection_status'] = User.OFFLINE
        self.save()

    def set_connected(self, time = datetime.now()):
        """
        Marks the user as online and sets the connected_time
        """
        self.dbdict['connection_status'] = User.ONLINE
        self.dbdict['connected_time'] = time
        self.save()

    def set_disconnected(self, time = datetime.now()):
        """
        Sets the user as offline, updating the disconnected_time
        """
        self.dbdict['connection_status'] = User.OFFLINE
        self.dbdict['disconnected_time'] = time
        self.save()

    def set_kicked(self, when, by, why):
        """
        Marks the user as offline and records information about
        them being kicked.
        """
        self.dbdict['connection_status'] = User.OFFLINE
        self.dbdict['disconnected_time'] = when
        self.dbdict['kicked_at'] = when
        self.dbdict['kicked_by'] = by.db_id
        self.dbdict['kicked_because'] = why
        self.save()

    def said(self, message, time=datetime.now()):
        self.dbdict['last_spoke'] = time
        self.dbdict['last_utterance'] = message
        self.save()

    def set_nick(self, newnick):
        self.dbdict['nick'] = newnick
        self.save()

    def db_id(self):
        """
        Provides access to the database id of the user
        """
        return self.dbdict['_id']

    @staticmethod
    def is_full_username(username):
        return "!" in username and "@" in username

    @staticmethod
    def username_has_host(username):
        return "@" in username

    @staticmethod
    def username_has_user(username):
        return "!" in username

    @staticmethod
    def split_username(username):
        """
        Splits a username into a 3 tuple of nick, user and host.
        Parts that aren't available are replaced with None.
        """
        host, user = None, None
        if User.username_has_host(username):
            username, host = username.split("@")
        if User.username_has_user(username):
            username, user = username.split("!")
        return (username, user, host)


class UserDB(object):
    """
    This class represents the users within the database.
    """
    def __init__(self, db):
        self.db = db
        self.db.users.ensure_index('nick')

    def find_user_by_nick(self, nick):
        """
        This finds a user in the database with the given nick.
        """
        if User.is_full_username(nick):
            nick, _, _ = User.split_username(nick)
        db_user = self.db.users.find_one({'nick': nick})
        if db_user:
            return self.to_user(db_user)
        else:
            raise UserNotFound("Sorry, {} could not be found in the database".format(nick))

    def find_users_by_tag(self, tag):
        return [self.to_user(usr) for usr in self.db.users.find({'tags': tag})]

    def online_users(self):
        """
        This returns a list of all the users currently known to be online.
        """
        return [self.to_user(usr) for usr in self.db.users.find({'connection_state': User.ONLINE})]

    def offline_users(self):
        """
        This returns a list of all the users currently known to be offfline.

        This only returns users who HAVE been in the channel. Reporting all users ever
        would be silly
        """
        return [self.to_user(usr) for usr in self.db.users.find({'connection_state': User.OFFLINE})]

    def all_users(self):
        """
        This returns a list of all the users currently in the database.
        """
        return [self.to_user(usr) for usr in self.db.users.find()]

    def ops(self):
        return [self.to_user(usr) for usr in self.db.users.find({'op': True})]

    def update_user(self, user):
        user = self.db.users.update({'_id': user['_id']}, user)

    def add_user(self, user):
        self.db.users.insert(user)

    def to_user(self, db_user):
        #user = User(db_user['nick'], db_user['user'], db_user['host'])
        user = User(self, None, None, None)
        # FIXME: check I'm still sane
        # set all the things on the user
        # not sure if checking each thing isn't nick, user or host is more efficient
        # than just resetting them to the same thing. Could probably get away with
        # not looking them up in the first place actually... bad idea anyone?
        for k, v in db_user.iteritems():
            user.dbdict[k] = v
        return user

    def load_from_database(self, user):
        db_user = self.db.users.find({'nick': user.dbdict['nick']})
        if db_user:
            for k, v in db_user.iteritems():
                user.dbdict[k] = v
        else:
            raise UserNotFound("Sorry, {} could not be found in the database".format(self.nick))


class UserInformationMissing(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


class DatabaseNotSet(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


class UserNotFound(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

