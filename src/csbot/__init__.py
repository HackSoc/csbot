import asyncio
import logging
import logging.config
import signal
import os

import click
import aiohttp
import rollbar

from .core import Bot


__version__ = None
try:
    import pkg_resources
    __version__ = pkg_resources.get_distribution('csbot').version
except (pkg_resources.DistributionNotFound, ImportError):
    pass


LOG = logging.getLogger(__name__)


@click.command(context_settings={
    'help_option_names': ['-h', '--help'],
    'auto_envvar_prefix': 'CSBOT',
})
@click.version_option(version=__version__)
@click.option('--debug', '-d', is_flag=True, default=False,
              help='Turn on debug logging for the bot.')
@click.option('--debug-irc', is_flag=True, default=False,
              help='Turn on debug logging for IRC client library.')
@click.option('--debug-events', is_flag=True, default=False,
              help='Turn on debug logging for event handler.')
@click.option('--debug-asyncio', is_flag=True, default=False,
              help='Turn on debug logging for asyncio library.')
@click.option('--debug-all', is_flag=True, default=False,
              help='Turn on all debug logging.')
@click.option('--colour/--no-colour', 'colour_logging', default=None,
              help='Use colour in logging. [default: automatic]')
@click.option('--rollbar-token', default=None,
              help='Rollbar access token, enables Rollbar error reporting.')
@click.option('--github-token', default=None,
              help='GitHub "personal access token", enables GitHub deployment reporting.')
@click.option('--github-repo', default=None,
              help='GitHub repository to report deployments to.')
@click.option('--env-name', default='development',
              help='Deployment environment name. [default: development]')
@click.argument('config', type=click.File('r'))
def main(config,
         debug,
         debug_irc,
         debug_events,
         debug_asyncio,
         debug_all,
         colour_logging,
         rollbar_token,
         github_token,
         github_repo,
         env_name):
    """Run an IRC bot from a configuration file.
    """
    revision = os.environ.get('SOURCE_COMMIT', None)

    # Apply "debug all" option
    if debug_all:
        debug = debug_irc = debug_events = debug_asyncio = True

    # Configure logging
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'default': {
                'format': '[{asctime}] ({levelname[0]}:{name}) {message}',
                'datefmt': '%Y/%m/%d %H:%M:%S',
                'style': '{',
            },
        },
        'handlers': {
            'pretty': {
                'class': 'csbot.PrettyStreamHandler',
                'level': 'DEBUG',
                'formatter': 'default',
                'colour': colour_logging,
            },
        },
        'root': {
            'level': 'DEBUG' if debug else 'INFO',
            'handlers': ['pretty'],
        },
        'loggers': {
            'csbot.irc': {
                'level': 'DEBUG' if debug_irc else 'INFO',
            },
            'csbot.events': {
                'level': 'DEBUG' if debug_events else 'INFO',
            },
            'asyncio': {
                # Default is WARNING because 'poll took x seconds' messages are annoying
                'level': 'DEBUG' if debug_asyncio else 'WARNING',
            },
        }
    })

    # Create and initialise the bot
    client = Bot(config)
    client.bot_setup()

    # Configure Rollbar for exception reporting, report deployment
    if rollbar_token:
        rollbar.init(rollbar_token, env_name)

        def handler(loop, context):
            exception = context.get('exception')
            if exception is not None:
                exc_info = (type(exception), exception, exception.__traceback__)
            else:
                exc_info = None
            extra_data = {
                'csbot_event': context.get('csbot_event'),
                'csbot_recent_messages': "\n".join(client.recent_messages),
            }
            rollbar.report_exc_info(exc_info, extra_data=extra_data)
            loop.default_exception_handler(context)
        client.loop.set_exception_handler(handler)

        if revision:
            client.loop.run_until_complete(rollbar_report_deploy(rollbar_token, env_name, revision))

    if github_token and github_repo and revision:
        client.loop.run_until_complete(github_report_deploy(github_token, github_repo, env_name, revision))

    # Run the client
    async def graceful_shutdown(future):
        LOG.info("Calling quit() and waiting for disconnect...")
        client.quit()
        try:
            await asyncio.wait_for(client.disconnected.wait(), 2)
            return
        except asyncio.TimeoutError:
            pass

        LOG.warning("Still connected after 2 seconds, calling disconnect()...")
        client.disconnect()
        try:
            await asyncio.wait_for(client.disconnected.wait(), 2)
            return
        except asyncio.TimeoutError:
            pass

        LOG.warning("Still connected after 2 seconds, forcing exit...")
        future.cancel()

    def stop(future):
        # Next ctrl+c should ignore our handler
        client.loop.remove_signal_handler(signal.SIGINT)
        LOG.info("Interrupt received, attempting graceful shutdown... (press ^c again to force exit)")
        asyncio.ensure_future(graceful_shutdown(future), loop=client.loop)

    # Run the client until it exits or gets SIGINT
    client_future = asyncio.ensure_future(client.run(), loop=client.loop)
    client.loop.add_signal_handler(signal.SIGINT, stop, client_future)
    try:
        client.loop.run_until_complete(client_future)
    except asyncio.CancelledError:
        LOG.error("client.run() task cancelled")

    # Run teardown before disposing of the event loop, in case teardown code needs asyncio
    client.bot_teardown()

    # Cancel all pending tasks (taken from asyncio.run() in python 3.7)
    to_cancel = asyncio.all_tasks(client.loop)
    for task in to_cancel:
        task.cancel()
    client.loop.run_until_complete(asyncio.gather(*to_cancel, loop=client.loop, return_exceptions=True))
    for task in to_cancel:
        if task.cancelled():
            continue
        if task.exception() is not None:
            client.loop.call_exception_handler({
                "message": "unhandled exception during shutdown",
                "exception": task.exception(),
                "future": task,
            })
    # Cancel async generators (taken from asyncio.run() in python 3.7)
    client.loop.run_until_complete(client.loop.shutdown_asyncgens())

    client.loop.close()
    LOG.info("Exited")


