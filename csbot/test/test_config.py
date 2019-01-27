import pytest

from csbot.test import TempEnvVars
import csbot.plugin


class MockPlugin(csbot.plugin.Plugin):
    CONFIG_DEFAULTS = {
        'default': 'a default value',
        'env_and_default': 'default, not env',
    }

    CONFIG_ENVVARS = {
        'env_and_default': ['CSBOTTEST_ENV_AND_DEFAULT'],
        'env_only': ['CSBOTTEST_ENV_ONLY'],
        'multiple_env': ['CSBOTTEST_ENV_MULTI_1', 'CSBOTTEST_ENV_MULTI_2'],
    }


class MockBot(csbot.core.Bot):
    available_plugins = csbot.plugin.build_plugin_dict([MockPlugin])


base_config = """
[@mockbot]
plugins = mockplugin
"""

plugin_config = """
[mockplugin]
default = config1
env_and_default = config2
env_only = config3
"""


@pytest.mark.bot(cls=MockBot, config=base_config)
def test_without_plugin_section(bot_helper):
    bot = bot_helper.bot
    # Check the test plugin was loaded
    assert 'mockplugin' in bot.plugins
    plugin = bot.plugins['mockplugin']
    # Check than absent config options are properly absent
    with pytest.raises(KeyError):
        plugin.config_get('absent')
    # Check that default values work
    assert plugin.config_get('default') == 'a default value'
    # Check that environment variables work, if present
    with pytest.raises(KeyError):
        plugin.config_get('env_only')
    with TempEnvVars({'CSBOTTEST_ENV_ONLY': 'env value'}):
        assert plugin.config_get('env_only') == 'env value'
    # Check that environment variables override defaults
    assert plugin.config_get('env_and_default') == 'default, not env'
    with TempEnvVars({'CSBOTTEST_ENV_AND_DEFAULT': 'env, not default'}):
        assert plugin.config_get('env_and_default') == 'env, not default'
    # Check that environment variable order is obeyed
    with pytest.raises(KeyError):
        plugin.config_get('multiple_env')
    with TempEnvVars({'CSBOTTEST_ENV_MULTI_2': 'lowest priority'}):
        assert plugin.config_get('multiple_env') == 'lowest priority'
        with TempEnvVars({'CSBOTTEST_ENV_MULTI_1': 'highest priority'}):
            assert plugin.config_get('multiple_env') == 'highest priority'



@pytest.mark.bot(cls=MockBot, config=base_config + plugin_config)
def test_with_plugin_section(bot_helper):
    bot = bot_helper.bot
    assert 'mockplugin' in bot.plugins
    plugin = bot.plugins['mockplugin']
    # Check that values override defaults
    assert plugin.config_get('default') == 'config1'
    # Check that values override environment variables
    assert plugin.config_get('env_only') == 'config3'
    with TempEnvVars({'CSBOTTEST_ENV_ONLY': 'env value'}):
        assert plugin.config_get('env_only') == 'config3'
