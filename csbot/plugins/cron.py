from csbot.plugin import Plugin
from csbot.events import Event
from twisted.internet import task
from datetime import datetime, timedelta
from collections import namedtuple
import sys

# A Task is the data structure used to represent a scheduled event. These can
# be nicely serialised and stored in the database, so all is good.
# - time: when the task is to be run
# - delay: the delay before running it again (if repeating)
# - plugin_name: the name of the plugin that registered it
# - method_name: the name of the method on the plugin it should call
# - args, kwargs: arguments to pass the callback method
# - repeating: whether it is repeating or not
Task = namedtuple('Task', ['time', 'delay',
                           'plugin_name', 'method_name',
                           'args', 'kwargs',
                           'repeating'])


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

    @Plugin.integrate_with('mongodb')
    def _get_db(self, mongodb):
        self.db = mongodb.get_db(self.plugin_name())

    def setup(self):
        super(Cron, self).setup()

        # self.tasks is a map name -> Task
        # If there are tasks in the database, pull them out. Otherwise insert
        # the empty tasks dict so we get an ID to use for future writes.
        if self.db.tasks.find_one():
            tasks = self.db.tasks.find_one()
            self.tasks = tasks[u'tasks']
            self.tasks_id = tasks[u'_id']
        else:
            self.tasks = {}
            self.tasks_id = self.db.tasks.insert({u'tasks': self.tasks})

        # self.plugins is a map plugin name -> plugin instance
        self.plugins = {'cron': self}

        # self.scheduler is a handle to the scheduler repeating task, and
        # self.scheduler_freq is how frequently it gets called. These need to
        # be set before anything is scheduled (like the repeated events).
        self.scheduler = None
        self.scheduler_freq = -1

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
                      'cron', 'setup_regular',
                      args=['cron.hourly', timedelta(hours=1)])

        when -= timedelta(hours=now.hour)
        self.schedule('cron.daily-init',
                      when + timedelta(days=1),
                      'cron', 'setup_regular',
                      args=['cron.daily', timedelta(days=1)])

        when -= timedelta(days=now.weekday())
        self.schedule('cron.weekly-init',
                      when + timedelta(weeks=1),
                      'cron', 'setup_regular',
                      args=['cron.weekly', timedelta(weeks=1)])

    def teardown(self):
        """
        Save all the tasks (other than hourly/daily/weekly as there is no
        point) which haven't yet run to the database.

        If there were tasks in the database before, overwrite them.
        """

        tasks = {name: taskdef
                 for name, taskdef in self.tasks.items()
                 if name not in ['cron.hourly', 'cron.daily', 'cron.weekly']}

        self.db.tasks.save({u'_id':   self.tasks_id,
                            u'tasks': tasks})

    def setup_regular(self, now, name, tdelta):
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
        Return the crond for the given plugin, and save a reference to the
        plugin so it can be used by scheduled tasks,
        """

        self.plugins[plugin.plugin_name()] = plugin
        return PluginCron(self, plugin)

    def schedule(self, name, delay, plugin_name, method_name,
                 args=[], kwargs={},
                 repeating=False):
        """
        Schedule a new callback, the "delay" is a timedelta.

        The name can be used to remove a callback. Names must be unique,
        otherwise a DuplicateNameException will be raised.
        """

        if name in self.tasks:
            raise DuplicateNameException(name)

        # Create the new task
        self.tasks[name] = Task(time=datetime.now() + delay,
                                delay=delay,
                                plugin_name=plugin_name,
                                method_name=method_name,
                                args=args,
                                kwargs=kwargs,
                                repeating=repeating)

        # Call the scheduler immediately, as it may now need to be called
        # sooner than it had planned.
        self.event_runner()

    def unschedule(self, name):
        """
        Unschedule a named callback.

        This could result in the scheduler having nothing to do in its next
        call, but this isn't a problem as it's not a very intensive function
        (unless there is a *lot* scheduled), so there's no point in
        rescheduling it here.
        """

        if name in self.tasks:
            self.tasks[name].cancel()
            del self.tasks[name]

        if name in self.repeating:
            del self.repeating[name]

    def event_runner(self):
        """
        Run all tasks which have a trigger time in the past, and then
        reschedule self to run in time for the next task.
        """

        now = datetime.now()

        # Firstly find the tasks which happen <= now
        to_run = {}

        for name, taskdef in self.tasks.items():
            if taskdef.time <= now:
                to_run[name] = taskdef

        # Then run each task
        for taskdef in to_run:
            self.log.info(u'Running callback {}'.format(taskdef.name))

            run_time = taskdef.time

            try:
                func = getattr(
                    self.plugins[taskdef.plugin_name],
                    taskdef.method_name)
            except:
                self.log.error(
                    u'Couldn\'t find method {}.{} for callback {}'.format(
                        taskdef.plugin_name, taskdef.method_name,
                        taskdef.name))
                del self.tasks[taskdef.name]
                continue

            try:
                func(run_time, *taskdef.args, **taskdef.kwargs)
            except:
                # Don't really want exceptions to kill cron, so let's just log
                # them as an error.
                exctype, value = sys.exc_info()[:2]
                self.log.error(
                    u'Exception raised when running callback {}: {} {}'.format(
                        taskdef.name, exctype, value))
            finally:
                # If the task is repeating we update its call time, otherwise
                # we drop it from the scheduler.
                if taskdef.repeating:
                    taskdef.time += taskdef.delay
                else:
                    del self.tasks[taskdef.name]

        # Schedule the event runner to happen no sooner than is required by the
        # next scheduled task.
        next_run = now + timedelta(days=100)

        for taskdef in self.tasks.values():
            if taskdef.time < next_run:
                next_run = taskdef.time

        freq = (next_run - now).total_seconds()

        if freq < self.scheduler_freq or self.scheduler is None:
            if self.scheduler is not None:
                self.scheduler.stop()

            self.scheduler = task.LoopingCall(self.event_runner)
            self.scheduler.start(freq, now=False)
            self.scheduler_freq = freq


class DuplicateNameException(Exception):
    """
    This can be raised by Cron::schedule if a plugin tries to register two
    events with the same name.
    """

    pass


class PluginCron(object):
    """
    An iterface to the cron methods restricted to the view of one named plugin.

    How scheduling works:

        All of the scheduling functions have a signature of the form
        (name, time, method_name, *args, **kwargs).

        This means that at the appropriate time, the method plugin.method_name
        will be called with the arguments (time, *args, **kwargs), where the
        time argument is the time it was supposed to be run by the scheduler
        (which may not be identical to teh actual time it is run).

        These functions will raise a DuplicateNameException if you try to
        schedule two events with the same name.
    """

    def __init__(self, cron, plugin):
        self.cron = cron
        self.plugin = plugin.plugin_name()

    def after(self, name, delay, method_name, *args, **kwargs):
        """
        Schedule an event to occur after the timedelta delay has passed.
        """

        name = '{}.{}'.format(self.plugin, name)

        self.cron.schedule(name, delay,
                           self.plugin, method_name,
                           args, kwargs)

    def at(self, name, when, method_name, *args, **kwargs):
        """
        Schedule an event to occur at a given time.
        """

        name = '{}.{}'.format(self.plugin, name)
        delay = when - datetime.now()

        self.cron.schedule(name, delay,
                           self.plugin, method_name,
                           args, kwargs)

    def every(self, name, freq, method_name, *args, **kwargs):
        """
        Schedule an event to occur every time the delay passes, starting
        immediately.
        """

        name = '{}.{}'.format(self.plugin, name)

        self.cron.schedule(name, freq,
                           self.plugin, method_name,
                           args, kwargs,
                           repeating=True)

    def unschedule(self, name):
        """
        Unschedule a named event which hasn't yet happened.
        If the name doesn't exist, nothing happens.
        """

        self.cron.unschedule('{}.{}'.format(self.plugin, name))
