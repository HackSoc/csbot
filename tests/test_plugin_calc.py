import pytest


pytestmark = pytest.mark.bot(config="""\
    ["@bot"]
    plugins = ["calc"]
    """)


def test_correct(bot_helper):
    calc = bot_helper['calc']
    assert calc._calc("2^6") == "4"
    assert calc._calc("2**6") == "64"
    assert calc._calc("1 + 2*3**(4^5) / (6 + -7)") == "-5.0"
    assert calc._calc("~5") == "-6"
    assert calc._calc("pi + 3") == "6.141592653589793"
    assert calc._calc("") == "You want to calculate something? Type in an expression then!"
    assert calc._calc("N") == "6.0221412927e+23"
    assert calc._calc("3 + π") == "6.141592653589793"  # Also tests unicode
    assert calc._calc("3 < 5") == "True"
    assert calc._calc("3 < 5 <= 7") == "True"
    assert calc._calc("456 == 1") == "False"
    assert calc._calc("True ^ True") == "False"
    assert calc._calc("True + 1") == "2"
    assert calc._calc("~True") == "-2"
    assert calc._calc("2 << 31 << 31 << 31") == "19807040628566084398385987584"
    assert calc._calc("sin(5)") == "-0.9589242746631385"
    assert calc._calc("factorial(factorial(4))") == "620448401733239439360000"


def test_error(bot_helper):
    calc = bot_helper['calc']
    assert calc._calc("9999**9999") == "Error, would take too long to calculate"
    assert calc._calc("1 / 0") == "Error, division by zero"
    assert calc._calc("1 % 0") == "Error, division by zero"
    assert calc._calc("1 // 0") == "Error, division by zero"
    assert calc._calc("1 + ") == "Error, invalid syntax"
    assert calc._calc("e = 1") == "Error, invalid calculation"
    assert calc._calc("sgdsdg + 3") == "Error, unknown constant or function"
    assert calc._calc("2.0 << 2.0") == "Error, non-integer shift values"
    assert calc._calc("2.0 >> 2.0") == "Error, non-integer shift values"
    assert calc._calc("1 << (1 << (1 << 10))") == "Error, would take too long to calculate"
    assert calc._calc("5 in 5") == "Error, invalid operator"
    assert calc._calc("429496729 << 1000") == "Error, result too long to be printed"
    assert calc._calc("factorial(101)") == "Error, would take too long to calculate"
    assert calc._calc("2**(2 << 512)") == "Error, would take too long to calculate"
    assert calc._calc("factorial(ceil)") == "Error, invalid arguments"
    assert calc._calc("factorial(1 == 2)"), "Error, invalid arguments"
    assert calc._calc("(lambda x: x)(1)") == "Error, invalid calculation"
    assert calc._calc("10.0**1000") == "Error, too large to represent as float"
    assert calc._calc("'B' > 'H'") == "Error, invalid argument"
    assert calc._calc("e ^ pi") == "Error, invalid arguments"
    assert calc._calc("factorial(-42)") == "Error, factorial() not defined for negative values"
    assert calc._calc("factorial(4.2)") == "Error, factorial() only accepts integral values"
    assert calc._calc("not await 1").startswith("Error,")   # ast SyntaxError in Python 3.6 but not 3.7
    assert calc._calc("(" * 200 + ")" * 200) == "Error, unable to parse"
    assert calc._calc("1@2") == "Error, invalid operator"
