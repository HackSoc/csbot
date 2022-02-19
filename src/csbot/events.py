from datetime import datetime
from collections import deque
import re
import asyncio
import logging

from csbot.util import parse_arguments, maybe_future


LOG = logging.getLogger('csbot.events')


class HybridEventRunner:
    """
    A hybrid synchronous/asynchronous event runner.

    *get_handlers* is called for each event passed to :meth:`post_event`, and
    should return an iterable of callables to handle that event, each of which
    will be called with the event object.

    Events are processed in the order they are received, with all handlers for
    an event being called before the handlers for the next event. If a handler
    returns an awaitable, it is added to a set of asynchronous tasks to wait on.

    The future returned by :meth:`post_event` completes only when all events
    have been processed and all asynchronous tasks have completed.

    :param get_handlers: Get functions to call for an event
    :param loop: asyncio event loop to use (default: use current loop)
    """
    def __init__(self, get_handlers, loop=None):
        self.get_handlers = get_handlers
        self.loop = loop

        self.events = deque()
        self.new_events = asyncio.Event()
        self.futures = set()
        self.future = None

    def __enter__(self):
        LOG.debug('entering event runner')

    def __exit__(self, exc_type, exc_value, traceback):
        LOG.debug('exiting event runner')
        self.future = None

    def post_event(self, event):
        """Post *event* to be handled soon.

        *event* is added to the queue of events.

        Returns a future which resolves when the handlers of *event* (and all
        events generated during those handlers) have completed.
        """
        self.events.append(event)
        LOG.debug('added event %s, pending=%s', event, len(self.events))
        self.new_events.set()
        if not self.future:
            self.future = self.loop.create_task(self._run())
        return self.future

    def _run_events(self):
        """Run event handlers, accumulating awaitables as futures.
        """
        new_futures = set()
        while len(self.events) > 0:
            LOG.debug('processing events (%s remaining)', len(self.events))
            # Get next event
            event = self.events.popleft()
            LOG.debug('processing event: %s', event)
            # Handle the event
            for handler in self.get_handlers(event):
                # Attempt to run the handler, but don't break everything if the handler fails
                LOG.debug('running handler: %r', handler)
                future = self._run_handler(handler, event)
                if future:
                    new_futures.add(future)
        self.new_events.clear()
        if len(new_futures) > 0:
            LOG.debug('got %s new futures', len(new_futures))
        return new_futures

    def _run_handler(self, handler, event):
        """Call *handler* with *event* and log any exception.

        If *handler* returns an awaitable, then it is wrapped in a coroutine that will log any
        exception from awaiting it.
        """
        result = None
        try:
            result = handler(event)
        except Exception as e:
            self._handle_exception(exception=e, csbot_event=event)
        future = maybe_future(result, log=LOG)
        if future:
            future = asyncio.ensure_future(self._finish_async_handler(future, event), loop=self.loop)
        return future

    async def _finish_async_handler(self, future, event):
        """Await *future* and log any exception.
        """
        try:
            await future
        except Exception:
            self._handle_exception(future=future, csbot_event=event)

    async def _run(self):
        """Run the event runner loop.

        Process events and await futures until all events and handlers have been
        processed.
        """
        # Use self as context manager so an escaping exception doesn't break
        # the event runner instance permanently (i.e. we clean up the future)
        with self:
            # Run until no more events or lingering futures
            while len(self.events) + len(self.futures) > 0:
                # Synchronously run event handler and collect new futures
                new_futures = self._run_events()
                self.futures |= new_futures
                # Don't bother waiting if no futures to wait on
                if len(self.futures) == 0:
                    continue

                # Run until one or more futures complete (or new events are added)
                new_events = self.loop.create_task(self.new_events.wait())
                LOG.debug('waiting on %s futures', len(self.futures))
                done, pending = await asyncio.wait(self.futures | {new_events}, return_when=asyncio.FIRST_COMPLETED)
                # Remove done futures from the set of futures being waited on
                done_futures = done - {new_events}
                LOG.debug('%s of %s futures done', len(done_futures), len(self.futures))
                self.futures -= done_futures
                if new_events.done():
                    LOG.debug('new events to process')
                else:
                    # If no new events, cancel the waiter, because we'll create a new one next iteration
                    new_events.cancel()

    def _handle_exception(self, *, message='Unhandled exception in event handler',
                          exception=None,
                          future=None,
                          csbot_event=None):
        if exception is None and future is not None:
            exception = future.exception()
        self.loop.call_exception_handler({
            'message': message,
            'exception': exception,
            'future': future,
            'csbot_event': csbot_event,
        })


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

    def __str__(self):
        return f'<Event {self.event_type!r} {self!r}>'

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
