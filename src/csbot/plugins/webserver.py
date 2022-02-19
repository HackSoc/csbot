"""
Creates a web server using :mod:`aiohttp` so that other plugins can register URL handlers.

To register a URL handler, a plugin should hook the ``webserver.build`` event and create a sub-application,
for example::

    class MyPlugin(Plugin):
        @Plugin.hook('webserver.build')
        def create_app(self, e):
            with e['webserver'].create_subapp('/my_plugin') as app:
                app.add_routes([web.get('/{item}', self.request_handler)])

        async def request_handler(self, request):
            return web.Response(text=f'No {request.match_info["item"]} here, oh dear!')

Configuration
=============

The following configuration options are supported in the ``[webserver]`` config section:

==================  ===========
Setting             Description
==================  ===========
``host``            Hostname/IP address to listen on. Default: ``localhost``.
``port``            Port to listen on. Default: ``1337``.
==================  ===========

Module contents
===============
"""


from contextlib import contextmanager

from aiohttp import web

from ..plugin import Plugin


class WebServer(Plugin):
    CONFIG_DEFAULTS = {
        'host': 'localhost',
        'port': 1337,
    }

    def setup(self):
        # Setup server
        self.bot.loop.run_until_complete(self._build_app())
        self.bot.loop.run_until_complete(self._start_app())

    async def _build_app(self):
        self.app = web.Application()
        await self.bot.emit_new('webserver.build', {
            'webserver': self,
        })

    async def _start_app(self):
        self.app_runner = web.AppRunner(self.app)
        await self.app_runner.setup()
        self.site = web.TCPSite(self.app_runner, self.config_get('host'), self.config_get('port'))
        await self.site.start()

    async def _stop_app(self):
        await self.app_runner.cleanup()
        self.app_runner = None
        self.site = None

    def teardown(self):
        self.bot.loop.run_until_complete(self._stop_app())

        super().teardown()

    @contextmanager
    def create_subapp(self, prefix):
        self.log.info(f'Registering web application at {prefix}')
        app = web.Application()
        yield app
        self.app.add_subapp(prefix, app)
