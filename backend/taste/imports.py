"""Importing inspiration from public Pinterest, Instagram and TikTok links, mostly through Bright Data.

A shopper pastes a link; the photos land in their lookbook like uploads and feed the same taste build. Only public
pages are read (no logins). We keep the outfit photos, never who posted them: account names and captions are not
stored with the images or sent to Claude, so the profile describes the style ("quiet luxury"), not the person.

What each link does (Bright Data scraper timings measured: 10 s cached to 5 minutes for a TikTok):
- Pinterest pin, TikTok video: first the free, instant route (the pin page's preview image; TikTok's public oEmbed
  cover). If the site blocks that, Bright Data's posts scrapers, collected by URL; for a TikTok that also brings the
  video, so Claude sees frames, not just the cover.
- Instagram post or reel: Bright Data's posts scraper (Instagram blocks direct reads), every carousel photo.
- Pinterest profile, TikTok profile: Bright Data's posts scrapers, discovering the latest posts.
- Instagram profile: Bright Data's Instagram profiles scraper, which lists the latest posts (its posts scraper returns
  nothing for a profile URL). Contact fields in that record are ignored.
- Pinterest board: the board's public RSS feed, read directly (free, seconds); if Pinterest blocks that, through
  Bright Data Web Unlocker when a zone is configured; failing both, the board owner's latest pins, said so plainly.
  The pre-built Pinterest scraper ignores a board in the URL.
- TikTok video via Bright Data: the cover plus three video frames as one 2x2 sheet, so Claude sees more than the cover.
"""
import asyncio
import html
import io
import json
import re
import uuid
from typing import Literal
from urllib.parse import quote, urlsplit
import httpx
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from sourcing import safe_fetch
from sourcing.store import now

API = 'https://api.brightdata.com/'
PINTEREST_POSTS = 'gd_lk0sjs4d21kdr7cnlv'
INSTAGRAM_POSTS = 'gd_lk5ns7kz21pck8jpis'
INSTAGRAM_PROFILES = 'gd_l1vikfch901nx3by4'
TIKTOK_POSTS = 'gd_lu702nij2f790tmv9h'
MAX_IMAGES = 12
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_VIDEO_BYTES = 40 * 1024 * 1024
MAX_FEED_BYTES = 2 * 1024 * 1024
# Paths that are not usernames.
PINTEREST_RESERVED = {'pin', 'search', 'ideas', 'today', 'business', 'settings', 'categories', 'explore', 'login'}
INSTAGRAM_RESERVED = {'stories', 'explore', 'tv', 'accounts', 'direct'}

Site = Literal['pinterest', 'instagram', 'tiktok']
Kind = Literal['board', 'profile', 'post']
NAMES = {'pinterest': 'Pinterest', 'instagram': 'Instagram', 'tiktok': 'TikTok'}


class LinkError(ValueError):
    """A message safe to show the shopper as is."""


class Link(BaseModel):
    site: Site
    kind: Kind
    url: str


class ImportJob(BaseModel):
    id: str
    profile_id: str
    site: Site
    kind: Kind
    url: str
    status: Literal['running', 'done', 'empty', 'failed'] = 'running'
    added: int = 0
    message: str = ''
    created_at: str


