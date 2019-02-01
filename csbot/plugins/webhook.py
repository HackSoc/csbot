from aiohttp import web

from ..plugin import Plugin


class Webhook(Plugin):
    CONFIG_DEFAULTS = {
        # Prefix for web application
        'prefix': '/webhook',
        # Secret for URLs
        'url_secret': '',
    }

    CONFIG_ENVVARS = {
        'url_secret': ['WEBHOOK_SECRET'],
    }

    @Plugin.hook('webserver.build')
    def create_app(self, e):
        with e['webserver'].create_subapp(self.config_get('prefix')) as app:
            app.add_routes([web.post('/{service}/{url_secret}', self.request_handler)])

    async def request_handler(self, request):
        if self.config_get('url_secret') != request.match_info['url_secret']:
            return web.HTTPUnauthorized()
        event_name = f'webhook.{request.match_info["service"]}'
        await self.bot.emit_new(event_name, {
            'request': request,
        })
        return web.Response(text="OK")
