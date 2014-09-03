from httpretty import httprettified, HTTPretty

from . import BotTestCase, read_fixture_file


#: Tests are (number, url, content-type, fixture, expected)
json_test_cases = [
    # (These test case are copied from the actual URLs, without the lengthy transcripts)

    # "Normal"
    (
        "fItlK6L-khc",
        "https://gdata.youtube.com/feeds/api/videos/fItlK6L-khc?alt=json&v=2",
        "application/json; charset=utf-8",
        "youtube_fItlK6L-khc.json",
        ''
    ),

    # Unicode
    (
        "vZ_YpOvRd3o",
        "https://gdata.youtube.com/feeds/api/videos/vZ_YpOvRd3o?alt=json&v=2",
        "application/json; charset=utf-8",
        "youtube_vZ_YpOvRd3o.json",
        ''
    ),

    # Broken
    (
        "flibble",
        "https://gdata.youtube.com/feeds/api/videos/flibble?alt=json&v=2",
        "application/vnd.google.gdata.error+xml",
        "empty_file",
        ""
    ),

    # No id
    (
        "",
        "https://gdata.youtube.com/feeds/api/videos/?alt=json&v=2",
        "application/json; charset=utf-8",
        "empty_file",  # actually does have some data, but should never get this far
        ""
    )
]



class TestYoutubePlugin(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = youtube
    """

    PLUGINS = ['youtube']

    @httprettified
    def test_ids(self):
        for _, url, content_type, fixture, _ in json_test_cases:
            HTTPretty.register_uri(HTTPretty.GET, url,
                                   body=read_fixture_file(fixture),
                                   content_type=content_type)

        for vid_id, url, _, _, expected in json_test_cases:
            with self.subTest(vid_id=vid_id):
                result = self.youtube._yt(vid_id)
                self.assertEqual(result, expected)


class TestYoutubeLinkInfoIntegration(BotTestCase):
    CONFIG = """\
    [@bot]
    plugins = linkinfo youtube
    """

    PLUGINS = ['linkinfo', 'youtube']

    @httprettified
    def test_integration(self):
        for _, url, content_type, fixture, _ in json_test_cases:
            HTTPretty.register_uri(HTTPretty.GET, url,
                                   body=read_fixture_file(fixture),
                                   content_type=content_type)

        url_types = {"https://www.youtube.com/watch?v={}",
                     "http://m.youtube.com/details?v={}",
                     "https://www.youtube.com/v/{}",
                     "http://www.youtube.com/watch?v={}&feature=youtube_gdata_player",
                     "http://youtu.be/{}"}
        for vid_id, _, _, _, response in json_test_cases:
            for url in url_types:
                with self.subTest(vid_id=vid_id, url=url):
                    url = url.format(vid_id)
                    _, _, linkinfo_title = self.linkinfo.get_link_info(url)
                    for key in response:
                        self.assertIn(response[key], linkinfo_title)
