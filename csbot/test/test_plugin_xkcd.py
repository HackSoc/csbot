from unittest.mock import patch

import pytest

from csbot.test import BotTestCase, read_fixture_file


#: Tests are (number, url, content-type, fixture, expected)
json_test_cases = [
    # (These test case are copied from the actual URLs, without the lengthy transcripts)

    # "Latest"
    (
        "0",  # 0 is latest
        "http://xkcd.com/info.0.json",
        "application/json; charset=utf-8",
        'xkcd_latest.json',
        ('http://xkcd.com/99999', 'Chaos', 'Although the oral exam for the doctorate was just \'can you do that weird laugh?\'')
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
    ),

    # No alt text
    (
        "1506",
        "http://xkcd.com/1506/info.0.json",
        "application/json; charset=utf-8",
        'xkcd_1506.json',
        ('http://xkcd.com/1506', 'xkcloud', '')
    )
]


class TestXKCDPlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = xkcd
    """

    PLUGINS = ['xkcd']

    @pytest.fixture
    def populate_responses(self, responses):
        """Populate all data into responses, don't assert that every request is fired."""
        responses.assert_all_requests_are_fired = False
        for num, url, content_type, fixture, expected in json_test_cases:
            responses.add(responses.GET, url, body=read_fixture_file(fixture),
                          content_type=content_type)

    @pytest.mark.usefixtures("populate_responses")
    @pytest.mark.parametrize("num, url, content_type, fixture, expected", json_test_cases,
                             ids=[_[1] for _ in json_test_cases])
    def test_correct(self, num, url, content_type, fixture, expected):
        result = self.xkcd._xkcd(num)
        assert result == expected

    @pytest.mark.usefixtures("populate_responses")
    def test_latest_success(self):
        # Also test the empty string
        num, url, content_type, fixture, expected = json_test_cases[0]
        assert self.xkcd._xkcd("") == expected

    @pytest.mark.usefixtures("populate_responses")
    def test_random(self):
        # !xkcd 221
        num, url, content_type, fixture, expected = json_test_cases[1]
        with patch("random.randint", return_value=1):
            assert self.xkcd._xkcd("rand") == expected

    def test_error(self, responses):
        num, url, content_type, fixture, _ = json_test_cases[0]  # Latest
        # Test if the comics are unavailable by making the latest return a 404
        responses.add(responses.GET, url, body="404 - Not Found",
                      content_type="text/html", status=404)
        with pytest.raises(self.xkcd.XKCDError):
            self.xkcd._xkcd("")
        responses.reset()

        # Now override the actual 404 page and the latest "properly"
        responses.add(responses.GET, url, body=read_fixture_file(fixture),
                      content_type=content_type)
        responses.add(responses.GET, "http://xkcd.com/404/info.0.json",
                      body="404 - Not Found", content_type="text/html",
                      status=404)

        error_cases = [
            "flibble",
            "404",      # Missing comic
            "-5",
            "1000000",  # Testing "latest"
        ]

        for case in error_cases:
            with pytest.raises(self.xkcd.XKCDError):
                self.xkcd._xkcd(case)


class TestXKCDLinkInfoIntegration(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = linkinfo xkcd
    """

    PLUGINS = ['linkinfo', 'xkcd']

    @pytest.fixture
    def populate_responses(self, responses):
        """Populate all data into responses, don't assert that every request is fired."""
        responses.assert_all_requests_are_fired = False
        for num, url, content_type, fixture, expected in json_test_cases:
            responses.add(responses.GET, url, body=read_fixture_file(fixture),
                          content_type=content_type)

    @pytest.mark.usefixtures("populate_responses")
    @pytest.mark.parametrize("num, url, content_type, fixture, expected", json_test_cases,
                             ids=[_[1] for _ in json_test_cases])
    def test_integration(self, num, url, content_type, fixture, expected):
        _, title, alt = expected
        url = 'http://xkcd.com/{}'.format(num)
        result = self.linkinfo.get_link_info(url)
        assert title in result.text
        assert alt in result.text

    @pytest.mark.usefixtures("populate_responses")
    def test_integration_error(self):
        # Error case
        result = self.linkinfo.get_link_info("http://xkcd.com/flibble")
        assert result.is_error
