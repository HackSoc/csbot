import unittest

from csbot.plugins.example import EmptyPlugin


class TestEmptyPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = EmptyPlugin(None)

    def test_plugin_name(self):
        self.assertEquals(self.plugin.plugin_name(), 'example.EmptyPlugin')
