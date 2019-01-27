import hmac

from ..plugin import Plugin


class GitHub(Plugin):
    PLUGIN_DEPENDS = ['webhook']

    CONFIG_DEFAULTS = {
        'notify': '',
    }

    def config_get(self, key, repo=None):
        """A special implementation of :meth:`Plugin.config_get` which looks at
        a repo-based configuration subsection before the plugin's
        configuration section.
        """
        default = super().config_get(key)

        if repo is None:
            return default
        else:
            return self.subconfig(repo).get(key, default)

    @Plugin.hook('webhook.github')
    async def webhook(self, e):
        self.log.info("Handling github webhook")
        request = e['request']
        github_event = request.headers['X-GitHub-Event'].lower()
        digest = request.headers['X-GitHub-Signature']
        payload = await request.read()
        if not self._hmac_compare(payload, digest):
            self.log.warning('X-GitHub-Signature verification failed')
            return
        method = getattr(self, f'handle_{github_event}', None)
        if method is not None:
            await method(await request.json())

    async def handle_ping(self, data):
        self.log.info("Received ping: {}", data)

    async def handle_issues(self, data):
        action = data['action']
        repo = data['repository']['full_name']
        self.log.info(f'Issue {action} event on {repo}')
        fmt = ('[{repository[full_name]}] {sender[login]} {action} issue #{issue[number]}: '
               '{issue[title]} ({issue[html_url]})')
        msg = fmt.format(**data)
        try:
            notify = self.config_get('notify', repo)
        except KeyError:
            return
        for target in notify.split():
            self.bot.reply(target, msg)

    def _hmac(self, msg):
        secret = self.bot.plugins['webhook'].config_get('secret').encode('utf-8')
        return hmac.new(secret, msg, 'sha1')

    def _hmac_digest(self, msg):
        return self._hmac(msg).hexdigest()

    def _hmac_compare(self, msg, digest):
        return hmac.compare_digest(self._hmac_digest(msg), digest)
