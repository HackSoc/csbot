from . import BotTestCase


class TestUserTrackPlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = usertrack
    """

    PLUGINS = ['usertrack']

    def setUp(self):
        super().setUp()
        # Enable client capabilities that the tests rely upon
        self.protocol_.line_received(":server CAP self ACK :account-notify extended-join")

    def _assert_channels(self, nick, channels):
        self.assertEqual(self.usertrack.get_user(nick)['channels'], channels)

    def _assert_account(self, nick, account):
        self.assertEqual(self.usertrack.get_user(nick)['account'], account)

    def test_join_part(self):
        self._assert_channels('Nick', set())
        self.protocol_.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
        self._assert_channels('Nick', {'#channel'})

        self._assert_channels('Other', set())
        self.protocol_.line_received(":Other!~user@hostname JOIN #channel accountname :Other Info")
        self._assert_channels('Other', {'#channel'})

        self.protocol_.line_received(":Other!~user@hostname JOIN #other accountname :Other Info")
        self._assert_channels('Other', {'#channel', '#other'})
        self._assert_channels('Nick', {'#channel'})

        self.protocol_.line_received(":Other!~user@hostname PART #channel")
        self._assert_channels('Other', {'#other'})

    def test_join_names(self):
        self._assert_channels('Nick', set())
        self._assert_channels('Other', set())
        # Initialise "PREFIX" feature so "NAMES" support works correctly
        self.protocol_.line_received(":server 005 self PREFIX=(ov)@+ :are supported by this server")
        self.protocol_.line_received(":server 353 self @ #channel :Nick Other")
        self.protocol_.line_received(":server 366 self #channel :End of /NAMES list.")
        self._assert_channels('Nick', {'#channel'})
        self._assert_channels('Other', {'#channel'})

    def test_quit_channels(self):
        self.protocol_.line_received(":Nick!~user@hostname JOIN #channel * :Other Info")
        self._assert_channels('Nick', {'#channel'})
        self.protocol_.line_received(":Nick!~user@hostname QUIT :Quit message")
        self._assert_channels('Nick', set())

    def test_nick_changed(self):
        self._assert_channels('Nick', set())
        self.protocol_.line_received(":Nick!~user@hostname JOIN #channel * :Other Info")
        self._assert_channels('Nick', {'#channel'})
        self._assert_channels('Other', set())
        self.assertEqual(self.usertrack.get_user('Nick')['nick'], 'Nick')
        self.protocol_.line_received(':Nick!~user@hostname NICK :Other')
        self._assert_channels('Nick', set())
        self._assert_channels('Other', {'#channel'})
        self.assertEqual(self.usertrack.get_user('Other')['nick'], 'Other')

    def test_account_discovery_on_join(self):
        self._assert_account('Nick', None)
        # Check that account name is discovered from "extended join" information
        self.protocol_.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
        self._assert_account('Nick', 'accountname')
        # Check that * is interpreted as "not authenticated"
        self.protocol_.line_received(":Nick!~user@hostname JOIN #channel * :Other Info")
        self._assert_account('Nick', None)

    def test_account_forgotten_on_lost_visibility(self):
        # User joins channels, account discovered by extended-join
        self._assert_account('Nick', None)
        self.protocol_.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
        self._assert_account('Nick', 'accountname')
        self.protocol_.line_received(":Nick!~user@hostname JOIN #other accountname :Other Info")
        self._assert_channels('Nick', {'#channel', '#other'})
        # User leaves one channel, account should still be known because user is still visible
        self.protocol_.line_received(":Nick!~user@hostname PART #channel")
        self._assert_account('Nick', 'accountname')
        self._assert_channels('Nick', {'#other'})
        # User leaves last remaining channel, account should be forgotten
        self.protocol_.line_received(":Nick!~user@hostname PART #other")
        self._assert_account('Nick', None)

    def test_account_forgotten_on_quit(self):
        self.protocol_.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
        self._assert_account('Nick', 'accountname')
        self.protocol_.line_received(":Nick!~user@hostname QUIT :Quit message")
        self._assert_account('Nick', None)

    def test_account_notify(self):
        self._assert_account('Nick', None)
        self._assert_channels('Nick', set())
        self.protocol_.line_received(":Nick!~user@hostname JOIN #channel * :Other Info")
        self._assert_account('Nick', None)
        self._assert_channels('Nick', {'#channel'})
        self.protocol_.line_received(":Nick!~user@hostname ACCOUNT accountname")
        self._assert_account('Nick', 'accountname')
        self._assert_channels('Nick', {'#channel'})
        self.protocol_.line_received(":Nick!~user@hostname ACCOUNT *")
        self._assert_account('Nick', None)
        self._assert_channels('Nick', {'#channel'})

    def test_account_kept_on_nick_changed(self):
        self._assert_account('Nick', None)
        self._assert_account('Other', None)
        self.protocol_.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
        self._assert_account('Nick', 'accountname')
        self._assert_account('Other', None)
        self.protocol_.line_received(':Nick!~user@hostname NICK :Other')
        self._assert_account('Nick', None)
        self._assert_account('Other', 'accountname')
