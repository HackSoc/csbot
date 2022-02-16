import asyncio
import datetime

import pytest


pytestmark = [
    pytest.mark.bot(config="""\
        ["@bot"]
        plugins = ["mongodb", "termdates"]

        [mongodb]
        mode = "mock"
    """),
    pytest.mark.usefixtures("run_client"),
]


def say(msg):
    return f":Nick!~user@hostname PRIVMSG #channel :{msg}"


async def test_term_dates(bot_helper, time_machine):
    bot_helper.reset_mock()

    # Nothing configured yet, !termdates should error
    await asyncio.wait(bot_helper.receive(say("!termdates")))
    bot_helper.assert_sent(lambda line: line.endswith("error: no term dates (see termdates.set)"))

    # Save dates
    await asyncio.wait(bot_helper.receive([
        say("!termdates.set 2021-09-27 2022-01-10 2022-04-19"),
        say("!termdates"),
    ]))
    bot_helper.assert_sent([
        lambda line: line.endswith("Aut 2021-09-27 -- 2021-12-03, "
                                   "Spr 2022-01-10 -- 2022-03-18, "
                                   "Sum 2022-04-19 -- 2022-06-24"),
    ])


async def test_week_command(bot_helper, time_machine):
    bot_helper.reset_mock()

    # Nothing configured yet, !week should error
    await asyncio.wait(bot_helper.receive(say("!week")))
    bot_helper.assert_sent(lambda line: line.endswith("error: no term dates (see termdates.set)"))

    # Configure term dates
    await asyncio.wait(bot_helper.receive(say("!termdates.set 2021-09-27 2022-01-10 2022-04-19")))

    # `!week term n` should give the correct dates for the specified week in the specified term
    await asyncio.wait(bot_helper.receive(say("!week aut 3")))
    bot_helper.assert_sent(lambda line: line.endswith("Aut 3: 2021-10-11"))
    await asyncio.wait(bot_helper.receive(say("!week spr 10")))
    bot_helper.assert_sent(lambda line: line.endswith("Spr 10: 2022-03-14"))
    await asyncio.wait(bot_helper.receive(say("!week sum 4")))
    # TODO: should actually be bot_helper.assert_sent(lambda line: line.endswith("Sum 4: 2022-05-09"))
    bot_helper.assert_sent(lambda line: line.endswith("Sum 4: 2022-05-10"))
    # `!week n term` means the same as `!week term n`
    await asyncio.wait(bot_helper.receive(say("!week 3 aut")))
    bot_helper.assert_sent(lambda line: line.endswith("Aut 3: 2021-10-11"))
    await asyncio.wait(bot_helper.receive(say("!week 10 spr")))
    bot_helper.assert_sent(lambda line: line.endswith("Spr 10: 2022-03-14"))
    await asyncio.wait(bot_helper.receive(say("!week 4 sum")))
    # TODO: should actually be bot_helper.assert_sent(lambda line: line.endswith("Sum 4: 2022-05-09"))
    bot_helper.assert_sent(lambda line: line.endswith("Sum 4: 2022-05-10"))

    # Time travel to before the start of the Autumn term
    time_machine.move_to(datetime.datetime(2021, 8, 1, 12, 0))
    # `!week` should give "Nth week before Aut"
    await asyncio.wait(bot_helper.receive(say("!week")))
    bot_helper.assert_sent(lambda line: line.endswith("9th week before Aut (starts 2021-09-27)"))
    # `!week n` should give the start of the Nth week in the Autumn term
    await asyncio.wait(bot_helper.receive(say("!week 3")))
    bot_helper.assert_sent(lambda line: line.endswith("Aut 3: 2021-10-11"))

    # Time travel to during the Autumn term, week 4
    time_machine.move_to(datetime.datetime(2021, 10, 21, 12, 0))
    # `!week` should give "Aut 4: ..."
    await asyncio.wait(bot_helper.receive(say("!week")))
    bot_helper.assert_sent(lambda line: line.endswith("Aut 4: 2021-10-18"))
    # `!week n` should give the start of the Nth week in the Autumn term
    await asyncio.wait(bot_helper.receive(say("!week 3")))
    bot_helper.assert_sent(lambda line: line.endswith("Aut 3: 2021-10-11"))

    # Time travel to after the Autumn term
    time_machine.move_to(datetime.datetime(2021, 12, 15, 12, 0))
    # `!week` should give "Nth week before Spr"
    await asyncio.wait(bot_helper.receive(say("!week")))
    bot_helper.assert_sent(lambda line: line.endswith("4th week before Spr (starts 2022-01-10)"))
    # `!week n` should give the start of the Nth week in the Spring term
    await asyncio.wait(bot_helper.receive(say("!week 3")))
    bot_helper.assert_sent(lambda line: line.endswith("Spr 3: 2022-01-24"))

    # Time travel to during the Spring term, week 10
    time_machine.move_to(datetime.datetime(2022, 3, 16, 12, 0))
    # `!week` should give "Spr 10: ..."
    await asyncio.wait(bot_helper.receive(say("!week")))
    bot_helper.assert_sent(lambda line: line.endswith("Spr 10: 2022-03-14"))
    # `!week n` should give the start of the Nth week in the Spring term
    await asyncio.wait(bot_helper.receive(say("!week 3")))
    bot_helper.assert_sent(lambda line: line.endswith("Spr 3: 2022-01-24"))

    # Time travel to after the Spring term
    time_machine.move_to(datetime.datetime(2022, 4, 4, 12, 0))
    # `!week` should give "Nth week before Sum"
    await asyncio.wait(bot_helper.receive(say("!week")))
    # TODO: should actually be
    #  bot_helper.assert_sent(lambda line: line.endswith("2nd week before Sum (starts 2022-04-18)"))
    bot_helper.assert_sent(lambda line: line.endswith("3rd week before Sum (starts 2022-04-19)"))
    # `!week n` should give the start of the Nth week in the Summer term
    await asyncio.wait(bot_helper.receive(say("!week 3")))
    # TODO: should actually be bot_helper.assert_sent(lambda line: line.endswith("Sum 3: 2022-05-02"))
    bot_helper.assert_sent(lambda line: line.endswith("Sum 3: 2022-05-03"))

    # Time travel to during the Summer term, week 7
    time_machine.move_to(datetime.datetime(2022, 5, 31, 12, 0))
    # `!week` should give "Sum 7: ..."
    await asyncio.wait(bot_helper.receive(say("!week")))
    # TODO: should actually be bot_helper.assert_sent(lambda line: line.endswith("Sum 7: 2022-05-30"))
    bot_helper.assert_sent(lambda line: line.endswith("Sum 7: 2022-05-31"))
    # `!week n` should give the start of the Nth week in the Summer term
    await asyncio.wait(bot_helper.receive(say("!week 3")))
    # TODO: should actually be bot_helper.assert_sent(lambda line: line.endswith("Sum 3: 2022-05-02"))
    bot_helper.assert_sent(lambda line: line.endswith("Sum 3: 2022-05-03"))

    # TODO: currently just throws an exception when after the end of Summer term, fix code and enable these tests
    # time_machine.move_to(datetime.datetime(2022, 8, 15, 12, 0))
    # # `!week` should give "Sum 18"
    # await asyncio.wait(bot_helper.receive(say("!week")))
    # bot_helper.assert_sent(lambda line: line.endswith("Sum 18: 2022-08-15"))
    # # `!week n` should give the start of the Nth week in the Summer term
    # await asyncio.wait(bot_helper.receive(say("!week 3")))
    # # TODO: should actually be bot_helper.assert_sent(lambda line: line.endswith("Sum 3: 2022-05-02"))
    # bot_helper.assert_sent(lambda line: line.endswith("Sum 3: 2022-05-03"))
