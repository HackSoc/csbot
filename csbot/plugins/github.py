from ..plugin import Plugin


class GitHub(Plugin):
    PLUGIN_DEPENDS = ['webhook']

    @Plugin.hook('webhook.github')
    async def webhook(self, e):
        self.log.info("Handling github webhook")
        request = e['request']
        github_event = request.headers['X-GitHub-Event'].lower()
        method = getattr(self, f'handle_{github_event}', None)
        if method is not None:
            await method(request)

    async def handle_ping(self, request):
        data = await request.json()
        self.log.info("Received ping event: {}", data)
