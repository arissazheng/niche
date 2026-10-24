import asyncio
from typing import Annotated
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import UnidentifiedImageError
from sourcing.models import SearchRequest, ShoppingRequest
from finance.budget import Budgets
from sourcing.prefetch import BROAD_QUERY, Prefetcher
from sourcing.store import Store
import json
from .chat import ChatRequest, ShopAgent, guess_category, profile_size, result_cards
from .imports import Importer, LinkError
from .links import extract_urls, read_link
from .engine import TasteEngine
from .models import EditInstruction, ImageKind, ImportRequest, LookbookNotes, NoteUpdate, Onboarding, ProfileSearch, PromptUpdate
from .store import TasteStore

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def create_router(settings, store: Store, budgets: Budgets | None = None):
    taste = TasteStore(store)
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
        return {'profile': profile.model_dump(mode='json'),
                'images': [x.model_dump(mode='json') for x in taste.images(profile.id)]}

    @router.post('/profiles', status_code=201)
    def create(onboarding: Onboarding):
        return view(taste.create_profile(onboarding))

    @router.get('/profiles/{ident}')
    def get(ident: str):
        return view(profile_or_404(ident))

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
            return engine.add_image(ident, data, kind, note).model_dump(mode='json')
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

    @router.put('/images/{ident}/note')
    def note(ident: str, update: NoteUpdate):
        # Long-press details ("I like the color, not the frills"). Clears analysis so the next build re-reads it.
        image = taste.image(ident)
        if not image:
            raise HTTPException(404, 'Image not found')
        image.note, image.analysis = update.note, None
        return taste.save_image(image).model_dump(mode='json')

    @router.delete('/images/{ident}', status_code=204)
    def delete(ident: str):
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
                currency=ob.currency, size=search.size, length=search.length))

    def start_search(profile, search: ProfileSearch):
        job = store.create(search_request(profile, search).model_dump(mode='json'))
        return {'search_id': job, 'status': 'queued', 'status_url': f'/v1/searches/{job}'}

    @router.post('/profiles/{ident}/searches', status_code=202)
    def search(ident: str, search: ProfileSearch):
        return start_search(built_profile(ident), search)

    agent = ShopAgent(settings, engine.model)

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
        turn = await agent.respond(profile, chat.messages, budget, on_screen(ident, chat.search_id), linked)
        out = {'reply': turn.reply, 'action': turn.action, 'brief': turn.brief,
               'budget': budget.model_dump() if budget else None}
        if linked:
            out['linked'] = [{'url': x.url, 'site': x.site, 'title': x.title, 'readable': x.readable} for x in linked]
        if turn.action in ('propose', 'search'):
            # Unless the user named a size, search in their saved size for this kind of garment.
            category = turn.category if turn.category != 'other' else guess_category(turn.brief)
            out['size'] = turn.size or profile_size(profile, category)
            out['length'] = profile.onboarding.sizes.bottom_length if category == 'bottom' else None
            out['category'] = category
            price = turn.max_item_price
            if price is None and budget and budget.remaining >= 1:
                # The agent should set a cap itself; if it didn't, keep the search inside what's left this month.
                price = min(profile.onboarding.budget_max, budget.remaining)
            out['max_item_price'] = price
        if turn.action == 'search':
            out.update(start_search(profile, ProfileSearch(query=turn.brief, max_item_price=out['max_item_price'],
                                                           size=out['size'], length=out['length'])))
        return out

    return router
