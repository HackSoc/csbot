import logging
import logging.config
import signal
import os

import click
import rollbar

from .core import Bot


@click.command(context_settings={'help_option_names': ['-h', '--help']})
@click.option('--debug', '-d', is_flag=True, default=False,
              help='Turn on debug logging for the bot.')
@click.option('--debug-irc', is_flag=True, default=False,
              help='Turn on debug logging for IRC client library.')
@click.option('--debug-asyncio', is_flag=True, default=False,
              help='Turn on debug logging for asyncio library.')
@click.option('--debug-all', is_flag=True, default=False,
              help='Turn on all debug logging.')
@click.option('--colour/--no-colour', 'colour_logging', default=None,
              help='Use colour in logging. [default: automatic]')
@click.option('--rollbar/--no-rollbar', 'use_rollbar', default=False,
              help='Enable Rollbar error reporting.')
@click.argument('config', type=click.File('r'))
def main(config, debug, debug_irc, debug_asyncio, debug_all, colour_logging, use_rollbar):
    """Run an IRC bot from a configuration file.
    """
    # Apply "debug all" option
    if debug_all:
        debug = debug_irc = debug_asyncio = True

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
            'asyncio': {
                # Default is WARNING because 'poll took x seconds' messages are annoying
                'level': 'DEBUG' if debug_asyncio else 'WARNING',
            },
        }
    })

    # Create and initialise the bot
    client = Bot(config)
    client.bot_setup()

    # Configure Rollbar for exception reporting
    if use_rollbar:
        rollbar.init(os.environ['ROLLBAR_ACCESS_TOKEN'],
                     os.environ.get('ROLLBAR_ENV', 'development'))
        def handler(loop, context):
            rollbar.report_exc_info()
            loop.default_exception_handler(context)
        client.loop.set_exception_handler(handler)

    # Run the client
    def stop():
        client.disconnect()
        client.loop.call_soon(client.loop.stop)
    client.loop.add_signal_handler(signal.SIGINT, stop)
    client.loop.run_until_complete(client.run())
    client.loop.close()

    # When the loop ends, run teardown
    client.bot_teardown()


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
