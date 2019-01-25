import pytest

from csbot.test import BotTestCase, read_fixture_file


class TestGitHubPlugin(BotTestCase):
    SECRET = 'foobar'
    CONFIG = f"""\
    [@bot]
    plugins = webserver webhook github

    [webhook]
    secret = {SECRET}

    [github]
    
    """
    PLUGINS = ['webserver', 'github']

    @pytest.fixture
    def loop(self, event_loop):
        """Override pytest-aiohttp's loop fixture with pytest-asyncio's.
        """
        return event_loop

    async def test_ping(self, aiohttp_client):
        # https://developer.github.com/webhooks/#ping-event
        payload = """\
        {
          "hook":{
            "type":"App",
            "id":11,
            "active":true,
            "events":["pull_request"],
            "app_id":37
          }
        }
        """.encode("utf-8")

        client = await aiohttp_client(self.webserver.app)
        resp = await client.post(f'/webhook/github/{self.SECRET}', data=payload)
        assert resp.status == 200

    async def test_push(self, aiohttp_client):
        payload = read_fixture_file('github_push.json')
        client = await aiohttp_client(self.webserver.app)
        resp = await client.post()
