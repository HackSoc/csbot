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
        @staticmethod
        def payload_and_headers_from_fixture(fixture):
            payload = read_fixture_file(f'{fixture}.payload.json')
            headers = json.loads(read_fixture_file(f'{fixture}.headers.json'))
            return payload, headers

    return Helper


class TestGitHubPlugin:
    BOT_CLASS = Bot
    CONFIG = """\
    [@bot]
    plugins = webserver webhook github

    [webhook]
    secret = foobar

    [github]
    fmt/issues/* = [{repository[name]}] {sender[login]} {action} issue #{issue[number]}: {issue[title]} ({issue[html_url]})
    fmt/issues/assigned = [{repository[name]}] {sender[login]} {action} issue #{issue[number]} to {assignee[login]}: {issue[title]} ({issue[html_url]})
    
    [github/alanbriolat/csbot-webhook-test]
    notify = #mychannel
    """
    URL = f'/webhook/github/foobar'
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
        # Test with a non-existent event name/handler
        event_name = '_test'
        with asynctest.patch.object(bot_helper['github'], f'handle_{event_name}',
                                    new=asynctest.CoroutineMock(), create=True) as m:
            payload, headers = bot_helper.payload_and_headers_from_fixture('github-ping-20190128-101509')
            headers['X-GitHub-Event'] = event_name
            # Signature is still intact, so handler should be called
            resp = await client.post(self.URL, data=payload, headers=headers)
            assert resp.status == 200
            m.assert_called_once()
            m.reset_mock()
            # Signature made to be incorrect, handler should *not* be called
            headers['X-Hub-Signature'] = 'sha1=0000000000000000000000000000000000000000'
            resp = await client.post(self.URL, data=payload, headers=headers)
            assert resp.status == 200
            m.assert_not_called()

    TEST_CASES = [
        # Ping: https://developer.github.com/webhooks/#ping-event
        ('github-ping-20190128-101509', []),

        # Issues: https://developer.github.com/v3/activity/events/types/#issuesevent
        ('github-issues-opened-20190128-101904', [
            ('NOTICE #mychannel :[csbot-webhook-test] alanbriolat opened issue #2: '
             'Another test (https://github.com/alanbriolat/csbot-webhook-test/issues/2)'),
        ]),
        ('github-issues-closed-20190128-101908', [
            ('NOTICE #mychannel :[csbot-webhook-test] alanbriolat closed issue #2: '
             'Another test (https://github.com/alanbriolat/csbot-webhook-test/issues/2)'),
        ]),
        ('github-issues-reopened-20190128-101912', [
            ('NOTICE #mychannel :[csbot-webhook-test] alanbriolat reopened issue #2: '
             'Another test (https://github.com/alanbriolat/csbot-webhook-test/issues/2)'),
        ]),
        ('github-issues-assigned-20190128-101919', [
            ('NOTICE #mychannel :[csbot-webhook-test] alanbriolat assigned issue #2 to alanbriolat: '
             'Another test (https://github.com/alanbriolat/csbot-webhook-test/issues/2)'),
        ]),
        ('github-issues-unassigned-20190128-101924', [
            ('NOTICE #mychannel :[csbot-webhook-test] alanbriolat unassigned issue #2: '
             'Another test (https://github.com/alanbriolat/csbot-webhook-test/issues/2)'),
        ]),
    ]

    # @pytest.mark.parametrize("event_name, fixture_file, expected", TEST_CASES)
    # async def test_handlers(self, bot_helper, client, event_name, fixture_file, expected):
    #     method_name = f'handle_{event_name}'
    #     payload, headers = bot_helper.payload_and_headers_from_fixture(event_name, fixture_file)
    #     with asynctest.patch.object(bot_helper['github'], method_name) as m:
    #         resp = await client.post(self.URL, data=payload, headers=headers)
    #         assert resp.status == 200
    #         m.assert_called_once_with(json.loads(payload))

    @pytest.mark.parametrize("fixture_file, expected", TEST_CASES)
    @pytest.mark.usefixtures("run_client")
    @pytest.mark.asyncio
    async def test_behaviour(self, bot_helper, client, fixture_file, expected):
        payload, headers = bot_helper.payload_and_headers_from_fixture(fixture_file)
        resp = await client.post(self.URL, data=payload, headers=headers)
        assert resp.status == 200
        bot_helper.assert_sent(expected)
