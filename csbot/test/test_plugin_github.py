import json

import pytest
import asynctest

from csbot import core
from csbot.test import read_fixture_file
from csbot.test.test_plugin_webserver import WebServer


class Bot(core.Bot):
    available_plugins = core.Bot.available_plugins.copy()
    available_plugins.update(
        webserver=WebServer,
    )


@pytest.fixture
def bot_helper_class(bot_helper_class):
    class Helper(bot_helper_class):
        def payload_and_headers_from_fixture(self, event, filename):
            payload = read_fixture_file(filename)
            headers = {
                'X-GitHub-Event': event,
                'X-GitHub-Delivery': '00000000-0000-0000-0000-000000000000',
                'X-GitHub-Signature': self['github']._hmac_digest(payload),
            }
            return payload, headers

        def payload_and_headers_from_object(self, event, obj):
            payload = json.dumps(obj).encode('utf-8')
            headers = {
                'X-GitHub-Event': event,
                'X-GitHub-Delivery': '00000000-0000-0000-0000-000000000000',
                'X-GitHub-Signature': self['github']._hmac_digest(payload),
            }
            return payload, headers

    return Helper


TEST_CASES = [
    ('ping', 'github_webhook_ping.json', []),
]


class TestGitHubPlugin:
    SECRET = 'foobar'
    BOT_CLASS = Bot
    CONFIG = f"""\
    [@bot]
    plugins = webserver webhook github

    [webhook]
    secret = {SECRET}

    [github]
    
    """
    URL = f'/webhook/github/{SECRET}'
    pytestmark = pytest.mark.bot(cls=Bot, config=CONFIG)

    @pytest.fixture
    def loop(self, event_loop):
        """Override pytest-aiohttp's loop fixture with pytest-asyncio's.
        """
        return event_loop

    @pytest.fixture
    async def client(self, bot_helper, aiohttp_client):
        return await aiohttp_client(bot_helper['webserver'].app)

    async def test_signature_check(self, bot_helper, client):
        with asynctest.patch.object(bot_helper['github'], 'handle_foo',
                                    new=asynctest.CoroutineMock(), create=True) as m:
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

            headers['X-GitHub-Signature'] = bot_helper['github']._hmac_digest(data)
            resp = await client.post(self.URL, data=data, headers=headers)
            assert resp.status == 200
            m.assert_called_once_with(payload)

    @pytest.mark.parametrize("event_name, fixture_file, expected", TEST_CASES)
    async def test_handlers(self, bot_helper, client, event_name, fixture_file, expected):
        method_name = f'handle_{event_name}'
        payload, headers = bot_helper.payload_and_headers_from_fixture(event_name, fixture_file)
        with asynctest.patch.object(bot_helper['github'], method_name) as m:
            resp = await client.post(self.URL, data=payload, headers=headers)
            assert resp.status == 200
            m.assert_called_once_with(json.loads(payload))

    @pytest.mark.parametrize("event_name, fixture_file, expected", TEST_CASES)
    @pytest.mark.usefixtures("run_client")
    @pytest.mark.asyncio
    async def test_behaviour(self, bot_helper, client, event_name, fixture_file, expected):
        payload, headers = bot_helper.payload_and_headers_from_fixture(event_name, fixture_file)
        resp = await client.post(self.URL, data=payload, headers=headers)
        assert resp.status == 200
        bot_helper.assert_sent(expected)
