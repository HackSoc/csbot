import pytest

from . import read_fixture_file


test_cases = [
    # Direct image link, no title
    (
        'http://i.imgur.com/ybgvNbm.png',
        'https://api.imgur.com/3/image/ybgvNbm',
        200,
        'application/json',
        'imgur_image_ybgvNbM.json',
        None,
    ),
    # HTML image link, no title
    (
        'http://imgur.com/ybgvNbm',
        'https://api.imgur.com/3/image/ybgvNbm',
        200,
        'application/json',
        'imgur_image_ybgvNbM.json',
        None,
    ),
    # Image with a title
    (
        'http://imgur.com/jSmKOXT',
        'https://api.imgur.com/3/image/jSmKOXT',
        200,
        'application/json',
        'imgur_image_jSmKOXT.json',
        '20150720-142742.png',
    ),
    # Album, no title
    (
        'http://imgur.com/a/26hit',
        'https://api.imgur.com/3/album/26hit',
        200,
        'application/json',
        'imgur_album_26hit.json',
        'Untitled album (3 images)',
    ),
    # Album, no title, specific image
    (
        'http://imgur.com/a/26hit#TttQsVD',
        'https://api.imgur.com/3/album/26hit',
        200,
        'application/json',
        'imgur_album_26hit.json',
        'Untitled album (3 images): 20160205-190834.png',
    ),
    # Album with a title
    (
        'http://imgur.com/a/myXfq',
        'https://api.imgur.com/3/album/myXfq',
        200,
        'application/json',
        'imgur_album_myXfq.json',
        'Cities: Skylines - rising water or sinking land? (8 images)',
    ),
    # Album with a title, specific image
    (
        'http://imgur.com/a/myXfq#n2ijrDs',
        'https://api.imgur.com/3/album/myXfq',
        200,
        'application/json',
        'imgur_album_myXfq.json',
        'Cities: Skylines - rising water or sinking land? (8 images): Water under the bridge right now',
    ),
    # Album with a title, invalid specific image
    (
        'http://imgur.com/a/myXfq#not_an_image',
        'https://api.imgur.com/3/album/myXfq',
        200,
        'application/json',
        'imgur_album_myXfq.json',
        'Cities: Skylines - rising water or sinking land? (8 images)',
    ),
    # Album with only one image
    (
        'http://imgur.com/a/ysj7k',
        'https://api.imgur.com/3/album/ysj7k',
        200,
        'application/json',
        'imgur_album_ysj7k.json',
        'Test (1 image)',
    ),
    # Gallery image
    (
        'http://imgur.com/gallery/HNUmA0P',
        'https://api.imgur.com/3/gallery/HNUmA0P',
        200,
        'application/json',
        'imgur_gallery_HNUmA0P.json',
        'Damn that was fast',
    ),
    # Gallery album
    (
        'http://imgur.com/gallery/rYRa1',
        'https://api.imgur.com/3/gallery/rYRa1',
        200,
        'application/json',
        'imgur_gallery_rYRa1.json',
        'How to Build a Gaming PC - Updated (13 images)',
    ),

    # Invalid API client ID
    (
        'http://i.imgur.com/ybgvNbm.png',
        'https://api.imgur.com/3/image/ybgvNbm',
        403,
        'application/json',
        'imgur_invalid_api_key.json',
        None,
    ),
    # Invalid image ID
    (
        'http://i.imgur.com/not_an_image.png',
        'https://api.imgur.com/3/image/not_an_image',
        404,
        'application/json',
        'imgur_invalid_image_id.json',
        None,
    ),
    # Invalid album ID
    (
        'http://imgur.com/a/not_an_album',
        'https://api.imgur.com/3/album/not_an_album',
        404,
        'application/json',
        'imgur_invalid_album_id.json',
        None,
    ),
    # Invalid gallery ID
    (
        'http://imgur.com/gallery/invalid_id',
        'https://api.imgur.com/3/gallery/invalid_id',
        404,
        'application/json',
        'imgur_invalid_gallery.json',
        None,
    ),
]

nsfw_test_cases = [
    (
        'http://imgur.com/a/cwXza',
        'https://api.imgur.com/3/album/cwXza',
        200,
        'application/json',
        'imgur_nsfw_album.json',
        'NSFW Celeb GIFS (81 images)',
    ),
]


pytestmark = pytest.mark.bot(config="""\
    [@bot]
    plugins = linkinfo imgur

    [imgur]
    client_id = abc
    client_secret = def
    """)


@pytest.mark.asyncio
@pytest.mark.parametrize("url, api_url, status, content_type, fixture, title", test_cases)
async def test_integration(bot_helper, aioresponses, url, api_url, status, content_type, fixture, title):
    aioresponses.get(api_url, status=status,
                     body=read_fixture_file(fixture),
                     content_type=content_type)
    result = await bot_helper['linkinfo'].get_link_info(url)
    if title is None:
        assert result.is_error
    else:
        assert not result.is_error
        assert title == result.text


@pytest.mark.asyncio
@pytest.mark.parametrize("url, api_url, status, content_type, fixture, title", nsfw_test_cases)
async def test_integration_nsfw(bot_helper, aioresponses, url, api_url, status, content_type, fixture, title):
    aioresponses.get(api_url, status=status,
                     body=read_fixture_file(fixture),
                     content_type=content_type)
    result = await bot_helper['linkinfo'].get_link_info(url)
    if title is None:
        assert result.is_error
    else:
        assert not result.is_error
        assert title == result.text


@pytest.mark.asyncio
async def test_invalid_URL(bot_helper, aioresponses):
    """Test that an unrecognised URL never even results in a request."""
    result = await bot_helper['linkinfo'].get_link_info('http://imgur.com/invalid/url')
    assert result.is_error
