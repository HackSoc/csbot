from datetime import datetime
from collections import deque

from csbot.util import parse_arguments


class ImmediateEventRunner(object):
    """A very simple blocking event runner for immediate chains of events.

    This class is only responsible for making sure chains of events get
    handled before the next root event happens.  The *handle_event* method
    should be a callable that expects a single argument - it will receive
    whatever is passed to :meth:`post_event`.

    The context manager technique is used to ensure the event runner is left in
    a usable state if an exception propagates out of it in response to running
    an event.
    """
    def __init__(self, handle_event):
        self.events = deque()
        self.running = False
        self.handle_event = handle_event

    def __enter__(self):
        """On entering the context, mark the event queue as running."""
        self.running = True

    def __exit__(self, exc_type, exc_value, traceback):
        """On exiting the context, reset to an empty non-running queue.

        When exiting normally this should have no additional effect.  If
        exiting abnormally, the rest of the event queue will be purged so that
        the next root event can be handled normally.
        """
        self.running = False
        self.events.clear()

    def post_event(self, event):
        """Post *event* to be handled soon.

        If this is a root event, i.e. this method hasn't been called while
        handling another event, then the event queue will run immediately and
        block until the event and all child events have been handled.

        If this is a child event, i.e. this method has been called from another
        event handler, then it will be added to the queue and will be processed
        before the :meth:`post_event` for the root event exits.

        If a chain of events forms a tree, the handling order is equivalent to
        a breadth-first traversal of the event tree.
        """
        self.events.append(event)
        if not self.running:
            with self:
                while len(self.events) > 0:
                    e = self.events.popleft()
                    self.handle_event(e)


class Event(dict):
    """IRC event information.

    Events are dicts of event information, plus some attributes which are
    applicable for all events.
    """
    #: The :class:`.BotProtocol` which triggered the event.
    protocol = None
    #: The name of the event.
    event_type = None
    #: The value of :meth:`datetime.datetime.now()` when the event was
    #: triggered.
    datetime = None

    def __init__(self, protocol, event_type, data=None):
        dict.__init__(self, data if data is not None else {})

        self.protocol = protocol
        self.event_type = event_type
        self.datetime = datetime.now()

    @classmethod
    def extend(cls, event, event_type=None, data=None):
        """Create a new event by extending an existing event.

        The main purpose of this classmethod is to duplicate an event as a new
        event type, preserving existing information.  For example:
        """
        # Duplicate event information
        e = cls(event.protocol,
                event.event_type,
                event)
        e.datetime = event.datetime

        # Apply optional updates
        if event_type is not None:
            e.event_type = event_type
        if data is not None:
            e.update(data)

        return e

    @property
    def bot(self):
        """Shortcut to ``self.protocol.bot``."""
        return self.protocol.bot


class CommandEvent(Event):
    @classmethod
    def parse_command(cls, event, prefix):
        """Attempt to create a :class:`CommandEvent` from a
        ``core.message.privmsg`` event.

        A command is signified by *event["message"]* starting with the command
        prefix string followed by one or more non-space characters.

        Returns None if *event['message']* wasn't recognised as being a
        command.
        """
        # Split on the first space to find the "command" part
        parts = event['message'].split(None, 1)
        if len(parts) == 0:
            # Called with an empty message, nothing to do
            return None
        elif len(parts) == 1:
            command, data = parts[0], ''
        else:
            command, data = parts

        # See if the command part is really a command
        if len(command) <= len(prefix) or not command.startswith(prefix):
            # Nothing to do if this doesn't fit the command pattern
            return None
        else:
            # Trim the command prefix from the command name
            command = command[len(prefix):]

        return cls.extend(event, 'core.command',
                          {'command': command, 'data': data.strip()})

    def reply(self, message):
        self.protocol.msg(e['reply_to'], message)

    def arguments(self):
        """Parse *self["data"]* into a list of arguments using
        :func:`~csbot.util.parse_arguments`.  This might raise a
        :exc:`~exceptions.ValueError` if the string cannot be parsed, e.g. if
        there are unmatched quotes.
        """
        return parse_arguments(self['data'])
