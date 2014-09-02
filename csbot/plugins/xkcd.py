import json
import random
import requests

from csbot.plugin import Plugin
from csbot.util import simple_http_get, cap_string, is_ascii


def fix_json_unicode(data):
    """Fixes the unicode silliness that is included in the json data.
    Why Randall, Why?"""
    for tag in data:
        if type(data[tag]) != str or is_ascii(data[tag]):
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

    def _xkcd(self, user_str):
        """Get the url and title stuff.
        Returns a string of the response.
        """

        latest = get_info()
        if not latest:
            return "Error getting comics"

        latest_num = latest["num"]

        if user_str is None or user_str in {'0', 'latest', 'current', 'newest'}:
            requested = latest
        elif user_str in {'rand', 'random'}:
            requested = get_info(random.randint(1, latest_num))
        else:
            try:
                num = int(user_str)
                if 1 <= num <= latest_num:
                    requested = get_info(num)
                else:
                    return ("Comic #{} is invalid. "
                            "The latest is #{}").format(num, latest_num)
            except ValueError:
                # TODO: google search?
                return "Invalid comic number"

        # Only happens for invalid comics (like 404)
        if not requested:
            return "So. It has come to this"

        return "{} [{} - \"{}\"]".format(requested["url"], requested["title"],
                                         cap_string(requested["alt"], 120))

    @Plugin.command('xkcd')
    def randall_is_awesome(self, e):
        """Well, Randall sucks at unicode actually :(
        """
        e.protocol.msg(e["reply_to"], self._xkcd(e["data"]))
