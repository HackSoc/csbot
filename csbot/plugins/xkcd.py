import json
import random
import requests
import lxml.html

from ..plugin import Plugin
from ..util import simple_http_get, cap_string, is_ascii
from .linkinfo import LinkInfoResult


def fix_json_unicode(data):
    """Fixes the unicode silliness that is included in the json data.
    Why Randall, Why?"""
    for tag in data:
        if type(data[tag]) != str:
            continue

        # Remove HTML escape characters
        data[tag] = lxml.html.fromstring(data[tag]).text

        if is_ascii(data[tag]):
            continue
        try:
            data[tag] = data[tag].encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return data


def get_info(number=None):
    """Gets the json data for a particular comic
    (or the latest, if none provided).
    """
    if number:
        url = "http://xkcd.com/{}/info.0.json".format(number)
    else:
        url = "http://xkcd.com/info.0.json"

    httpdata = simple_http_get(url)
    if httpdata.status_code != requests.codes.ok:
        return None

    # Only care about part of the data
    httpjson = httpdata.json()
    data = {key: httpjson[key] for key in ["title", "alt", "num"]}

    # Unfuck up unicode strings
    data = fix_json_unicode(data)

    data["url"] = "http://xkcd.com/" + str(data["num"])
    return data


class xkcd(Plugin):
    """A plugin that does some xkcd things.
    Based on williebot xkcd plugin.
    """

    class XKCDError(Exception):
        pass

    def _xkcd(self, user_str):
        """Get the url and title stuff.
        Returns a string of the response.
        """

        latest = get_info()
        if not latest:
            raise self.XKCDError("Error getting comics")

        latest_num = latest["num"]

        if not user_str or user_str in {'0', 'latest', 'current', 'newest'}:
            requested = latest
        elif user_str in {'rand', 'random'}:
            requested = get_info(random.randint(1, latest_num))
        else:
            try:
                num = int(user_str)
                if 1 <= num <= latest_num:
                    requested = get_info(num)
                else:
                    raise self.XKCDError("Comic #{} is invalid. The latest is #{}"
                                         .format(num, latest_num))
            except ValueError:
                # TODO: google search?
                raise self.XKCDError("Invalid comic number")

        # Only happens for invalid comics (like 404)
        if not requested:
            raise self.XKCDError("So. It has come to this")

        return (requested["url"], requested["title"],
                cap_string(requested["alt"], 120))

    @Plugin.integrate_with('linkinfo')
    def linkinfo_integrate(self, linkinfo):
        """Handle recognised xkcd urls."""

        def page_handler(url, match):
            """Use the main _xkcd function, then modify
            the result (if success) so it looks nicer.
            """

            # Remove leading and trailing '/'
            try:
                response = self._xkcd(url.path.strip('/'))
                return LinkInfoResult(url.geturl(), '{1} - "{2}"'.format(*response))
            except self.XKCDError:
                return None

        linkinfo.register_handler(lambda url: url.netloc == "xkcd.com",
                                  page_handler, exclusive=True)

    @Plugin.command('xkcd')
    def randall_is_awesome(self, e):
        """Well, Randall sucks at unicode actually :(
        """
        try:
            e.protocol.msg(e["reply_to"],
                           "{} [{} - \"{}\"]".format(*self._xkcd(e["data"])))
        except self.XKCDError as ex:
            e.protocol.msg(e["reply_to"], str(ex))
