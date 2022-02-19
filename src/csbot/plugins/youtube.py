import datetime
import urllib.parse as urlparse

import isodate
from aiogoogle import Aiogoogle, HTTPError

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

    Pass the :exc:`~apiclient.errors.HttpError` from the API call as an argument.
    """
    def __init__(self, http_error):
        super(YoutubeError, self).__init__(http_error)
        self.http_error = http_error

    def __str__(self):
        s = '%s: %s' % (self.http_error.res.status_code,
                        self.http_error.res.json['error']['message'])
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

    RESPONSE = '"{title}" [{duration}] (by {uploader} at {uploaded}) | Views: {views}'
    CMD_RESPONSE = RESPONSE + ' | {link}'

    async def get_video_json(self, id):
        async with Aiogoogle(api_key=self.config_get('api_key')) as aiogoogle:
            youtube_v3 = await aiogoogle.discover('youtube', 'v3')
            request = youtube_v3.videos.list(id=id, hl='en', part='snippet,contentDetails,statistics')
            response = await aiogoogle.as_api_key(request)
            if len(response['items']) == 0:
                return None
            else:
                return response['items'][0]

    async def _yt(self, url):
        """Builds a nicely formatted version of youtube's own internal JSON"""

        vid_id = get_yt_id(url)
        if not vid_id:
            return None
        try:
            json = await self.get_video_json(vid_id)
            if json is None:
                return None
        except (KeyError, ValueError):
            return None
        except HTTPError as e:
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
        except KeyError:
            vid_info["duration"] = "N/A"

        try:
            views = int(json["statistics"]["viewCount"])
            vid_info["views"] = "{:,}".format(views)
        except KeyError:
            vid_info["views"] = "N/A"

        return vid_info

    @Plugin.integrate_with('linkinfo')
    def linkinfo_integrate(self, linkinfo):
        """Handle recognised youtube urls."""

        async def page_handler(url, match):
            """Handles privmsg urls."""
            try:
                response = await self._yt(url)
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
    async def all_hail_our_google_overlords(self, e):
        """I for one, welcome our Google overlords."""

        try:
            response = await self._yt(urlparse.urlparse(e["data"]))
            if not response:
                e.reply("Invalid video ID")
            else:
                e.reply(self.CMD_RESPONSE.format(**response))
        except YoutubeError as exc:
            e.reply("Error: " + str(exc))
