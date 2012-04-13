from datetime import datetime
import shlex
import inspect
from functools import wraps

from twisted.words.protocols import irc

from csbot.util import nick, is_channel, parse_arguments


PROXY_DOC = """

Fires ``{event}`` :class:`.Event` with attributes ``({attrs})``."""
PROXY_TWISTED_DOC = """

Implements Twisted `IRCClient.{event}`_ callback.

.. _`IRCClient.{event}`: http://twistedmatrix.com/documents/current/api/
                         twisted.words.protocols.irc.IRCClient.html#{event}"""


def proxy(*args, **kwargs):
    """Here be dragons (and magic).

    This is a decorator for creating methods on :class:`.BotProtocol` that
    result in events that can be hooked by the bot and plugins.

    When the new method is called, the decorated method is called first, as
    normal.  Afterwards an :class:`Event` is created and the arguments are
    stored in it as attributes.  The :attr:`~Event.event_type` is the name of
    the method being decorated.  This event is passed to the :class:`.Bot`'s
    method of the same name and then the hook of the same name.

    If the decorator is used without arguments, the attribute names are defined
    by the parameter names of the decorated method::

        class BotProtocol(IRCClient):
            # Creates events with 'user', 'channel' and 'message' attributes
            @events.proxy
            def privmsg(self, user, channel, message):
                pass

    If the decorator has arguments, then these define the attribute names
    instead::

        class BotProtocol(IRCClient):
            # Creates events with 'u', 'c' and 'msg' attributes
            @events.proxy('u', 'c', 'msg')
            def privmsg(self, user, channel, message):
                pass

    If the decorator has the *name* keyword argument it's used instead of the
    method to define :attr:`~Event.event_type`::

        class BotProtocol(IRCClient):
            # Fires the 'messageReceived' event instead of 'privmsg'
            @events.proxy(name='messageReceived')
            def privmsg(self, user, channel, message):
                pass

    Usually the decorated methods won't return anything, and the original
    arguments are re-used for the :class:`Event`.  If the method *does* return
    something, it will be treated as a tuple of arguments that should be used
    instead of the original arguments::

        class BotProtocol(IRCClient):
            # Pretend we can't hear Alan
            @events.proxy
            def privmsg(self, user, channel, message):
                if nick(user) == 'Alan':
                    return (user, channel, '')

            # Make an event with a completely different signature
            @events.proxy('users')
            def userJoined(self, user, channel):
                self.users[channel].add(user)
                return (self.users[channel],)

    Docstrings on each decorated method are automatically augmented with
    information about the events generated, and a link to the Twisted
    documentation if the method implements part of the Twisted
    :class:`IRCClient` interface.
    """
    def decorate(f, attrs=args, name=kwargs.get('name', None)):
        # The event type is the name of the method being decorated
        event_type = name or f.__name__
        # The attribute mapping can either be specified by the decorator
        # or use the parameter names of the wrapped method.  The "no arguments"
        # version of the decorator uses the latter approach by setting
        # attrs=None
        if attrs is None:
            attrs = inspect.getargspec(f).args[1:]

        # Create new function, copying info from f
        @wraps(f)
        def newf(self, *args):
            # Fire the decorated function
            result = f(self, *args)
            # Allow the decorated function to return new arguments, but if it
            # doesn't return anything keep the same arguments
            args = result or args
            # Create an Event
            event = Event(self.bot, self, event_type, dict(zip(attrs, args)))
            # Fire the Bot's method of the same name
            method = getattr(self.bot, event_type, None)
            if method is not None:
                method(event)
            # Fire the hook of the same name
            self.bot.fire_hook(event_type, event)

        # Augment documentation with a note about the event firing
        newf.__doc__ = newf.__doc__ or ''
        newf.__doc__ += PROXY_DOC.format(event=event_type,
                                          attrs=', '.join(attrs))
        # If this is a Twisted IRCClient callback, link to the relevant docs
        if getattr(irc.IRCClient, event_type, None) is not None:
            newf.__doc__ += PROXY_TWISTED_DOC.format(event=event_type)
        newf.__doc__ = newf.__doc__.lstrip('\n')

        return newf

    # If decorating without arguments, the first argument to proxy will end up
    # being the method to decorate.
    if len(args) == 1 and callable(args[0]):
        return decorate(args[0], attrs=None, name=None)
    else:
        return decorate


