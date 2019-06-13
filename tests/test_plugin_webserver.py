import pytest
from aiohttp import web

from csbot import core
from csbot.plugin import Plugin
from csbot.plugins import webserver


class WebServer(webserver.WebServer):
    async def _start_app(self):
        pass

    async def _stop_app(self):
        pass


class WebServerExample(Plugin):
    @Plugin.hook('webserver.build')
    def create_app(self, e):
        with e['webserver'].create_subapp('/prefix') as app:
            app.add_routes([web.get('/', self.request_handler)])

    async def request_handler(self, request):
        return web.Response(text='Hello, world')


class Bot(core.Bot):
    available_plugins = core.Bot.available_plugins.copy()
    available_plugins.update(
        webserver=WebServer,
        webserverexample=WebServerExample,
    )


pytestmark = pytest.mark.bot(cls=Bot, config="""\
    ["@bot"]
    plugins = "webserver webserverexample"
    """)


class TestWebServerPlugin:
    async def test_example(self, bot_helper, aiohttp_client):
        client = await aiohttp_client(bot_helper['webserver'].app)
        resp = await client.get('/prefix/')
        assert resp.status == 200
        assert await resp.text() == 'Hello, world'
