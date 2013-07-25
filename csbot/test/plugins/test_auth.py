from StringIO import StringIO

from twisted.trial import unittest


from csbot.core import Bot
from csbot.plugins.auth import Auth, PermissionDB


class TestPermissionDB(unittest.TestCase):
    def setUp(self):
        self.permissions = PermissionDB()

    def tearDown(self):
        self.permissions = None

    def test_channel_permissions(self):
        """Check that channel permissions are interpreted correctly."""
        self.permissions.process('User1', '#hello:world #foo:bar,baz *:topic #channel:*')
        self.assertEqual(self.permissions.get_permissions('User1'), {
            ('#hello', 'world'),
            ('#foo', 'bar'), ('#foo', 'baz'),
            ('*', 'topic'),
            ('#channel', '*'),
        })

    def test_invalid_channel_permissions(self):
        """Check that invalid channel permissions aren't accepted."""
        self.assertRaises(ValueError, self.permissions.process,
                          'User1', 'foo:bar')
        self.assertRaises(ValueError, self.permissions.process,
                          'User1', 'foo:')
        self.assertRaises(ValueError, self.permissions.process,
                          'User1', ':bar')
        self.assertRaises(ValueError, self.permissions.process,
                          'User1', ':')

    def test_bot_permissions(self):
        """Check that bot (non-channel) permissions are interpreted correctly."""
        self.permissions.process('User1', 'hello world *')
        self.assertEqual(self.permissions.get_permissions('User1'), {
            'hello', 'world', '*',
        })

    def test_group_permissions(self):
        """Check that permission groups result in users getting the correct permissions."""
        self.permissions.process('@group', '#foo:a,b #bar:* baz')
        self.permissions.process('User1', '@group')
        self.assertEqual(self.permissions.get_permissions('User1'), {
            ('#foo', 'a'), ('#foo', 'b'),
            ('#bar', '*'),
            'baz',
        })

    def test_undefined_group(self):
        """Check that undefined groups raise errors."""
        self.assertRaises(ValueError, self.permissions.process,
                          'User1', '@group')

    def test_recursive_group(self):
        """Check that a recursive group raises errors."""
        self.assertRaises(ValueError, self.permissions.process,
                          '@group', '@group')

    def test_redefined_group(self):
        """Check that redefined groups raise errors."""
        self.permissions.process('@group', 'foo')
        self.assertRaises(ValueError, self.permissions.process,
                          '@group', 'bar')

    def test_universal_permissions(self):
        """Check that users get permissions granted to everybody."""
        self.permissions.process('*', '#boring-channel:*')
        self.permissions.process('User1', '#other-channel:topic')
        self.assertEqual(self.permissions.get_permissions('User1'), {
            ('#boring-channel', '*'), ('#other-channel', 'topic'),
        })
        self.assertEqual(self.permissions.get_permissions(None), {
            ('#boring-channel', '*'),
        })
