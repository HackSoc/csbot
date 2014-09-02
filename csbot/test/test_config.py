import unittest
from io import StringIO

from . import TempEnvVars
import csbot.core
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


class TestPluginConfig(unittest.TestCase):
    def test_without_plugin_section(self):
        bot = MockBot(StringIO(base_config))
        # Check the test plugin was loaded
        self.assertTrue('mockplugin' in bot.plugins)
        plugin = bot.plugins['mockplugin']
        # Check than absent config options are properly absent
        self.assertRaises(KeyError, plugin.config_get, 'absent')
        # Check that default values work
        self.assertEqual(plugin.config_get('default'), 'a default value')
        # Check that environment variables work, if present
        self.assertRaises(KeyError, plugin.config_get, 'env_only')
        with TempEnvVars({'CSBOTTEST_ENV_ONLY': 'env value'}):
            self.assertEqual(plugin.config_get('env_only'), 'env value')
        # Check that environment variables override defaults
        self.assertEqual(plugin.config_get('env_and_default'),
                         'default, not env')
        with TempEnvVars({'CSBOTTEST_ENV_AND_DEFAULT': 'env, not default'}):
            self.assertEqual(plugin.config_get('env_and_default'),
                             'env, not default')
        # Check that environment variable order is obeyed
        self.assertRaises(KeyError, plugin.config_get, 'multiple_env')
        with TempEnvVars({'CSBOTTEST_ENV_MULTI_2': 'lowest priority'}):
            self.assertEqual(plugin.config_get('multiple_env'),
                             'lowest priority')
            with TempEnvVars({'CSBOTTEST_ENV_MULTI_1': 'highest priority'}):
                self.assertEqual(plugin.config_get('multiple_env'),
                                 'highest priority')

    def test_with_plugin_section(self):
        bot = MockBot(StringIO(base_config + plugin_config))
        self.assertTrue('mockplugin' in bot.plugins)
        plugin = bot.plugins['mockplugin']
        # Check that values override defaults
        self.assertEqual(plugin.config_get('default'), 'config1')
        # Check that values override environment variables
        self.assertEqual(plugin.config_get('env_only'), 'config3')
        with TempEnvVars({'CSBOTTEST_ENV_ONLY': 'env value'}):
            self.assertEqual(plugin.config_get('env_only'), 'config3')