async def rollbar_report_deploy(rollbar_token, env_name, revision):
    async with aiohttp.ClientSession() as session:
        request = session.post(
            'https://api.rollbar.com/api/1/deploy/',
            data={
                'access_token': rollbar_token,
                'environment': env_name,
                'revision': revision,
            },
        )
        async with request as response:
            data = await response.json()
            if response.status == 200:
                LOG.info('Reported deploy to Rollbar: env=%s revision=%s deploy_id=%s',
                         env_name, revision, data['data']['deploy_id'])
            else:
                LOG.error('Error reporting deploy to Rollbar: %s', data['message'])


async def github_report_deploy(github_token, github_repo, env_name, revision):
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json',
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        create_request = session.post(
            f'https://api.github.com/repos/{github_repo}/deployments',
            json={
                'ref': revision,
                'auto_merge': False,
                'environment': env_name,
                'description': 'Bot running with new version',
            },
        )
        async with create_request as create_response:
            if create_response.status != 201:
                LOG.error('Error reporting deploy to GitHub (create deploy): %s %s\n%s',
                          create_response.status, create_response.reason, await create_response.text())
                return

            deploy = await create_response.json()

        status_request = session.post(
            deploy['statuses_url'],
            json={
                'state': 'success',

            },
        )
        async with status_request as status_response:
            if status_response.status != 201:
                LOG.error('Error reporting deploy to GitHub (update status): %s %s\n%s',
                          create_response.status, create_response.reason, await create_response.text())
                return

            status = await status_response.json()

        LOG.info('Reported deploy to GitHub: env=%s revision=%s deploy_id=%s',
                 env_name, revision, deploy["id"])


class PrettyStreamHandler(logging.StreamHandler):
    """Wrap log messages with severity-dependent ANSI terminal colours.

    Use in place of :class:`logging.StreamHandler` to have log messages coloured
    according to severity.

    >>> handler = PrettyStreamHandler()
    >>> handler.setFormatter(logging.Formatter('[%(levelname)-8s] %(message)s'))
    >>> logging.getLogger('').addHandler(handler)

    *stream* corresponds to the same argument to :class:`logging.StreamHandler`,
    defaulting to stderr.

    *colour* overrides TTY detection to force colour on or off.

    This source for this class is released into the public domain.

    .. codeauthor:: Alan Briolat <alan.briolat@gmail.com>
    """
    #: Mapping from logging levels to ANSI colours.
    COLOURS = {
        logging.DEBUG: '\033[36m',      # Cyan foreground
        logging.WARNING: '\033[33m',    # Yellow foreground
        logging.ERROR: '\033[31m',      # Red foreground
        logging.CRITICAL: '\033[31;7m'  # Red foreground, inverted
    }
    #: ANSI code for resetting the terminal to default colour.
    COLOUR_END = '\033[0m'

    def __init__(self, stream=None, colour=None):
        super(PrettyStreamHandler, self).__init__(stream)
        if colour is None:
            self.colour = self.stream.isatty()
        else:
            self.colour = colour

    def format(self, record):
        """Get a coloured, formatted message for a log record.

        Calls :func:`logging.StreamHandler.format` and applies a colour to the
        message if appropriate.
        """
        msg = super(PrettyStreamHandler, self).format(record)
        if self.colour:
            colour = self.COLOURS.get(record.levelno, '')
            return colour + msg + self.COLOUR_END
        else:
            return msg


if __name__ == '__main__':
    main()
