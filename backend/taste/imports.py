"""Importing inspiration photos from public Pinterest and Instagram pages, through Bright Data.

A shopper pastes a link; the photos land in their lookbook like uploads and feed the same taste build. Only public
pages are read (no logins). From Instagram we keep the outfit photos, never who posted them: the account name is not
stored with the images or sent to Claude, so the profile describes the style ("quiet luxury"), not the person.

Sources:
- Pinterest profile: Bright Data's Pinterest posts scraper (Web Scraper API), 1-3 minutes.
- Instagram profile: Bright Data's Instagram profiles scraper, which lists the latest posts (the posts scraper
  returned nothing for public profiles when tested). Only post photos are used; contact fields are ignored.
- Pinterest board: the board's public RSS feed, fetched through Bright Data Web Unlocker (needs a zone; seconds).
  The pre-built Pinterest scraper only discovers by profile and ignores a board in the URL.
"""
import asyncio
import html
import re
import uuid
from typing import Literal
from urllib.parse import urlsplit
import httpx
from PIL import UnidentifiedImageError
from pydantic import BaseModel
from sourcing import safe_fetch
from sourcing.store import now

API = 'https://api.brightdata.com/'
PINTEREST_POSTS = 'gd_lk0sjs4d21kdr7cnlv'
INSTAGRAM_PROFILES = 'gd_l1vikfch901nx3by4'
MAX_IMAGES = 12
MAX_IMAGE_BYTES = 15 * 1024 * 1024
# Pinterest paths that are not usernames.
PINTEREST_RESERVED = {'pin', 'search', 'ideas', 'today', 'business', 'settings', 'categories', 'explore', 'login'}
INSTAGRAM_RESERVED = {'p', 'reel', 'reels', 'stories', 'explore', 'tv', 'accounts', 'direct'}

Site = Literal['pinterest', 'instagram']


class LinkError(ValueError):
    """A message safe to show the shopper as is."""


class Link(BaseModel):
    site: Site
    kind: Literal['board', 'profile']
    url: str


class ImportJob(BaseModel):
    id: str
    profile_id: str
    site: Site
    kind: Literal['board', 'profile']
    url: str
    status: Literal['running', 'done', 'empty', 'failed'] = 'running'
    added: int = 0
    message: str = ''
    created_at: str


def parse_link(url: str) -> Link:
    parts = urlsplit(url.strip() if '://' in url else 'https://' + url.strip())
    host = (parts.hostname or '').lower().removeprefix('www.')
    path = [p for p in parts.path.split('/') if p]
    if host == 'pin.it':
        raise LinkError('Short pin.it links point to a single pin. Open it and copy the board or profile link instead.')
    if host == 'pinterest.com' or host.endswith('.pinterest.com'):
        if not path or path[0] in PINTEREST_RESERVED:
            raise LinkError("That's not a board or profile. Paste a link like pinterest.com/yourname/your-board.")
        if len(path) == 1:
            return Link(site='pinterest', kind='profile', url=f'https://www.pinterest.com/{path[0]}/')
        return Link(site='pinterest', kind='board', url=f'https://www.pinterest.com/{path[0]}/{path[1]}/')
    if host == 'instagram.com':
        if len(path) != 1 or path[0] in INSTAGRAM_RESERVED:
            raise LinkError("Paste a profile link like instagram.com/name, not a single post.")
        return Link(site='instagram', kind='profile', url=f'https://www.instagram.com/{path[0]}/')
    raise LinkError('Paste a link to a public Pinterest board or profile, or a public Instagram profile.')


def board_feed_images(xml: str) -> list[str]:
    """Image URLs from a Pinterest board RSS feed, upgraded from 236px thumbnails to 736px."""
    urls = []
    for description in re.findall(r'<description>(.*?)</description>', xml, re.S):
        match = re.search(r'<img[^>]+src="([^"]+)"', html.unescape(description))
        if match:
            urls.append(match.group(1).replace('/236x/', '/736x/'))
    return list(dict.fromkeys(urls))


