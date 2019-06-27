from ..plugin import Plugin
from ..util import pluralize, simple_http_get_async
from .linkinfo import LinkInfoResult


class ImgurError(Exception):
    pass


class Imgur(Plugin):
    CONFIG_DEFAULTS = {
        'client_id': None,
        'client_secret': None,
    }

    CONFIG_ENVVARS = {
        'client_id': ['IMGUR_CLIENT_ID'],
        'client_secret': ['IMGUR_CLIENT_SECRET'],
    }

    @Plugin.integrate_with('linkinfo')
    def integrate_with_linkinfo(self, linkinfo):
        linkinfo.register_handler(lambda url: url.netloc in ('imgur.com', 'i.imgur.com'),
                                  self._linkinfo_handler, exclusive=True)

    async def _linkinfo_handler(self, url, match):
        # Split up endpoint and ID: /<image>, /a/<album> or /gallery/<id>
        kind, _, id = url.path.lstrip('/').rpartition('/')
        # Strip file extension from direct image links
        id = id.partition('.')[0]

        try:
            if kind == '':
                nsfw, title = self._format_image(await self._get_image(id))
            elif kind == 'a':
                nsfw, title = self._format_album(await self._get_album(id), url.fragment)
            elif kind == 'gallery':
                data = await self._get_gallery_item(id)
                if data['is_album']:
                    nsfw, title = self._format_album(data, None)
                else:
                    nsfw, title = self._format_image(data)
            else:
                nsfw, title = False, None
        except ImgurError as e:
            return LinkInfoResult(url.geturl(), str(e), is_error=True)

        if title:
            return LinkInfoResult(url.geturl(), title, nsfw=nsfw)
        else:
            return None

    @staticmethod
    def _format_image(data):
        title = data['title'] or ''
        return data['nsfw'] or 'nsfw' in title.lower(), title

    @staticmethod
    def _format_album(data, image_id):
        title = '{0} ({1})'.format(data['title'] or 'Untitled album',
                                   pluralize(data['images_count'], 'image', 'images'))
        images = {i['id']: i for i in data['images']}
        image = images.get(image_id)
        if image and image['title']:
            title += ': ' + image['title']
        return data['nsfw'] or 'nsfw' in title.lower(), title

    async def _get(self, url):
        headers = {'Authorization': f'Client-ID {self.config_get("client_id")}'}
        async with simple_http_get_async(url, headers=headers) as resp:
            json = await resp.json()
            if json['success']:
                return json['data']
            else:
                raise ImgurError(json['data']['error'])

    async def _get_image(self, id):
        return await self._get(f'https://api.imgur.com/3/image/{id}')

    async def _get_album(self, id):
        return await self._get(f'https://api.imgur.com/3/album/{id}')

    async def _get_gallery_item(self, id):
        return await self._get(f'https://api.imgur.com/3/gallery/{id}')
