from ..helpers import BotTestCase


class TestXKCDPlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = xkcd
    """

    PLUGINS = ['xkcd']

    def test_correct(self):
        self.assertEqual(self.xkcd._xkcd("1"), "http://xkcd.com/1 [Barrel - Part 1 - \"Don't we all.\"]")
        self.assertEqual(self.xkcd._xkcd("403"),
                         "http://xkcd.com/403 [Convincing Pickup Line - \"Check it out; I've had sex with someone who's had sex with someone who's written a paper with Paul Erdős!\"]")  # Unicode
        self.assertEqual(self.xkcd._xkcd("1363"),
                         "http://xkcd.com/1363 [xkcd Phone - \"Presented in partnership with Qualcomm, Craigslist, Whirlpool, Hostess, LifeStyles, and the US Chamber of Commerce. M...\"]")  # A long alt-text

    def test_error(self):
        self.assertEqual(self.xkcd._xkcd("flibble"), "Invalid comic number")
        self.assertEqual(self.xkcd._xkcd("404"), "So. It has come to this")  # Missing comic
        self.assertEqual(self.xkcd._xkcd("-5"), "Invalid comic number")
        self.assertEqual(self.xkcd._xkcd("1000000"),
                         "Comic #1000000 is invalid. The latest is #{}".format(self.xkcd.get_info()))


