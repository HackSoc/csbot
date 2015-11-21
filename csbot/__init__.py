import docopt
import textwrap
import sys
import logging
import signal
import os

import rollbar

from .core import Bot, BotClient


def main(argv=None):
    """
    Run an IRC bot from a configuration file.

    Usage: csbot [options] <config>

    Options:
      -h, --help        Show this help.
      -d, --debug       Turn on debug logging for the bot.
      --debug-irc       Turn on debug logging for IRC client library.
      --debug-asyncio   Turn on debug logging for asyncio library.
      --debug-all       Turn on all debug logging.
      --colour          Force use of color in logging (automatic in a TTY).
      --no-colour       Don't use color in logging.
      --rollbar         Enable Rollbar error reporting
    """
    argv = argv or sys.argv[1:]
    args = docopt.docopt(textwrap.dedent(main.__doc__), argv)

    # Apply "debug all" option
    if args['--debug-all']:
        for k in ('--debug', '--debug-irc', '--debug-asyncio'):
            args[k] = True

    # See if logging colour should be forced on/off
    colour_logging = None
    if args['--colour']:
        colour_logging = True
    elif args['--no-colour']:
        colour_logging = False

    # Create and attach logging handler
    handler = PrettyStreamHandler(colour=colour_logging)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
        '[%(asctime)s] (%(levelname).1s:%(name)s) %(message)s',
        '%Y/%m/%d %H:%M:%S'))
    rootlogger = logging.getLogger('')
    rootlogger.addHandler(handler)

    # Set logging level for the bot
    rootlogger.setLevel(logging.DEBUG if args['--debug'] else logging.INFO)
    # Set logging level for IRCClient
    logging.getLogger('csbot.irc').setLevel(
        logging.DEBUG if args['--debug-irc'] else logging.INFO)
    # Set logging level for asyncio - default is WARNING because "poll took x
    # seconds" messages are annoying
    logging.getLogger('asyncio').setLevel(
        logging.DEBUG if args['--debug-asyncio'] else logging.WARNING)

    # Create and initialise the bot
    with open(args['<config>'], 'r') as f:
        bot = Bot(f)
    bot.bot_setup()

    # Create the bot client
    client = BotClient(bot)

    # Configure Rollbar for exception reporting
    if args['--rollbar']:
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
    bot.bot_teardown()


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
