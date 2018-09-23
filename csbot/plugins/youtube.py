import datetime
import urllib.parse as urlparse

from apiclient.discovery import build as google_api
from apiclient.errors import HttpError
import isodate

from ..plugin import Plugin
from .linkinfo import LinkInfoResult


def get_yt_id(url):
    """Gets the video ID from a urllib ParseResult object."""
    if url.netloc == "":
        # Must have been passed the video id
        return url.geturl()
    elif url.netloc == "youtu.be":
        return url.path.strip('/')
    elif "/v/" in url.path:
        # Unusual youtube.com/v/<id> fullscreen urls
        return url.path.split('/')[-1]
    elif "details" in url.path or "watch" in url.path:
        # Must be a 'v' parameter
        params = urlparse.parse_qs(url.query)
        if 'v' in params:
            return params['v'][0]
    return None


class YoutubeError(Exception):
    """Signifies some error occurred accessing the Youtube API.

    This is only used for actual errors, e.g. invalid API key, not failure to
    find any data matching a query.

    Pass the :exc:`HttpError` from the API call as an argument.
    """
    def __init__(self, http_error):
        super(YoutubeError, self).__init__(http_error)
        self.http_error = http_error

    def __str__(self):
        s = '%s: %s' % (self.http_error.resp.status, self.http_error._get_reason())
        if self.http_error.resp.status == 400:
            return s + ' - invalid API key?'
        else:
            return s


class Youtube(Plugin):
    """A plugin that does some youtube things.
    Based on williebot youtube plugin.
    """
    CONFIG_DEFAULTS = {
        'api_key': '',
    }

    CONFIG_ENVVARS = {
        'api_key': ['YOUTUBE_DATA_API_KEY'],
    }

    RESPONSE = '"{title}" [{duration}] (by {uploader} at {uploaded}) | Views: {views} [{likes}]'
    CMD_RESPONSE = RESPONSE + ' | {link}'

    #: Hook for mocking HTTP responses to Google API client
    http = None

    def setup(self):
        super().setup()
        self.client = google_api('youtube',  'v3', developerKey=self.config_get('api_key'), http=self.http)

    def get_video_json(self, id):
        response = self.client.videos().list(id=id, hl='en', part='snippet,contentDetails,statistics').execute(http=self.http)
        if len(response['items']) == 0:
            return None
        else:
            return response['items'][0]

    def _yt(self, url):
        """Builds a nicely formatted version of youtube's own internal JSON"""

        vid_id = get_yt_id(url)
        if not vid_id:
            return None
        try:
            json = self.get_video_json(vid_id)
            if json is None:
                return None
        except (KeyError, ValueError):
            return None
        except HttpError as e:
            # Chain our own exception that gets a more sanitised error message
            raise YoutubeError(e) from e

        vid_info = {}
        try:
            # Last part of the ID format is the actual ID
            vid_id = json["id"]
            vid_info["link"] = "http://youtu.be/" + vid_id
        except KeyError:
            # No point getting any more info if we don't have a valid link
            return None

        try:
            if json["snippet"]["localized"]:
                vid_info["title"] = json["snippet"]["localized"]["title"]
            else:
                vid_info["title"] = json["snippet"]["title"]
        except KeyError:
            vid_info["title"] = "N/A"

        try:
            vid_info["uploader"] = json["snippet"]["channelTitle"]
        except KeyError:
            vid_info["uploader"] = "N/A"

        try:
            dt = isodate.parse_datetime(json["snippet"]["publishedAt"])
            vid_info["uploaded"] = dt.strftime("%Y-%m-%d")
        except KeyError:
            vid_info["uploaded"] = "N/A"

        try:
            duration = isodate.parse_duration(json["contentDetails"]["duration"])
            if duration == datetime.timedelta():
                vid_info["duration"] = "LIVE"
            else:
                vid_info["duration"] = str(duration)
                if vid_info["duration"].startswith('0:'):
                    vid_info["duration"] = vid_info["duration"][2:]
        except KeyError as ex:
            vid_info["duration"] = "N/A"

        try:
            views = int(json["statistics"]["viewCount"])
            vid_info["views"] = "{:,}".format(views)
        except KeyError:
            vid_info["views"] = "N/A"

        try:
            likes = int(json["statistics"]["likeCount"])
            dislikes = int(json["statistics"]["dislikeCount"])
            vid_info["likes"] = "+{:,}/-{:,}".format(likes, dislikes)
        except KeyError:
            vid_info["likes"] = "N/A"

        return vid_info

    @Plugin.integrate_with('linkinfo')
    def linkinfo_integrate(self, linkinfo):
        """Handle recognised youtube urls."""

        def page_handler(url, match):
            """Handles privmsg urls."""
            try:
                response = self._yt(url)
                if response:
                    return LinkInfoResult(url.geturl(), self.RESPONSE.format(**response))
                else:
                    return None
            except YoutubeError as e:
                return LinkInfoResult(url.geturl(), str(e), is_error=True)

        linkinfo.register_handler(lambda url: url.netloc in {"m.youtube.com", "www.youtube.com", "youtu.be"},
                                  page_handler)


    @Plugin.command('youtube')
    @Plugin.command('yt')
    def all_hail_our_google_overlords(self, e):
        """I for one, welcome our Google overlords."""

        try:
            response = self._yt(urlparse.urlparse(e["data"]))
            if not response:
                e.reply("Invalid video ID")
            else:
                e.reply(self.CMD_RESPONSE.format(**response))
        except YoutubeError as exc:
            e.reply("Error: " + str(exc))
