import sys

import click

from . import config
from .core import Bot
from .plugin import build_config_cls


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def util():
    pass


@util.command(help="Generate example configuration file")
def generate_config():
    cls = build_config_cls(Bot.available_plugins.values())
    generator = config.TomlExampleGenerator()
    generator.generate(cls, sys.stdout)
