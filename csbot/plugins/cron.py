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
                self.cron.after(
                    "hello world",
                    datetime.timedelta(days=1),
                    lambda when: print "I was called at " + repr(when))

            @Plugin.hook('cron.hourly')
            def hourlyevent(self, e):
                self.log.info(u'An hour has passed')
    """

    def setup(self):
        super(Cron, self).setup()

        # self.asks is a map name -> callback
        self.tasks = {}

        # self.repeating is used to get the call time for a repeating event
        self.repeating = {}

        # Add regular cron.hourly/daily/weekly events which
        # plugins can listen to. Unfortunately LoopingCall can't
        # handle things like "run this every hour, starting in x
        # seconds", which is what we need, so I handle this by having
        # a seperate set-up method for the recurring events which
        # isn't called until the first time they should run.
        now = datetime.now()
        when = -timedelta(minutes=now.minute,
                          seconds=now.second,
                          microseconds=now.microsecond)

        self.schedule('cron.hourly-init',
                      when + timedelta(hours=1),
                      lambda t: self.setup_regular('cron.hourly',
                                                   timedelta(hours=1)))

        when -= timedelta(hours=when.hour)
        self.schedule('cron.daily-init',
                      when + timedelta(days=1),
                      lambda t: self.setup_regular('cron.daily',
                                                   timedelta(days=1)))

        when -= timedelta(days=when.weekday())
        self.schedule('cron.weekly-init',
                      when + timedelta(weeks=1),
                      lambda t: self.setup_regular('cron.weekly',
                                                   timedelta(weeks=1)))

    def setup_regular(self, name, tdelta):
        """
        Set up a recurring event: hourly, daily, weekly, etc. This should be
        called at the first time such an event should be sent.
        """

        self.log.info(u'Registering repeating event {}'.format(name))

        func = lambda t: self.bot.post_event(Event(None, name))

        # Schedule the recurring event
        self.schedule(name, tdelta, func, repeat=True)

        # Call it now
        self.log.info(u'Running initial repeating event {}.'.format(name))
        func(datetime.now())

    def get_cron(self, plugin):
        """
        Return the crond for the given plugin
        """

        return PluginCron(self, plugin)

    def schedule(self, name, delay, callback, repeat=False):
        """
        Schedule a new callback, the "delay" is a timedelta.

        The name can be used to remove a callback. Names must be unique,
        otherwise a DuplicateNameException will be raised.
        """

        if name in self.tasks:
            raise DuplicateNameException(name)

        seconds = delay.total_seconds()
        callback = self._runcb(name, callback, datetime.now() + delay, repeat)

        if repeat:
            task_id = task.LoopingCall(callback)
            task_id.start(seconds)
            self.repeating[name] = {'last': datetime.now(),
                                    'delay': delay}
        else:
            task_id = reactor.callLater(seconds, callback)

        self.tasks[name] = task_id

    def unschedule(self, name):
        """
        Unschedule a named callback.
        """

        if name in self.tasks:
            self.tasks[name].cancel()
            del self.tasks[name]

        if name in self.repeating:
            del self.repeating[name]

    def _runcb(self, name, cb, now, repeating=False):
        """
        Return a function to run a callback, and remove it from the tasks dict.
        """

        def run():
            self.log.info(u'Running callback {} {}'.format(name, cb))

            if repeating:
                self.repeating[name]['last'] += self.repeating[name]['delay']
                now = self.repeating[name]

            try:
                cb(now)
            except:
                exctype, value = sys.exc_info()[:2]
                self.log.error(
                    u'Exception raised when running callback {} {}: {} {}'.format(
                        name, cb,
                        exctype, value))
            finally:
                if not repeating:
                    del self.tasks[name]

        return run


class DuplicateNameException(Exception):
    """
    This can be raised by Cron::schedule if a plugin tries to register two
    events with the same name.
    """

    pass


class PluginCron(object):
    """
    An iterface to the cron methods restricted to the view of one named plugin.

    All of the scheduling functions have a signature of the form
    (time, callback, name). The time is either a delay (as a timedelta) or an
    absolute time (as a datetime), the callback is the function to call then,
    and the name is an optional name which can be used to remove a callback
    before it is fired.

    These functions will raise a DuplicateNameException if you try to schedule
    two events with the same name.
    """

    def __init__(self, cron, plugin):
        self.cron = cron
        self.plugin = plugin.plugin_name()

    def after(self, name, delay, callback):
        """
        Schedule an event to occur after the timedelta delay has passed.
        """

        name = '{}.{}'.format(self.plugin, name)

        self.cron.schedule(name, delay, callback)

    def at(self, name, when, callback):
        """
        Schedule an event to occur at a given time.
        """

        name = '{}.{}'.format(self.plugin, name)
        delay = when - datetime.now()

        self.cron.schedule(name, delay, callback)

    def every(self, name, freq, callback):
        """
        Schedule an event to occur every time the delay passes, starting
        immediately.
        """

        name = '{}.{}'.format(self.plugin, name)

        self.cron.schedule(name, freq, callback, repeat=True)

    def unschedule(self, name):
        """
        Unschedule a named event which hasn't yet happened.
        If the name doesn't exist, nothing happens.
        """

        self.cron.unschedule('{}.{}'.format(self.plugin, name))
