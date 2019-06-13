import re

import pytest
import urllib.parse as urlparse

from . import read_fixture_file
from csbot.plugins.youtube import YoutubeError


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


@pytest.fixture
def pre_irc_client(aioresponses):
    # Use fixture JSON for API client setup
    aioresponses.get('https://www.googleapis.com/discovery/v1/apis/youtube/v3/rest',
                     status=200, content_type='application/json',
                     body=read_fixture_file('google-discovery-youtube-v3.json'),
                     repeat=True)


@pytest.mark.bot(config="""\
    ["@bot"]
    plugins = "youtube"

    [youtube]
    api_key = "abc"
    """)
class TestYoutubePlugin:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("vid_id, status, fixture, expected", json_test_cases)
    async def test_ids(self, bot_helper, aioresponses, vid_id, status, fixture, expected):
        pattern = re.compile(rf'https://www.googleapis.com/youtube/v3/videos\?.*\bid={vid_id}\b.*')
        aioresponses.get(pattern, status=status, content_type='application/json',
                         body=read_fixture_file(fixture))

        if expected is YoutubeError:
            with pytest.raises(YoutubeError):
                await bot_helper['youtube']._yt(urlparse.urlparse(vid_id))
        else:
            assert await bot_helper['youtube']._yt(urlparse.urlparse(vid_id)) == expected


@pytest.mark.bot(config="""\
    ["@bot"]
    plugins = "linkinfo youtube"

    [youtube]
    api_key = "abc"
    """)
class TestYoutubeLinkInfoIntegration:
    @pytest.fixture
    def bot_helper(self, bot_helper):
        # Make sure URLs don't try to fall back to the default handler
        bot_helper['linkinfo'].register_exclude(
            lambda url: url.netloc in {
                "m.youtube.com",
                "youtu.be",
                "www.youtube.com",
            })
        return bot_helper

    @pytest.mark.asyncio
    @pytest.mark.parametrize("vid_id, status, fixture, response", json_test_cases)
    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v={}",
        "http://m.youtube.com/details?v={}",
        "https://www.youtube.com/v/{}",
        "http://www.youtube.com/watch?v={}&feature=youtube_gdata_player",
        "http://youtu.be/{}",
    ])
    async def test_integration(self, bot_helper, aioresponses, vid_id, status, fixture, response, url):
        pattern = re.compile(rf'https://www.googleapis.com/youtube/v3/videos\?.*\bid={vid_id}\b.*')
        aioresponses.get(pattern, status=status, content_type='application/json',
                         body=read_fixture_file(fixture))

        url = url.format(vid_id)
        result = await bot_helper['linkinfo'].get_link_info(url)
        if response is None or response is YoutubeError:
            assert result.is_error
        else:
            for key in response:
                if key == "link":
                    continue
                assert response[key] in result.text
