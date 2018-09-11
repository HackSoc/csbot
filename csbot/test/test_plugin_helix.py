from csbot.test import BotTestCase


class TestHelixPlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = helix
    """

    PLUGINS = ['helix']

    def test_same_question(self):
        assert self.helix._answer('test') == self.helix._answer('test')

    def test_question_filtering(self):
        assert self.helix._answer('test') == self.helix._answer('t e s t ?')

        assert self.helix._answer('test') == self.helix._answer('TEST')

    def test_different_questions(self):
        # Maybe should randomify
        assert self.helix._answer('test1') == self.helix._answer('test2')
