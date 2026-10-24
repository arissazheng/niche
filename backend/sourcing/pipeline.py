import asyncio
import re
from .models import Listing
from .sources import NICHE, ApifySources, FixtureSources
from .claude import Claude
from .live import Live
from . import risk, sizes


# Never shown, from any source (new, mainstream or resale): Shein and its in-house labels, and Fashion Nova.
EXCLUDED_BRANDS = re.compile(r'\b(shein|romwe|dazy|motf|emery rose|fashion ?nova)\b', re.I)
EXCLUDED_DOMAINS = ('shein.com', 'romwe.com', 'fashionnova.com')


def excluded(item):
    host = re.sub(r'^https?://', '', item.url).split('/')[0].lower()
    if any(host == d or host.endswith('.' + d) for d in EXCLUDED_DOMAINS):
        return True
    fields = (item.retailer, item.seller, item.brand, item.title)
    return any(f and EXCLUDED_BRANDS.search(f) for f in fields)


def eligible(items, request, left_out=None):
    """Listings that pass the hard filters. left_out, when given, tallies why others were dropped (shown to the shopper)."""
    result, seen = [], set()
    r = request.request

    def tally(reason):
        if left_out is not None:
            left_out[reason] = left_out.get(reason, 0) + 1

    for item in items:
        if item.id in seen or item.url in seen:
            continue
        seen.update((item.id,item.url))
        if excluded(item):
            tally('excluded_brand')
            continue
        if item.available is False:
            tally('sold')
            continue
        if item.currency != r.currency:
            continue
        if item.price > r.max_item_price:
            tally('over_price')
            continue
        unknown = []
        if item.available is None:
            unknown.append('Availability unverified')
        if r.size:
            fits = sizes.match(r.size, item.sizes)
            if fits is False:
                tally('wrong_size')
                continue
            if fits is None:
                unknown.append(f'Size unverified (listed as {", ".join(item.sizes)})' if item.sizes else 'Size unverified')
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


STOPWORDS = {'and', 'the', 'for', 'with', 'find', 'some', 'something', 'like', 'that', 'this', 'please', 'want',
             'need', 'looking', 'everyday'}


def terms(text):
    return {w.rstrip('s') for w in re.findall(r'[a-z]+', text.lower()) if len(w) > 2 and w not in STOPWORDS}


# Item types a search can ask for. When the request names one, only listings of that type are shown before ranking.
ITEM_TYPES = {
    'outerwear': r'jackets?|coats?|blazers?|parkas?|puffers?|trench|anoraks?|windbreakers?|bombers?|shackets?|gilets?|vests?',
    'knit': r'cardigans?|sweaters?|jumpers?|pullovers?|hoodies?|sweatshirts?|shrugs?|boleros?',
    'top': r'tops?|shirts?|tees?|t-shirts?|blouses?|tanks?|camis?|camisoles?|halters?|bodysuits?|polos?|corsets?|bustiers?',
    'dress': r'dress(es)?|gowns?|jumpsuits?|rompers?',
    'bottom': r'pants|jeans|trousers|skirts?|shorts|leggings|slacks|culottes',
    'shoes': r'boots?|shoes?|sneakers?|heels?|flats?|loafers?|sandals?|mules?|clogs?|pumps?|trainers?',
    'bag': r'bags?|purses?|totes?|clutch(es)?|backpacks?|handbags?|wallets?',
    'accessory': r'belts?|hats?|caps?|beanies?|scarf|scarves|jewel(le)?ry|necklaces?|earrings?|rings?|bracelets?|sunglasses',
}
COLOURS = {'black', 'white', 'grey', 'gray', 'charcoal', 'navy', 'blue', 'red', 'green', 'brown', 'beige', 'cream',
           'pink', 'purple', 'yellow', 'orange', 'silver', 'gold', 'tan', 'olive', 'ivory', 'burgundy'}


# The chat agent's categories, as item types above.
CATEGORY_TYPES = {'top': {'top', 'knit'}, 'outerwear': {'outerwear', 'knit'}, 'dress': {'dress'}, 'bottom': {'bottom'},
                  'shoes': {'shoes'}, 'accessory': {'bag', 'accessory'}}


def requested_types(request):
    """Item types the search is for: the agent's category when it gave one, else the item words in the query."""
    return CATEGORY_TYPES.get(request.category or '') or item_types(request.query)


def item_types(text):
    return {kind for kind, words in ITEM_TYPES.items() if re.search(rf'\b({words})\b', text, re.I)}


def same_item(listing, wanted_types):
    """True when the listing's title is the kind of item asked for (or the request named no item type)."""
    return not wanted_types or bool(item_types(listing.title) & wanted_types)


def has_features(listing, must_have):
    """True when the photo-tagged features include at least one the request needs (or it needs none)."""
    return not must_have or bool(set(listing.features) & set(must_have))


