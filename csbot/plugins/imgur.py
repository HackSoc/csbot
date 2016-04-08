from imgurpython import ImgurClient
from imgurpython.helpers.error import ImgurClientError

from ..plugin import Plugin
from ..util import pluralize
from .linkinfo import LinkInfoResult


class Imgur(Plugin):
    CONFIG_DEFAULTS = {
        'client_id': None,
        'client_secret': None,
    }

    CONFIG_ENVVARS = {
        'client_id': ['IMGUR_CLIENT_ID'],
        'client_secret': ['IMGUR_CLIENT_SECRET'],
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = ImgurClient(self.config_get('client_id'),
                                  self.config_get('client_secret'))

    @Plugin.integrate_with('linkinfo')
    def integrate_with_linkinfo(self, linkinfo):
        linkinfo.register_handler(lambda url: url.netloc in ('imgur.com', 'i.imgur.com'),
                                  self._linkinfo_handler, exclusive=True)

    def _linkinfo_handler(self, url, match):
        # Split up endpoint and ID: /<image>, /a/<album> or /gallery/<id>
        kind, _, id = url.path.lstrip('/').rpartition('/')
        # Strip file extension from direct image links
        id = id.partition('.')[0]

        try:
            if kind == '':
                nsfw, title = self._format_image(self.client.get_image(id))
            elif kind == 'a':
                nsfw, title = self._format_album(self.client.get_album(id), url.fragment)
            elif kind == 'gallery':
                data = self.client.gallery_item(id)
                if data.is_album:
                    nsfw, title = self._format_album(data, None)
                else:
                    nsfw, title = self._format_image(data)
            else:
                nsfw, title = False, None
        except ImgurClientError as e:
            return LinkInfoResult(url, str(e), is_error=True)

        if title:
            return LinkInfoResult(url, title, nsfw=nsfw)
        else:
            return None

    @staticmethod
    def _format_image(data):
        title = data.title or ''
        return data.nsfw or 'nsfw' in title.lower(), title

    @staticmethod
    def _format_album(data, image_id):
        title = '{0} ({1})'.format(data.title or 'Untitled album',
                                   pluralize(data.images_count, 'image', 'images'))
        images = {i['id']: i for i in data.images}
        image = images.get(image_id)
        if image and image['title']:
            title += ': ' + image['title']
        return data.nsfw or 'nsfw' in title.lower(), title
