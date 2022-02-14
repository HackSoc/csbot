import unittest.mock as mock
import asyncio
import inspect
import logging

import pytest

from csbot.core import Bot
from csbot.plugin import Plugin, PluginDependencyUnmet, PluginFeatureError


class TestDependency:
    class MockPlugin1(Plugin):
        PLUGIN_DEPENDS = ["mockplugin2", "mockplugin3"]

    class MockPlugin2(Plugin):
        PLUGIN_DEPENDS = ["mockplugin3"]

    class MockPlugin3(Plugin):
        pass

    class MockPlugin4(Plugin):
        PLUGIN_DEPENDS = ["mockplugin5"]

    class MockPlugin5(Plugin):
        PLUGIN_DEPENDS = ["mockplugin4"]

    def test_single_dependency_not_met(self, event_loop, config_example_mode):
        """Check that an exception happens if a plugin's dependencies are not met."""
        with pytest.raises(PluginDependencyUnmet):
            Bot(plugins=[self.MockPlugin2, self.MockPlugin3],
                config={"@bot": {"plugins": ["mockplugin2"]}})

    def test_single_dependency_met(self, event_loop, config_example_mode):
        """Check that plugin loads correctly if dependencies are met."""
        bot = Bot(plugins=[self.MockPlugin2, self.MockPlugin3],
                  config={"@bot": {"plugins": ["mockplugin3", "mockplugin2"]}})
        assert isinstance(bot.plugins["mockplugin2"], self.MockPlugin2)

    def test_multiple_dependency_partially_met(self, event_loop, config_example_mode):
        """Check that plugin fails to load if only *some* dependencies are met."""
        with pytest.raises(PluginDependencyUnmet):
            Bot(plugins=[self.MockPlugin1, self.MockPlugin2, self.MockPlugin3],
                config={"@bot": {"plugins": ["mockplugin2", "mockplugin1"]}})

    def test_multiple_dependency_met(self, event_loop, config_example_mode):
        """Check that plugin loads correctly if *all* dependencies are met."""
        bot = Bot(plugins=[self.MockPlugin1, self.MockPlugin2, self.MockPlugin3],
                  config={"@bot": {"plugins": ["mockplugin3", "mockplugin2", "mockplugin1"]}})
        assert isinstance(bot.plugins["mockplugin1"], self.MockPlugin1)

    def test_dependency_order(self, event_loop, config_example_mode):
        """Check that plugin dependencies can be satisfied regardless of order in config."""
        bot = Bot(plugins=[self.MockPlugin2, self.MockPlugin3],
                  config={"@bot": {"plugins": ["mockplugin2", "mockplugin3"]}})
        assert isinstance(bot.plugins["mockplugin2"], self.MockPlugin2)

    def test_dependency_cycle(self, event_loop, config_example_mode):
        """Check that plugin dependency cycles are handled."""
        with pytest.raises(ValueError):
            Bot(plugins=[self.MockPlugin4, self.MockPlugin5],
                config={"@bot": {"plugins": ["mockplugin4", "mockplugin5"]}})


