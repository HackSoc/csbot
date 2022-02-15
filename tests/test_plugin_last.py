import asyncio

import pytest

from csbot.plugins.last import Last


pytestmark = [
    pytest.mark.bot(config="""\
        ["@bot"]
        plugins = ["mongodb", "last"]

        [mongodb]
        mode = "mock"
    """),
    pytest.mark.usefixtures("run_client"),
]


def diff_dict(actual: dict, expected: dict) -> dict:
    """Find items in *expected* that are different at the same keys in *actual*, returning a dict
    mapping the offending key to a dict with "expected" and "actual" items."""
    diff = dict()
    for k, v in expected.items():
        actual_value = actual.get(k)
        expected_value = expected.get(k)
        if actual_value != expected_value:
            diff[k] = dict(actual=actual_value, expected=expected_value)
    return diff


async def test_message_types(bot_helper):
    plugin: Last = bot_helper["last"]

    # Starting state: should have no "last message" for a user
    assert plugin.last("Nick") is None
    assert plugin.last_message("Nick") is None
    assert plugin.last_action("Nick") is None
    assert plugin.last_command("Nick") is None

    # Receive a PRIVMSG from the user
    await bot_helper.client.line_received(":Nick!~user@hostname PRIVMSG #channel :Example message")
    # Check that message was recorded correctly
    assert diff_dict(plugin.last("Nick"), {"nick": "Nick", "message": "Example message"}) == {}
    # Check that message was only recorded in the correct category
    assert plugin.last_message("Nick") == plugin.last("Nick")
    assert not plugin.last_action("Nick") == plugin.last("Nick")
    assert not plugin.last_command("Nick") == plugin.last("Nick")

    # Receive a CTCP ACTION from the user (inside a PRIVMSG)
    await bot_helper.client.line_received(":Nick!~user@hostname PRIVMSG #channel :\x01ACTION emotes\x01")
    # Check that message was recorded correctly
    assert diff_dict(plugin.last("Nick"), {"nick": "Nick", "message": "emotes"}) == {}
    # Check that message was only recorded in the correct category
    assert not plugin.last_message("Nick") == plugin.last("Nick")
    assert plugin.last_action("Nick") == plugin.last("Nick")
    assert not plugin.last_command("Nick") == plugin.last("Nick")

    # Receive a bot command from the user (inside a PRIVMSG)
    await bot_helper.client.line_received(":Nick!~user@hostname PRIVMSG #channel :!help")
    # Check that message was recorded correctly
    assert diff_dict(plugin.last("Nick"), {"nick": "Nick", "message": "!help"}) == {}
    # Check that message was only recorded in the correct category
    assert not plugin.last_message("Nick") == plugin.last("Nick")
    assert not plugin.last_action("Nick") == plugin.last("Nick")
    assert plugin.last_command("Nick") == plugin.last("Nick")

    # Final confirmation that the "message", "action" and "command" message types were all recorded separately
    assert diff_dict(plugin.last_message("Nick"), {"nick": "Nick", "message": "Example message"}) == {}
    assert diff_dict(plugin.last_action("Nick"), {"nick": "Nick", "message": "emotes"}) == {}
    assert diff_dict(plugin.last_command("Nick"), {"nick": "Nick", "message": "!help"}) == {}

    # Also there shouldn't be any records for a different nick
    assert plugin.last("OtherNick") is None


async def test_channel_filter(bot_helper):
    plugin: Last = bot_helper["last"]

    # Starting state: should have no "last message" for a user
    assert plugin.last("Nick") is None
    assert plugin.last("Nick", channel="#a") is None
    assert plugin.last("Nick", channel="#b") is None

    # Receive a PRIVMSG from the user in #a
    await bot_helper.client.line_received(":Nick!~user@hostname PRIVMSG #a :Message A")
    # Check that the message was recorded correctly
    assert diff_dict(plugin.last("Nick"), {"nick": "Nick", "channel": "#a", "message": "Message A"}) == {}
    # Check that channel filter applies correctly
    assert plugin.last("Nick", channel="#a") == plugin.last("Nick")
    assert not plugin.last("Nick", channel="#b") == plugin.last("Nick")

    # Receive a PRIVMSG from the user in #b
    await bot_helper.client.line_received(":Nick!~user@hostname PRIVMSG #b :Message B")
    # Check that the message was recorded correctly
    assert diff_dict(plugin.last("Nick"), {"nick": "Nick", "channel": "#b", "message": "Message B"}) == {}
    # Check that channel filter applies correctly
    assert not plugin.last("Nick", channel="#a") == plugin.last("Nick")
    assert plugin.last("Nick", channel="#b") == plugin.last("Nick")

    # Final confirmation that the latest message for each channel is stored
    assert diff_dict(plugin.last("Nick", channel="#a"), {"nick": "Nick", "channel": "#a", "message": "Message A"}) == {}
    assert diff_dict(plugin.last("Nick", channel="#b"), {"nick": "Nick", "channel": "#b", "message": "Message B"}) == {}

    # Also there shouldn't be any records for a different channel
    assert plugin.last("Nick", channel="#c") is None


async def test_seen_command(bot_helper):
    bot_helper.reset_mock()

    # !seen for a nick not yet seen
    await asyncio.wait(bot_helper.receive(":A!~user@hostname PRIVMSG #a :!seen B"))
    bot_helper.assert_sent("NOTICE #a :Nothing recorded for B")

    # !seen for a nick only seen in a different channel
    await asyncio.wait(bot_helper.receive(":B!~user@hostname PRIVMSG #b :First message"))
    await asyncio.wait(bot_helper.receive(":A!~user@hostname PRIVMSG #a :!seen B"))
    bot_helper.assert_sent("NOTICE #a :Nothing recorded for B")

    # !seen for nick seen in the same channel
    await asyncio.wait(bot_helper.receive(":A!~user@hostname PRIVMSG #b :!seen B"))
    bot_helper.assert_sent(lambda line: "<B> First message" in line)

    # Now seen in both channels, !seen should only return the message relating to the current channel
    await asyncio.wait(bot_helper.receive(":B!~user@hostname PRIVMSG #a :Second message"))
    await asyncio.wait(bot_helper.receive(":A!~user@hostname PRIVMSG #a :!seen B"))
    bot_helper.assert_sent(lambda line: "<B> Second message" in line)
    await asyncio.wait(bot_helper.receive(":A!~user@hostname PRIVMSG #b :!seen B"))
    bot_helper.assert_sent(lambda line: "<B> First message" in line)

    # !seen on own nick should get the !seen command itself (because it makes more sense than "Nothing recorded")
    await asyncio.wait(bot_helper.receive(":B!~user@hostname PRIVMSG #a :!seen B"))
    bot_helper.assert_sent(lambda line: "<B> !seen B" in line)

    # Check different formatting for actions
    await asyncio.wait(bot_helper.receive(":B!~user@hostname PRIVMSG #a :\x01ACTION does something\x01"))
    await asyncio.wait(bot_helper.receive(":A!~user@hostname PRIVMSG #a :!seen B"))
    bot_helper.assert_sent(lambda line: "* B does something" in line)

    # Error when bad message type is specified
    await asyncio.wait(bot_helper.receive(":A!~user@hostname PRIVMSG #a :!seen B foobar"))
    bot_helper.assert_sent("NOTICE #a :Bad filter: foobar. Accepted are \"message\", \"command\", and \"action\".")
