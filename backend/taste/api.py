import asyncio
import hashlib
import secrets
import logging
import httpx
from typing import Annotated, Literal
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import UnidentifiedImageError
from sourcing.models import SearchRequest, ShoppingRequest
from finance.budget import Budgets
from sourcing import safe_fetch
from sourcing.prefetch import BROAD_QUERY, Prefetcher
from sourcing.features import clean as clean_features
from sourcing.store import Store
from sourcing.webshops import WebShops
from actors.niche_actors.indie_shops import SHOPS as INDIE_SHOPS
import json
from .chat import ChatRequest, ShopAgent, find_cards, guess_category, result_cards, search_sizes
from .finds import Finds
from .fit import inches, suggest
from .sizing import CATALOG
from .imports import Importer, LinkError
from .nearby import Nearby, NearbyError
from .links import extract_urls, read_link
from .engine import TasteEngine, fingerprint
from .models import EditInstruction, ImageFromUrl, ImageKind, ImportRequest, Measurements, LookbookNotes, NoteUpdate, Onboarding, PhotoReaction, ProfileSearch, PromptUpdate, ShopRequest
from . import brands, shops
from .signing import Signer
from .store import TasteStore

log = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_SHOPS = 30
LOOKUPS_PER_BUILD = 10  # favorite brands looked up for a store per build; the rest wait for the next one


