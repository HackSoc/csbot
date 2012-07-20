.. highlight:: python

How to write plugins
====================

This document is a quick guide to writing plugins for the bot.  To get started, you need to create a
module under :mod:`csbot.plugins`.  Any classes found in this hierarchy which subclass
:class:`~csbot.core.Plugin` will be treated as available plugins.

Interaction with the outside world is by registering hooks and commands, using the
:class:`~csbot.core.PluginFeatures` class.


Events
------

All hooks and commands received a single argument, an 
:class:`~csbot.events.Event` instance.  Events are generated in response to some 
external stimulus, or during the handling of another event.  See :doc:`events` 
for further information and the available event types.


Hooks
-----

Registering hooks allows you to receive basic IRC events.

::

    class HookExample(Plugin):
        features = PluginFeatures()

        @features.hook('core.message.privmsg')
        def handle_privmsg(self, event):
            print event.user, 'says', event.message


Commands
--------

Registering commands lets users interact with your plugin in a direct way, either using the command
prefix, addressing the bot directly in a channel or addressing the bot in a private chat.  The
command mechanism removes the need for the plugin to concern itself with recognising commands.  When
a defined command is invoked, its handler is called with a :class:`~csbot.events.CommandEvent`
instance.  See its documentation for the features available to you.

::

    class CommandExample(Plugin):
        features = PluginFeatures()

        @features.command('foo')
        def handle_foo(self, event):
            event.reply('You said ' + event.raw_data)

.. autoattribute:: csbot.events.CommandEvent.direct
    :noindex:

.. _twisted.words.protocols.irc.IRCClient: http://twistedmatrix.com/documents/current/api/twisted.words.protocols.irc.IRCClient.html
