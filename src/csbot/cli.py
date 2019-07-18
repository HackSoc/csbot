import sys

import click

from .core import Bot
from .plugin import find_plugins


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