def post_images(site: Site, rows: list[dict]) -> list[str]:
    """Photo URLs from Pinterest post rows, or from the `posts` of an Instagram profile row (video covers included)."""
    if site == 'pinterest':
        urls = [r['image_video_url'] for r in rows if r.get('post_type') in (None, 'image') and r.get('image_video_url')]
    else:
        urls = [p.get('image_url') for r in rows for p in (r.get('posts') or []) if isinstance(p, dict)]
    return [u for u in dict.fromkeys(urls) if isinstance(u, str) and u.startswith('https://')]


def is_private(site: Site, rows: list[dict]) -> bool:
    return site == 'instagram' and any(r.get('is_private') for r in rows)


class BrightData:
    def __init__(self, api_key='', unlocker_zone=''):
        self.api_key, self.unlocker_zone = api_key, unlocker_zone

    def client(self):
        # Without a key (local runs behind an injecting proxy) the header is supplied in transit.
        headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
        return httpx.AsyncClient(base_url=API, headers=headers, timeout=30)

    async def collect(self, dataset_id, url, limit, timeout=300):
        """Run a pre-built scraper on one public URL; returns its records ([] when the page had none)."""
        # Pinterest posts are discovered from a profile; an Instagram profile is collected as one record.
        params = ({'type': 'discover_new', 'discover_by': 'profile_url', 'limit_per_input': limit}
                  if dataset_id == PINTEREST_POSTS else {})
        async with self.client() as http:
            response = await http.post('datasets/v3/trigger', json=[{'url': url}],
                                       params={'dataset_id': dataset_id, **params})
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
        if link.kind == 'board' and not self.brightdata.unlocker_zone:
            raise LinkError('Board links need one more setup step on our side. For now, paste your Pinterest '
                            'profile link (pinterest.com/yourname) to import your latest pins.')
        job = self.save(ImportJob(id=str(uuid.uuid4()), profile_id=profile_id, created_at=now(),
                                  **link.model_dump()))
        task = asyncio.create_task(self.run(job))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job

    async def image_urls(self, job: ImportJob):
        """Photo URLs, or None when the page is private."""
        if job.kind == 'board':
            return board_feed_images(await self.brightdata.unlock(job.url.rstrip('/') + '.rss'))
        dataset = PINTEREST_POSTS if job.site == 'pinterest' else INSTAGRAM_PROFILES
        rows = await self.brightdata.collect(dataset, job.url, MAX_IMAGES * 2)
        return None if is_private(job.site, rows) else post_images(job.site, rows)

    async def run(self, job: ImportJob):
        where = 'board' if job.kind == 'board' else 'profile'
        try:
            urls = await self.image_urls(job)
            if urls is None:
                job.status, job.message = 'empty', 'That account is private. Only public profiles can be imported.'
                self.save(job)
                return
            urls = urls[:MAX_IMAGES]
            async with safe_fetch.client() as http:
                downloads = await asyncio.gather(*(safe_fetch.fetch(http, u, MAX_IMAGE_BYTES) for u in urls))
            for fetched in downloads:
                if not fetched:
                    continue
                try:
                    # Only the photo is kept: no caption, account name or link travels with it.
                    self.engine.add_image(job.profile_id, fetched[0], 'outfit', source=job.site)
                    job.added += 1
                except (UnidentifiedImageError, OSError):
                    continue
            if job.added:
                job.status, job.message = 'done', f'Added {job.added} photos from {job.site.title()}.'
            elif urls:
                job.status, job.message = 'failed', "We found photos but couldn't download them. Try again in a minute."
            else:
                job.status = 'empty'
                job.message = (f"We couldn't see any photos on that {where}. Make sure the {where} is public "
                               f"(not secret or private) and has photos.")
        except Exception as exc:
            self.taste.event(job.profile_id, 'import_failed', {'site': job.site, 'type': type(exc).__name__,
                                                               'detail': str(exc)[:200]})
            job.status, job.message = 'failed', f"{job.site.title()} didn't respond. Try again in a minute."
        self.save(job)
