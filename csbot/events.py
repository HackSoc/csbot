from datetime import datetime
from collections import deque
import re
import asyncio
import logging

from csbot.util import parse_arguments


LOG = logging.getLogger('csbot.events')
LOG.setLevel(logging.INFO)


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


class AsyncEventRunner(object):
    """
    An asynchronous event runner.

    Runs on *loop*, and events are passed to *handle_event* which should return
    an iterable of awaitables (coroutine objects, tasks, etc.).

    :param handle_event: Function to turn an event into awaitables
    :param loop: asyncio event loop to use (default: None, use current loop)
    """
    def __init__(self, handle_event, loop=None):
        self.handle_event = handle_event
        self.loop = loop

        self.pending = set()
        self.pending_event = asyncio.Event(loop=self.loop)
        self.pending_event.clear()
        self.future = None

    def __enter__(self):
        LOG.debug('Entering async event runner')

    def __exit__(self, exc_type, exc_value, traceback):
        LOG.debug('Exiting async event runner')
        self.future = None

    def post_event(self, event):
        """Post *event* to be handled soon.

        All tasks resulting from calling :meth:`handle_event` on *event* are
        created and a future that completes only when those tasks are complete
        is returned.

        The returned future may depend on more than just the tasks resulting
        from *event*, because new tasks are aggregated into an existing future
        if there are still outstanding tasks.
        """
        self._add_pending(event)
        LOG.debug('Added event {}, pending={}'.format(event, len(self.pending)))
        if not self.future:
            self.future = self.loop.create_task(self._run())
        return self.future

    def _add_pending(self, event):
        self.pending.update(self.handle_event(event))
        self.pending_event.set()

    def _get_pending(self):
        pending = self.pending
        self.pending = set()
        self.pending_event.clear()
        return pending

    @asyncio.coroutine
    def _run(self):
        # Use self as context manager so an escaping exception doesn't break
        # the event runner instance permanently (i.e. we clean up the future)
        with self:
            not_done = self._get_pending()
            # Use pending_event to wait for new tasks, so we can schedule them
            # even if we were already in asyncio.wait()
            new_pending = self.loop.create_task(self.pending_event.wait())
            not_done.add(new_pending)
            while not_done:
                # If we're only waiting on new tasks, time to exit
                if not_done == {new_pending}:
                    LOG.debug('Only pending_event.wait() remains')
                    new_pending.cancel()
                    break
                # Run until 1 or more tasks complete (or more tasks are added)
                done, not_done = yield from asyncio.wait(not_done,
                                                         loop=self.loop,
                                                         return_when=asyncio.FIRST_COMPLETED)
                # Handle exceptions raised by tasks
                for f in done:
                    e = f.exception()
                    if e is not None:
                        self.loop.call_exception_handler({
                            'message': 'Unhandled exception in event task',
                            'exception': e,
                            'future': f,
                        })
                LOG.debug('Event runner ran: done={}, not_done={}'.format(
                    len(done), len(not_done),
                ))
                # Grab new tasks?
                if new_pending.done():
                    pending = self._get_pending()
                    LOG.debug('Events were added: pending={}'.format(len(pending)))
                    not_done |= pending
                    # New pending_event.wait(), because the old one was used up.
                    new_pending = self.loop.create_task(self.pending_event.wait())
                    not_done.add(new_pending)


class Event(dict):
    """IRC event information.

    Events are dicts of event information, plus some attributes which are
    applicable for all events.
    """
    #: The :class:`.Bot` which triggered the event.
    bot = None
    #: The name of the event.
    event_type = None
    #: The value of :meth:`datetime.datetime.now()` when the event was
    #: triggered.
    datetime = None

    def __init__(self, bot, event_type, data=None):
        dict.__init__(self, data if data is not None else {})

        self.bot = bot
        self.event_type = event_type
        self.datetime = datetime.now()

    @classmethod
    def extend(cls, event, event_type=None, data=None):
        """Create a new event by extending an existing event.

        The main purpose of this classmethod is to duplicate an event as a new
        event type, preserving existing information.  For example:
        """
        # Duplicate event information
        e = cls(event.bot,
                event.event_type,
                event)
        e.datetime = event.datetime

        # Apply optional updates
        if event_type is not None:
            e.event_type = event_type
        if data is not None:
            e.update(data)

        return e

    def reply(self, message):
        """Send a reply.

        For messages that have a ``reply_to`` key, instruct the :attr:`bot`
        to send a reply.
        """
        self.bot.reply(self['reply_to'], message)


class CommandEvent(Event):
    @classmethod
    def parse_command(cls, event, prefix, nick):
        """Attempt to create a :class:`CommandEvent` from a
        ``core.message.privmsg`` event.

        A command is signified by *event["message"]* starting with the command
        prefix string followed by one or more non-space characters.

        Returns None if *event['message']* wasn't recognised as being a
        command.
        """
        pattern = r'({prefix}|{nick}[,:]\s*)(?P<command>[^\s]+)(\s+(?P<data>.+))?'.format(
            prefix=re.escape(prefix),
            nick=re.escape(nick),
        )
        match = re.fullmatch(pattern, event['message'].strip())

        if match is None:
            return None
        else:
            return cls.extend(event, 'core.command',
                              {'command': match.group('command'),
                               'data': match.group('data') or ''})

    def arguments(self):
        """Parse *self["data"]* into a list of arguments using
        :func:`~csbot.util.parse_arguments`.  This might raise a
        :exc:`~exceptions.ValueError` if the string cannot be parsed, e.g. if
        there are unmatched quotes.
        """
        return parse_arguments(self['data'])
