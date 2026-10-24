"""Warm-up searches: when a taste profile is built, scrape and rank its core pieces in the background.

Nothing is shown to the user. The listings are kept for a few hours, already scored against the taste profile; a
later search for a matching item shows them straight away (see Pipeline.run) while its own live scrape is still
running. Ranking ahead of time matters as much as scraping: Claude takes ~15 s to rank a page of photos.
"""
import asyncio
from .claude import Claude
from .pipeline import eligible, lexical_score
from .sources import ApifySources

RANKED_PER_SOURCE = 24  # two Claude pages per source

BROAD_QUERY = 'the core wardrobe pieces and accessories this taste profile is built around'


class Prefetcher:
    def __init__(self, settings, store, sources=None, model=None):
        self.settings, self.store = settings, store
        self.sources = sources or ApifySources(settings, store)
        self.model = model or Claude(settings, store)
        self.running = set()

    def start(self, request):
        """Fire and forget; one warm-up per profile at a time."""
        if self.settings.sourcing_mode != 'live' or not request.profile_id or request.profile_id in self.running:
            return None
        self.running.add(request.profile_id)
        task = asyncio.create_task(self.warm(request))
        task.add_done_callback(lambda _: self.running.discard(request.profile_id))
        return task

    async def warm(self, request):
        job = f'prefetch:{request.profile_id}'
        try:
            queries = await self.model.plan(request, job)
            mine = request.taste_profile.indie_shops
            results = await asyncio.gather(*(self.sources.fetch(source, queries, request.candidates_per_source, job,
                                                                request.request.max_item_price,
                                                                **({'shops': mine} if source in ('indie', 'web') and mine else {}))
                                             for source in request.sources), return_exceptions=True)
            listings = [x for r in results if not isinstance(r, BaseException) for x in r[0]]
            kept = eligible(listings, request)
            pages = []
            for source in request.sources:
                best = sorted((x for x in kept if x.source == source), key=lambda x: lexical_score(x, request),
                              reverse=True)[:RANKED_PER_SOURCE]
                pages += [best[i:i+12] for i in range(0, len(best), 12)]
            ranked = await asyncio.gather(*(self.model.rank(request, page, job, tag=True) for page in pages), return_exceptions=True)
            scored = [x for page in ranked if not isinstance(page, BaseException) for x in page]
            self.store.save_prefetch(request.profile_id, [x.model_dump(mode='json') for x in scored])
            self.store.event(job, 'prefetched', {'queries': queries, 'kept': len(kept), 'ranked': len(scored),
                'failed': [s for s, r in zip(request.sources, results) if isinstance(r, BaseException)]})
        except Exception as exc:
            self.store.event(job, 'prefetch_failed', {'type': type(exc).__name__, 'detail': str(exc)[:200]})
