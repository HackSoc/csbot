import json

import pytest
import asynctest

from csbot import core
from csbot.test import BotTestCase, read_fixture_file
from csbot.test.test_plugin_webserver import WebServer


class Bot(core.Bot):
    available_plugins = core.Bot.available_plugins.copy()
    available_plugins.update(
        webserver=WebServer,
    )


class TestGitHubPlugin(BotTestCase):
    SECRET = 'foobar'
    BOT_CLASS = Bot
    CONFIG = f"""\
    [@bot]
    plugins = webserver webhook github

    [webhook]
    secret = {SECRET}

    [github]
    
    """
    PLUGINS = ['webserver', 'github']
    URL = f'/webhook/github/{SECRET}'

    @pytest.fixture
    def loop(self, event_loop):
        """Override pytest-aiohttp's loop fixture with pytest-asyncio's.
        """
        return event_loop

    def _payload_and_headers_from_fixture(self, event, filename):
        payload = read_fixture_file(filename)
        headers = {
            'X-GitHub-Event': event,
            'X-GitHub-Delivery': '00000000-0000-0000-0000-000000000000',
            'X-GitHub-Signature': self.github._hmac_digest(payload),
        }
        return payload, headers

    def _payload_and_headers_from_object(self, event, obj):
        payload = json.dumps(obj).encode('utf-8')
        headers = {
            'X-GitHub-Event': event,
            'X-GitHub-Delivery': '00000000-0000-0000-0000-000000000000',
            'X-GitHub-Signature': self.github._hmac_digest(payload),
        }
        return payload, headers

    # @pytest.fixture
    # async def webserver_client(self, aiohttp_client, bot_setup):
    #     print("doing webserver_client")
    #     print(self)
    #     return await aiohttp_client(self.webserver.app)

    async def test_signature_check(self, aiohttp_client):
        client = await aiohttp_client(self.webserver.app)
        with asynctest.patch.object(self.github, 'handle_foo', new=asynctest.CoroutineMock(), create=True) as m:
            payload = {}
            data = json.dumps(payload).encode('utf-8')
            headers = {
                'X-GitHub-Event': 'foo',
                'X-GitHub-Delivery': '00000000-0000-0000-0000-000000000000',
                'X-GitHub-Signature': '0000000000000000000000000000000000000000',
            }
            resp = await client.post(self.URL, data=data, headers=headers)
            assert resp.status == 200
            m.assert_not_called()

            headers['X-GitHub-Signature'] = self.github._hmac_digest(data)
            resp = await client.post(self.URL, data=data, headers=headers)
            assert resp.status == 200
            m.assert_called_once_with(payload)

    async def test_ping(self, aiohttp_client):
        # https://developer.github.com/webhooks/#ping-event
        payload, headers = self._payload_and_headers_from_object("ping", {
            "hook": {
                "type": "App",
                "id": 11,
                "active": True,
                "events": ["pull_request"],
                "app_id": 37
            }
        })

        client = await aiohttp_client(self.webserver.app)
        with asynctest.patch.object(self.github, 'handle_ping') as m:
            resp = await client.post(
                self.URL,
                data=payload,
                headers={
                    'X-GitHub-Event': 'ping',
                    'X-GitHub-Delivery': '00000000-0000-0000-0000-000000000000',
                    'X-GitHub-Signature': self.github._hmac_digest(payload),
                },
            )
            assert resp.status == 200
            m.assert_called_once()
    #
    # @pytest.mark.usefixtures("run_client")
    # async def test_push(self, aiohttp_client):
    #     payload, headers = self._payload_and_headers_from_fixture("push", 'github_webhook_push.json')
    #     client = await aiohttp_client(self.webserver.app)
    #     resp = await client.post(self.URL, data=payload, headers=headers)
    #     self.assert_sent([''])

    # @pytest.mark.usefixtures("run_client")
    # async def test_issue_opened(self, webserver_client):
    #     pass
