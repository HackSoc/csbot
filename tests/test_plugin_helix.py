import pytest


pytestmark = pytest.mark.bot(config="""\
    [@bot]
    plugins = helix
    """)


def test_same_question(bot_helper):
    assert bot_helper['helix']._answer('test') == bot_helper['helix']._answer('test')


def test_question_filtering(bot_helper):
    assert bot_helper['helix']._answer('test') == bot_helper['helix']._answer('t e s t ?')

    assert bot_helper['helix']._answer('test') == bot_helper['helix']._answer('TEST')


def test_different_questions(bot_helper):
    # Maybe should randomify
    assert bot_helper['helix']._answer('test1') == bot_helper['helix']._answer('test2')