def matching(listings, query, wanted_types=None):
    """Prefetched listings for this search: the requested item type ("jacket" lets in coats and parkas, not corsets),
    or with no type named, a shared word other than a colour ("black" alone isn't a match)."""
    wanted_types = wanted_types if wanted_types is not None else item_types(query)
    if wanted_types:
        return [x for x in listings if same_item(x, wanted_types)]
    wanted = terms(query) - COLOURS
    return [x for x in listings if wanted & terms(x.title)]


def lexical_score(item, request):
    text = (item.title+' '+item.description).lower()
    query_terms = set(re.findall(r'\w+',request.request.query.lower())) - {'find','me','a','some','everyday','please'}
    profile = request.taste_profile
    positive = profile.colors + profile.silhouettes + profile.materials
    labels = ' '.join(x for x in (item.brand, item.retailer, item.seller) if x).lower()
    preferred = sum(t.lower() in text or t.lower() in labels for t in profile.preferred_brands + profile.preferred_stores)
    return max(0,min(100, 20 + 15*sum(t in text for t in query_terms) + 10*sum(t.lower() in text for t in positive)
        + 10*min(preferred, 1) - 30*sum(t.lower() in text for t in profile.avoid)))


# Each source (new from stores, secondhand) with good matches gets at least this share of the results, so one side
# can't crowd out the other just by returning more listings. Better fits still rank first within the list.
MIX_FLOOR = 0.25
GOOD_FIT = 50
RELEVANT = 40  # Claude scores below this miss the request (wrong item, or none of its defining features)


def copy_key(item):
    """Same marketplace, title and price: one item posted several times (often from look-alike accounts)."""
    return (item.marketplace or item.source, re.sub(r'[^a-z0-9]', '', item.title.lower())[:80], round(item.price, 2))


