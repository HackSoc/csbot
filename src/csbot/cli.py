import sys

import click

from . import config
from .core import Bot
from .plugin import find_plugins


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def util():
    pass


@util.command(help="List available plugins")
def list_plugins():
    for P in find_plugins():
        sys.stdout.write(f"{P.plugin_name():<20}  ({P.__module__}.{P.__name__})\n")


@util.command(help="Generate example configuration file")
def example_config():
    plugins = [Bot]
    plugins.extend(find_plugins())
    generator = config.TomlExampleGenerator()
    for P in plugins:
        cls = getattr(P, 'Config', None)
        if config.is_structure(cls):
            generator.generate(cls, sys.stdout, prefix=[P.plugin_name()])
            sys.stdout.write("\n\n")
