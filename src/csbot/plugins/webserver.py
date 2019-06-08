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
