Events
======

All events are represented by :class:`~csbot.events.Event` instances.  Every 
event has the following attributes:

.. autoattribute:: csbot.events.Event.protocol
    :noindex:
.. autoattribute:: csbot.events.Event.bot
    :noindex:
.. autoattribute:: csbot.events.Event.event_type
    :noindex:
.. autoattribute:: csbot.events.Event.datetime
    :noindex:

Event instances are also dictionaries, and the keys present depend on the
particular event type.  The following sections describe each event, specified
as ``event_type(keys)``.


Raw events
----------

These events are very low-level and most plugins shouldn't need them.

.. describe:: core.raw.connected

    Client established connection.

.. describe:: core.raw.disconnected

    Client lost connection.

.. describe:: core.raw.sent(message)

    Client sent *message* to the server.

.. describe:: core.raw.received(message)

    Client received *message* from the server.


Bot events
----------

These events represent changes in the bot's state.

.. describe:: core.self.connected

    IRC connection successfully established.

.. describe:: core.self.joined(channel)

    Client joined *channel*.

.. describe:: core.self.left(channel)

    Client left *channel*.


Message events
--------------

These events occur when messages are received by the bot.

.. describe:: core.message.privmsg(channel, user, message, is_private, reply_to)

    Received *message* from *user* which was sent to *channel*.  If the message
    was sent directly to the client, i.e. *channel* is the client's nick and
    not a channel name, then *is_private* will be True and any response should
    be to *user*, not *channel*.  *reply_to* is the channel/user any response
    should be sent to.

.. describe:: core.message.notice(channel, user, message, is_private, reply_to)

    As ``core.message.privmsg``, but representing a NOTICE rather than a
    PRIVMSG.  Bear in mind that according to `RFC 1459`_ "automatic replies must
    never be sent in response to a NOTICE message" - this definitely applies to
    bot functionality!

    .. _RFC 1459: http://www.irchelp.org/irchelp/rfc/chapter4.html#c4_4_2

.. describe:: core.message.action(channel, user, message, is_private, reply_to)

    Received a ``CTCP ACTION`` of *message* from *user* sent to *channel*.  Other arguments are as 
    for ``core.message.privmsg``.


Channel events
--------------

These events occur when something about the channel changes, e.g. people
joining or leaving, the topic changing, etc.

.. describe:: core.channel.joined(channel, user)

    *user* joined *channel*.

.. describe:: core.channel.left(channel, user)

    *user* left *channel*.

.. describe:: core.channel.names(channel, names, raw_names)

    Received the list of users currently in the channel, in response to a 
    ``NAMES`` command.

.. describe:: cores.channel.topic(channel, author, topic)

    Fired whenever the channel topic is changed, and also immediately after joining a channel.  The 
    *author* field will usually be the server name when joining a channel (on Freenode, at least), 
    and the nick of the user setting the topic when the topic has been changed.


User events
-----------

These events occur when a user changes state in some way, i.e. actions that
aren't limited to a single channel.

.. describe:: core.user.quit(user, message)

.. describe:: core.user.renamed(oldnick, newnick)
