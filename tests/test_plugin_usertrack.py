import pytest


@pytest.fixture
def irc_client(irc_client):
    irc_client.line_received(":server CAP self ACK :account-notify extended-join")
    return irc_client


@pytest.fixture
def bot_helper_class(bot_helper_class):
    class Helper(bot_helper_class):
        def assert_channels(self, nick, channels):
            assert self['usertrack'].get_user(nick)['channels'] == channels

        def assert_account(self, nick, account):
            assert self['usertrack'].get_user(nick)['account'] == account

    return Helper


pytestmark = [
    pytest.mark.bot(config="""\
        ["@bot"]
        plugins = ["usertrack"]
        """),
    pytest.mark.usefixtures("run_client"),
]


async def test_join_part(bot_helper):
    bot_helper.assert_channels('Nick', set())
    await bot_helper.client.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
    bot_helper.assert_channels('Nick', {'#channel'})

    bot_helper.assert_channels('Other', set())
    await bot_helper.client.line_received(":Other!~user@hostname JOIN #channel accountname :Other Info")
    bot_helper.assert_channels('Other', {'#channel'})

    await bot_helper.client.line_received(":Other!~user@hostname JOIN #other accountname :Other Info")
    bot_helper.assert_channels('Other', {'#channel', '#other'})
    bot_helper.assert_channels('Nick', {'#channel'})

    await bot_helper.client.line_received(":Other!~user@hostname PART #channel")
    bot_helper.assert_channels('Other', {'#other'})


async def test_join_names(bot_helper):
    bot_helper.assert_channels('Nick', set())
    bot_helper.assert_channels('Other', set())
    # Initialise "PREFIX" feature so "NAMES" support works correctly
    await bot_helper.client.line_received(":server 005 self PREFIX=(ov)@+ :are supported by this server")
    await bot_helper.client.line_received(":server 353 self @ #channel :Nick Other")
    await bot_helper.client.line_received(":server 366 self #channel :End of /NAMES list.")
    bot_helper.assert_channels('Nick', {'#channel'})
    bot_helper.assert_channels('Other', {'#channel'})


async def test_quit_channels(bot_helper):
    await bot_helper.client.line_received(":Nick!~user@hostname JOIN #channel * :Other Info")
    bot_helper.assert_channels('Nick', {'#channel'})
    await bot_helper.client.line_received(":Nick!~user@hostname QUIT :Quit message")
    bot_helper.assert_channels('Nick', set())


async def test_nick_changed(bot_helper):
    bot_helper.assert_channels('Nick', set())
    await bot_helper.client.line_received(":Nick!~user@hostname JOIN #channel * :Other Info")
    bot_helper.assert_channels('Nick', {'#channel'})
    bot_helper.assert_channels('Other', set())
    assert bot_helper['usertrack'].get_user('Nick')['nick'] == 'Nick'
    await bot_helper.client.line_received(':Nick!~user@hostname NICK :Other')
    bot_helper.assert_channels('Nick', set())
    bot_helper.assert_channels('Other', {'#channel'})
    assert bot_helper['usertrack'].get_user('Other')['nick'] == 'Other'


async def test_account_discovery_on_join(bot_helper):
    bot_helper.assert_account('Nick', None)
    # Check that account name is discovered from "extended join" information
    await bot_helper.client.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
    bot_helper.assert_account('Nick', 'accountname')
    # Check that * is interpreted as "not authenticated"
    await bot_helper.client.line_received(":Nick!~user@hostname JOIN #channel * :Other Info")
    bot_helper.assert_account('Nick', None)


async def test_account_forgotten_on_lost_visibility(bot_helper):
    # User joins channels, account discovered by extended-join
    bot_helper.assert_account('Nick', None)
    await bot_helper.client.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
    bot_helper.assert_account('Nick', 'accountname')
    await bot_helper.client.line_received(":Nick!~user@hostname JOIN #other accountname :Other Info")
    bot_helper.assert_channels('Nick', {'#channel', '#other'})
    # User leaves one channel, account should still be known because user is still visible
    await bot_helper.client.line_received(":Nick!~user@hostname PART #channel")
    bot_helper.assert_account('Nick', 'accountname')
    bot_helper.assert_channels('Nick', {'#other'})
    # User leaves last remaining channel, account should be forgotten
    await bot_helper.client.line_received(":Nick!~user@hostname PART #other")
    bot_helper.assert_account('Nick', None)


async def test_account_forgotten_on_quit(bot_helper):
    await bot_helper.client.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
    bot_helper.assert_account('Nick', 'accountname')
    await bot_helper.client.line_received(":Nick!~user@hostname QUIT :Quit message")
    bot_helper.assert_account('Nick', None)


async def test_account_notify(bot_helper):
    bot_helper.assert_account('Nick', None)
    bot_helper.assert_channels('Nick', set())
    await bot_helper.client.line_received(":Nick!~user@hostname JOIN #channel * :Other Info")
    bot_helper.assert_account('Nick', None)
    bot_helper.assert_channels('Nick', {'#channel'})
    await bot_helper.client.line_received(":Nick!~user@hostname ACCOUNT accountname")
    bot_helper.assert_account('Nick', 'accountname')
    bot_helper.assert_channels('Nick', {'#channel'})
    await bot_helper.client.line_received(":Nick!~user@hostname ACCOUNT *")
    bot_helper.assert_account('Nick', None)
    bot_helper.assert_channels('Nick', {'#channel'})


async def test_account_kept_on_nick_changed(bot_helper):
    bot_helper.assert_account('Nick', None)
    bot_helper.assert_account('Other', None)
    await bot_helper.client.line_received(":Nick!~user@hostname JOIN #channel accountname :Other Info")
    bot_helper.assert_account('Nick', 'accountname')
    bot_helper.assert_account('Other', None)
    await bot_helper.client.line_received(':Nick!~user@hostname NICK :Other')
    bot_helper.assert_account('Nick', None)
    bot_helper.assert_account('Other', 'accountname')
