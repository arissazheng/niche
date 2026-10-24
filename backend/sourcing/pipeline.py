import asyncio
import re
from .sources import NICHE, ApifySources, FixtureSources
from .claude import Claude
from .live import Live


def eligible(items, request):
    result, seen = [], set()
    r = request.request
    for item in items:
        if item.id in seen or item.url in seen:
            continue
        seen.update((item.id,item.url))
        if item.available is False or item.currency != r.currency or item.price > r.max_item_price:
            continue
        unknown = []
        if item.available is None:
            unknown.append('Availability unverified')
        if r.size:
            if not item.sizes:
                unknown.append('Size unverified')
            elif r.size.casefold() not in [x.casefold() for x in item.sizes]:
                continue
        if not r.allow_secondhand:
            if item.condition is None:
                unknown.append('Condition unverified')
            elif item.condition.lower() not in ('new','new with tags','nwt','new/never worn'):
                continue
        if item.ships_to is None:
            unknown.append('Shipping destination unverified')
        elif r.ship_to_country not in item.ships_to:
            continue
        if unknown and r.unknown_policy == 'exclude':
            continue
        item.warnings.extend(unknown)
        if item.shipping_cost is None:
            item.warnings.append('Shipping and tax not included in item price')
        result.append(item)
    return result


def lexical_score(item, request):
    text = (item.title+' '+item.description).lower()
    query_terms = set(re.findall(r'\w+',request.request.query.lower())) - {'find','me','a','some','everyday','please'}
    profile = request.taste_profile
    positive = profile.colors + profile.silhouettes + profile.materials
    labels = ' '.join(x for x in (item.brand, item.retailer, item.seller) if x).lower()
    preferred = sum(t.lower() in text or t.lower() in labels for t in profile.preferred_brands + profile.preferred_stores)
    return max(0,min(100, 20 + 15*sum(t in text for t in query_terms) + 10*sum(t.lower() in text for t in positive)
        + 10*min(preferred, 1) - 30*sum(t.lower() in text for t in profile.avoid)))


def diversify(items, limit):
    counts, selected = {}, []
    for item in sorted(items,key=lambda x: x.score or 0,reverse=True):
        key = (item.source,item.seller or item.id)
        if counts.get(key,0)>=2:
            continue
        counts[key] = counts.get(key,0)+1
        selected.append(item)
        if len(selected)>=limit:
            break
    return selected

class Pipeline:
    def __init__(self, settings, store, sources=None, model=None, live=None):
        self.settings,self.store = settings,store
        self.sources = sources or (FixtureSources() if settings.sourcing_mode=='fixture' else ApifySources(settings,store))
        self.model = model or Claude(settings,store)
        self.live = live or Live(settings)

    async def run(self, request, job_id):
        result = {'mode':self.settings.sourcing_mode,'sources':{},'results':[],'warnings':[]}
        self.store.update(job_id,'running',result)
        queries = [request.request.query]
        if self.settings.sourcing_mode=='live':
            try:
                queries = await self.model.plan(request,job_id)
            except Exception as exc:
                self.store.event(job_id,'planner_failed',{'type':type(exc).__name__})
                result['warnings'].append('Query planning failed; searched the original request')
        result['queries'] = queries
        live_args = (job_id, request.profile_id or '', request.request.query)
        await self.live.search(*live_args, 'running')
        # One bounded run per marketplace for MVP. Rotate query variants across marketplaces.
        sources = list(dict.fromkeys(request.sources))
        if not request.request.allow_secondhand and len(sources) > 1:
            # New-only requests skip the resale actor's paid runs; condition filtering still applies below.
            sources = [s for s in sources if s != 'secondhand']
        async def fetch(source, query):
            try:
                items,status = await self.sources.fetch(source,query,request.candidates_per_source,job_id,
                                                        request.request.max_item_price)
                return source,items,status
            except Exception as exc:
                self.store.event(job_id,'source_failed',{'source':source,'type':type(exc).__name__})
                return source,[],{'status':'failed','error':'Source unavailable; see server events'}
        # Niche actors take every query variant in one run; single-marketplace adapters rotate through them.
        tasks = [asyncio.create_task(fetch(s,queries if s in NICHE else queries[i%len(queries)]))
                 for i,s in enumerate(sources)]
        collected = []
        try:
            for task in asyncio.as_completed(tasks):
                source,items,status = await task
                collected.extend(items)
                # Provisional rows so the UI fills in per marketplace; copies keep eligible() from
                # appending warnings to the items ranked below.
                await self.live.listings(job_id, eligible([x.model_copy(deep=True) for x in items], request)[:8])
                result['sources'][source] = status
                self.store.update(job_id,'running',result)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
        candidates = eligible(collected,request)
        result['counts'] = {'retrieved':len(collected),'eligible':len(candidates)}
        # Cheap lexical shortlist limits image-token consumption, balanced across sources.
        shortlist = []
        per_source = max(1,24//len(sources))
        for source in sources:
            shortlist.extend(sorted((x for x in candidates if x.source==source),
                key=lambda x:lexical_score(x,request),reverse=True)[:per_source])
        if shortlist:
            if self.settings.sourcing_mode=='live':
                try:
                    shortlist = await self.model.rank(request,shortlist,job_id)
                    result['ranking_method'] = 'claude'
                except Exception as exc:
                    self.store.event(job_id,'ranking_failed',{'type':type(exc).__name__})
                    result['warnings'].append('Claude ranking unavailable; lexical fallback used')
                    result['ranking_method'] = 'lexical_fallback'
            else:
                result['ranking_method'] = 'fixture_lexical'
            if result['ranking_method'] != 'claude':
                for item in shortlist:
                    item.score = lexical_score(item,request)
                    item.match_dimensions = {}
                    item.reason = 'Text keyword overlap only; visual taste matching has not been evaluated.'
            result['results'] = [x.model_dump(mode='json') for x in diversify(shortlist,request.limit)]
        # Replace the provisional rows with the final ranked set (or none).
        await self.live.listings(job_id, [{**x, 'rank': i+1} for i,x in enumerate(result['results'])], replace=True)
        failures = sum(x['status']=='failed' for x in result['sources'].values())
        status = 'failed' if failures==len(sources) else 'partial' if failures or result['warnings'] else 'completed'
        self.store.update(job_id,status,result)
        await self.live.search(*live_args, status, result.get('ranking_method', ''), result['warnings'])
        return result
