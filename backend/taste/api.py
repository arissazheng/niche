import asyncio
from typing import Annotated, Literal
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import UnidentifiedImageError
from sourcing.models import SearchRequest, ShoppingRequest
from finance.budget import Budgets
from sourcing import safe_fetch
from sourcing.prefetch import BROAD_QUERY, Prefetcher
from sourcing.features import clean as clean_features
from sourcing.store import Store
import json
from .chat import ChatRequest, ShopAgent, find_cards, guess_category, result_cards, search_sizes
from .finds import Finds
from .fit import inches, suggest
from .sizing import CATALOG
from .imports import Importer, LinkError
from .links import extract_urls, read_link
from .engine import TasteEngine, fingerprint
from .models import EditInstruction, ImageFromUrl, ImageKind, ImportRequest, Measurements, LookbookNotes, NoteUpdate, Onboarding, ProfileSearch, PromptUpdate
from .signing import Signer
from .store import TasteStore

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def create_router(settings, store: Store, budgets: Budgets | None = None, signer: Signer | None = None):
    taste = TasteStore(store)
    signer = signer or Signer(settings)
    engine = TasteEngine(settings, taste)
    prefetcher = Prefetcher(settings, store)
    importer = Importer(settings, taste, engine)
    router = APIRouter(prefix='/v1/taste', tags=['taste'])

    def profile_or_404(ident):
        profile = taste.profile(ident)
        if not profile:
            raise HTTPException(404, 'Profile not found')
        return profile

    def view(profile):
        images = taste.images(profile.id)
        # up_to_date: built, and nothing in the lookbook or preferences changed since, so Build can just show it.
        return {'profile': profile.model_dump(mode='json'),
                'images': [signer.image(x.model_dump(mode='json')) for x in images],
                'up_to_date': bool(profile.version and profile.built_from == fingerprint(profile, images))}

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
        taste.forget(ident)
        await engine.publish.forget_profile(ident)

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
        # Start scraping this taste's core pieces now, so the first search has results ready to rank.
        prefetcher.start(search_request(profile, ProfileSearch(query=BROAD_QUERY)))
        return view(profile)

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

    def search_request(profile, search: ProfileSearch):
        # Hand-off to the sourcing pipeline: the taste prompt becomes the SearchRequest's taste_profile.
        ob = profile.onboarding
        return SearchRequest(taste_profile=profile.to_sourcing(), sources=search.sources, limit=search.limit,
            profile_id=profile.id,
            request=ShoppingRequest(query=search.query, max_item_price=search.max_item_price or ob.budget_max,
                currency=ob.currency, size=search.size, length=search.length, measurements=inches(ob.measurements),
                shoe_size_system=search.shoe_size_system, size_note=search.size_note,
                must_have=clean_features(search.must_have),
                category=search.category if search.category not in (None, 'other') else guess_category(search.query)))

    def start_search(profile, search: ProfileSearch):
        job = store.create(search_request(profile, search).model_dump(mode='json'))
        return {'search_id': job, 'status': 'queued', 'status_url': f'/v1/searches/{job}'}

    @router.post('/profiles/{ident}/searches', status_code=202)
    def search(ident: str, search: ProfileSearch):
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

    @router.get('/profiles/{ident}/budget')
    async def budget(ident: str):
        profile_or_404(ident)
        snap = await budgets.snapshot(ident) if budgets else None
        return {'linked': snap is not None, **(snap.model_dump() if snap else {})}

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
        if turn.action in ('propose', 'search'):
            # Unless the user named a size, search in their saved size for this kind of garment.
            category = turn.category if turn.category != 'other' else guess_category(turn.brief)
            fit = search_sizes(profile, category, turn.brief)
            out.update(fit, category=category)
            if turn.size:  # a size the user named in the conversation wins
                out.update(size=turn.size, size_note=f'Size {turn.size}, as asked')
            price = turn.max_item_price
            if price is None and steer and steer.remaining >= 1:
                # The agent should set a cap itself; if it didn't, keep the search inside what's left this month.
                price = min(profile.onboarding.budget_max, steer.remaining)
            out['max_item_price'] = price
            out['must_have'] = clean_features(turn.must_have)
        if turn.action == 'search':
            out.update(start_search(profile, ProfileSearch(query=turn.brief, max_item_price=out['max_item_price'],
                                                           size=out['size'], length=out['length'],
                                                           shoe_size_system=out['shoe_size_system'],
                                                           size_note=out['size_note'],
                                                           must_have=out['must_have'], category=out['category'])))
        return out

    return router
