from csbot.core import Plugin
from csbot.util import nick, sensible_time
from datetime import datetime

def needs_db(fn):
    def decorator():
        if hasattr(User, 'db'):
            fn()
        else:
            raise DatabaseNotSet("You need to set up the database before calling {}".format(fn.__name__))
    return decorator


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
        User.set_database(self.db)
        # Mark any previous records as untrustworth as the may be out of date
        users = User.all_users()
        print "Users in setup: {}".format(users)
        for user in users:
            user.set_offline()

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

    def __init__(self, irc_user):
        """
        This relies on the irc_user being passed in being a full username
        including nick, user and host information. If it isn't an exception
        will be raised.
        """
        if is_full_username(irc_user):
            self.nick, self.user, self.host = split_username(irc_user)
        else:
            raise UserInformationMissing("A username must have a nick, user and a host")

    def __init__(self, nick, user, host):
        """
        Creates a new user object by passing nick, user and host separately to skip
        any validation.
        """
        self.nick = nick
        self.user = user
        self.host = host

    def is_online(self):
        """
        This checks to see if the user is known to be online.
        """
        return self.connection_status == User.ONLINE

    def is_offline(self):
        """
        This checks to see if the user is known to be offline.
        """
        return self.connection_status == User.OFFLINE

    def is_op(self):
        return self.op == True

    @needs_db
    def set_op(self, is_op = True):
        """
        This checks to see if the user has operator privilages.
        """
        self.op = is_op
        self.save

    @needs_db
    def set_tag(self, tag):
        self.tag = True
        self.save

    @needs_db
    def unset_tag(self, tag):
        self.tag = False
        self.save

    @needs_db
    def save(self):
        """
        This saves the current user to the database.
        If the user doesn't already exist in the db it should fail.
        """
        User.db.users.update({'_id': self._id}, self.to_db_dict)

    @needs_db
    def save_or_create(self):
        """
        This saves the current user to the database.
        If the user doesn't already exist in the db it should create it.
        """
        User.db.users.update({'_id': self._id}, self.to_db_dict, True)

    @needs_db
    def set_online(self, time = datetime.now()):
        self.connection_status = User.ONLINE
        self.save

    @needs_db
    def set_offline(self, time = datetime.now()):
        self.connection_status = User.OFFLINE
        self.save

    @needs_db
    def set_connected(self, time = datetime.now()):
        self.connection_status = User.ONLINE
        self.connected_time = time
        self.save

    @needs_db
    def set_disconnected(self, time = datetime.now()):
        self.connection_status = User.OFFLINE
        self.disconnected_time = time
        self.save

    @needs_db
    def said(self, message, time=datetime.now()):
        self.last_spoke = time
        self.last_utterance = message
        self.save

    @needs_db
    def set_nick(self, newnick):
        self.nick = newnick
        self.save

    def to_db_dict(self):
        return __dict__

    @staticmethod
    @needs_db
    def find_user_by_nick(nick):
        """
        This finds a user in the database with the given nick.
        """
        if is_full_username(nick):
            nick, _, _ = split_username(nick)
        db_user = User.db.users.find({'nick': nick})
        if db_user:
            return from_database(db_user)
        else:
            raise NotFound("Sorry, {} could not be found in the database".format(nick))

    @staticmethod
    @needs_db
    def online_users():
        """
        This returns a list of all the users currently known to be online.
        """
        return [User.from_database(usr) for usr in User.db.users.find({'connection_state': User.ONLINE})]

    @staticmethod
    @needs_db
    def offline_users():
        """
        This returns a list of all the users currently known to be offfline.

        This only returns users who HAVE been in the channel. Reporting all users ever
        would be silly
        """
        return [User.from_database(usr) for usr in User.db.users.find({'connection_state': User.OFFLINE})]

    @staticmethod
    @needs_db
    def all_users():
        """
        This returns a list of all the users currently in the database.
        """
        users = [User.from_database(usr) for usr in User.db.users.find()]
        print "Users in all_users: {}".format(users)
        return users

    @staticmethod
    def from_database(db_user):
        #user = User(db_user['nick'], db_user['user'], db_user['host'])
        user = User(None, None, None)
        # FIXME: check I'm still sane
        # set all the things on the user
        # not sure if checking each thing isn't nick, user or host is more efficient
        # than just resetting them to the same thing. Could probably get away with
        # not looking them up in the first place actually... bad idea anyone?
        for k, v in db_user.iteritems():
            setattr(user, k, v)
        return user

    @needs_db
    def load_from_database(self):
        db_user = User.db.users.find({'nick': nick})
        if db_user:
            for k, v in db_user.iteritems():
                setattr(user, k, v)
        else:
            raise NotFound("Sorry, {} could not be found in the database".format(self.nick))

    @classmethod
    def set_database(cls, db):
        """
        This sets a reference to the DB which is necessary to store users in the db.
        """
        setattr(cls, 'db', db)

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
        host, user = None
        if username_has_host(username):
            username, host = username.split("@")
        if username_has_user(username):
            username, user = username.split("!")
        return (username, user, host)


class InformationMissing(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


class DatabaseNotSet(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


class NotFound(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)

