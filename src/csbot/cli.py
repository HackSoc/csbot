import asyncio
import configparser
import json
import logging
import logging.config
import os
import signal
import sys

import aiohttp
import click
import rollbar
import toml

from .core import Bot
from .plugin import find_plugins


LOG = logging.getLogger(__name__)


__version__ = None
try:
    import pkg_resources
    __version__ = pkg_resources.get_distribution('csbot').version
except (pkg_resources.DistributionNotFound, ImportError):
    pass


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
@click.option('--config-format', type=click.Choice(("ini", "json", "toml")),
              help='Configuration file format. [default: based on file extension]')
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
         env_name,
         config_format):
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
                'class': 'csbot.util.PrettyStreamHandler',
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
    _, ext = os.path.splitext(config.name)
    if config_format == "ini" or ext.lower() in {".ini", ".cfg"}:
        LOG.debug("Reading configuration with ConfigParser")
        config_data = load_ini(config)
    elif config_format == "json" or ext.lower() in {".json"}:
        LOG.debug("Reading configuration as JSON")
        config_data = load_json(config)
    elif config_format == "toml" or ext.lower() in {".toml"}:
        LOG.debug("Reading configuration as TOML")
        config_data = load_toml(config)
    else:
        raise click.BadArgumentUsage('config file extension not in {".ini", ".cfg", ".json", ".toml"} '
                                     'and no --config-format specified, unsure how to load config')
    client = Bot(config_data)
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


def load_ini(f):
    parser = configparser.ConfigParser(interpolation=None, allow_no_value=True)
    parser.optionxform = str    # Preserve case
    parser.read_file(f)
    config = {}
    for name, parser_section in parser.items():
        config[name] = section = {}
        for key, value in parser_section.items():
            section[key] = value
    return config


def load_json(f):
    return json.load(f)


def load_toml(f):
    return toml.load(f)


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

            await status_response.json()

        LOG.info('Reported deploy to GitHub: env=%s revision=%s deploy_id=%s',
                 env_name, revision, deploy["id"])


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def util():
    pass


@util.command(help="List available plugins")
def list_plugins():
    for P in sorted(find_plugins(), key=lambda p: p.plugin_name()):
        sys.stdout.write(f"{P.plugin_name():<20}  ({P.qualified_name()})\n")


@util.command(help="Generate example configuration file")
@click.option("--commented/--uncommented", "commented", default=False,
              help="Comment out all generated configuration")
def example_config(commented):
    Bot.write_example_config(sys.stdout, plugins=find_plugins(), commented=commented)
