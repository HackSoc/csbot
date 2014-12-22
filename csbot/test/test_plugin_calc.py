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
        self.assertEqual(self.calc._calc("2 << 31 << 31 << 31"), "19807040628566084398385987584")
        self.assertEqual(self.calc._calc("sin(5)"), "-0.9589242746631385")
        self.assertEqual(self.calc._calc("factorial(factorial(4))"), "620448401733239439360000")

    def test_error(self):
        self.assertEqual(self.calc._calc("9999**9999"), "Error, 9999**9999 would take too long to calculate")
        self.assertEqual(self.calc._calc("1 / 0"), "Error, division by zero")
        self.assertEqual(self.calc._calc("1 + "), "Error, '1 + ' is not a valid calculation")
        self.assertEqual(self.calc._calc("e = 1"), "Error, 'e = 1' is not a valid calculation")
        self.assertEqual(self.calc._calc("sgdsdg + 3"), "Error, unknown or invalid value 'sgdsdg'")
        self.assertEqual(self.calc._calc("1 << (1 << (1 << 10))"), "Error, result is too long to be printed")
        self.assertEqual(self.calc._calc("5 in 5"), "Error, invalid operator 'in'")
        self.assertEqual(self.calc._calc("429496729 << 1000"), "Error, result is too long to be printed")
        self.assertEqual(self.calc._calc("factorial(101)"), "Error, factorial(101) is too large to calculate")
        self.assertEqual(self.calc._calc("2**(2 << 512)"), "Error, result is too long to be printed")
        self.assertEqual(self.calc._calc("factorial(ceil)"), "Error, unorderable types: builtin_function_or_method() > int()")
        self.assertEqual(self.calc._calc("factorial(1, 2)"), "Error, limited_factorial() takes 1 positional argument but 2 were given")

