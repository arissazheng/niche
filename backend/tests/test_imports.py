import asyncio
import time
import io
import pytest
from PIL import Image
from sourcing import safe_fetch
from sourcing.config import Settings
from sourcing.store import Store
from taste.engine import TasteEngine
from taste.imports import BrightData, Importer, LinkError, board_feed_images, parse_link, post_media
from taste.store import TasteStore


def jpeg():
    out = io.BytesIO()
    Image.new('RGB', (40, 60), (107, 112, 58)).save(out, format='JPEG')
    return out.getvalue()


@pytest.mark.parametrize('url,site,kind,clean', [
    ('https://www.pinterest.com/jane/fall-outfits/', 'pinterest', 'board', 'https://www.pinterest.com/jane/fall-outfits/'),
    ('pinterest.com/jane', 'pinterest', 'profile', 'https://www.pinterest.com/jane/'),
    ('https://uk.pinterest.com/jane/fall-outfits?x=1', 'pinterest', 'board', 'https://www.pinterest.com/jane/fall-outfits/'),
    ('https://instagram.com/somestylist/', 'instagram', 'profile', 'https://www.instagram.com/somestylist/'),
    ('https://www.pinterest.com/pin/123/', 'pinterest', 'post', 'https://www.pinterest.com/pin/123/'),
    ('https://pin.it/abc', 'pinterest', 'post', 'https://pin.it/abc'),
    ('https://www.instagram.com/reel/XYZ/?igsh=1', 'instagram', 'post', 'https://www.instagram.com/reel/XYZ/'),
    ('https://www.tiktok.com/@style/video/123?lang=en', 'tiktok', 'post', 'https://www.tiktok.com/@style/video/123'),
    ('https://vm.tiktok.com/ZMabc/', 'tiktok', 'post', 'https://vm.tiktok.com/ZMabc/'),
    ('tiktok.com/@style', 'tiktok', 'profile', 'https://www.tiktok.com/@style'),
])
def test_parse_link(url, site, kind, clean):
    link = parse_link(url)
    assert (link.site, link.kind, link.url) == (site, kind, clean)


@pytest.mark.parametrize('url', ['https://www.pinterest.com/search/pins/?q=x', 'https://www.tiktok.com/foryou',
                                 'https://www.instagram.com/explore/', 'https://example.com/board'])
def test_parse_link_rejects_with_a_helpful_message(url):
    with pytest.raises(LinkError):
        parse_link(url)


def test_board_feed_and_post_images():
    feed = ('<rss><channel><description>Board</description><item><description>&lt;a href="/pin/1/"&gt;&lt;img '
            'src="https://i.pinimg.com/236x/aa/bb/1.jpg"&gt;&lt;/a&gt;Linen</description></item></channel></rss>')
    assert board_feed_images(feed) == ['https://i.pinimg.com/736x/aa/bb/1.jpg']
    pins = [{'post_type': 'image', 'image_video_url': 'https://i.pinimg.com/originals/1.jpg'},
            {'post_type': 'video', 'image_video_url': 'https://v.pinimg.com/2.mp4'}]
    assert post_media('pinterest', pins) == [('https://i.pinimg.com/originals/1.jpg', None)]
    profile = [{'account': 'somestylist', 'is_private': False, 'business_email': 'x@y.z',
                'posts': [{'image_url': 'https://scontent.cdninstagram.com/1.jpg', 'caption': 'hi'}, {'caption': 'x'}]}]
    assert post_media('instagram', profile) == [('https://scontent.cdninstagram.com/1.jpg', None)]
    carousel = [{'photos': ['https://scontent.cdninstagram.com/a.jpg', 'https://scontent.cdninstagram.com/b.jpg'],
                 'content_type': 'Carousel'}]
    assert len(post_media('instagram', carousel)) == 2
    tiktok = [{'post_type': 'video', 'preview_image': 'https://p16.tiktokcdn.com/c.jpg', 'video_url': 'https://v16.tiktok.com/v.mp4',
               'carousel_images': None}]
    assert post_media('tiktok', tiktok) == [('https://p16.tiktokcdn.com/c.jpg', 'https://v16.tiktok.com/v.mp4')]


