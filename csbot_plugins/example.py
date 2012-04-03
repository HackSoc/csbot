from csbot import Plugin


class Example(Plugin):

    NAME = 'example'

    def privmsg(self, user, channel, msg):
        print ">>>", msg

    def action(self, user, channel, action):
        print "*", action
