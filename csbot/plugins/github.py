import hmac
import datetime
import json
import string
from functools import partial

from ..plugin import Plugin


class GitHub(Plugin):
    PLUGIN_DEPENDS = ['webhook']

    CONFIG_DEFAULTS = {
        'notify': '',
        'debug_payloads': False,
        'fmt/*': None,
        # TODO: include events, exclude events
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
        payload = await request.read()
        json_payload = await request.json()

        if self.config_getboolean('debug_payloads'):
            try:
                extra = f'-{json_payload["action"]}'
            except KeyError:
                extra = ''
            now = datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')
            with open(f'github-{github_event}{extra}-{now}.headers.json', 'w') as f:
                json.dump(dict(request.headers), f, indent=2)
            with open(f'github-{github_event}{extra}-{now}.payload.json', 'wb') as f:
                f.write(payload)

        digest = request.headers['X-Hub-Signature']

        if not self._hmac_compare(payload, digest):
            self.log.warning('X-Hub-Signature verification failed')
            return
        method = getattr(self, f'handle_{github_event}', None)
        if method is None:
            await self.generic_handler(github_event, json_payload)
        else:
            await method(json_payload)

    async def generic_handler(self, github_event, data):
        repo = data.get("repository", {}).get("full_name", None)
        action = data.get('action', None)
        # Build event matchers from least to most specific
        matchers = ['*']
        if action is None:
            matchers.append(github_event)
        else:
            matchers.append(f'{github_event}/*')
            matchers.append(f'{github_event}/{action}')
        # Re-order from most to least specific
        matchers.reverse()
        # Most specific event name
        event_name = matchers[0]

        self.log.info(f'{event_name} event on {repo}')

        fmt = self.find_by_matchers(['fmt/' + m for m in matchers], self.config)
        if not fmt:
            return
        formatter = MessageFormatter(partial(self.config_get, repo=repo))
        msg = formatter.format(fmt, **data)
        try:
            notify = self.config_get('notify', repo)
        except KeyError:
            return
        for target in notify.split():
            self.bot.reply(target, msg)

    @staticmethod
    def find_by_matchers(matchers, d):
        for m in matchers:
            if m in d:
                return d[m]
        raise KeyError(f'none of {matchers} found')

    async def handle_ping(self, data):
        self.log.info("Received ping: {}", data)

    def _hmac_digest(self, msg, algorithm):
        secret = self.bot.plugins['webhook'].config_get('secret').encode('utf-8')
        return hmac.new(secret, msg, algorithm).hexdigest()

    def _hmac_compare(self, msg, digest):
        algorithm, _, signature = digest.partition('=')
        return hmac.compare_digest(self._hmac_digest(msg, algorithm), signature)


class MessageFormatter(string.Formatter):
    def __init__(self, config_get):
        self.config_get = config_get

    def get_field(self, field_name, args, kwargs):
        if field_name.startswith('fmt.'):
            fmt = self.config_get(field_name)
            if not fmt:
                raise KeyError('format not configured: ' + field_name)
            return self.vformat(fmt, args, kwargs), field_name

        return super().get_field(field_name, args, kwargs)
