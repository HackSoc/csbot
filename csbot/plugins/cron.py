from csbot.plugin import Plugin
from csbot.events import Event
from twisted.internet import reactor, task
from datetime import datetime, timedelta
import sys


class Cron(Plugin):
    """
    Time, that most mysterious of things. What is it? Is it discrete or
    continuous? What was before time? Does that even make sense to ask? This
    plugin will attempt to address some, perhaps all, of these questions.

    More seriously, this plugin allows the scheduling of events. Due to
    computers being the constructs of fallible humans, it's not guaranteed
    that a callback will be run precisely when you want it to be. Furthermore,
    if you schedule multiple events at the same time, don't make any
    assumptions about the order in which they'll be called.

    Example of usage:

        class MyPlugin(Plugin):
            PLUGIN_DEPENDS = ['cron']

            @Plugin.integrate_with('cron')
            def _get_cron(self, cron):
                self.cron = cron.get_cron(self)

            def setup(self):
                ...
                self.cron.schedule(
                    self.plugin_name(),
                    datetime.timedelta(days=1),
                    lambda: self._callback(),
                    "hello world")

            @Plugin.hook('cron.hourly')
            def hourlyevent(self, e):
                self.log.info(u'An hour has passed')
    """

    def setup(self):
        super(Cron, self).setup()

        # Tasks is a map plugin -> name -> (date, callback)
        self.tasks = {}

        # Add regular cron.hourly/daily/weekly events which
        # plugins can listen to. Unfortunately LoopingCall can't
        # handle things like "run this every hour, starting in x
        # seconds", which is what we need, so I handle this by having
        # a seperate set-up method for the recurring events which
        # isn't called until the first time they should run.
        when = datetime.now()
        when -= timedelta(minutes=when.minute,
                          seconds=when.second,
                          microseconds=when.microsecond)

        self.scheduleAt(self.plugin_name(),
                        when + timedelta(hours=1),
                        lambda: self.setup_regular('hourly',
                                                   timedelta(hours=1)),
                        "hourly set-up")

        when -= timedelta(hours=when.hour)
        self.scheduleAt(self.plugin_name(),
                        when + timedelta(days=1),
                        lambda: self.setup_regular('daily',
                                                   timedelta(days=1)),
                        "daily set-up")

        when -= timedelta(days=when.weekday())
        self.scheduleAt(self.plugin_name(),
                        when + timedelta(weeks=1),
                        lambda: self.setup_regular('weekly',
                                                   timedelta(weeks=1)),
                        "weekly set-up")

    def setup_regular(self, name, tdelta):
        """
        Set up a recurring event: hourly, daily, weekly, etc. This should be
        called at the first time such an event should be sent.
        """

        self.log.info(u'Registering regular event cron.{}'.format(name))

        func = lambda: self.bot.post_event(
            Event(None, 'cron.{}'.format(name)))

        # Schedule the recurring event
        self.schedule(self.plugin_name(),
                      tdelta, func,
                      name=name, repeat=True)

        # Call it now
        self.log.info(u'Running initial repeating event {}.{}.'.format(
            self.plugin_name(), name))
        func()

    def get_cron(self, plugin):
        """
        Return the crond for the given plugin
        """

        return PluginCron(self, plugin)

    def schedule(self, plugin, delay, callback, name=None, repeat=False):
        """
        Schedule a new callback, the "delay" is a timedelta.

        The name, if given, can be used to remove a callback. Names must be
        unique.

        True is returned if the event was scheduled, False otherwise.
        """

        # Create the empty plugin schedule if it doesn't exist
        if plugin not in self.tasks:
            self.tasks[plugin] = {}

        if name is not None and name in self.tasks[plugin]:
            return False

        seconds = delay.total_seconds()
        callback = self._runcb(plugin, name, callback, unschedule=not repeat)

        if repeat:
            task_id = task.LoopingCall(callback)
            task_id.start(seconds)
        else:
            task_id = reactor.callLater(seconds, callback)

        if name is not None:
            self.tasks[plugin][name] = task_id

        return True

    def unschedule(self, plugin, name):
        """
        Unschedule a named callback.
        """

        if plugin in self.tasks and name in self.tasks[plugin]:
            self.tasks[plugin][name].cancel()
            del self.tasks[plugin][name]

    def _runcb(self, plugin, name, cb, unschedule=True):
        """
        Return a function to run a callback, and remove it from the tasks dict.
        """

        def run():
            self.log.info(u'Running callback {}.{} {}'.format(
                plugin, name, cb))

            try:
                cb()
            except:
                exctype, value = sys.exc_info()[:2]
                self.log.error(
                    u'Exception raised when running callback {}.{} {}: {} {}'.format(
                        plugin, name, cb,
                        exctype, value))
            finally:
                if unschedule and name is not None:
                    del self.tasks[plugin][name]

        return run


class PluginCron(object):
    """
    An iterface to the cron methods restricted to the view of one named plugin.

    All of the scheduling functions have a signature of the form
    (time, callback, name). The time is either a delay (as a timedelta) or an
    absolute time (as a datetime), the callback is the function to call then,
    and the name is an optional name which can be used to remove a callback
    before it is fired.
    """

    def __init__(self, cron, plugin):
        self.cron = cron
        self.plugin = plugin.plugin_name()

    def schedule(self, delay, callback, name=None):
        """
        Schedule an event to occur after the timedelta delay has passed.
        """

        self.cron.schedule(self.plugin, delay, callback, name=name)

    def at(self, when, callback, name=None):
        """
        Schedule an event to occur at a given time.
        """

        delay = when - datetime.now()
        self.cron.schedule(self.plugin, delay, callback, name=name)

    def every(self, freq, callback, name=None):
        """
        Schedule an event to occur every time the delay passes, starting
        immediately.
        """

        self.cron.schedule(self.plugin, freq, callback, name=name, repeat=True)

    def unschedule(self, name):
        """
        Unschedule a named event which hasn't yet happened.
        """

        self.cron.unschedule(self.plugin, name)