class Event(object):
    #: The :class:`.Bot` for which the message was received.
    bot = None
    #: The :class:`.BotProtocol` which received the message.  This subclasses
    #: Twisted :class:`IRCClient` and so exposes all of the same methods.
    protocol = None
    #: The name of the event.  This will usually correspond to a method in
    #: :class:`.BotProtocol` marked by the :func:`proxy` decorator.
    event_type = None
    #: The value of :meth:`datetime.datetime.now()` when the message was
    #: first received.
    datetime = None

    def __init__(self, bot, protocol, event_type, attributes):
        # Set datetime before attributes so it can be forced
        self.datetime = datetime.now()
        # Set attributes from dictionary
        for attr, value in attributes.iteritems():
            setattr(self, attr, value)
        # Set attributes from arguments
        self.bot = bot
        self.protocol = protocol
        self.event_type = event_type


class CommandEvent(Event):
    #: The command invoked (minus any trigger characters).
    command = None
    #: User string for the source of the command.
    user = None
    #: Channel that the command was received on.
    channel = None
    #: Was the bot addressed directly, either by nick or in private chat?
    #: This will be False if the command was triggered by just the command
    #: prefix in a public channel.
    direct = False
    #: The rest of the line after the command name.
    raw_data = None
    #: Cached argument list, see :attr:`data`.
    data_ = None

    @staticmethod
    def create(event):
        """Attempt to create a :class:`CommandEvent` from an :class:`Event`.

        Returns None if *event* does not contain a command, otherwise returns a
        :class:`CommandEvent`.
        """
        command_prefix = event.bot.config.get('DEFAULT', 'command_prefix')
        own_nick = event.protocol.nickname
        msg = event.message
        channel = event.channel

        command = None
        direct = False

        if is_channel(channel):
            # In channel, must be triggered explicitly
            if msg.startswith(command_prefix):
                # Triggered by command prefix: "<prefix><cmd> <args>"
                command = msg[len(command_prefix):]
            elif msg.startswith(own_nick):
                # Addressing the bot by name: "<nick>, <cmd> <args>"
                msg = msg[len(own_nick):].lstrip()
                # Check that the bot was specifically addressed, rather than
                # a similar nick or just talking about the bot
                if len(msg) > 0 and msg[0] in ',:;.':
                    command = msg.lstrip(',:;.')
                    direct = True
        else:
            command = msg
            direct = True

        if command is None or command.strip() == '':
            return None

        command = command.split(None, 1)
        cmd = command[0]
        data = command[1] if len(command) == 2 else ''
        return CommandEvent(event.bot, event.protocol, command, {
            'datetime': event.datetime,
            'user': event.user,
            'channel': event.channel,
            'command': cmd,
            'direct': direct,
            'raw_data': data,
        })

    @property
    def data(self):
        """Command data as an argument list, using
        :func:`.util.parse_arguments`.

        The parsed argument list is cached on first use so repeatedly accessing
        elements of this attribute is cheap.  If :attr:`raw_data` couldn't be
        parsed then accessing this attribute might raise a
        :exc:`~exceptions.ValueError`.
        """
        if self.data_ is None:
            try:
                self.data_ = parse_arguments(self.raw_data)
            except ValueError as e:
                self.error('Unmatched quotation marks')
                raise e
        return self.data_

    def reply(self, msg, is_verbose=False):
        """Send a reply message.

        All plugin responses should be via this method.  The :attr:`user` is
        addressed by name if the response is in a channel rather than a private
        chat.  If *is_verbose* is True, the reply is suppressed unless the bot
        was addressed directly, i.e. in private chat or by name in a channel.
        """
        if self.channel == self.protocol.nickname:
            self.protocol.msg(nick(self.user), msg)
        elif self.direct or not is_verbose:
            self.protocol.msg(self.channel,
                              nick(self.user) + ': ' + msg)

    def error(self, err):
        """Send an error message."""
        self.reply('Error: ' + err, is_verbose=True)
