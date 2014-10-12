import responses
from unittest.mock import patch

from . import BotTestCase, read_fixture_file


#: Tests are (number, url, content-type, fixture, expected)
json_test_cases = [
    # (These test case are copied from the actual URLs, without the lengthy transcripts)

    # "Latest"
    (
        "0",  # 0 is latest
        "http://xkcd.com/info.0.json",
        "application/json; charset=utf-8",
        'xkcd_1399.json',
        ('http://xkcd.com/1399', 'Chaos', 'Although the oral exam for the doctorate was just \'can you do that weird laugh?\'')
    ),

    # Normal
    (
        "1",
        "http://xkcd.com/1/info.0.json",
        "application/json; charset=utf-8",
        'xkcd_1.json',
        ('http://xkcd.com/1', 'Barrel - Part 1', 'Don\'t we all.')
    ),

    # HTML Entities
    (
        "259",
        "http://xkcd.com/259/info.0.json",
        "application/json; charset=utf-8",
        'xkcd_259.json',
        ('http://xkcd.com/259', 'Clichéd Exchanges', 'It\'s like they say, you gotta fight fire with clichés.')
    ),

    # Unicode
    (
        "403",
        "http://xkcd.com/403/info.0.json",
        "application/json; charset=utf-8",
        'xkcd_403.json',
        ('http://xkcd.com/403', 'Convincing Pickup Line', 'Check it out; I\'ve had sex with someone who\'s had sex with someone who\'s written a paper with Paul Erdős!')
    ),

    # Long alt text
    (
        "1363",
        "http://xkcd.com/1363/info.0.json",
        "application/json; charset=utf-8",
        'xkcd_1363.json',
        ('http://xkcd.com/1363', 'xkcd Phone', 'Presented in partnership with Qualcomm, Craigslist, Whirlpool, Hostess, LifeStyles, and the US Chamber of Commerce. M...')
    )
]


class TestXKCDPlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = xkcd
    """

    PLUGINS = ['xkcd']

    @responses.activate
    def test_correct(self):
        for _, url, content_type, fixture, _ in json_test_cases:
            responses.add(responses.GET, url, body=read_fixture_file(fixture),
                          content_type=content_type)

        for num, url, _, _, expected in json_test_cases:
            with self.subTest(url=url):
                result = self.xkcd._xkcd(num)
                self.assertEqual(result, expected, url)

        # Also test the empty string
        self.assertEqual(self.xkcd._xkcd(""), json_test_cases[0][4])

        # !xkcd 221
        with patch("random.randint", return_value=1):
            self.assertEqual(self.xkcd._xkcd("rand"), json_test_cases[1][4])

    @responses.activate
    def test_error(self):
        _, url, content_type, fixture, _ = json_test_cases[0]  # Latest
        # Test if the comics are unavailable by making the latest return a 404
        responses.add(responses.GET, url, body="404 - Not Found",
                      content_type="text/html", status=404)
        self.assertRaises(self.xkcd.XKCDError, self.xkcd._xkcd, "")
        responses.reset()

        # Now override the actual 404 page and the latest "properly"
        responses.add(responses.GET, url, body=read_fixture_file(fixture),
                      content_type=content_type)
        responses.add(responses.GET, "http://xkcd.com/404/info.0.json",
                      body="404 - Not Found", content_type="text/html",
                      status=404)

        self.assertRaises(self.xkcd.XKCDError, self.xkcd._xkcd, "flibble")
        self.assertRaises(self.xkcd.XKCDError, self.xkcd._xkcd, "404")  # Missing comic
        self.assertRaises(self.xkcd.XKCDError, self.xkcd._xkcd, "-5")
        self.assertRaises(self.xkcd.XKCDError, self.xkcd._xkcd, "1000000")  # Testing "latest"


class TestXKCDLinkInfoIntegration(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = linkinfo xkcd
    """

    PLUGINS = ['linkinfo', 'xkcd']

    @responses.activate
    def test_integration(self):
        for _, url, content_type, fixture, _ in json_test_cases:
            responses.add(responses.GET, url, body=read_fixture_file(fixture),
                          content_type=content_type)

        for num, _, _, _, (_, title, alt) in json_test_cases:
            with self.subTest(num=num):
                url = 'http://xkcd.com/{}'.format(num)
                result = self.linkinfo.get_link_info(url)
                self.assertIn(title, result.text)
                self.assertIn(alt, result.text)

        # Error case
        result = self.linkinfo.get_link_info("http://xkcd.com/flibble")
        self.assertTrue(result.is_error)