def parse_link(url: str) -> Link:
    raw = url.strip()
    parts = urlsplit(raw if '://' in raw else 'https://' + raw)
    host = (parts.hostname or '').lower().removeprefix('www.').removeprefix('m.')
    path = [p for p in parts.path.split('/') if p]
    clean = f'https://{parts.hostname}{parts.path}'
    if host == 'pin.it' and path:
        return Link(site='pinterest', kind='post', url=clean)
    if host == 'pinterest.com' or host.endswith('.pinterest.com'):
        if len(path) >= 2 and path[0] == 'pin':
            return Link(site='pinterest', kind='post', url=f'https://www.pinterest.com/pin/{path[1]}/')
        if not path or path[0] in PINTEREST_RESERVED:
            raise LinkError("That's not a board, pin or profile. Paste a link like pinterest.com/yourname/your-board.")
        if len(path) == 1:
            return Link(site='pinterest', kind='profile', url=f'https://www.pinterest.com/{path[0]}/')
        return Link(site='pinterest', kind='board', url=f'https://www.pinterest.com/{path[0]}/{path[1]}/')
    if host == 'instagram.com':
        if len(path) >= 2 and path[0] in ('p', 'reel', 'reels'):
            return Link(site='instagram', kind='post', url=f'https://www.instagram.com/{path[0].rstrip("s")}/{path[1]}/')
        if len(path) >= 3 and path[1] in ('p', 'reel'):  # instagram.com/name/p/CODE
            return Link(site='instagram', kind='post', url=f'https://www.instagram.com/{path[1]}/{path[2]}/')
        if len(path) != 1 or path[0] in INSTAGRAM_RESERVED:
            raise LinkError('Paste a public Instagram profile (instagram.com/name) or a post link.')
        return Link(site='instagram', kind='profile', url=f'https://www.instagram.com/{path[0]}/')
    if host in ('vm.tiktok.com', 'vt.tiktok.com') and path:
        return Link(site='tiktok', kind='post', url=clean)
    if host == 'tiktok.com':
        if len(path) >= 3 and path[0].startswith('@') and path[1] in ('video', 'photo'):
            return Link(site='tiktok', kind='post', url=f'https://www.tiktok.com/{path[0]}/{path[1]}/{path[2]}')
        if len(path) == 1 and path[0].startswith('@'):
            return Link(site='tiktok', kind='profile', url=f'https://www.tiktok.com/{path[0]}')
        raise LinkError('Paste a TikTok video link or a public profile link (tiktok.com/@name).')
    raise LinkError('Paste a public Pinterest, Instagram or TikTok link: a board, profile, pin, post or video.')


PINIMG_SIZE = re.compile(r'^(https://i\.pinimg\.com/)(\d+x\d*(?:_[A-Za-z]+)?)/')


def larger(url: str) -> str:
    """Pinterest serves every pin at several sizes ("/60x60/", "/236x/"...); ask for the 736px one."""
    return PINIMG_SIZE.sub(r'\g<1>736x/', url or '')


def board_feed_images(xml: str) -> list[str]:
    """Image URLs from a Pinterest board RSS feed, upgraded from 236px thumbnails to 736px."""
    urls = []
    for description in re.findall(r'<description>(.*?)</description>', xml, re.S):
        match = re.search(r'<img[^>]+src="([^"]+)"', html.unescape(description))
        if match:
            urls.append(larger(match.group(1)))
    return list(dict.fromkeys(urls))


def _list(value):
    return value if isinstance(value, list) else []


def post_media(site: Site, rows: list[dict]) -> list[tuple[str, str | None]]:
    """(image URL, video URL or None) per post. Instagram profile records carry their posts in `posts`."""
    media = []
    for row in rows:
        if site == 'pinterest':
            if row.get('post_type') in (None, 'image') and row.get('image_video_url'):
                media.append((row['image_video_url'], None))
        elif site == 'instagram':
            if row.get('posts'):  # a profile record
                media += [(p.get('image_url'), None) for p in _list(row['posts']) if isinstance(p, dict)]
            else:  # a single post: every carousel photo
                media += [(u, None) for u in _list(row.get('photos'))] or [(row.get('thumbnail') or row.get('display_url'), None)]
        else:
            photos = _list(row.get('carousel_images'))
            if photos:
                media += [(u if isinstance(u, str) else u.get('url') if isinstance(u, dict) else None, None) for u in photos]
            elif row.get('preview_image'):
                media.append((row['preview_image'], row.get('video_url')))
    seen, out = set(), []
    for image, video in media:
        if isinstance(image, str) and image.startswith('https://') and image not in seen:
            seen.add(image)
            out.append((image, video if isinstance(video, str) and video.startswith('https://') else None))
    return out


def is_private(rows: list[dict]) -> bool:
    return any(r.get('is_private') for r in rows)


