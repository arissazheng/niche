from typing import Annotated
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import UnidentifiedImageError
from sourcing.models import SearchRequest, ShoppingRequest
from sourcing.store import Store
from .chat import ChatRequest, ShopAgent
from .engine import TasteEngine
from .models import EditInstruction, ImageKind, NoteUpdate, Onboarding, ProfileSearch, PromptUpdate
from .store import TasteStore

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def create_router(settings, store: Store):
    taste = TasteStore(store)
    engine = TasteEngine(settings, taste)
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
        try:
            return view(await engine.build(profile_or_404(ident)))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

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

    def start_search(profile, search: ProfileSearch):
        # Hand-off to the sourcing pipeline: the taste prompt becomes the SearchRequest's taste_profile.
        ob = profile.onboarding
        request = SearchRequest(taste_profile=profile.to_sourcing(), sources=search.sources, limit=search.limit,
            profile_id=profile.id,
            request=ShoppingRequest(query=search.query, max_item_price=search.max_item_price or ob.budget_max,
                currency=ob.currency, size=search.size))
        job = store.create(request.model_dump(mode='json'))
        return {'search_id': job, 'status': 'queued', 'status_url': f'/v1/searches/{job}'}

    @router.post('/profiles/{ident}/searches', status_code=202)
    def search(ident: str, search: ProfileSearch):
        return start_search(built_profile(ident), search)

    agent = ShopAgent(settings, engine.model)

    @router.post('/profiles/{ident}/chat')
    async def chat(ident: str, chat: ChatRequest):
        # One conversational turn: a clarifying question, or a refined search over the whole conversation.
        if chat.messages[-1].role != 'user':
            raise HTTPException(422, 'The last message must be from the user')
        profile = built_profile(ident)
        turn = await agent.respond(profile, chat.messages)
        out = {'reply': turn.reply, 'action': turn.action, 'brief': turn.brief}
        if turn.action == 'search':
            out.update(start_search(profile, ProfileSearch(query=turn.brief, max_item_price=turn.max_item_price,
                                                           size=turn.size)))
        return out

    return router
