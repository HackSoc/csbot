import unittest.mock as mock
import asyncio

import pytest

from csbot import core
from csbot.plugin import Plugin


class TestHookOrdering:
    class Bot(core.Bot):
        class MockPlugin(Plugin):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.handler_mock = mock.Mock(spec=callable)

            @Plugin.hook('core.message.privmsg')
            async def privmsg(self, event):
                await asyncio.sleep(0.5)
                self.handler_mock('privmsg', event['message'])

            @Plugin.hook('core.user.quit')
            def quit(self, event):
                self.handler_mock('quit', event['user'])

        available_plugins = core.Bot.available_plugins.copy()
        available_plugins.update(
            mockplugin=MockPlugin,
        )

    CONFIG = f"""\
    ["@bot"]
    plugins = ["mockplugin"]
    """
    pytestmark = pytest.mark.bot(cls=Bot, config=CONFIG)

    @pytest.mark.asyncio
    @pytest.mark.parametrize('n', list(range(1, 10)))
    async def test_burst_in_order(self, bot_helper, n):
        """Check that a plugin always gets messages in receive order."""
        plugin = bot_helper['mockplugin']
        users = [f':nick{i}!user{i}@host{i}' for i in range(n)]
        messages = [f':{user} QUIT :*.net *.split' for user in users]
        await asyncio.wait(bot_helper.receive(messages))
        assert plugin.handler_mock.mock_calls == [mock.call('quit', user) for user in users]

    @pytest.mark.asyncio
    async def test_non_blocking(self, bot_helper):
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