def importer(tmp_path, rows, zone=''):
    settings = Settings(database_path=str(tmp_path / 'i.sqlite'), upload_dir=str(tmp_path / 'up'))
    taste = TasteStore(Store(settings.database_path))

    class Fake(BrightData):
        async def collect(self, dataset_id, url, limit=None, discover_by=None, timeout=300):
            return rows

    return Importer(settings, taste, TasteEngine(settings, taste), Fake(unlocker_zone=zone)), taste


def test_instagram_import_keeps_photos_not_the_account(tmp_path, monkeypatch):
    async def fake_fetch(http, url, max_bytes):
        return jpeg(), url, 'image/jpeg'
    monkeypatch.setattr(safe_fetch, 'fetch', fake_fetch)
    rows = [{'account': 'somestylist', 'is_private': False, 'posts': [
        {'image_url': f'https://scontent.cdninstagram.com/{i}.jpg', 'caption': 'my outfit'} for i in range(3)]}]
    imp, taste = importer(tmp_path, rows)

    async def go():
        job = imp.start('p1', 'https://www.instagram.com/somestylist/')
        await asyncio.gather(*imp.tasks)
        return imp.jobs('p1')[0], job
    done, _ = asyncio.run(go())
    assert done.status == 'done' and done.added == 3
    images = taste.images('p1')
    assert {x.source for x in images} == {'instagram'}
    assert all('somestylist' not in x.model_dump_json() and x.note == '' for x in images)


def test_private_or_empty_page_says_make_it_public(tmp_path):
    imp, _ = importer(tmp_path, [])

    async def go():
        imp.start('p1', 'https://www.pinterest.com/jane/')
        await asyncio.gather(*imp.tasks)
        return imp.jobs('p1')[0]
    job = asyncio.run(go())
    assert job.status == 'empty' and 'public' in job.message


def test_board_reads_its_public_feed_directly(tmp_path, monkeypatch):
    feed = ('<rss><channel><item><description>&lt;img src="https://i.pinimg.com/236x/aa/1.jpg"&gt;</description></item>'
            '</channel></rss>').encode()

    async def fake_fetch(http, url, max_bytes):
        return (feed if url.endswith('.rss') else jpeg()), url, ''
    monkeypatch.setattr(safe_fetch, 'fetch', fake_fetch)
    imp, taste = importer(tmp_path, [])  # Bright Data never called: no zone, and the feed worked

    async def go():
        imp.start('p1', 'https://www.pinterest.com/jane/fall-outfits/')
        await asyncio.gather(*imp.tasks)
        return imp.jobs('p1')[0]
    job = asyncio.run(go())
    assert job.status == 'done' and job.added == 1 and 'newest pins' not in job.message


def test_blocked_board_falls_back_to_the_owners_pins_and_says_so(tmp_path, monkeypatch):
    async def fake_fetch(http, url, max_bytes):
        return None if url.endswith('.rss') else (jpeg(), url, '')
    monkeypatch.setattr(safe_fetch, 'fetch', fake_fetch)
    imp, _ = importer(tmp_path, [{'post_type': 'image', 'image_video_url': 'https://i.pinimg.com/originals/1.jpg'}])

    async def go():
        imp.start('p1', 'https://www.pinterest.com/jane/fall-outfits/')
        await asyncio.gather(*imp.tasks)
        return imp.jobs('p1')[0]
    job = asyncio.run(go())
    assert job.status == 'done' and 'newest pins from the same account' in job.message


def test_tiktok_video_becomes_one_sheet_of_frames(tmp_path, monkeypatch):
    import av
    out = io.BytesIO()
    with av.open(out, 'w', format='mp4') as container:
        stream = container.add_stream('mpeg4', rate=10)
        stream.width, stream.height, stream.pix_fmt = 64, 96, 'yuv420p'
        for i in range(30):
            frame = av.VideoFrame.from_image(Image.new('RGB', (64, 96), (i * 8, 100, 60)))
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    video = out.getvalue()

    async def fake_fetch(http, url, max_bytes):
        if 'oembed' in url:
            return None  # TikTok blocked the free route, so Bright Data (with the video) is used
        return (video if url.endswith('.mp4') else jpeg()), url, ''
    monkeypatch.setattr(safe_fetch, 'fetch', fake_fetch)
    rows = [{'post_type': 'video', 'preview_image': 'https://p16.tiktokcdn.com/c.jpg', 'video_url': 'https://v16.tiktok.com/v.mp4'}]
    imp, taste = importer(tmp_path, rows)

    async def go():
        imp.start('p1', 'https://www.tiktok.com/@style/video/1')
        await asyncio.gather(*imp.tasks)
        return imp.jobs('p1')[0]
    job = asyncio.run(go())
    assert job.status == 'done' and job.added == 1
    image = taste.images('p1')[0]
    assert image.source == 'tiktok'
    sheet = Image.open(tmp_path / 'up' / f'{image.id}.jpg')
    assert sheet.width > 600  # 2x2 sheet, not the bare 40px cover