class TestHook:
    class MockPlugin(Plugin):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.handler_mock = mock.Mock(spec=callable)

        @Plugin.hook('test.event1')
        def test1a(self, event):
            self.handler_mock('test1a', event)

        @Plugin.hook('test.event1')
        def test1b(self, event):
            self.handler_mock('test1b', event)

        @Plugin.hook('test.event2a')
        @Plugin.hook('test.event2b')
        def test2(self, event):
            self.handler_mock('test2', event)

        @Plugin.hook('test.event3')
        @Plugin.hook('test.event3')
        def test3(self, event):
            self.handler_mock('test3', event)

        @Plugin.hook('core.message.privmsg')
        async def privmsg(self, event):
            await asyncio.sleep(0.5)
            self.handler_mock('privmsg', event['message'])

        @Plugin.hook('core.user.quit')
        def quit(self, event):
            self.handler_mock('quit', event['user'])

    CONFIG = {
        "@bot": {
            "plugins": ["mockplugin"],
        },
    }

    pytestmark = pytest.mark.bot(plugins=[MockPlugin], config=CONFIG)

    async def test_hooks(self, bot_helper):
        """Check that hooks fire in the expected way."""
        bot = bot_helper.bot
        plugin = bot_helper['mockplugin']

        # Test that all hooks for an event are fired (in definition order within a plugin)
        plugin.handler_mock.reset_mock()
        await bot.emit_new('test.event1', {})
        assert plugin.handler_mock.mock_calls == [
            mock.call('test1a', {}),
            mock.call('test1b', {}),
        ]

        # Test that a method can be registered for multiple events
        plugin.handler_mock.reset_mock()
        await bot.emit_new('test.event2a', {})
        assert plugin.handler_mock.mock_calls == [
            mock.call('test2', {}),
        ]
        await bot.emit_new('test.event2b', {})
        assert plugin.handler_mock.mock_calls == [
            mock.call('test2', {}),
            mock.call('test2', {}),
        ]

        # Test that a method is only called once, even if registered for an event multiple times
        plugin.handler_mock.reset_mock()
        await bot.emit_new('test.event3', {})
        assert plugin.handler_mock.mock_calls == [
            mock.call('test3', {}),
        ]

    @pytest.mark.parametrize('n', list(range(1, 10)))
    async def test_burst_in_order(self, bot_helper, n):
        """Check that a plugin always gets messages in receive order."""
        plugin = bot_helper['mockplugin']
        users = [f':nick{i}!user{i}@host{i}' for i in range(n)]
        messages = [f':{user} QUIT :*.net *.split' for user in users]
        await asyncio.wait(bot_helper.receive(messages))
        assert plugin.handler_mock.mock_calls == [mock.call('quit', user) for user in users]

    async def test_non_blocking(self, bot_helper):
        """Check that long-running hooks don't block other events from being processed."""
        plugin = bot_helper['mockplugin']
        messages = [
            ':nick0!user@host QUIT :bye',
            ':nick1!user@host QUIT :bye',
            ':foo!user@host PRIVMSG #channel :hello',
            ':nick2!user@host QUIT :bye',
            ':nick3!user@host QUIT :bye',
            ':nick4!user@host QUIT :bye',
        ]
        await asyncio.wait(bot_helper.receive(messages))
        assert plugin.handler_mock.mock_calls == [
            mock.call('quit', 'nick0!user@host'),
            mock.call('quit', 'nick1!user@host'),
            mock.call('quit', 'nick2!user@host'),
            mock.call('quit', 'nick3!user@host'),
            mock.call('quit', 'nick4!user@host'),
            mock.call('privmsg', 'hello'),
        ]


