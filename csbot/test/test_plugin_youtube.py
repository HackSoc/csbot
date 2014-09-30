import responses
import urllib.parse as urlparse
import requests

from . import BotTestCase, read_fixture_file


#: Tests are (number, url, content-type, status, fixture, expected)
json_test_cases = [
    # (These test case are copied from the actual URLs, without the lengthy transcripts)

    # "Normal"
    (
        "fItlK6L-khc",
        "https://gdata.youtube.com/feeds/api/videos/fItlK6L-khc?alt=json&v=2",
        "application/json; charset=utf-8",
        200,
        "youtube_fItlK6L-khc.json",
        {'link': 'http://youtu.be/fItlK6L-khc', 'uploader': 'BruceWillakers',
         'uploaded': '2014-08-29', 'views': '22,387', 'duration': '21:00',
         'likes': '+1,076/-11', 'title': 'Trouble In Terrorist Town | Hiding in Fire'}
    ),

    # Unicode
    (
        "vZ_YpOvRd3o",
        "https://gdata.youtube.com/feeds/api/videos/vZ_YpOvRd3o?alt=json&v=2",
        "application/json; charset=utf-8",
        200,
        "youtube_vZ_YpOvRd3o.json",
        {'title': "Oh! it's just me! / Фух! Это всего лишь я!", 'likes': '+4,267/-66',
         'duration': '00:24', 'uploader': 'ignoramusky', 'uploaded': '2014-08-26',
         'views': '807,645', 'link': 'http://youtu.be/vZ_YpOvRd3o'}
    ),

    # Broken
    (
        "flibble",
        "https://gdata.youtube.com/feeds/api/videos/flibble?alt=json&v=2",
        "application/vnd.google.gdata.error+xml",
        400,
        "empty_file",
        None
    ),

    # No id
    (
        "",
        "https://gdata.youtube.com/feeds/api/videos/?alt=json&v=2",
        "application/json; charset=utf-8",
        400,
        "empty_file",  # actually does have some data, but should never get this far
        None
    ),

    # Malformed json
    (
        "malformed_id",
        "https://gdata.youtube.com/feeds/api/videos/malformed_id?alt=json&v=2",
        "application/json; charset=utf-8",
        200,
        "youtube_malformed.json",
        {'title': 'N/A', 'uploaded': 'N/A', 'duration': 'N/A', 'likes': 'N/A',
         'link': 'http://youtu.be/malformed_id', 'uploader': 'N/A', 'views': 'N/A'}
    ),

    # Malformed json (missing ID)
    (
        "malformed_id2",
        "https://gdata.youtube.com/feeds/api/videos/malformed_id2?alt=json&v=2",
        "application/json; charset=utf-8",
        200,
        "youtube_malformed2.json",
        None
    )
]


class TestYoutubePlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = youtube
    """

    PLUGINS = ['youtube']

    @responses.activate
    def test_ids(self):
        for _, url, content_type, status, fixture, _ in json_test_cases:
            responses.add(responses.GET, url, body=read_fixture_file(fixture),
                          content_type=content_type, status=status,
                          match_querystring=True)

        for vid_id, _, _, _, _, expected in json_test_cases:
            with self.subTest(vid_id=vid_id):
                result = self.youtube._yt(urlparse.urlparse(vid_id))
                self.assertEqual(result, expected)


class TestYoutubeLinkInfoIntegration(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = linkinfo youtube
    """

    PLUGINS = ['linkinfo', 'youtube']
    def setUp(self):
        super(TestYoutubeLinkInfoIntegration, self).setUp()
        self.linkinfo.register_exclude(lambda url: url.netloc in {"m.youtube.com",
                                                                  "youtu.be",
                                                                  "www.youtube.com"})

    @responses.activate
    def test_integration(self):
        for _, url, content_type, status, fixture, _ in json_test_cases:
            responses.add(responses.GET, url, body=read_fixture_file(fixture),
                          content_type=content_type, status=status,
                          match_querystring=True)

        url_types = {"https://www.youtube.com/watch?v={}",
                     "http://m.youtube.com/details?v={}",
                     "https://www.youtube.com/v/{}",
                     "http://www.youtube.com/watch?v={}&feature=youtube_gdata_player",
                     "http://youtu.be/{}"}
        for vid_id, _, _, _, _, response in json_test_cases:
            for url in url_types:
                with self.subTest(vid_id=vid_id, url=url):
                    url = url.format(vid_id)
                    link_resp = self.linkinfo.get_link_info(url)
                    if link_resp is None:
                        break
                    _, _, linkinfo_title = link_resp
                    for key in response:
                        if key == "link":
                            continue
                        self.assertIn(response[key], linkinfo_title)
