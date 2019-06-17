import sys

import click

from .core import Bot


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def util():
    pass


@util.command(help="List available plugins")
def list_plugins():
    for P in sorted(Bot.available_plugins.values(), key=lambda P: P.plugin_name()):
        sys.stdout.write(f"{P.plugin_name():<20}  ({P.__module__}.{P.__name__})\n")


@util.command(help="Generate example configuration file")
@click.option("--commented/--uncommented", "commented", default=False,
              help="Comment out all generated configuration")
def example_config(commented):
    Bot.write_example_config(sys.stdout, commented)
