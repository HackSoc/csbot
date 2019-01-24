from aiohttp import web

from csbot import core
from csbot.plugin import Plugin
from csbot.plugins import webserver
from csbot.test import BotTestCase


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


class TestWebServerPlugin(BotTestCase):
    BOT_CLASS = Bot
    CONFIG = f"""\
    [@bot]
    plugins = webserver webserverexample
    """
    PLUGINS = ['webserver', 'webserverexample']

    async def test_example(self, aiohttp_client):
        client = await aiohttp_client(self.webserver.app)
        resp = await client.get('/prefix/')
        assert resp.status == 200
        assert await resp.text() == 'Hello, world'
