from unittest.mock import patch
from distutils.version import StrictVersion

import pytest
import responses
import urllib.parse as urlparse
import apiclient
from apiclient.http import HttpMock

from csbot.test import BotTestCase, fixture_file
from csbot.plugins.youtube import Youtube, YoutubeError


#: Tests are (number, url, content-type, status, fixture, expected)
json_test_cases = [
    # (These test case are copied from the actual URLs, without the lengthy transcripts)

    # "Normal"
    (
        "fItlK6L-khc",
        200,
        "youtube_fItlK6L-khc.json",
        {'link': 'http://youtu.be/fItlK6L-khc', 'uploader': 'BruceWillakers',
         'uploaded': '2014-08-29', 'views': '28,843', 'duration': '21:00',
         'likes': '+1,192/-13', 'title': 'Trouble In Terrorist Town | Hiding in Fire'}
    ),

    # Unicode
    (
        "vZ_YpOvRd3o",
        200,
        "youtube_vZ_YpOvRd3o.json",
        {'title': "Oh! it's just me! / Фух! Это всего лишь я!", 'likes': '+12,571/-155',
         'duration': '00:24', 'uploader': 'ignoramusky', 'uploaded': '2014-08-26',
         'views': '6,054,406', 'link': 'http://youtu.be/vZ_YpOvRd3o'}
    ),

    # LIVE stream
    (
        "sw4hmqVPe0E",
        200,
        "youtube_sw4hmqVPe0E.json",
        {'title': "Sky News Live", 'likes': '+2,195/-586',
         'duration': 'LIVE', 'uploader': 'Sky News', 'uploaded': '2015-03-24',
         'views': '2,271,999', 'link': 'http://youtu.be/sw4hmqVPe0E'}
    ),

    # Localized title
    (
        "539OnO-YImk",
        200,
        "youtube_539OnO-YImk.json",
        {'title': 'sharpest Underwear kitchen knife in the world', 'likes': '+52,212/-2,209',
         'duration': '12:24', 'uploader': '圧倒的不審者の極み!', 'uploaded': '2018-07-14',
         'views': '2,710,723', 'link': 'http://youtu.be/539OnO-YImk'}
    ),

    # Non-existent ID
    (
        "flibble",
        200,
        "youtube_flibble.json",
        None
    ),
]

# Non-success HttpMock results are broken in older versions of google-api-python-client
if StrictVersion(apiclient.__version__) > StrictVersion("1.4.1"):
    json_test_cases += [
        # Invalid API key (400 Bad Request)
        (
            "dQw4w9WgXcQ",
            400,
            "youtube_invalid_key.json",
            YoutubeError
        ),

        # Valid API key, but Youtube Data API not enabled (403 Forbidden)
        (
            "dQw4w9WgXcQ",
            403,
            "youtube_access_not_configured.json",
            YoutubeError
        ),
    ]


class TestYoutubePlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = youtube
    """

    PLUGINS = ['youtube']

    @pytest.fixture(autouse=True)
    def pre_irc_client(self):
        # Use fixture JSON for API client setup
        http = HttpMock(fixture_file('google-discovery-youtube-v3.json'),
                        {'status': '200'})
        with patch.object(Youtube, 'http', wraps=http):
            yield

    @pytest.mark.parametrize("vid_id, status, fixture, expected", json_test_cases)
    def test_ids(self, vid_id, status, fixture, expected):
        http = HttpMock(fixture_file(fixture), {'status': status})
        with patch.object(self.youtube, 'http', wraps=http):
            if expected is YoutubeError:
                with pytest.raises(YoutubeError):
                    self.youtube._yt(urlparse.urlparse(vid_id))
            else:
                assert self.youtube._yt(urlparse.urlparse(vid_id)) == expected


class TestYoutubeLinkInfoIntegration(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = linkinfo youtube
    """

    PLUGINS = ['linkinfo', 'youtube']

    @pytest.fixture(autouse=True)
    def pre_irc_client(self):
        # Use fixture JSON for API client setup
        http = HttpMock(fixture_file('google-discovery-youtube-v3.json'),
                        {'status': '200'})
        with patch.object(Youtube, 'http', wraps=http):
            yield

    @pytest.fixture(autouse=True)
    def extra_bot_setup(self, bot_setup):
        # Make sure URLs don't try to fall back to the default handler
        self.linkinfo.register_exclude(lambda url: url.netloc in {"m.youtube.com",
                                                                  "youtu.be",
                                                                  "www.youtube.com"})

    @pytest.mark.parametrize("vid_id, status, fixture, response", json_test_cases)
    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v={}",
        "http://m.youtube.com/details?v={}",
        "https://www.youtube.com/v/{}",
        "http://www.youtube.com/watch?v={}&feature=youtube_gdata_player",
        "http://youtu.be/{}",
    ])
    def test_integration(self, vid_id, status, fixture, response, url):
        http = HttpMock(fixture_file(fixture), {'status': status})
        with patch.object(self.youtube, 'http', wraps=http):
            url = url.format(vid_id)
            result = self.linkinfo.get_link_info(url)
            if response is None or response is YoutubeError:
                assert result.is_error
            else:
                for key in response:
                    if key == "link":
                        continue
                    assert response[key] in result.text
