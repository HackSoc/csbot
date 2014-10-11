from . import BotTestCase


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
        self.assertEqual(self.calc._calc("~5"), "-6")
        self.assertEqual(self.calc._calc("pi + 3"), "6.141592653589793")
        self.assertEqual(self.calc._calc(""),
                         "You want to calculate something? Type in an expression then!"),
        self.assertEqual(self.calc._calc("N"), "6.0221412927e+23")
        self.assertEqual(self.calc._calc("3 + π"), "6.141592653589793")  # Also tests unicode
        self.assertEqual(self.calc._calc("3 < 5"), "True")
        self.assertEqual(self.calc._calc("3 < 5 <= 7"), "True")
        self.assertEqual(self.calc._calc("456 == 1"), "False")
        self.assertEqual(self.calc._calc("True ^ True"), "False")
        self.assertEqual(self.calc._calc("True + 1"), "2")
        self.assertEqual(self.calc._calc("~True"), "-2")

    def test_error(self):
        self.assertEqual(self.calc._calc("9999**9999"), "Error, 9999**9999 is too big")
        self.assertEqual(self.calc._calc("1 / 0"), "Error, division by zero")
        self.assertEqual(self.calc._calc("1 + "), "Error, '1 + ' is not a valid calculation")
        self.assertEqual(self.calc._calc("e = 1"), "Error, 'e = 1' is not a valid calculation")
        self.assertEqual(self.calc._calc("sgdsdg + 3"), "Error, unknown or invalid constant 'sgdsdg'")
        self.assertEqual(self.calc._calc("1 << (1 << (1 << 10))"), "Error, cannot use bitshifting")
        self.assertEqual(self.calc._calc("5 in 5"), "Error, invalid operator 'in'")
        self.assertEqual(self.calc._calc("sin(5)"), "Error, 'sin(5)' is not a valid calculation")