class TestCommand:
    class MockPlugin1(Plugin):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.handler_mock = mock.Mock(spec=callable)

        @Plugin.command('a')
        def command_a(self, *args, **kwargs):
            self.handler_mock(inspect.currentframe().f_code.co_name)

        @Plugin.command('b', help='This command has help')
        def command_b(self, *args, **kwargs):
            self.handler_mock(inspect.currentframe().f_code.co_name)

        @Plugin.command('c')
        @Plugin.command('d')
        def command_cd(self, *args, **kwargs):
            self.handler_mock(inspect.currentframe().f_code.co_name)

    CONFIG_A = """\
    ["@bot"]
    command_prefix = "&"
    plugins = ["mockplugin1"]
    """

    @pytest.mark.bot(plugins=[MockPlugin1], config=CONFIG_A)
    async def test_command_help(self, bot_helper):
        """Check that commands fire in the expected way."""
        await asyncio.wait(bot_helper.receive([':nick!user@host PRIVMSG #channel :&plugins']))
        bot_helper.assert_sent('NOTICE #channel :loaded plugins: @bot, mockplugin1')

        await asyncio.wait(bot_helper.receive([':nick!user@host PRIVMSG #channel :&help']))
        bot_helper.assert_sent('NOTICE #channel :a, b, c, d, help, plugins')

        await asyncio.wait(bot_helper.receive([':nick!user@host PRIVMSG #channel :&help x']))
        bot_helper.assert_sent('NOTICE #channel :x: no such command')

        await asyncio.wait(bot_helper.receive([':nick!user@host PRIVMSG #channel :&help a']))
        bot_helper.assert_sent('NOTICE #channel :a: no help string')

        await asyncio.wait(bot_helper.receive([':nick!user@host PRIVMSG #channel :&help b']))
        bot_helper.assert_sent('NOTICE #channel :This command has help')

    @pytest.mark.bot(plugins=[MockPlugin1], config=CONFIG_A)
    async def test_command_fired(self, bot_helper):
        """Check that commands fire in the expected way."""
        plugin = bot_helper['mockplugin1']

        # Test that a command method is called
        plugin.handler_mock.reset_mock()
        await asyncio.wait(bot_helper.receive([':nick!user@host PRIVMSG #channel :&a']))
        assert plugin.handler_mock.mock_calls == [
            mock.call('command_a'),
        ]

        # Test that a method can be registered for multiple commands
        plugin.handler_mock.reset_mock()
        await asyncio.wait(bot_helper.receive([':nick!user@host PRIVMSG #channel :&c']))
        assert plugin.handler_mock.mock_calls == [
            mock.call('command_cd'),
        ]
        await asyncio.wait(bot_helper.receive([':nick!user@host PRIVMSG #channel :&d']))
        assert plugin.handler_mock.mock_calls == [
            mock.call('command_cd'),
            mock.call('command_cd'),
        ]

    # TODO: test "one handler per command" - xfail?
    class MockPlugin2(Plugin):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.handler_mock = mock.Mock(spec=callable)

        @Plugin.command('a')
        def command_a(self, *args, **kwargs):
            self.handler_mock(inspect.currentframe().f_code.co_name)

    CONFIG_B = """\
    ["@bot"]
    command_prefix = "&"
    plugins = ["mockplugin1", "mockplugin2"]
    """

    @pytest.mark.bot(plugins=[MockPlugin1, MockPlugin2], config=CONFIG_B)
    async def test_command_single_handler(self, caplog, bot_helper):
        count = 0
        for r in caplog.get_records("setup"):
            if (r.levelno == logging.WARNING and
                    r.name == "csbot.core" and
                    r.message == "tried to overwrite command: a"):
                count += 1
        assert count == 1


class TestIntegrateWith:
    class MockPlugin1(Plugin):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.handler_mock = mock.Mock(spec=callable)

        @Plugin.integrate_with('mockplugin0')
        def integrate_a(self, p0):
            self.handler_mock(inspect.currentframe().f_code.co_name, p0)

        @Plugin.integrate_with('mockplugin2')
        def integrate_b(self, p2):
            self.handler_mock(inspect.currentframe().f_code.co_name, p2)

        @Plugin.integrate_with('mockplugin2', 'mockplugin3')
        def integrate_c(self, p2, p3):
            self.handler_mock(inspect.currentframe().f_code.co_name, p2, p3)

    class MockPlugin2(Plugin):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.handler_mock = mock.Mock(spec=callable)

    class MockPlugin3(Plugin):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.handler_mock = mock.Mock(spec=callable)

    @pytest.mark.bot(plugins=[MockPlugin1, MockPlugin2, MockPlugin3],
                     config="""["@bot"]\nplugins = ["mockplugin1"]""")
    def test_no_integrations(self, bot_helper):
        """Check that no integration methods are called when the dependency plugins are not loaded."""
        assert bot_helper["mockplugin1"].handler_mock.mock_calls == []

    @pytest.mark.bot(plugins=[MockPlugin1, MockPlugin2, MockPlugin3],
                     config="""["@bot"]\nplugins = ["mockplugin1", "mockplugin2"]""")
    def test_some_integrations(self, bot_helper):
        """Check that integration methods only fire when all dependency plugins are loaded."""
        assert bot_helper["mockplugin1"].handler_mock.mock_calls == [
            mock.call("integrate_b", bot_helper["mockplugin2"]),
        ]

    @pytest.mark.bot(plugins=[MockPlugin1, MockPlugin2, MockPlugin3],
                     config="""["@bot"]\nplugins = ["mockplugin1", "mockplugin2", "mockplugin3"]""")
    def test_all_integrations(self, bot_helper):
        """Check that integration methods only fire when all dependency plugins are loaded."""
        assert bot_helper["mockplugin1"].handler_mock.mock_calls == [
            mock.call("integrate_b", bot_helper["mockplugin2"]),
            mock.call("integrate_c", bot_helper["mockplugin2"], bot_helper["mockplugin3"]),
        ]


