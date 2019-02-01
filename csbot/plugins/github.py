import hmac
import datetime
import json
import string
from functools import partial

from ..plugin import Plugin


class GitHub(Plugin):
    PLUGIN_DEPENDS = ['webhook']

    CONFIG_DEFAULTS = {
        'secret': '',
        'notify': '',
        'debug_payloads': False,
        'fmt/*': None,
    }

    __sentinel = object()

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
        data = await request.json()
        repo = data.get("repository", {}).get("full_name", None)

        if self.config_getboolean('debug_payloads'):
            try:
                extra = f'-{data["action"]}'
            except KeyError:
                extra = ''
            now = datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')
            with open(f'github-{github_event}{extra}-{now}.headers.json', 'w') as f:
                json.dump(dict(request.headers), f, indent=2)
            with open(f'github-{github_event}{extra}-{now}.payload.json', 'wb') as f:
                f.write(payload)

        secret = self.config_get('secret', repo)
        if not secret:
            self.log.warning('No secret set, not verifying X-Hub-Signature')
        else:
            digest = request.headers['X-Hub-Signature']
            if not self._hmac_compare(secret, payload, digest):
                self.log.warning('X-Hub-Signature verification failed')
                return
        method = getattr(self, f'handle_{github_event}', self.generic_handler)
        await method(data, github_event)

    async def generic_handler(self, data, event_type, event_subtype=None, event_subtype_key='action', context=None):
        repo = data.get("repository", {}).get("full_name", None)
        if event_subtype is None:
            event_subtype = data.get(event_subtype_key, None)
        # Build event matchers from least to most specific
        matchers = ['*']
        if event_subtype is None:
            matchers.append(event_type)
        else:
            matchers.append(f'{event_type}/*')
            matchers.append(f'{event_type}/{event_subtype}')
        # Re-order from most to least specific
        matchers.reverse()
        # Most specific event name
        event_name = matchers[0]

        self.log.info(f'{event_name} event on {repo}')

        fmt = self.find_by_matchers(['fmt/' + m for m in matchers], self.config, None)
        if not fmt:
            return
        formatter = MessageFormatter(partial(self.config_get, repo=repo))
        format_context = {
            'event_type': event_type,
            'event_subtype': event_subtype,
            'event_name': event_name,
        }
        format_context.update(context or {})
        format_context.update(data)
        msg = formatter.format(fmt, **format_context)
        try:
            notify = self.config_get('notify', repo)
        except KeyError:
            return
        for target in notify.split():
            self.bot.reply(target, msg)

    async def handle_pull_request(self, data, event_type):
        if data['action'] == 'closed' and data['pull_request']['merged']:
            event_subtype = 'merged'
        else:
            event_subtype = None
        return await self.generic_handler(data, event_type, event_subtype)

    async def handle_push(self, data, event_type):
        context = {
            'count': len(data['commits']),
            'short_ref': data['ref'].rsplit('/')[-1],
        }
        if data['forced']:
            event_subtype = 'forced'
        else:
            event_subtype = 'pushed'
        return await self.generic_handler(data, event_type, event_subtype, context=context)

    async def handle_pull_request_review(self, data, event_type):
        context = {
            'review_state': data['review']['state'].replace('_', ' '),
        }
        return await self.generic_handler(data, event_type, context=context)

    @classmethod
    def find_by_matchers(cls, matchers, d, default=__sentinel):
        for m in matchers:
            if m in d:
                return d[m]
        if default is not cls.__sentinel:
            return default
        raise KeyError(f'none of {matchers} found')

    async def handle_ping(self, data):
        self.log.info("Received ping: {}", data)

    def _hmac_digest(self, secret, msg, algorithm):
        return hmac.new(secret.encode('utf-8'), msg, algorithm).hexdigest()

    def _hmac_compare(self, secret, msg, digest):
        algorithm, _, signature = digest.partition('=')
        return hmac.compare_digest(self._hmac_digest(secret, msg, algorithm), signature)


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