def create_router(settings, store: Store, budgets: Budgets | None = None, signer: Signer | None = None):
    taste = TasteStore(store)
    signer = signer or Signer(settings)
    engine = TasteEngine(settings, taste)
    prefetcher = Prefetcher(settings, store)
    nearby = Nearby(settings)
    importer = Importer(settings, taste, engine)
    web = WebShops(settings)
    router = APIRouter(prefix='/v1/taste', tags=['taste'])

    def profile_or_404(ident):
        profile = taste.profile(ident)
        if not profile:
            raise HTTPException(404, 'Profile not found')
        return profile

    def board_id(profile):
        # The live (SpacetimeDB) board key: shared by owner and friends, but it doesn't reveal the profile id.
        return hashlib.sha256(f'board:{profile.id}'.encode()).hexdigest()[:20]

    def view(profile):
        images = taste.images(profile.id)
        # up_to_date: built, and nothing in the lookbook or preferences changed since, so Build can just show it.
        return {'profile': profile.model_dump(mode='json'),
                'images': [signer.image(x.model_dump(mode='json')) for x in images],
                'board_id': board_id(profile),
                'up_to_date': bool(profile.version and profile.built_from == fingerprint(profile, images))}

    def first_name(profile):
        return (profile.onboarding.name.split() or [''])[0][:40]

    def shared_view(profile):
        """What a friend with the share link sees: the board (clusters, palette, summary, photos) and a first name.
        Not the profile id, email, age, sizes, measurements, budget, notes, ZIP or bank."""
        keep = {'version', 'summary', 'clusters', 'colors', 'silhouettes', 'patterns', 'materials', 'designers',
                'aesthetics', 'avoid', 'mode', 'updated_at'}
        public = profile.model_dump(mode='json', include=keep)
        public.update(id='', prompt='', onboarding={**Onboarding().model_dump(mode='json'), 'name': first_name(profile)})
        images = [signer.image({**x.model_dump(mode='json', exclude={'analysis'}), 'profile_id': '', 'note': ''})
                  for x in taste.images(profile.id)]
        return {'profile': public, 'images': images, 'board_id': board_id(profile), 'up_to_date': True}

    def shared_or_404(token):
        profile = taste.by_share_token(token)
        if not profile:
            raise HTTPException(404, 'This link was turned off or never existed')
        return profile

    @router.get('/sizing/catalog')
    def sizing_catalog():
        # The onboarding page draws its size pickers from this, so the charts live in one place (taste/sizing.py).
        return CATALOG

    @router.post('/sizes/suggest')
    def suggest_sizes(measurements: Measurements, system: Literal['womens', 'mens'] = 'womens'):
        # Live preview on the onboarding form: what sizes these measurements point to.
        return suggest(measurements, system).model_dump()

    @router.post('/profiles', status_code=201)
    def create(onboarding: Onboarding):
        return view(taste.create_profile(onboarding))

    @router.get('/profiles/{ident}')
    def get(ident: str):
        return view(profile_or_404(ident))

    @router.delete('/profiles/{ident}', status_code=204)
    async def forget(ident: str):
        # Delete my data: photo files first, then every record tied to the profile, then the live (SpacetimeDB) copy.
        # The mock bank (Nessie) keeps its own demo transactions; Niche only drops the link to it.
        profile_or_404(ident)
        for image in taste.images(ident):
            engine.remove_image_file(image.id)
        board = board_id(profile_or_404(ident))
        taste.forget(ident)
        await engine.publish.forget_profile(ident)
        await engine.publish.forget_profile(board)  # the live board is keyed by board_id(...), not the profile id

    @router.put('/profiles/{ident}/onboarding')
    def onboarding(ident: str, onboarding: Onboarding):
        profile = profile_or_404(ident)
        profile.onboarding = onboarding
        return view(taste.save_profile(profile))

    @router.post('/profiles/{ident}/images', status_code=201)
    async def upload(ident: str, file: Annotated[UploadFile, File()], kind: Annotated[ImageKind, Form()] = 'outfit',
                     note: Annotated[str, Form(max_length=1000)] = ''):
        profile_or_404(ident)
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, 'Image larger than 15 MB')
        try:
            return signer.image(engine.add_image(ident, data, kind, note).model_dump(mode='json'))
        except (UnidentifiedImageError, OSError):
            raise HTTPException(422, 'Unsupported image')

    @router.post('/profiles/{ident}/react')
    async def react(ident: str, body: PhotoReaction):
        """The assistant's one-line reaction to photos just added ("Ooh, I'm sensing a 90s minimal thing")."""
        profile = profile_or_404(ident)
        images = [x for x in (taste.image(i) for i in body.image_ids) if x and x.profile_id == ident]
        if not images:
            raise HTTPException(404, 'Photos not found')
        return {'text': await engine.react(profile, images)}

    @router.put('/profiles/{ident}/notes')
    def lookbook_notes(ident: str, body: LookbookNotes):
        # "Can't find the right pic? Leave a short note": these feed the next build like photos do.
        profile = profile_or_404(ident)
        profile.lookbook_notes = body.notes
        return view(taste.save_profile(profile))

    @router.post('/profiles/{ident}/imports', status_code=202)
    async def start_import(ident: str, body: ImportRequest):
        # Public Pinterest boards/profiles and Instagram profiles, via Bright Data; photos arrive in the background.
        # Async so the background task starts on the server's event loop.
        profile_or_404(ident)
        try:
            return importer.start(ident, body.url).model_dump(mode='json')
        except LinkError as exc:
            raise HTTPException(422, str(exc))

    @router.get('/profiles/{ident}/imports')
    def imports(ident: str):
        profile_or_404(ident)
        return [x.model_dump(mode='json') for x in importer.jobs(ident)]

    @router.post('/profiles/{ident}/images/from-url', status_code=201)
    async def image_from_url(ident: str, body: ImageFromUrl):
        # A pasted or dragged web image that arrived as an address rather than a file ("Copy image" on some sites).
        profile_or_404(ident)
        async with safe_fetch.client() as http:
            fetched = await safe_fetch.fetch(http, body.url, MAX_UPLOAD_BYTES)
        if not fetched:
            raise HTTPException(422, "Couldn't load that image. Try saving it and adding it from your computer.")
        try:
            return signer.image(engine.add_image(ident, fetched[0], body.kind).model_dump(mode='json'))
        except (UnidentifiedImageError, OSError):
            raise HTTPException(422, "That link isn't an image. Copy the image itself, or paste a page link above.")

    @router.put('/images/{ident}/note')
    async def note(ident: str, update: NoteUpdate):
        # Long-press details ("I like the color, not the frills"). Clears analysis so the next build re-reads it.
        image = taste.image(ident)
        if not image:
            raise HTTPException(404, 'Image not found')
        image.note, image.analysis = update.note, None
        saved = taste.save_image(image)
        engine.read_soon(saved)
        return signer.image(saved.model_dump(mode='json'))

    @router.delete('/images/{ident}', status_code=204)
    def delete(ident: str):
        engine.remove_image_file(ident)
        taste.delete_image(ident)

    @router.post('/profiles/{ident}/build')
    async def build(ident: str):
        profile = profile_or_404(ident)
        if not profile.onboarding.data_consent:
            raise HTTPException(403, 'Agree to send your photos to Claude on your Profile page first')
        try:
            profile = await engine.build(profile)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        profile = await find_favorite_shops(profile)
        # Start scraping this taste's core pieces now, so the first search has results ready to rank.
        prefetcher.start(search_request(profile, ProfileSearch(query=BROAD_QUERY)))
        return view(profile)

    async def find_favorite_shops(profile):
        # Favorite brands that sell from their own Shopify store get searched directly from then on (taste/shops.py).
        have = {x.domain for x in profile.indie_shops}
        names = [b for b in profile.onboarding.favorite_brands if b.strip().lower() not in profile.shop_lookups]
        names = names[:LOOKUPS_PER_BUILD]
        if not names or len(profile.indie_shops) >= MAX_SHOPS:
            return profile
        found = [x for x in await shops.find_many(names) if x.domain not in have]
        for shop in await asyncio.gather(*(brands.verify(x) for x in found)):
            if shop.domain not in have and len(profile.indie_shops) < MAX_SHOPS:
                have.add(shop.domain)
                profile.indie_shops.append(shop)
        profile.shop_lookups = list(dict.fromkeys(profile.shop_lookups + [n.strip().lower() for n in names]))[-100:]
        return await engine.save(profile)

    @router.post('/profiles/{ident}/shops', status_code=201)
    async def add_shop(ident: str, body: ShopRequest):
        profile = profile_or_404(ident)
        if len(profile.indie_shops) >= MAX_SHOPS:
            raise HTTPException(422, f'You can add up to {MAX_SHOPS} shops; remove one first')
        shop = await shops.find(body.shop, any_platform=web.enabled)
        if not shop:
            raise HTTPException(422, "Couldn't find an online shop Niche can read for that. Try pasting the brand's "
                                     "website" + ("." if web.enabled else
                                     " (Niche can read shops built on Shopify, which most small labels use)."))
        if all(x.domain != shop.domain for x in profile.indie_shops):
            profile.indie_shops.append(await brands.verify(shop))
            profile = await engine.save(profile)
        return view(profile)

    discovered = {}  # (profile id, version, its shops) -> suggestions, so reopening the page doesn't ask again

    @router.get('/profiles/{ident}/brands/suggestions')
    async def brand_suggestions(ident: str):
        # Independent labels close to this taste; only ones that pass every check in taste/brands.py are listed.
        profile = built_profile(ident)
        key = (profile.id, profile.version, tuple(sorted(x.domain for x in profile.indie_shops)))
        if key not in discovered:
            if settings.taste_mode == 'live':
                found = await brands.discover(engine.model, profile, profile.id)
            else:  # no Claude: Niche's own seed list of labels, checked the same way
                have = {x.domain for x in profile.indie_shops}
                found = await brands.verified_only([(x['domain'], "From Niche's list of independent labels")
                                                    for x in INDIE_SHOPS[:brands.SUGGESTIONS]], have)
            discovered[key] = [{'shop': shop.model_dump(mode='json'), 'reason': reason} for shop, reason in found]
        return {'suggestions': discovered[key]}

    @router.delete('/profiles/{ident}/shops/{domain}')
    async def remove_shop(ident: str, domain: str):
        profile = profile_or_404(ident)
        profile.indie_shops = [x for x in profile.indie_shops if x.domain != domain.lower()]
        return view(await engine.save(profile))

    @router.post('/profiles/{ident}/edit')
    async def edit(ident: str, edit: EditInstruction):
        return view(await engine.edit(profile_or_404(ident), edit.instruction, edit.source))

    @router.put('/profiles/{ident}/prompt')
    async def prompt(ident: str, update: PromptUpdate):
        profile = profile_or_404(ident)
        taste.event(ident, 'profile_edit', {'source': 'manual', 'prompt': update.prompt})
        profile.prompt, profile.version = update.prompt, profile.version + 1
        return view(await engine.save(profile))

    def built_profile(ident):
        profile = profile_or_404(ident)
        if not (profile.prompt or profile.summary):
            raise HTTPException(422, 'Build the taste profile first')
        return profile

    def search_request(profile, search: ProfileSearch, for_friend=False):
        # Hand-off to the sourcing pipeline: the taste prompt becomes the SearchRequest's taste_profile.
        ob = profile.onboarding
        sources = list(search.sources)
        if 'indie' in sources and 'web' not in sources and web.enabled:
            sources.append('web')  # independent labels on any platform, through Bright Data
        return SearchRequest(taste_profile=profile.to_sourcing(), sources=sources, limit=search.limit,
            profile_id=profile.id, for_friend=for_friend,
            # A gift search has no cap unless the friend shopping names one (the owner's own budget isn't theirs).
            request=ShoppingRequest(query=search.query,
                max_item_price=search.max_item_price or (10000 if for_friend else ob.budget_max),
                currency=ob.currency, size=search.size, length=search.length, measurements=inches(ob.measurements),
                shoe_size_system=search.shoe_size_system, size_note=search.size_note,
                must_have=clean_features(search.must_have), brands=[b.strip()[:40] for b in search.brands if b.strip()][:3],
                category=search.category if search.category not in (None, 'other') else guess_category(search.query)))

    def start_search(profile, search: ProfileSearch, for_friend=False):
        job = store.create(search_request(profile, search, for_friend).model_dump(mode='json'))
        ob = profile.onboarding
        if not for_friend and ob.nearby_shops and ob.zip_code and nearby.enabled:  # the friend's ZIP stays private
            nearby.warm(ob.zip_code, search.query)  # Shops near you, looked up alongside the search
        return {'search_id': job, 'status': 'queued', 'status_url': f'/v1/searches/{job}'}

    @router.post('/profiles/{ident}/searches', status_code=202)
    async def search(ident: str, search: ProfileSearch):
        return start_search(built_profile(ident), search)

    agent = ShopAgent(settings, engine.model)
    finds = Finds(settings, store)  # earlier finds in Moss, for "the green one from before"

    def on_screen(ident, search_id):
        # Loaded server-side (not sent by the browser), and only for this profile's own searches.
        if not search_id:
            return None
        with store.connect() as db:
            row = db.execute('SELECT request FROM jobs WHERE id=?', (search_id,)).fetchone()
        if not row or json.loads(row[0]).get('profile_id') != ident:
            return None
        return result_cards(store.get(search_id))

    @router.get('/profiles/{ident}/nearby')
    async def nearby_shops(ident: str, search_id: str):
        # Opt-in only: the shopper's ZIP and this search's brief go to Gemini (Google Maps grounding), nothing else.
        profile = profile_or_404(ident)
        ob = profile.onboarding
        if not (ob.nearby_shops and ob.zip_code and nearby.enabled):
            return {'enabled': False, 'shops': []}
        with store.connect() as db:
            row = db.execute('SELECT request FROM jobs WHERE id=?', (search_id,)).fetchone()
        request = json.loads(row[0]) if row else {}
        if request.get('profile_id') != ident:
            raise HTTPException(404, 'Search not found')
        try:
            shops = await nearby.shops(ob.zip_code, request['request']['query'])
        except (NearbyError, httpx.HTTPError, ValueError) as exc:
            log.warning('nearby shops unavailable: %s', exc)
            return {'enabled': True, 'shops': [], 'unavailable': True}
        return {'enabled': True, 'zip_code': ob.zip_code, 'shops': shops}

    @router.get('/profiles/{ident}/budget')
    async def budget(ident: str):
        profile_or_404(ident)
        snap = await budgets.snapshot(ident) if budgets else None
        return {'linked': snap is not None, **(snap.model_dump() if snap else {})}

    def plan(profile, turn, chat, out, budget=None, steer=None, for_friend=False):
        """Sizes, price cap, must-haves and brands for a proposed or run search; starts it when the agent searches."""
        if turn.action in ('propose', 'search'):
            # Unless the user named a size, search in their saved size for this kind of garment.
            category = turn.category if turn.category != 'other' else guess_category(turn.brief)
            fit = search_sizes(profile, category, turn.brief)
            out.update(fit, category=category)
            if turn.size:  # a size the user named in the conversation wins
                out.update(size=turn.size, size_note=f'Size {turn.size}, as asked')
            price = turn.max_item_price
            said = ' '.join(m.text for m in chat.messages if m.role == 'user')
            if price and budget and not steer and round(price) == round(budget.remaining) and str(round(price)) not in said:
                price = None  # "Keep to budget" is off: don't carry over an earlier budget cap the shopper never typed
            if price is None and steer and steer.remaining >= 1:
                # The agent should set a cap itself; if it didn't, keep the search inside what's left this month.
                price = min(profile.onboarding.budget_max, steer.remaining)
            out['max_item_price'] = price
            out['must_have'] = clean_features(turn.must_have)
            out['brands'] = [b.strip()[:40] for b in turn.brands if b.strip()][:3]
        if turn.action == 'search':
            out.update(start_search(profile, ProfileSearch(query=turn.brief, max_item_price=out['max_item_price'],
                                                           size=out['size'], length=out['length'],
                                                           shoe_size_system=out['shoe_size_system'],
                                                           size_note=out['size_note'],
                                                           must_have=out['must_have'], category=out['category'],
                                                           brands=out['brands']), for_friend))
        return out

    @router.post('/profiles/{ident}/chat')
    async def chat(ident: str, chat: ChatRequest):
        # One conversational turn: a clarifying question, or a refined search over the whole conversation.
        if chat.messages[-1].role != 'user':
            raise HTTPException(422, 'The last message must be from the user')
        profile = built_profile(ident)
        budget = await budgets.snapshot(ident) if budgets else None
        urls = extract_urls(chat.messages[-1].text)
        linked = list(await asyncio.gather(*map(read_link, urls))) if urls else None
        # The monthly budget shapes searches only when the shopper switches it on; the strip shows either way.
        steer = budget if chat.use_budget else None
        results = on_screen(ident, chat.search_id)
        if results is not None:
            finds.remember_soon(ident, chat.search_id)  # what's on screen now becomes an earlier find
        earlier = await finds.recall(ident, chat.messages[-1].text, skip_search=chat.search_id)
        turn = await agent.respond(profile, chat.messages, steer, results, linked,
                                   **({'earlier': find_cards(earlier)} if earlier else {}))
        out = {'reply': turn.reply, 'action': turn.action, 'brief': turn.brief,
               'budget': budget.model_dump() if budget else None}
        by_ref = {f'E{n}': x for n, x in enumerate(earlier, start=1)}
        if recalled := [by_ref[r] for r in dict.fromkeys(turn.recall) if r in by_ref][:5]:
            out['recalled'] = [{'title': x['title'], 'url': x['url'], 'price': x['price'], 'currency': x['currency'],
                                'store': x.get('retailer') or x.get('seller') or x['source']} for x in recalled]
        if linked:
            out['linked'] = [{'url': x.url, 'site': x.site, 'title': x.title, 'readable': x.readable} for x in linked]
        return plan(profile, turn, chat, out, budget, steer)

    # ---- Sharing: a friend with the link sees the board and can shop for the owner (gift chat) ----

    @router.post('/profiles/{ident}/share')
    def share(ident: str):
        profile = profile_or_404(ident)
        if not profile.share_token:
            profile.share_token = secrets.token_urlsafe(12)
            taste.save_profile(profile)
        return {'token': profile.share_token}

    @router.delete('/profiles/{ident}/share', status_code=204)
    def unshare(ident: str):
        # Stop sharing: every link handed out stops working at once.
        profile = profile_or_404(ident)
        profile.share_token = ''
        taste.save_profile(profile)

    @router.get('/shared/{token}')
    def shared(token: str):
        return shared_view(shared_or_404(token))

    @router.post('/shared/{token}/chat')
    async def gift_chat(token: str, chat: ChatRequest):
        # Shopping for the owner, by a friend: the owner's taste and sizes, the friend's price. No bank, no earlier
        # finds, no nearby shops, and nothing about the owner beyond their first name comes back.
        if chat.messages[-1].role != 'user':
            raise HTTPException(422, 'The last message must be from the user')
        profile = shared_or_404(token)
        if not (profile.prompt or profile.summary):
            raise HTTPException(422, "Their taste profile isn't built yet")
        urls = extract_urls(chat.messages[-1].text)
        linked = list(await asyncio.gather(*map(read_link, urls))) if urls else None
        name = first_name(profile) or 'your friend'
        turn = await agent.respond(profile, chat.messages, None, on_screen(profile.id, chat.search_id), linked,
                                   recipient=name)
        out = {'reply': turn.reply, 'action': turn.action, 'brief': turn.brief, 'budget': None}
        if linked:
            out['linked'] = [{'url': x.url, 'site': x.site, 'title': x.title, 'readable': x.readable} for x in linked]
        out = plan(profile, turn, chat, out, for_friend=True)
        for private in ('size', 'size_note', 'length', 'shoe_size_system'):
            out.pop(private, None)  # the search uses their size; the friend shopping doesn't need to see it
        return out

    return router
