from csbot.plugin import Plugin
import urlparse


class Imgur(Plugin):
    @Plugin.integrate_with('linkinfo')
    def integrate_with_linkinfo(self, linkinfo):
        """Handle recognised imgur URLs.

        Currently this just fetches titles where the image has been directly
        linked by constructing the "image page" URL based on the image ID.
        """
        def handler(url, match):
            newurl = urlparse.ParseResult(url.scheme,
                                          'imgur.com',
                                          url.path.rsplit('.', 1)[0],
                                          url.params,
                                          url.query,
                                          url.fragment)
            reply = linkinfo.scrape_html_title(newurl)
            # Don't say anything if the title was never set on the image
            if reply is not None and \
                    reply[2] == '"imgur: the simple image sharer"':
                return None
            return reply

        linkinfo.register_handler(
            lambda url: url.netloc == 'i.imgur.com',
            handler)
