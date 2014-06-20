from csbot.plugin import Plugin
import urlparse


class Imgur(Plugin):
    @Plugin.integrate_with('linkinfo')
    def integrate_with_linkinfo(self, linkinfo):
        """Handle recognised imgur URLs.

        Direct image URLs are converted to page URLs for title scraping.  The
        default imgur title is ignored.  If this plugin doesn't respond, the URL
        is excluded from default :mod:`~csbot.plugins.linkinfo` behaviour.
        """
        def image_handler(url, match):
            """Get page URL from image URL, then scrape title."""
            newurl = urlparse.ParseResult(url.scheme,
                                          'imgur.com',
                                          url.path.rsplit('.', 1)[0],
                                          url.params,
                                          url.query,
                                          url.fragment)
            return page_handler(newurl, match)

        def page_handler(url, match):
            """Scrape title, but don't say anything for the default title."""
            reply = linkinfo.scrape_html_title(url)
            if reply is None:
                return None
            elif reply[2] == '"imgur: the simple image sharer"':
                return None
            else:
                return reply

        # Handle direct image links
        linkinfo.register_handler(lambda url: url.netloc == 'i.imgur.com',
                                  image_handler)
        # Handle image page links
        linkinfo.register_handler(lambda url: url.netloc == 'imgur.com',
                                  page_handler)
        # If we didn't reply for an imgur page, nobody should
        linkinfo.register_exclude(lambda url: url.netloc in {'i.imgur.com',
                                                             'imgur.com'})