def diversify(items, limit):
    counts, capped, copies = {}, [], {}
    for item in items:
        copies[copy_key(item)] = copies.get(copy_key(item), 0) + 1
    shown = set()
    for item in sorted(items,key=lambda x: x.score or 0,reverse=True):
        if copy_key(item) in shown:
            continue  # keep the best-ranked copy only
        shown.add(copy_key(item))
        item.copies = copies[copy_key(item)]
        key = (item.source,item.seller or item.id)
        if counts.get(key,0)>=2:
            continue
        counts[key] = counts.get(key,0)+1
        capped.append(item)
    selected = capped[:limit]
    floor = int(limit*MIX_FLOOR)
    for source in dict.fromkeys(x.source for x in capped):
        chosen = {id(x) for x in selected}
        missing = floor - sum(x.source==source for x in selected)
        extra = [x for x in capped if x.source==source and id(x) not in chosen and (x.score or 0)>=GOOD_FIT][:max(0,missing)]
        for item in extra:
            others = [x for x in selected if x.source!=source]
            biggest = max({x.source for x in others}, key=lambda s: sum(x.source==s for x in selected), default=None)
            if biggest is None or sum(x.source==biggest for x in selected) <= floor:
                break
            selected.remove(min((x for x in selected if x.source==biggest), key=lambda x: x.score or 0))
            selected.append(item)
    return sorted(selected,key=lambda x: x.score or 0,reverse=True)

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
        live_args = (job_id, '' if request.for_friend else request.profile_id or '', request.request.query)
        await self.live.search(*live_args, 'running')
        # One bounded run per marketplace for MVP. Rotate query variants across marketplaces.
        sources = list(dict.fromkeys(request.sources))
        if not request.request.allow_secondhand and len(sources) > 1:
            # New-only requests skip the resale actor's paid runs; condition filtering still applies below.
            sources = [s for s in sources if s != 'secondhand']
        async def batches(source, query):
            args = (source,query,request.candidates_per_source,job_id,request.request.max_item_price)
            named = {'brands': request.request.brands} if request.request.brands else {}  # older test doubles lack it
            if source in ('indie', 'web') and request.taste_profile.indie_shops:
                named['shops'] = request.taste_profile.indie_shops  # the shopper's own independent shops
            if hasattr(self.sources,'stream'):
                async for batch in self.sources.stream(*args, **named):
                    yield batch
            else:
                yield await self.sources.fetch(*args, **named)

        # Each batch is filtered, shortlisted and ranked as soon as it arrives, so Claude ranks the fast
        # sources (and the fast marketplaces inside the secondhand actor) while the slow ones are still scraping.
        # Each source can fill the whole page on its own: mainstream often keeps only a handful of results.
        per_source = max(request.limit,24//len(sources))
        counts = {'retrieved':0,'eligible':0,'left_out':{},'max_item_price':request.request.max_item_price}
        seen_urls, ranked, provisional, methods, rankers = set(), [], {}, [], []

        def scored_rows():
            # Claude-ranked items that don't match the request are dropped rather than padding the page.
            relevant = [x for x in ranked if not x.match_dimensions or (x.score or 0) >= RELEVANT]
            shown = risk.flag(diversify(relevant,request.limit))  # price warnings compare against this page
            return [{**x.model_dump(mode='json'), 'rank': i+1} for i,x in enumerate(shown)]

        async def publish():
            waiting = [x for rows in provisional.values() for x in rows]
            # Also saved on the job, so a page polling without SpacetimeDB sees results as they're ranked.
            result['results'] = scored_rows()+waiting
            self.store.update(job_id,'running',result)
            await self.live.listings(job_id, result['results'], replace=True)

        async def rank_batch(key, batch):
            source = key[0]
            if self.settings.sourcing_mode=='live':
                try:
                    batch = await self.model.rank(request,batch,job_id)
                    methods.append('claude')
                except Exception as exc:
                    self.store.event(job_id,'ranking_failed',{'source':source,'type':type(exc).__name__,'detail':str(exc)[:200]})
                    methods.append('lexical_fallback')
                    lexical(batch)
            else:
                methods.append('fixture_lexical')
                lexical(batch)
            ranked.extend(batch)
            provisional.pop(key,None)
            await publish()

        def lexical(batch):
            for item in batch:
                item.score = lexical_score(item,request)
                item.match_dimensions = {}
                item.reason = 'Text keyword overlap only; visual taste matching has not been evaluated.'

        shortlisted = set()

        async def take(source, items):
            candidates = [x for x in eligible(items,request,counts['left_out']) if x.url not in seen_urls]
            seen_urls.update(x.url for x in candidates)
            counts['retrieved'] += len(items)
            counts['eligible'] += len(candidates)
            # Cheap lexical shortlist limits image-token consumption. A source's later batches (each marketplace in
            # the secondhand actor, e.g. Etsy arriving last) get half a page each, so late arrivals are still ranked.
            room = per_source if source not in shortlisted else max(6, per_source//2)
            batch = sorted(candidates,key=lambda x:lexical_score(x,request),reverse=True)[:room]
            if batch:
                shortlisted.add(source)
                key = (source, len(rankers))
                # Live listings have no feature labels yet, so they appear only once Claude has ranked them: a short
                # wait beats showing pieces that merely share a colour with the request.
                rankers.append(asyncio.create_task(rank_batch(key,batch)))

        async def consume(source, query):
            try:
                async for items, status in batches(source, query):
                    result['sources'][source] = status
                    await take(source, items)
                    self.store.update(job_id,'running',result)
            except Exception as exc:
                self.store.event(job_id,'source_failed',{'source':source,'type':type(exc).__name__})
                result['sources'][source] = {'status':'failed','error':'Source unavailable; see server events'}

        # Listings scraped and scored in the background when the profile was built (sourcing.prefetch) show at once.
        if request.profile_id:
            ready = [x for x in eligible(matching([Listing.model_validate(x) for x in
                     self.store.prefetched(request.profile_id)], request.request.query,
                     requested_types(request.request)), request)
                     if x.url not in seen_urls]
            for x in ready:
                x.warnings = list(dict.fromkeys(x.warnings))  # eligible() re-adds warnings saved with the item
            if ready:
                seen_urls.update(x.url for x in ready)
                result['prefetched'] = len(ready)
                # Their saved scores judged the taste in general, not this request ("top" also matched corsets), so
                # they show straight away as unranked and are re-ranked against the actual search.
                batch = sorted(ready,key=lambda x:lexical_score(x,request),reverse=True)[:per_source]
                key = ('prefetched', len(rankers))
                # Shown before ranking only when the request named must-have features and the warm-up's photo labels
                # include one; otherwise these wait for ranking like everything else (no guessing from colours).
                must_have = request.request.must_have
                provisional[key] = [x.model_dump(mode='json') for x in batch
                                    if must_have and has_features(x, must_have)][:8]
                await publish()
                rankers.append(asyncio.create_task(rank_batch(key,batch)))
        # Niche actors take every query variant in one run; single-marketplace adapters rotate through them.
        tasks = [asyncio.create_task(consume(s,queries if s in NICHE else queries[i%len(queries)]))
                 for i,s in enumerate(sources)]
        try:
            await asyncio.gather(*tasks)
            await asyncio.gather(*rankers)
        finally:
            for task in tasks+rankers:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks,*rankers,return_exceptions=True)
        result['counts'] = counts
        if methods:
            if 'lexical_fallback' in methods:
                result['warnings'].append('Claude ranking unavailable for some results; lexical fallback used')
            result['ranking_method'] = ('claude' if set(methods)=={'claude'} else
                                        'fixture_lexical' if 'fixture_lexical' in methods else 'lexical_fallback')
            result['results'] = scored_rows()  # same relevance floor and scam checks as the streamed pages
        # Replace the provisional rows with the final ranked set (or none).
        await self.live.listings(job_id, [{**x, 'rank': i+1} for i,x in enumerate(result['results'])], replace=True)
        failures = sum(x['status']=='failed' for x in result['sources'].values())
        status = 'failed' if failures==len(sources) else 'partial' if failures or result['warnings'] else 'completed'
        self.store.update(job_id,status,result)
        await self.live.search(*live_args, status, result.get('ranking_method', ''), result['warnings'])
        return result
