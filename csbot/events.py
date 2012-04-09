from datetime import datetime
import shlex

from csbot.util import nick, is_channel


def proxy(event_type, attributes):
    """Proxy :class:`csbot.core.BotProtocol` events to the
    :class:`csbot.core.Bot`.

    Wraps the bot, protocol and arguments into an :class:`Event`.  The
    *attributes* list defines the attribute names on the :class:`Event` that
    will be used for each of the positional arguments to the decorated method.

    First the :class:`Bot`'s method with the same name as *event_type* will be
    called (if one exists), then :meth:`Bot.fire_hook` will be called with
    *event_type* and the newly generated event.
    """
    def newf(self, *args):
        event = Event(self.bot, self, event_type, dict(zip(attributes, args)))
        method = getattr(self.bot, event_type, None)
        if method is not None:
            method(event)
        self.bot.fire_hook(event_type, event)
    newf.__doc__ = """Proxy method for ``t.w.p.i.IRCClient.{}``.

Attributes set: {}.
""".format(event_type, ', '.join(attributes))
    return newf


class Event(object):
    #: The :class:`~csbot.core.Bot` for which the message was received.
    bot = None
    #: The :class:`~csbot.core.BotProtocol` which received the message - this
    #: subclasses :class:`twisted.words.protocols.irc.IRCClient` and so exposes
    #: all of the same methods.
    protocol = None
    #: The name of the event type - this will usually correspond to an event
    #: method in :class:`twisted.words.protocols.irc.IRCClient`.
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
    #: The command invoked (minus any trigger characters)
    command = None
    #: User string for the source of the command
    user = None
    #: Channel that the command was received on
    channel = None
    #: False if the command was triggered by the command prefix, True otherwise
    direct = False
    #: The rest of the line after the command name
    raw_data = None
    #: Cached argument list, see :attr:`data`
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
        """Command data as an argument list.

        On first access, the argument list is processed from :attr:`raw_data`
        using :py:mod:`shlex`.  The lexer is customised to only use `"` for
        argument quoting, allowing `'` to be used naturally within arguments.

        If the lexer fails to process the argument list, :meth:`error` is
        called and :py:exc:`~exceptions.ValueError` is raised.
        """
        if self.data_ is None:
            try:
                # Create a shlex instance just like shlex.split does
                lex = shlex.shlex(self.raw_data, posix=True)
                lex.whitespace_split = True
                # Don't treat ' as a quote character, so it can be used
                # naturally in words
                lex.quotes = '"'
                self.data_ = list(lex)
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
            self.protocol.msg(self.channel, msg)

    def error(self, err):
        """Send an error message."""
        self.reply('Error: ' + err, is_verbose=True)
