"""Earlier finds, kept in Moss. Every listing a shopper has been shown goes into their own Moss index, so the shop agent
can bring back "the green skirt from before" or "that leather jacket" without running another search.

Writes use Moss's manage API. Reads use the Moss SDK (`pip install inferedge-moss`), which loads the index and runs
the semantic query in memory; without the SDK they go to Moss's cloud query API. Moss is optional: with no project
key, or when Moss is unreachable, the agent simply has no earlier finds to draw on."""
import asyncio
import json
import logging
import httpx
from sourcing.store import Store

log = logging.getLogger(__name__)
transport = None  # tests swap in an httpx.MockTransport
RECALL_SECONDS = 2.5  # a chat turn never waits longer than this on Moss
DONE = ('completed', 'partial')


def index_name(profile_id):
    return f'niche-finds-{profile_id}'


def doc_text(item, brief):
    """What the semantic search matches against: the listing as a shopper would describe it, plus what they asked for."""
    store = item.get('retailer') or item.get('seller') or item.get('source')
    parts = [item['title'], f"from {store}" if store else '', f"{item['price']:g} {item['currency']}",
             item.get('condition') or '', item.get('brand') or '', item.get('reason') or '', f'searched for: {brief}']
    return '. '.join(p for p in parts if p)[:1000]


class Finds:
    def __init__(self, settings, store: Store, sdk=None):
        self.settings, self.store = settings, store
        self.on = bool(settings.moss_project_id and settings.moss_project_key)
        self.sdk = sdk  # an inferedge_moss.MossClient, created on first recall when the package is installed
        self.indexed: set[str] = set()  # search ids already sent (Moss upserts, so a restart only re-sends)
        self.indexes: set[str] = set()  # index names known to exist
        self.loaded: set[str] = set()  # indexes the SDK holds in memory, current as of their last load
        self.loading: dict[str, asyncio.Task] = {}  # loads in flight; they outlive a timed-out recall
        self.tasks: set[asyncio.Task] = set()

    async def manage(self, action, **body):
        async with httpx.AsyncClient(transport=transport, timeout=20) as client:
            response = await client.post(f'{self.settings.moss_url}/manage',
                headers={'X-Project-Key': self.settings.moss_project_key},
                json={'action': action, 'projectId': self.settings.moss_project_id, **body})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def remember_soon(self, profile_id, search_id):
        """Index a search's results in the background so the chat reply isn't held up."""
        if not self.on or not search_id or search_id in self.indexed:
            return
        task = asyncio.create_task(self.remember(profile_id, search_id))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def remember(self, profile_id, search_id):
        job, request = self.store.get(search_id), self.request(search_id)
        if not job or job.get('status') not in DONE or request.get('profile_id') != profile_id or search_id in self.indexed:
            return
        brief = (request.get('request') or {}).get('query', '')
        docs = [{'id': f"{search_id}:{item['id']}", 'text': doc_text(item, brief),
                 'metadata': {'search_id': search_id, 'listing_id': item['id']}}
                for item in (job.get('results') or [])[:24]]
        self.indexed.add(search_id)
        if not docs:
            return
        name = index_name(profile_id)
        try:
            if name not in self.indexes and await self.manage('getIndex', indexName=name) is None:
                await self.manage('createIndex', indexName=name, docs=docs, modelId='moss-minilm')
            else:
                await self.manage('addDocs', indexName=name, docs=docs, options={'upsert': True})
            self.indexes.add(name)
            self.loaded.discard(name)  # the SDK's in-memory copy is now out of date
            self.store.event(profile_id, 'moss_indexed', {'search_id': search_id, 'docs': len(docs)})
        except (httpx.HTTPError, ValueError) as err:
            self.indexed.discard(search_id)  # try again on the next turn
            log.warning('moss indexing failed for %s: %s', search_id, err)

    async def recall(self, profile_id, text, skip_search=None, top_k=5) -> list[dict]:
        """Earlier listings that match what the shopper just said, newest information from the stored search."""
        if not self.on or not text.strip():
            return []
        try:
            hits = await asyncio.wait_for(self._query(index_name(profile_id), text, top_k + 3), RECALL_SECONDS)
        except Exception as err:  # Moss is a nice-to-have: never fail the chat turn over it
            log.warning('moss recall failed: %s', err)
            return []
        found, seen = [], set()
        for hit in hits:
            meta = hit.get('metadata') or {}
            search_id, listing_id = meta.get('search_id'), meta.get('listing_id')
            if not search_id or search_id == skip_search or (search_id, listing_id) in seen:
                continue
            item = self.listing(profile_id, search_id, listing_id)
            if item:
                seen.add((search_id, listing_id))
                found.append({**item, 'search_id': search_id, 'score': hit.get('score')})
            if len(found) == top_k:
                break
        return found

    def listing(self, profile_id, search_id, listing_id):
        # Server-side truth: the listing as stored with that search, and only from this shopper's own searches.
        job = self.store.get(search_id)
        if not job or self.request(search_id).get('profile_id') != profile_id:
            return None
        return next((x for x in job.get('results') or [] if x['id'] == listing_id), None)

    def request(self, search_id):
        with self.store.connect() as db:
            row = db.execute('SELECT request FROM jobs WHERE id=?', (search_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    async def _query(self, name, text, top_k):
        if name not in self.indexes:
            if await self.manage('getIndex', indexName=name) is None:
                return []
            self.indexes.add(name)
        sdk = self._sdk()
        if sdk:
            from inferedge_moss import QueryOptions
            if name not in self.loaded:
                # A first load takes a few seconds, longer than RECALL_SECONDS. Shielded, it finishes in the
                # background when this turn gives up, so the next turn finds the index ready.
                if name not in self.loading:
                    self.loading[name] = asyncio.create_task(self._load(sdk, name))
                await asyncio.shield(self.loading[name])
            result = await sdk.query(name, text, QueryOptions(top_k=top_k))
            return [{'id': d.id, 'metadata': d.metadata, 'score': d.score} for d in result.docs]
        async with httpx.AsyncClient(transport=transport, timeout=RECALL_SECONDS) as client:
            response = await client.post(f'{self.settings.moss_url}/query', json={
                'query': text, 'indexName': name, 'topK': top_k,
                'projectId': self.settings.moss_project_id, 'projectKey': self.settings.moss_project_key})
        response.raise_for_status()
        return response.json().get('docs', [])

    async def _load(self, sdk, name):
        try:
            await sdk.load_index(name)
            self.loaded.add(name)
        finally:
            self.loading.pop(name, None)

    def _sdk(self):
        if self.sdk is None:
            try:
                from inferedge_moss import MossClient
            except ImportError:
                self.sdk = False
            else:
                self.sdk = MossClient(self.settings.moss_project_id, self.settings.moss_project_key)
        return self.sdk or None
