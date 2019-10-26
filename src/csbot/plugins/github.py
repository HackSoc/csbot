"""
GitHub Deployment Tracking
==========================

GitHub's `Deployments API <https://developer.github.com/v3/repos/deployments/>`_ allows a repository to track deployment
activity. For example, deployments of the main instance of csbot can be seen at
https://github.com/HackSoc/csbot/deployments.

Getting csbot to report deployments to your repository during bot startup requires the following:

* ``SOURCE_COMMIT`` environment variable set to the current git revision (the
  `Docker image <https://hub.docker.com/r/alanbriolat/csbot>`_ has this baked in)
* ``--env-name`` command-line option (defaults to ``development``)
* ``--github-repo`` command-line option with the repository to report deployments to (e.g. ``HackSoc/csbot``)
* ``--github-token`` command-line option with a GitHub "personal access token" that has ``repo_deployment`` scope

.. note:: Deployments API functionality is implemented in :mod:`csbot.cli`, not here.

GitHub Webhooks
===============

The GitHub plugin provides a webhook endpoint that will turn incoming events into messages that are sent to IRC
channels. To use the GitHub webhook, the :mod:`~csbot.plugins.webserver` and :mod:`~csbot.plugins.webhook` plugins must
be enabled in addition to this one, and the csbot webserver must be exposed to the internet somehow.

Follow the `GitHub documentation <https://developer.github.com/webhooks/creating/>`_ to create a webhook on the desired
repository, with the following settings:

* **Payload URL**: see :mod:`~csbot.plugins.webhook` for how webhook URL routing works
* **Content type**: ``application/json``
* **Secret**: the same value as chosen for the ``secret`` plugin option, for signing payloads
* **Which events ...**: Configure for whichever events you want to handle

Configuration
-------------

The following configuration options are supported in the ``[github]`` config section:

==================  ===========
Setting             Description
==================  ===========
``secret``          The secret used when creating the GitHub webhook. **Optional**, will not verify payload signatures if unset.
``notify``          Space-separated list of IRC channels to send messages to.
``fmt/[...]``       Format strings to use for particular events, for turning an event into an IRC message. See below.
``fmt.[...]``       Re-usable format string fragments. See below.
==================  ===========

``secret`` and ``notify`` can be overridden on a per-repository basis, in a ``[github/{repo}]`` config section, e.g.
``[github/HackSoc/csbot]``.

Event format strings
--------------------

When writing format strings to handle GitHub webhook events, it's essential to refer to the
`GitHub Event Types & Payloads <https://developer.github.com/v3/activity/events/types>`_ documentation.

Each event ``event_type``, and possibly an ``event_subtype``. The ``event_type`` always corresponds to the "Webhook
event name" defined by GitHub's documentation, e.g. ``release`` for *ReleaseEvent*. The ``event_subtype`` is generally
the ``action`` from the payload, if that event type has one (but see below for exceptions).

The plugin will attempt to find the most specific config option that exists to supply a format string:

* For an event with ``event_type`` and ``event_subtype``, will try ``fmt/event_type/event_subtype``,
  ``fmt/event_type/*`` and ``fmt/*``
* For an event with no ``event_subtype``, will try ``fmt/event_type`` and ``fmt/*``

The first config option that exists will be used, and if that format string is empty (zero-length string, None, False)
then no message will be sent. This means it's possible to set a useful format string for ``fmt/issues/*``, but then set
an empty format for ``fmt/issues/labeled`` and ``fmt/issues/unlabeled`` to ignore some unwanted noise.

The string is formatted with the context of the entire webhook payload, plus additional keys for ``event_type``,
``event_subtype`` and ``event_name`` (which is ``{event_type}/{event_subtype}`` if there is an ``event_subtype``,
otherwise ``{event_type}``. (But see below for exceptions where additional context exists.)

Re-usable format strings
------------------------

There are a lot of recurring structures in the GitHub webhook payloads, and those will usually want to be formatted in
similar ways in resulting messages. For example, it might be desirable to start every message with the repository name
and user that caused the event. Instead of duplicating the same fragment of format string for each event type, which
makes the format strings long and hard to maintain, a format string fragment can be defined as a ``fmt.name`` config
option, and referenced in another format string as ``{fmt.name}``. These fragments will get formatted with the same
context as the top-level format string.

Customised event handling
-------------------------

To represent certain events more clearly, additional processing is required, either to extend the string format context
or to introduce an ``event_subtype`` where there is no ``action`` in the payload. This is the approach needed when
thinking "I wish string formatting had conditionals". Implementing such handling is done by creating a
``handle_{event_type}`` method, which should ultimately call ``generic_handler`` with appropriate arguments.

There is already customised handling for the following:

* ``push``
    * Sets ``event_subtype``: ``forced`` for forced update of a ref, and ``pushed`` for regular pushes
    * Sets ``count``: number of commits pushed to the ref
    * Sets ``short_ref``: only the final element of the long ref name, e.g. ``v1.0`` from ``refs/tags/v1.0``
* ``pull_request``
    * Overrides ``event_subtype`` with ``merged`` if PR was ``closed`` due to a merge
* ``pull_request_review``
    * Sets ``review_state`` to a human-readable version of the review state

Module contents
===============
"""
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

    CONFIG_ENVVARS = {
        'secret': ['GITHUB_WEBHOOK_SECRET'],
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
