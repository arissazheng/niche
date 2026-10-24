"""Publishes live state to SpacetimeDB (build progress, profile versions, streaming search results).

Best effort: a missing or unreachable SpacetimeDB never fails a build, edit or search; the web app falls back
to polling the REST API. Calls go to the module's service-only reducers with the publisher identity's token.
"""
import logging
import httpx

log = logging.getLogger(__name__)


class Live:
    def __init__(self, settings):
        self.url = settings.spacetime_url.rstrip('/')
        self.db = settings.spacetime_db
        self.token = settings.spacetime_token

    @property
    def enabled(self):
        return bool(self.url and self.token)

    async def call(self, reducer, *args):
        if not self.enabled:
            return
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(f'{self.url}/v1/database/{self.db}/call/{reducer}', json=list(args),
                    headers={'Authorization': f'Bearer {self.token}'}, params={'confirmed': 'false'})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning('spacetime %s failed: %s', reducer, type(exc).__name__)

    async def build_progress(self, profile_id, stage, done, total, message=''):
        await self.call('set_build_progress', profile_id, stage, done, total, message[:200])

    async def profile_version(self, profile_id, version):
        await self.call('set_profile_version', profile_id, version)

    async def search(self, search_id, profile_id, query, status, ranking_method='', warnings=()):
        await self.call('upsert_search', search_id, profile_id, query, status, ranking_method or '', list(warnings))

    async def listings(self, search_id, items, replace=False):
        await self.call('upsert_listings', search_id, [listing_row(x) for x in items], replace)


def listing_row(item):
    """Listing (model or dict) -> the module's ListingInput. The HTTP API takes snake_case fields and
    encodes options as sums: {"some": value} or {"none": []}."""
    x = item if isinstance(item, dict) else item.model_dump(mode='json')
    option = lambda v: {'some': v} if v is not None else {'none': []}
    return {'listing_id': x['id'], 'source': x['source'], 'title': x['title'][:300], 'url': x['url'],
            'image_url': (x.get('image_urls') or [''])[0], 'price': float(x['price']), 'currency': x['currency'],
            'seller': x.get('seller') or '', 'reason': x.get('reason') or '', 'warnings': x.get('warnings') or [],
            'score': option(x.get('score')), 'rank': option(x.get('rank')), 'is_fixture': bool(x.get('is_fixture'))}