class TestUse:
    class MockPlugin1(Plugin):
        a = Plugin.use("mockplugin2", foo="bar")

    class MockPlugin2(Plugin):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.handler_mock = mock.Mock(spec=callable)

        def provide(self, plugin_name, **kwargs):
            self.handler_mock(inspect.currentframe().f_code.co_name, plugin_name, kwargs)
            return "baz"

    class MockPlugin3(Plugin):
        a = Plugin.use("mockplugin4", foo="bar")

    class MockPlugin4(Plugin):
        pass

    def test_use_dependency_not_met(self, event_loop, config_example_mode):
        """Check that an error happens when loading a plugin that use()s a non-loaded plugin."""
        with pytest.raises(PluginDependencyUnmet):
            Bot(plugins=[self.MockPlugin1, self.MockPlugin2],
                config={"@bot": {"plugins": ["mockplugin1"]}})

    def test_use_called_provide(self, event_loop, config_example_mode):
        """Check that provide() method is called during setup()."""
        bot = Bot(plugins=[self.MockPlugin1, self.MockPlugin2],
                  config={"@bot": {"plugins": ["mockplugin2", "mockplugin1"]}})
        assert bot.plugins["mockplugin2"].handler_mock.mock_calls == []

        # Setup bot, access provided value, assert provide() was called
        bot.bot_setup()
        assert bot.plugins["mockplugin1"].a == "baz"
        assert bot.plugins["mockplugin2"].handler_mock.mock_calls == [
            mock.call("provide", "mockplugin1", {"foo": "bar"}),
        ]

    def test_provide_called_only_once(self, event_loop, config_example_mode):
        """Check that provide() method is only called once for each plugin."""
        bot = Bot(plugins=[self.MockPlugin1, self.MockPlugin2],
                  config={"@bot": {"plugins": ["mockplugin2", "mockplugin1"]}})
        assert bot.plugins["mockplugin2"].handler_mock.mock_calls == []

        # Setup bot, access provided value, assert provide() was called
        bot.bot_setup()
        assert bot.plugins["mockplugin1"].a == "baz"
        assert bot.plugins["mockplugin2"].handler_mock.mock_calls == [
            mock.call("provide", "mockplugin1", {"foo": "bar"}),
        ]

        # Access provided value again, assert provide() wasn't called a second time
        bot.plugins["mockplugin2"].handler_mock.reset_mock()
        assert bot.plugins["mockplugin1"].a == "baz"
        assert bot.plugins["mockplugin2"].handler_mock.mock_calls == []

    def test_no_provide_method(self, event_loop, config_example_mode):
        """Check that an error happens when target plugin doesn't implement provide()."""
        bot = Bot(plugins=[self.MockPlugin3, self.MockPlugin4],
                  config={"@bot": {"plugins": ["mockplugin4", "mockplugin3"]}})
        with pytest.raises(PluginFeatureError):
            bot.bot_setup()
