"""
Uses :mod:`~csbot.plugins.webserver` to create a generic URL for incoming webhooks so that other plugins can handle
webhook events.

To act as a webhook handler, a plugin should hook the ``webhook.{service}`` event, for example::

    class MyPlugin(Plugin):
        @Plugin.hook('webhook.myplugin')
        async def webhook(self, e):
            self.log.info(f'Handling {e["request"]}')

The ``request`` key of the event contains the :class:`aiohttp.web.Request` object.

.. note:: The webhook plugin only responds to ``POST`` requests.

Configuration
=============

The following configuration options are supported in the ``[webserver]`` config section:

==================  ===========
Setting             Description
==================  ===========
``prefix``          URL prefix for the web server sub-application. Default: ``/webhook``.
``url_secret``      Extra URL component to make valid endpoints hard to guess.
==================  ===========

URL Format & Request Handling
=============================

The URL path for a webhook is ``{prefix}/{service}/{url_secret}``. The host and port elements, plus any additional
prefix, are determined by the :mod:`~csbot.plugins.webserver` plugin and/or any reverse-proxy that is in front of it.

For example, the main deployment of csbot received webhooks at ``https://{host}/csbot/webhook/{service}/{url_secret}``
and sits behind nginx with the following configuration::

    location /csbot/ {
        proxy_pass http://localhost:8180/;
    }

Module contents
===============
"""
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
