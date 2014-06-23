from csbot.plugin import Plugin
from csbot.events import Event
import asyncio
from datetime import datetime, timedelta
import pymongo


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
            cron = Plugin.use('cron')

            def setup(self):
                ...
                self.cron.after(
                    "hello world",
                    datetime.timedelta(days=1),
                    "callback")

            def callback(self, when):
                self.log.info(u'I got called at {}'.format(when))

            @Plugin.hook('cron.hourly')
            def hourlyevent(self, e):
                self.log.info(u'An hour has passed')
    """
    tasks = Plugin.use('mongodb', collection='tasks')

    def setup(self):
        super(Cron, self).setup()

        # Schedule own events with the same API other plugins will use
        self.cron = self.provide(self.plugin_name())

        # An asyncio.Handle for the event runner delayed call
        self.scheduler = None
        # The datetime of the next task, which self.scheduler was created for
        self.scheduler_next = None

        # Now we need to remove the hourly, daily, and weekly events
        # (if there are any), because the scheduler just runs things
        # when their time has passed, but for these we want to run
        # them as close to the correct time as possible, so running a
        # past event is useless for our purposes.
        #
        # Sadly this can't happen in the teardown, as we want to do
        # this even if the bot crashes unexpectedly.
        self.cron.unschedule_all()

        # Add regular cron.hourly/daily/weekly events which plugins
        # can listen to.
        now = datetime.now()
        when = -timedelta(minutes=now.minute,
                          seconds=now.second,
                          microseconds=now.microsecond)

        self.cron.schedule(name='hourly',
                           when=now + when + timedelta(hours=1),
                           interval=timedelta(hours=1),
                           callback='fire_event',
                           args=['cron.hourly'])

        when -= timedelta(hours=now.hour)
        self.cron.schedule(name='daily',
                           when=now + when + timedelta(days=1),
                           interval=timedelta(days=1),
                           callback='fire_event',
                           args=['cron.daily'])

        when -= timedelta(days=now.weekday())
        self.cron.schedule(name='weekly',
                           when=now + when + timedelta(weeks=1),
                           interval=timedelta(weeks=1),
                           callback='fire_event',
                           args=['cron.weekly'])

    def teardown(self):
        super().teardown()
        if self.scheduler is not None:
            self.scheduler.cancel()

    def fire_event(self, now, name):
        """Fire off a regular event.

        This gets called by the scheduler at the appropriate time.
        """
        self.bot.post_event(Event(None, name))

    def provide(self, plugin_name):
        """Return the crond for the given plugin."""
        return PluginCron(self, plugin_name)

    def match_task(self, owner, name=None, args=None, kwargs=None):
        """Create a MongoDB search for a task definition."""
        matcher = {'owner': owner}
        if name is not None:
            matcher['name'] = name
        if args is not None:
            matcher['args'] = args
        if kwargs is not None:
            matcher['kwargs'] = kwargs
        return matcher

    def schedule(self, owner, name, when,
                 interval=None, callback=None,
                 args=None, kwargs=None):
        """Schedule a new task.

        :param owner:    The plugin which created the task
        :param name:     The name of the task
        :param when:     The datetime to trigger the task at
        :param interval: Optionally, reschedule at when + interval
                         when triggered. Gives rise to repeating
                         tasks.
        :param callback: Call owner.callback when triggered; if None,
                         call owner.name.
        :param args:     Callback positional arguments.
        :param kwargs:   Callback keyword arguments.

        The signature of a task is ``(owner, name, args, kwargs)``, and trying
        to create a task with the same signature as an existing task will raise
        :exc:`DuplicateTaskError`.  Any subset of the signature can be used to
        :meth:`unschedule` all matching tasks (``owner`` is mandatory).
        """
        # Create the new task
        secs = interval.total_seconds() if interval is not None else None
        task = {'owner': owner,
                'name': name,
                'when': when,
                'interval': secs,
                'callback': callback or name,
                'args': args or [],
                'kwargs': kwargs or {}}

        # See if this task duplicates another
        match = self.match_task(task['owner'], task['name'],
                                task['args'], task['kwargs'])
        if self.tasks.find_one(match):
            raise DuplicateTaskError('Identical task already scheduled', match)

        # If we made it this far, save the task
        self.tasks.insert(task)

        # Reschedule the event runner in case it now needs to happen earlier
        self.schedule_event_runner()

    def unschedule(self, owner, name=None, args=None, kwargs=None):
        """Unschedule a task.

        Removes all existing tasks that match based on the criteria passed as
        arguments (see :meth:`match_task`).

        This could result in the scheduler having nothing to do in its next
        call, but this isn't a problem as it's not a very intensive function,
        so there's no point in rescheduling it here.
        """
        self.tasks.remove(self.match_task(owner, name, args, kwargs))

    def schedule_event_runner(self):
        """Schedule the event runner.

        Set up a delayed call for :meth:`event_runner` to happen no sooner than
        is required by the next scheduled task.  If a different call already
        exists it is replaced.
        """
        now = datetime.now()
        # There will always be at least one event remaining because we
        # have three repeating ones, so this is safe.
        remaining_tasks = self.tasks.find().sort('when', pymongo.ASCENDING)
        next_run = remaining_tasks[0]['when']

        if self.scheduler_next is None or next_run != self.scheduler_next:
            if self.scheduler is not None:
                self.scheduler.cancel()
            delay = (next_run - now).total_seconds()
            self.log.debug('calling event runner in %s seconds', delay)
            # TODO: need a better API for using the bot's event loop
            self.scheduler = asyncio.get_event_loop().call_later(delay, self.event_runner)
            self.scheduler_next = next_run
        else:
            self.log.debug('already scheduled for %s', self.scheduler_next)

    def event_runner(self):
        """Run pending tasks.

        Run all tasks which have a trigger time in the past, and then
        reschedule self to run in time for the next task.
        """
        now = datetime.now()
        self.log.debug('running event runner at %s', now)

        # Find and run every task from before now
        for taskdef in self.tasks.find({'when': {'$lt': now}}):
            # Going to be using this a lot
            task_name = u'{}/{}'.format(
                taskdef['owner'],
                taskdef['name'])

            self.log.info(u'Running task ' + task_name)

            # Now that we have the task, we need to remove it from the
            # database (or reschedule it for the future) straight
            # away, as if it schedules things itself, the scheduler
            # will be called again, but the task will still be there
            # (and so be run again), resulting in an error when it
            # tries to schedule the second time.
            if taskdef['interval'] is not None:
                taskdef['when'] += timedelta(seconds=taskdef['interval'])
                self.tasks.save(taskdef)
            else:
                self.unschedule(taskdef['owner'], taskdef['name'])

            # There are two things that could go wrong in running a
            # task. The method might not exist, this can arise in two
            # ways: a plugin scheduled it in a prior incarnation of
            # the bot, and then didn't register start up on this run,
            # resulting in there being no entry in self.bot.plugins,
            # or it could have just provided a bad method name.
            #
            # There is clearly no way to recover from this with any
            # degree of certainty, so we just drop it from the
            # database to prevent an error cropping up every time it
            # gets run.
            try:
                func = getattr(self.bot.plugins[taskdef['owner']],
                               taskdef['callback'])
            except AttributeError:
                self.log.error(
                    u'Couldn\'t find method {}.{} for task {}'.format(
                        taskdef['owner'],
                        taskdef['callback'],
                        task_name))
                self.unschedule(taskdef['owner'], taskdef['name'])
                continue

            # The second way is if the method does exist, but raises
            # an exception during its execution. There are two ways to
            # handle this. We could let the exception propagate
            # upwards and outwards, killing the bot, or we could log
            # it as an error and carry on. I went for the latter here,
            # on the assumption that, whilst exceptions are bad and
            # shouldn't get this far anyway, killing the bot is worse.
            try:
                func(taskdef['when'], *taskdef['args'], **taskdef['kwargs'])
            except Exception as e:
                # Don't really want exceptions to kill cron, so let's just log
                # them as an error.

                self.log.error(
                    u'Exception raised when running task {}: {} {}'.format(
                        task_name,
                        type(e), e.args))

        # Schedule the event runner for the next task
        self.schedule_event_runner()


class DuplicateTaskError(Exception):
    """Task with a given signature already exists.

    This can be raised by :meth:`Cron.schedule` if a plugin tries to register
    two events with the same name.
    """
    pass


class PluginCron(object):
    """Interface to the cron methods restricted to *plugin* as the task owner..

    How scheduling works
    --------------------

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
        self.plugin = plugin

    def schedule(self, name, when, interval=None, callback=None, args=None, kwargs=None):
        """Pass through to :meth:`Cron.schedule`, adding *owner* argument."""
        self.cron.schedule(self.plugin, name, when, interval, callback, args, kwargs)

    def after(self, _delay, _name, _method_name, *args, **kwargs):
        """Schedule an event to occur after the timedelta delay has passed."""
        self.schedule(_name,
                      datetime.now() + _delay,
                      callback=_method_name,
                      args=args,
                      kwargs=kwargs)

    def at(self, _when, _name, _method_name, *args, **kwargs):
        """Schedule an event to occur at a given time."""
        self.schedule(_name,
                      _when,
                      callback=_method_name,
                      args=args,
                      kwargs=kwargs)

    def every(self, _freq, _name, _method_name, *args, **kwargs):
        """Schedule an event to occur every time the delay passes."""
        self.schedule(_name,
                      datetime.now() + _freq,
                      interval=_freq,
                      callback=_method_name,
                      args=args,
                      kwargs=kwargs)

    def unschedule(self, name, args=None, kwargs=None):
        """Pass through to :meth:`Cron.unschedule`, adding *owner* argument."""
        self.cron.unschedule(self.plugin, name, args, kwargs)

    def unschedule_all(self):
        """Unschedule all tasks for this plugin.

        This could be supported by :meth:`unschedule`, but it's nice to
        prevent code accidentally wiping all of a plugin's tasks.
        """
        self.cron.unschedule(self.plugin)
