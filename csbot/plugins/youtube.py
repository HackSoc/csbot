import json
import requests
from datetime import datetime
import urllib.parse as urlparse

from ..plugin import Plugin
from ..util import simple_http_get, cap_string
from .linkinfo import LinkInfoResult


def get_yt_json(vid_id):
    """Gets the (vaguely) relevant parts of the raw json from youtube.
    """

    # v=2 needed for like count
    url = "https://gdata.youtube.com/feeds/api/videos/{}?alt=json&v=2".format(vid_id)
    httpdata = simple_http_get(url)
    if httpdata.status_code != requests.codes.ok:
        return None

    return httpdata.json()["entry"]


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


class Youtube(Plugin):
    """A plugin that does some youtube things.
    Based on williebot youtube plugin.
    """
    RESPONSE = '"{title}" [{duration}] (by {uploader} at {uploaded}) | Views: {views} [{likes}]'
    CMD_RESPONSE = RESPONSE + ' | {link}'

    def _yt(self, url):
        """Builds a nicely formatted version of youtube's own internal JSON"""

        vid_id = get_yt_id(url)
        if not vid_id:
            return None
        try:
            json = get_yt_json(vid_id)
            if json is None:
                return None
        except (KeyError, ValueError):
            return None

        vid_info = {}
        try:
            # Last part of the ID format is the actual ID
            vid_id = json["id"]["$t"].split(':')[-1]
            vid_info["link"] = "http://youtu.be/" + vid_id
        except KeyError:
            # No point getting any more info if we don't have a valid link
            return None

        try:
            vid_info["title"] = json["title"]["$t"]
        except KeyError:
            vid_info["title"] = "N/A"

        try:
            vid_info["uploader"] = json["author"][0]["name"]["$t"]
        except KeyError:
            vid_info["uploader"] = "N/A"

        try:
            dt = datetime.strptime(json["published"]["$t"], "%Y-%m-%dT%H:%M:%S.%fZ")
            vid_info["uploaded"] = dt.strftime("%Y-%m-%d")
        except KeyError:
            vid_info["uploaded"] = "N/A"

        try:
            vid_secs = int(json["media$group"]["yt$duration"]["seconds"])
            vid_info["duration"] = ""
            if vid_secs < 1:
                vid_info["duration"] = "LIVE"
            else:
                hours, rem = divmod(vid_secs, 3600)
                mins, secs = divmod(rem, 60)

                if hours != 0:
                    vid_info["duration"] += format(hours, "02d") + ":"

                vid_info["duration"] += "{:02d}:{:02d}".format(mins, secs)
        except KeyError as ex:
            vid_info["duration"] = "N/A"

        try:
            views = int(json["yt$statistics"]["viewCount"])
            vid_info["views"] = "{:,}".format(views)
        except KeyError:
            vid_info["views"] = "N/A"

        try:
            likes = int(json["yt$rating"]["numLikes"])
            dislikes = int(json["yt$rating"]["numDislikes"])
            vid_info["likes"] = "+{:,}/-{:,}".format(likes, dislikes)
        except KeyError:
            vid_info["likes"] = "N/A"

        return vid_info

    @Plugin.integrate_with('linkinfo')
    def linkinfo_integrate(self, linkinfo):
        """Handle recognised youtube urls."""

        def page_handler(url, match):
            """Handles privmsg urls."""
            response = self._yt(url)
            if not response:
                return None
            return LinkInfoResult(url.geturl(), self.RESPONSE.format(**response))

        linkinfo.register_handler(lambda url: url.netloc in {"m.youtube.com", "www.youtube.com", "youtu.be"},
                                  page_handler)


    @Plugin.command('youtube')
    @Plugin.command('yt')
    def all_hail_our_google_overlords(self, e):
        """I for one, welcome our Google overlords."""

        response = self._yt(urlparse.urlparse(e["data"]))
        if not response:
            e.protocol.msg(e["reply_to"], "Invalid video ID")
        else:
            e.protocol.msg(e["reply_to"], self.CMD_RESPONSE.format(**response))
