from httpretty import httprettified, HTTPretty

from ..helpers import BotTestCase


#: Tests are (number, url, content-type, body, expected)
json_test_cases = [
    # (These test case are copied from the actual URLs, without the lengthy transcripts)

    # "Latest"
    (
        "0",  # 0 is latest
        "http://xkcd.com/info.0.json",
        "application/json; charset=utf-8",
        (b'{'
           b'"month": "7", '
           b'"num": 1399, '
           b'"link": "", '
           b'"year": "2014", '
           b'"news": "", '
           b'"safe_title": "Chaos", '
           b'"alt": "Although the oral exam for the doctorate was just \'can you do that weird laugh?\'", '
           b'"img": "http:\\/\\/imgs.xkcd.com\\/comics\\/chaos.png", '
           b'"title": "Chaos", '
           b'"day": "25"'
         b'}'
        ),
        'http://xkcd.com/1399 [Chaos - "Although the oral exam for the doctorate was just \'can you do that weird laugh?\'"]'
    ),

    # Normal
    (
        "1",
        "http://xkcd.com/1/info.0.json",
        "application/json; charset=utf-8",
        (b'{'
           b'"month": "1", '
           b'"num": 1, '
           b'"link": "", '
           b'"year": "2006", '
           b'"news": "", '
           b'"safe_title": "Barrel - Part 1", '
           b'"alt": "Don\'t we all.", '
           b'"img": "http:\\/\\/imgs.xkcd.com\\/comics\\/barrel_cropped_(1).jpg", '
           b'"title": "Barrel - Part 1", "day": "1"'
         b'}'),
        'http://xkcd.com/1 [Barrel - Part 1 - "Don\'t we all."]'
    ),

    # HTML Entities
    (
        "259",
        "http://xkcd.com/259/info.0.json",
        "application/json; charset=utf-8",
        (b'{'
           b'"month": "5", '
           b'"num": 259, '
           b'"link": "", '
           b'"year": "2007", '
           b'"news": "", '
           b'"safe_title": "Clichd Exchanges", '
           b'"alt": "It\'s like they say, you gotta fight fire with clich&eacute;s.", '
           b'"img": "http:\\/\\/imgs.xkcd.com\\/comics\\/cliched_exchanges.png", '
           b'"title": "Clich&eacute;d Exchanges", '
           b'"day": "9"'
         b'}'),
        'http://xkcd.com/259 [Clichéd Exchanges - "It\'s like they say, you gotta fight fire with clichés."]'
    ),

    # Unicode
    (
        "403",
        "http://xkcd.com/403/info.0.json",
        "application/json; charset=utf-8",
        (b'{'
           b'"month": "3", '
           b'"num": 403, '
           b'"link": "", '
           b'"year": "2008", '
           b'"news": "", '
           b'"safe_title": "Convincing Pickup Line", '
           b'"alt": "Check it out; I\'ve had sex with someone who\'s had sex with someone who\'s written a paper with Paul Erd\\u00c5\\u0091s!", '
           b'"img": "http:\\/\\/imgs.xkcd.com\\/comics\\/convincing_pickup_line.png", '
           b'"title": "Convincing Pickup Line", '
           b'"day": "31"'
         b'}'),
        'http://xkcd.com/403 [Convincing Pickup Line - "Check it out; I\'ve had sex with someone who\'s had sex with someone who\'s written a paper with Paul Erdős!"]'
    ),

    # Long alt text
    (
        "1363",
        "http://xkcd.com/1363/info.0.json",
        "application/json; charset=utf-8",
        (b'{'
           b'"month": "5", '
           b'"num": 1363, '
           b'"link": "", '
           b'"year": "2014", '
           b'"news": "", '
           b'"safe_title": "xkcd Phone", '
           b'"alt": "Presented in partnership with Qualcomm, Craigslist, Whirlpool, Hostess, LifeStyles, and the US Chamber of Commerce. Manufactured on equipment which also processes peanuts. Price includes 2-year Knicks contract. Phone may extinguish nearby birthday candles. If phone ships with Siri, return immediately; do not speak to her and ignore any instructions she gives. Do not remove lead casing. Phone may attract\\/trap insects; this is normal. Volume adjustable (requires root). If you experience sudden tingling, nausea, or vomiting, perform a factory reset immediately. Do not submerge in water; phone will drown. Exterior may be frictionless. Prolonged use can cause mood swings, short-term memory loss, and seizures. Avert eyes while replacing battery. Under certain circumstances, wireless transmitter may control God.", '
           b'"img": "http:\\/\\/imgs.xkcd.com\\/comics\\/xkcd_phone.png", '
           b'"title": "xkcd Phone", '
           b'"day": "2"'
         b'}'),
        'http://xkcd.com/1363 [xkcd Phone - "Presented in partnership with Qualcomm, Craigslist, Whirlpool, Hostess, LifeStyles, and the US Chamber of Commerce. M..."]'
    )
]


class TestXKCDPlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = xkcd
    """

    PLUGINS = ['xkcd']

    @httprettified
    def test_correct(self):
        for _, url, content_type, body, _ in json_test_cases:
            HTTPretty.register_uri(HTTPretty.GET, url, body=body,
                                   content_type=content_type)

        for num, url, _, _, expected in json_test_cases:
            with self.subTest(url=url):
                result = self.xkcd._xkcd(num)
                self.assertEqual(result, expected, url)

    @httprettified
    def test_error(self):
        # Still need to overrride the "latest" and the 404 page
        _, url, content_type, body, _ = json_test_cases[0]
        HTTPretty.register_uri(HTTPretty.GET, url, body=body,
                               content_type=content_type)
        HTTPretty.register_uri(HTTPretty.GET, "http://xkcd.com/404/info.0.json",
                               body="404 - Not Found",
                               content_type="text/html", status=404)

        self.assertEqual(self.xkcd._xkcd("flibble"), "Invalid comic number")
        self.assertEqual(self.xkcd._xkcd("404"), "So. It has come to this")  # Missing comic
        self.assertEqual(self.xkcd._xkcd("-5"),
                         "Comic #-5 is invalid. The latest is #1399")
        self.assertEqual(self.xkcd._xkcd("1000000"),
                         "Comic #1000000 is invalid. The latest is #1399")  # Testing "latest"