def video_sheet(cover: bytes, video: bytes, frames=3) -> bytes:
    """Cover plus `frames` evenly spaced video frames, as one 2x2 JPEG for Claude to read."""
    import av  # imported here: only TikTok videos need it
    tiles = [Image.open(io.BytesIO(cover)).convert('RGB')]
    with av.open(io.BytesIO(video)) as container:
        stream = container.streams.video[0]
        duration = float(stream.duration * stream.time_base) if stream.duration else float(container.duration or 0) / 1e6
        for i in range(frames):
            if duration:
                container.seek(int(duration * (i + 1) / (frames + 1) / stream.time_base), stream=stream)
            frame = next(container.decode(stream), None)
            if frame is not None:
                tiles.append(frame.to_image().convert('RGB'))
    width, height = 480, 640
    sheet = Image.new('RGB', (width * 2, height * 2), 'white')
    for i, tile in enumerate(tiles[:4]):
        tile.thumbnail((width, height))
        sheet.paste(tile, ((i % 2) * width + (width - tile.width) // 2, (i // 2) * height + (height - tile.height) // 2))
    out = io.BytesIO()
    sheet.save(out, format='JPEG', quality=85)
    return out.getvalue()


class BrightData:
    def __init__(self, api_key='', unlocker_zone=''):
        self.api_key, self.unlocker_zone = api_key, unlocker_zone

    def client(self):
        # Without a key (local runs behind an injecting proxy) the header is supplied in transit.
        headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
        return httpx.AsyncClient(base_url=API, headers=headers, timeout=30)

    async def collect(self, dataset_id, url, limit=None, discover_by=None, timeout=600):
        """Run a pre-built scraper on one public URL; returns its records ([] when the page had none)."""
        params = {'dataset_id': dataset_id}
        if discover_by:
            params.update(type='discover_new', discover_by=discover_by, limit_per_input=limit)
        async with self.client() as http:
            response = await http.post('datasets/v3/trigger', json=[{'url': url}], params=params)
            response.raise_for_status()
            snapshot = response.json()['snapshot_id']
            async with asyncio.timeout(timeout):
                while True:
                    await asyncio.sleep(3)
                    progress = (await http.get(f'datasets/v3/progress/{snapshot}')).raise_for_status().json()
                    if progress['status'] == 'failed':
                        raise RuntimeError(progress.get('error_message') or 'Bright Data collection failed')
                    if progress['status'] == 'ready':
                        break
            if not progress.get('records'):
                return []
            rows = (await http.get(f'datasets/v3/snapshot/{snapshot}', params={'format': 'json'})).raise_for_status().json()
        return [r for r in (rows if isinstance(rows, list) else [rows]) if isinstance(r, dict) and not r.get('error')]

    async def unlock(self, url):
        async with self.client() as http:
            response = await http.post('request', json={'zone': self.unlocker_zone, 'url': url, 'format': 'raw'},
                                       timeout=60)
            response.raise_for_status()
            return response.text


class Importer:
    def __init__(self, settings, taste, engine, brightdata: BrightData | None = None):
        self.taste, self.engine = taste, engine
        self.brightdata = brightdata or BrightData(settings.brightdata_api_key, settings.brightdata_unlocker_zone)
        self.tasks = set()
        with taste.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, profile_id TEXT, data TEXT, created_at TEXT)')
            stale = [ImportJob.model_validate_json(r[0]) for r in db.execute('SELECT data FROM imports').fetchall()]
        # Imports run in this process; any still marked running were cut off by a restart.
        for job in stale:
            if job.status == 'running':
                job.status, job.message = 'failed', 'The import was interrupted. Paste the link again.'
                self.save(job)

    def save(self, job: ImportJob):
        with self.taste.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO imports VALUES (?,?,?,?)', (job.id, job.profile_id, job.model_dump_json(),
                                                                          job.created_at))
        return job

    def jobs(self, profile_id) -> list[ImportJob]:
        with self.taste.store.connect() as db:
            rows = db.execute('SELECT data FROM imports WHERE profile_id=? ORDER BY created_at DESC LIMIT 10',
                              (profile_id,)).fetchall()
        return [ImportJob.model_validate_json(r[0]) for r in rows]

    def start(self, profile_id, url) -> ImportJob:
        link = parse_link(url)
        job = ImportJob(id=str(uuid.uuid4()), profile_id=profile_id, created_at=now(), **link.model_dump())
        task = asyncio.create_task(self.run(job))
        self.save(job)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job

    async def board_images(self, job: ImportJob):
        """(image URLs, note): the board's own pins when we can read them, else its owner's latest pins."""
        feed = job.url.rstrip('/') + '.rss'
        async with safe_fetch.client() as http:
            fetched = await safe_fetch.fetch(http, feed, MAX_FEED_BYTES)
        urls = board_feed_images(fetched[0].decode('utf-8', 'replace')) if fetched else []
        if not urls and self.brightdata.unlocker_zone:
            try:
                urls = board_feed_images(await self.brightdata.unlock(feed))
            except httpx.HTTPError:
                urls = []
        if urls:
            return urls, ''
        owner = job.url.rstrip('/').rsplit('/', 1)[0] + '/'
        rows = await self.brightdata.collect(PINTEREST_POSTS, owner, MAX_IMAGES * 2, 'profile_url')
        return [u for u, _ in post_media('pinterest', rows)], " We couldn't open that board directly, so these are the newest pins from the same account."

    async def direct(self, job: ImportJob):
        """The free route for a single pin or TikTok: its preview image, or None when the site blocks us."""
        from .links import parse_meta
        async with safe_fetch.client() as http:
            if job.site == 'tiktok':
                fetched = await safe_fetch.fetch(http, f'https://www.tiktok.com/oembed?url={quote(job.url, safe="")}',
                                                 MAX_FEED_BYTES)
                try:
                    return json.loads(fetched[0]).get('thumbnail_url') if fetched else None
                except ValueError:
                    return None
            fetched = await safe_fetch.fetch(http, job.url, MAX_FEED_BYTES)
            return parse_meta(fetched[0].decode('utf-8', 'replace'), fetched[1])['image_url'] if fetched else None

    async def media(self, job: ImportJob):
        """(media, note), or None when the account is private."""
        if job.kind == 'post' and job.site in ('pinterest', 'tiktok'):
            image = await self.direct(job)
            if image and image.startswith('https://'):
                return [(image, None)], ''
        if job.kind == 'board':
            urls, note = await self.board_images(job)
            return [(u, None) for u in urls], note
        if job.site == 'instagram' and job.kind == 'profile':
            rows = await self.brightdata.collect(INSTAGRAM_PROFILES, job.url)
        else:
            dataset = {'pinterest': PINTEREST_POSTS, 'instagram': INSTAGRAM_POSTS, 'tiktok': TIKTOK_POSTS}[job.site]
            discover = 'profile_url' if job.kind == 'profile' else None
            rows = await self.brightdata.collect(dataset, job.url, MAX_IMAGES * 2 if discover else None, discover)
        return (None if is_private(rows) else post_media(job.site, rows)), ''

    async def photo(self, http, image_url, video_url):
        """JPEG/PNG bytes for one post: the image, or for a video its cover plus frames (cover alone if that fails)."""
        big = larger(image_url)
        fetched = (big != image_url and await safe_fetch.fetch(http, big, MAX_IMAGE_BYTES)) or \
            await safe_fetch.fetch(http, image_url, MAX_IMAGE_BYTES)
        if not fetched:
            return None
        if video_url:
            video = await safe_fetch.fetch(http, video_url, MAX_VIDEO_BYTES)
            if video:
                try:
                    return await asyncio.to_thread(video_sheet, fetched[0], video[0])
                except Exception:  # undecodable video: the cover still carries the look
                    pass
        return fetched[0]

    async def run(self, job: ImportJob):
        name = NAMES[job.site]
        what = {'board': 'board', 'profile': 'profile', 'post': 'post'}[job.kind]
        try:
            found, note = await self.media(job)
            if found is None:
                job.status, job.message = 'empty', 'That account is private. Only public profiles can be imported.'
                self.save(job)
                return
            found = found[:MAX_IMAGES]
            async with safe_fetch.client() as http:
                photos = await asyncio.gather(*(self.photo(http, image, video) for image, video in found))
            for data in photos:
                if not data:
                    continue
                try:
                    # Only the pixels are kept: no caption, account name or link travels with the photo.
                    self.engine.add_image(job.profile_id, data, 'outfit', source=job.site)
                    job.added += 1
                except (UnidentifiedImageError, OSError):
                    continue
            if job.added:
                job.status = 'done'
                job.message = f'Added {job.added} photo{"s" if job.added > 1 else ""} from {name}.{note}'
            elif found:
                job.status, job.message = 'failed', "We found photos but couldn't download them. Try again in a minute."
            else:
                job.status = 'empty'
                job.message = (f"We couldn't see any photos in that {what}. Make sure it's public (not a secret board "
                               f"or private account).")
        except Exception as exc:
            self.taste.event(job.profile_id, 'import_failed', {'site': job.site, 'type': type(exc).__name__,
                                                               'detail': str(exc)[:200]})
            job.status, job.message = 'failed', f"{name} didn't respond. Try again in a minute."
        self.save(job)
