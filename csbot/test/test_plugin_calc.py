from csbot.test import BotTestCase


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
        self.assertEqual(self.calc._calc("2 << 31 << 31 << 31"), "19807040628566084398385987584")
        self.assertEqual(self.calc._calc("sin(5)"), "-0.9589242746631385")
        self.assertEqual(self.calc._calc("factorial(factorial(4))"), "620448401733239439360000")

    def test_error(self):
        self.assertEqual(self.calc._calc("9999**9999"), "Error, would take too long to calculate")
        self.assertEqual(self.calc._calc("1 / 0"), "Error, division by zero")
        self.assertEqual(self.calc._calc("1 % 0"), "Error, division by zero")
        self.assertEqual(self.calc._calc("1 // 0"), "Error, division by zero")
        self.assertEqual(self.calc._calc("1 + "), "Error, invalid syntax (<unknown>, line 1)")
        self.assertEqual(self.calc._calc("e = 1"), "Error, invalid calculation")
        self.assertEqual(self.calc._calc("sgdsdg + 3"), "Error, unknown constant or function")
        self.assertEqual(self.calc._calc("2.0 << 2.0"), "Error, non-integer shift values")
        self.assertEqual(self.calc._calc("2.0 >> 2.0"), "Error, non-integer shift values")
        self.assertEqual(self.calc._calc("1 << (1 << (1 << 10))"), "Error, would take too long to calculate")
        self.assertEqual(self.calc._calc("5 in 5"), "Error, invalid operator")
        self.assertEqual(self.calc._calc("429496729 << 1000"), "Error, result too long to be printed")
        self.assertEqual(self.calc._calc("factorial(101)"), "Error, would take too long to calculate")
        self.assertEqual(self.calc._calc("2**(2 << 512)"), "Error, would take too long to calculate")
        self.assertEqual(self.calc._calc("factorial(ceil)"), "Error, invalid arguments")
        self.assertEqual(self.calc._calc("factorial(1, 2)"), "Error, invalid arguments")
        self.assertEqual(self.calc._calc("(lambda x: x)(1)"), "Error, unknown constant or function")
        self.assertEqual(self.calc._calc("10.0**1000"), "Error, too large to represent as float")
        self.assertEqual(self.calc._calc("'B' > 'H'"), "Error, invalid argument")
        self.assertEqual(self.calc._calc("e ^ pi"), "Error, invalid arguments")
        self.assertEqual(self.calc._calc("factorial(-42)"), "Error, factorial() not defined for negative values")
        self.assertEqual(self.calc._calc("factorial(4.2)"), "Error, factorial() only accepts integral values")
