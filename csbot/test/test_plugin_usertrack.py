from csbot.test import BotTestCase, run_client


class TestUserTrackPlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = usertrack
    """

    PLUGINS = ['usertrack']

    def setUp(self):
        super().setUp()
        # Enable client capabilities that the tests rely upon
        self.client.line_received(":server CAP self ACK :account-notify extended-join")

    def _assert_channels(self, nick, channels):
        self.assertEqual(self.usertrack.get_user(nick)['channels'], channels)

    def _assert_account(self, nick, account):
        self.assertEqual(self.usertrack.get_user(nick)['account'], account)

    @run_client
    def test_join_part(self):
        self._assert_channels('Nick', set())
        self.client.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
        yield
        self._assert_channels('Nick', {'#channel'})

        self._assert_channels('Other', set())
        self.client.line_received(":Other!~user@hostname JOIN #channel accountname :Other Info")
        yield
        self._assert_channels('Other', {'#channel'})

        self.client.line_received(":Other!~user@hostname JOIN #other accountname :Other Info")
        yield
        self._assert_channels('Other', {'#channel', '#other'})
        self._assert_channels('Nick', {'#channel'})

        self.client.line_received(":Other!~user@hostname PART #channel")
        yield
        self._assert_channels('Other', {'#other'})

    @run_client
    def test_join_names(self):
        self._assert_channels('Nick', set())
        self._assert_channels('Other', set())
        # Initialise "PREFIX" feature so "NAMES" support works correctly
        self.client.line_received(":server 005 self PREFIX=(ov)@+ :are supported by this server")
        self.client.line_received(":server 353 self @ #channel :Nick Other")
        self.client.line_received(":server 366 self #channel :End of /NAMES list.")
        yield
        self._assert_channels('Nick', {'#channel'})
        self._assert_channels('Other', {'#channel'})

    @run_client
    def test_quit_channels(self):
        self.client.line_received(":Nick!~user@hostname JOIN #channel * :Other Info")
        yield
        self._assert_channels('Nick', {'#channel'})
        self.client.line_received(":Nick!~user@hostname QUIT :Quit message")
        yield
        self._assert_channels('Nick', set())

    @run_client
    def test_nick_changed(self):
        self._assert_channels('Nick', set())
        self.client.line_received(":Nick!~user@hostname JOIN #channel * :Other Info")
        yield
        self._assert_channels('Nick', {'#channel'})
        self._assert_channels('Other', set())
        self.assertEqual(self.usertrack.get_user('Nick')['nick'], 'Nick')
        self.client.line_received(':Nick!~user@hostname NICK :Other')
        yield
        self._assert_channels('Nick', set())
        self._assert_channels('Other', {'#channel'})
        self.assertEqual(self.usertrack.get_user('Other')['nick'], 'Other')

    @run_client
    def test_account_discovery_on_join(self):
        self._assert_account('Nick', None)
        # Check that account name is discovered from "extended join" information
        self.client.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
        yield
        self._assert_account('Nick', 'accountname')
        # Check that * is interpreted as "not authenticated"
        self.client.line_received(":Nick!~user@hostname JOIN #channel * :Other Info")
        yield
        self._assert_account('Nick', None)

    @run_client
    def test_account_forgotten_on_lost_visibility(self):
        # User joins channels, account discovered by extended-join
        self._assert_account('Nick', None)
        self.client.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
        yield
        self._assert_account('Nick', 'accountname')
        self.client.line_received(":Nick!~user@hostname JOIN #other accountname :Other Info")
        yield
        self._assert_channels('Nick', {'#channel', '#other'})
        # User leaves one channel, account should still be known because user is still visible
        self.client.line_received(":Nick!~user@hostname PART #channel")
        yield
        self._assert_account('Nick', 'accountname')
        self._assert_channels('Nick', {'#other'})
        # User leaves last remaining channel, account should be forgotten
        self.client.line_received(":Nick!~user@hostname PART #other")
        yield
        self._assert_account('Nick', None)

    @run_client
    def test_account_forgotten_on_quit(self):
        self.client.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
        yield
        self._assert_account('Nick', 'accountname')
        self.client.line_received(":Nick!~user@hostname QUIT :Quit message")
        yield
        self._assert_account('Nick', None)

    @run_client
    def test_account_notify(self):
        self._assert_account('Nick', None)
        self._assert_channels('Nick', set())
        self.client.line_received(":Nick!~user@hostname JOIN #channel * :Other Info")
        yield
        self._assert_account('Nick', None)
        self._assert_channels('Nick', {'#channel'})
        self.client.line_received(":Nick!~user@hostname ACCOUNT accountname")
        yield
        self._assert_account('Nick', 'accountname')
        self._assert_channels('Nick', {'#channel'})
        self.client.line_received(":Nick!~user@hostname ACCOUNT *")
        yield
        self._assert_account('Nick', None)
        self._assert_channels('Nick', {'#channel'})

    @run_client
    def test_account_kept_on_nick_changed(self):
        self._assert_account('Nick', None)
        self._assert_account('Other', None)
        self.client.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
        yield
        self._assert_account('Nick', 'accountname')
        self._assert_account('Other', None)
        self.client.line_received(':Nick!~user@hostname NICK :Other')
        yield
        self._assert_account('Nick', None)
        self._assert_account('Other', 'accountname')
