import unittest.mock as mock

import pytest

from csbot import core
from csbot.plugin import Plugin
from csbot.test import BotTestCase
from csbot.test.test_plugin_webserver import WebServer


class WebhookTest(Plugin):
    handler_mock = mock.Mock(spec=callable)

    @Plugin.hook('webhook.example')
    def handler(self, *args, **kwargs):
        self.handler_mock(*args, **kwargs)


class Bot(core.Bot):
    available_plugins = core.Bot.available_plugins.copy()
    available_plugins.update(
        webserver=WebServer,
        webhookexample=WebhookTest,
    )

# @pytest.mark.skip
class TestWebhookPlugin(BotTestCase):
    SECRET = 'foobar'
    BOT_CLASS = Bot
    CONFIG = f"""\
    [@bot]
    plugins = webserver webhook webhookexample

    [webhook]
    secret = {SECRET}
    """
    PLUGINS = ['webserver', 'webhook', 'webhookexample']

    @pytest.fixture
    def loop(self, event_loop):
        """Override pytest-aiohttp's loop fixture with pytest-asyncio's.
        """
        return event_loop

    async def test_unauthorised(self, aiohttp_client):
        client = await aiohttp_client(self.webserver.app)
        resp = await client.post('/webhook/example/wrong-token', data=b'')
        assert resp.status == 401
        self.webhookexample.handler_mock.assert_not_called()

    async def test_not_found(self, aiohttp_client):
        client = await aiohttp_client(self.webserver.app)
        resp = await client.post('/webhook/this/path/doesnt/exist', data=b'')
        assert resp.status == 404
        self.webhookexample.handler_mock.assert_not_called()

    async def test_webhook_fired(self, aiohttp_client):
        client = await aiohttp_client(self.webserver.app)
        resp = await client.post(f'/webhook/example/{self.SECRET}', data=b'')
        assert resp.status == 200
        assert await resp.text() == 'OK'
        self.webhookexample.handler_mock.assert_called_once()
