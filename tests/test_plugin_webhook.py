import unittest.mock as mock

import pytest

from csbot.plugin import Plugin
from csbot.plugins.webhook import Webhook
from .test_plugin_webserver import WebServer


class WebhookExample(Plugin):
    handler_mock = mock.Mock(spec=callable)

    @Plugin.hook('webhook.example')
    def handler(self, *args, **kwargs):
        self.handler_mock(*args, **kwargs)


PLUGINS = [WebServer, Webhook, WebhookExample]


class TestWebhookPlugin:
    SECRET = 'foobar'
    CONFIG = f"""\
    ["@bot"]
    plugins = ["webserver", "webhook", "webhookexample"]

    [webhook]
    url_secret = "{SECRET}"
    """
    pytestmark = pytest.mark.bot(plugins=PLUGINS, config=CONFIG)

    @pytest.fixture
    def loop(self, event_loop):
        """Override pytest-aiohttp's loop fixture with pytest-asyncio's.
        """
        return event_loop

    @pytest.fixture
    async def client(self, bot_helper, aiohttp_client):
        return await aiohttp_client(bot_helper['webserver'].app)

    async def test_unauthorised(self, bot_helper, client):
        resp = await client.post('/webhook/example/wrong-token', data=b'')
        assert resp.status == 401
        bot_helper['webhookexample'].handler_mock.assert_not_called()

    async def test_not_found(self, bot_helper, client):
        resp = await client.post('/webhook/this/path/doesnt/exist', data=b'')
        assert resp.status == 404
        bot_helper['webhookexample'].handler_mock.assert_not_called()

    async def test_webhook_fired(self, bot_helper, client):
        resp = await client.post(f'/webhook/example/{self.SECRET}', data=b'')
        assert resp.status == 200
        assert await resp.text() == 'OK'
        bot_helper['webhookexample'].handler_mock.assert_called_once()
