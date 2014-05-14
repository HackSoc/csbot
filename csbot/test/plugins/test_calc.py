from ..helpers import BotTestCase


class TestCalcPlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = calc
    """

    PLUGINS = ['calc']

    def test_correct(self):
        self.assertEqual(self.calc._calc("2^6"), "4")
        self.assertEqual(self.calc._calc("2**6"), "64")
        self.assertEqual(self.calc._calc("1 + 2*3**(4^5) / (6 + -7)"), "-5.0")
        self.assertEqual(self.calc._calc(""),
                         "You want to calculate something? Type in an expression then, silly!")

    def test_error(self):
        self.assertEqual(self.calc._calc("999**999"), "Error, 999**999 is too big")
        self.assertEqual(self.calc._calc("1 / 0"), "Silly, you cannot divide by 0")
        self.assertEqual(self.calc._calc("pi + 3"), "No constants or variables allowed")
        self.assertEqual(self.calc._calc("1 + "), "Error, \"1 + \" is not a valid calculation")



