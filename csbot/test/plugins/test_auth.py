import unittest

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

    def test_check_exact_channel_permission(self):
        """Check that exact channel permission checks work."""
        self.permissions.process('User1', '#channel:foo')
        self.assertTrue(self.permissions.check('User1', 'foo', '#channel'))
        self.assertFalse(self.permissions.check('User1', 'foo', '#other-channel'))
        self.assertFalse(self.permissions.check('User1', 'bar', '#channel'))
        self.assertFalse(self.permissions.check('User2', 'foo', '#channel'))
        # Ensure channel and bot permissions are not confused
        self.assertFalse(self.permissions.check('User1', 'foo'))

    def test_check_exact_bot_permission(self):
        """Check that exact bot permission checks work."""
        self.permissions.process('User1', 'foo')
        self.assertTrue(self.permissions.check('User1', 'foo'))
        self.assertFalse(self.permissions.check('User1', 'bar'))
        self.assertFalse(self.permissions.check('User2', 'foo'))
        # Ensure channel and bot permissions are not confused
        self.assertFalse(self.permissions.check('User1', 'foo', '#channel'))

    def test_check_wildcard_channel_permission(self):
        """Check that wildcard channel permissions work."""
        self.permissions.process('User1', '#channel:*')
        self.permissions.process('User2', '*:foo')
        self.permissions.process('User3', '*:*')
        # Test permission wildcard with fixed channel
        self.assertTrue(self.permissions.check('User1', 'foo', '#channel'))
        self.assertTrue(self.permissions.check('User1', 'bar', '#channel'))
        self.assertFalse(self.permissions.check('User1', 'foo', '#other'))
        # Test channel wildcard with fixed permission
        self.assertTrue(self.permissions.check('User2', 'foo', '#channel'))
        self.assertTrue(self.permissions.check('User2', 'foo', '#other'))
        self.assertFalse(self.permissions.check('User2', 'bar', '#channel'))
        # Test channel and permission wildcard
        self.assertTrue(self.permissions.check('User3', 'foo', '#other'))
        self.assertTrue(self.permissions.check('User3', 'bar', '#channel'))
        # Ensure channel and bot permissions are not confused
        self.assertFalse(self.permissions.check('User1', 'foo'))
        self.assertFalse(self.permissions.check('User2', 'foo'))
        self.assertFalse(self.permissions.check('User3', 'foo'))

    def test_check_wildcard_bot_permission(self):
        """Check that wildcard bot permissions work."""
        self.permissions.process('User1', '*')
        self.assertTrue(self.permissions.check('User1', 'foo'))
        self.assertTrue(self.permissions.check('User1', 'bar'))
        self.assertFalse(self.permissions.check('User2', 'foo'))
        # Ensure channel and bot permissions are not confused
        self.assertFalse(self.permissions.check('User1', 'foo', '#channel'))