def test_private_instagram_says_so(tmp_path):
    imp, _ = importer(tmp_path, [{'account': 'x', 'is_private': True, 'posts': []}])

    async def go():
        imp.start('p1', 'https://www.instagram.com/x/')
        await asyncio.gather(*imp.tasks)
        return imp.jobs('p1')[0]
    job = asyncio.run(go())
    assert job.status == 'empty' and 'private' in job.message


def test_import_endpoint_starts_a_background_job(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import create_app

    async def no_photos(self, dataset_id, url, limit=None, discover_by=None, timeout=300):
        return []
    monkeypatch.setattr(BrightData, 'collect', no_photos)
    settings = Settings(database_path=str(tmp_path / 'a.sqlite'), upload_dir=str(tmp_path / 'up'))
    with TestClient(create_app(settings)) as client:
        pid = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
        bad = client.post(f'/v1/taste/profiles/{pid}/imports', json={'url': 'https://www.pinterest.com/ideas/x/'})
        assert bad.status_code == 422 and 'board, pin or profile' in bad.json()['detail']
        started = client.post(f'/v1/taste/profiles/{pid}/imports', json={'url': 'https://www.pinterest.com/jane/'})
        assert started.status_code == 202 and started.json()['status'] == 'running'
        for _ in range(50):
            jobs = client.get(f'/v1/taste/profiles/{pid}/imports').json()
            if jobs[0]['status'] != 'running':
                break
            time.sleep(0.1)
        assert jobs[0]['status'] == 'empty' and 'public' in jobs[0]['message']


def test_imports_cut_off_by_a_restart_are_marked_failed(tmp_path):
    imp, taste = importer(tmp_path, [])
    from taste.imports import ImportJob
    imp.save(ImportJob(id='j', profile_id='p1', site='pinterest', kind='profile', url='u', created_at='t'))
    again = Importer(Settings(database_path=str(tmp_path / 'i.sqlite')), taste, imp.engine, imp.brightdata)
    assert again.jobs('p1')[0].status == 'failed'


def test_single_pin_and_tiktok_use_the_free_route_first(tmp_path, monkeypatch):
    pin_page = b'<html><head><meta property="og:image" content="https://i.pinimg.com/736x/aa/1.jpg"></head></html>'
    oembed = b'{"thumbnail_url": "https://p16-sign.tiktokcdn.com/cover.jpg", "author_name": "someone"}'

    async def fake_fetch(http, url, max_bytes):
        if 'oembed' in url:
            return oembed, url, 'application/json'
        if '/pin/' in url:
            return pin_page, url, 'text/html'
        return jpeg(), url, 'image/jpeg'
    monkeypatch.setattr(safe_fetch, 'fetch', fake_fetch)

    class NoBrightData(BrightData):
        async def collect(self, *args, **kwargs):
            raise AssertionError('Bright Data should not be needed')
    settings = Settings(database_path=str(tmp_path / 'f.sqlite'), upload_dir=str(tmp_path / 'up'))
    taste = TasteStore(Store(settings.database_path))
    imp = Importer(settings, taste, TasteEngine(settings, taste), NoBrightData())

    async def go():
        imp.start('p1', 'https://www.pinterest.com/pin/1/')
        imp.start('p1', 'https://www.tiktok.com/@someone/video/2')
        await asyncio.gather(*imp.tasks)
        return imp.jobs('p1')
    jobs = asyncio.run(go())
    assert [j.status for j in jobs] == ['done', 'done']
    assert all('someone' not in x.model_dump_json() for x in taste.images('p1'))
