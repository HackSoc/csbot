.. highlight:: python

How to write plugins
====================

Anatomy of a plugin
-------------------

Plugins are automatically discovered if they match the right pattern.  They must

* subclass :class:`csbot.plugin.Plugin`, and
* live under the package specified by :attr:`csbot.core.Bot.PLUGIN_PACKAGE` (``csbot.plugins`` by 
  default).

For example, a minimal plugin that does nothing might live in ``csbot/plugins/nothing.py`` and look 
like::

    from csbot.plugin import Plugin

    class Nothing(Plugin):
        pass

A plugin's name is its class name in lowercase [#plugin_name]_ and must be unique, so plugin classes 
should be named meaningfully.  Changing a plugin name will cause it to lose access to its associated 
configuration and database, so try not to do that unless you're prepared to migrate these things.

The vast majority of interaction with the outside world is through subscribing to events and 
registering commands.


Events
------

Root events are generated when the bot receives data from the IRC server, and further events may be 
generated while handling an event.

All events are represented by the :class:`~.Event` class, which is a dictionary of event-related 
information with some additional helpful attributes.  See :doc:`events` for further information on 
the :class:`~csbot.events.Event` class and available events.

Events are hooked with the :meth:`.Plugin.hook` decorator.  The decorated method will be called for 
every event that matches the specified :attr:`~.Event.event_type`, with the event object as the only 
argument.  For example, a basic logging plugin that prints sent and received data::

    class Logger(Plugin):
        @Plugin.hook('core.raw.sent')
        def sent(self, e):
            print('<-- ' + e['message'])

        @Plugin.hook('core.raw.received')
        def received(self, e):
            print('--> ' + e['message'])

A single handler can hook more than one event::

    class MessagePrinter(Plugin):
        @Plugin.hook('core.message.privmsg')
        @Plugin.hook('core.message.notice')
        def got_message(self, e):
            """Print out all messages, ignoring if they were PRIVMSG or NOTICE."""
            print(e['message'])


Commands
--------

Registering commands provides a more structured way for users to interact with a plugin.  A command 
can be any unique, non-empty sequence of non-whitespace characters, and are invoked when prefixed 
with the bot's configured command prefix.  Command events use the :class:`.CommandEvent` class, 
extending a ``core.message.privmsg`` :class:`.Event` and adding the :meth:`~.CommandEvent.arguments` 
method and the ``command`` and ``data`` items.

::

    class CommandTest(Plugin):
        @Plugin.command('test')
        def hello(self, e):
            print(e['command'] + ' invoked with arguments ' + repr(e.arguments()))

A single handler can be registered for more than one command, e.g. to give aliases, and commands and 
hooks can be freely mixed.

::

    class Friendly(Plugin):
        @Plugin.hook('core.channel.joined')
        @Plugin.command('hello')
        @Plugin.command('hi')
        def hello(self, e):
            e.protocol.msg(e['channel'], 'Hello, ' + nick(e['user']))


Responding: the :class:`.BotProtocol` object
--------------------------------------------

In the above example the :attr:`.Event.protocol` attribute was used to respond back to the IRC 
server.  This attribute is an instance of :class:`.BotProtocol`, which subclasses 
twisted.words.protocols.irc.IRCClient_ for IRC protocol support.  The documentation for IRCClient is 
the best place to find out what methods are supported when responding to an event or command.


Configuration
-------------

Basic string key/value configuration can be stored in an INI-style file.  A plugin's 
:attr:`~.Plugin.config` attribute is a shortcut to a configuration section with the same name as the 
plugin.  The Python 3 :mod:`configparser` is used instead of the Python 2
:mod:`python:ConfigParser` because it supports the mapping access protocol, i.e. it acts like a 
dictionary in addition to supporting its own API.

An example of using plugin configuration::

    class Say(Plugin):
        @Plugin.command('say')
        def say(self, e):
            if self.config.getboolean('shout', False):
                e.protocol.msg(e['reply_to'], e['data'].upper() + '!')
            else:
                e.protocol.msg(e['reply_to'], e['data'])

For even more convenience, automatic fallback values are supported through the 
:attr:`~.Plugin.CONFIG_DEFAULTS` attribute when using the :meth:`~.Plugin.config_get` or 
:meth:`~.Plugin.config_getboolean` methods instead of the corresponding methods on 
:attr:`~.Plugin.config`.  This is encouraged, since it makes it clear what configuration the plugin 
supports and what the default values are by looking at just one part of the plugin source code.  The 
above example would look like this::

    class Say(Plugin):
        CONFIG_DEFAULTS = {
            'shout': False,
        }

        @Plugin.command('say')
        def say(self, e):
            if self.config_getboolean('shout'):
                e.protocol.msg(e['reply_to'], e['data'].upper() + '!')
            else:
                e.protocol.msg(e['reply_to'], e['data'])

Configuration can be changed at runtime, but won't be saved.  This allows for temporary state 
changes, whilst ensuring the startup state of the bot reflects the configuration file.  For example, 
the above plugin could be modified with a toggle for the "shout" mode::

    class Say(Plugin):
        # ...
        @Plugin.command('toggle')
        def toggle(self, e):
            self.config['shout'] = not self.config_get('shout')

Database
--------

The bot supports easy access to MongoDB through PyMongo_.  Plugins have a :attr:`~.Plugin.db` 
attribute which is a :class:`pymongo.database.Database`, unique to the plugin and created as needed.  
Refer to the PyMongo_ documentation for further guidance on using the API.


.. [#plugin_name] This can be changed by overriding the :meth:`~.PluginBase.plugin_name`
    class method if absolutely necessary.

.. _twisted.words.protocols.irc.IRCClient: http://twistedmatrix.com/documents/current/api/twisted.words.protocols.irc.IRCClient.html
.. _PyMongo: http://api.mongodb.org/python/current/
