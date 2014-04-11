from csbot.plugin import Plugin
import threading
from twisted.internet import reactor
from datetime import datetime


class Cron(Plugin):
    """
    Time, that most mysterious of things. What is it? Is it discrete or
    continuous? What was before time? Does that even make sense to ask? This
    plugin will attempt to address some, perhaps all, of these questions.

    More seriously, this plugin allows the scheduling of events with a
    resolution of one second. Due to computers being the constructs of
    fallible humans, it's not guaranteed that a callback will be run
    precisely when you want it to be.

    Example of usage:

        class MyPlugin(Plugin):
            PLUGIN_DEPENDS = ['cron']

            @Plugin.integrate_with('cron')
            def _get_cron(self, cron):
                self.cron = cron

            def setup(self):
                ...
                self.cron.schedule(
                    self.plugin_name(),
                    datetime.timedelta(days=1),
                    lambda date: self._callback(date),
                    "hello world")
    """

    def setup(self):
        super(Cron, self).setup()

        # Tasks is a map plugin -> name -> (date, callback)
        self.tasks = {}

        # Because we keep a dict of all tasks (to allow easy cancellation), we
        # need to be able to ensure atomic access to the tasks dict.
        self.tasklock = threading.RLock()

    def schedule(self, plugin, when, callback, name=None):
        """
        Schedule a new callback, the "when" is a timedelta.

        The name, if given, can be used to remove a callback. Names must be
        unique.

        True is returned if the event was scheduled, False otherwise.
        """

        with self.tasklock:
            # Create the empty plugin schedule if it doesn't exist
            if plugin not in self.tasks:
                self.tasks[plugin] = {}

            if name is not None and name in self.tasks[plugin]:
                return False

            task_id = reactor.callLater(when.total_seconds(),
                                        self._runcb(plugin, name, callback))

            if name is not None:
                self.tasks[plugin][name] = task_id

            return True

    def scheduleAt(self, plugin, when, callback, name=None):
        """
        Exactly the same as schedule(...), except the when is a datetime.
        """

        self.schedule(plugin, when - datetime.now(), callback, name)

    def unschedule(self, plugin, name):
        """
        Unschedule a named callback.
        """

        with self.tasklock:
            if plugin in self.tasks and name in self.tasks[plugin]:
                self.tasks[plugin][name].cancel()
                del self.tasks[plugin][name]

    def _runcb(self, plugin, name, cb):
        """
        Run a callback, and remove it from the tasks dict.
        """

        def run():
            self.log.info(u'Running callback {}.{} {}'.format(
                plugin, name, cb))

            try:
                cb()
            except:
                pass

            if name is not None:
                with self.tasklock:
                    del self.tasks[plugin][name]

        return run
