import asyncio
import hmac
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .config import Settings
from .models import SearchRequest, Feedback
from .pipeline import Pipeline
from .store import Store

logging.basicConfig(level=logging.INFO)


def create_app(settings=None):
    settings = settings or Settings()
    settings.validate_live()
    store = Store(settings.database_path)
    from market.service import Market  # here, not at module top: market imports sourcing.pipeline
    market = Market(settings)
    pipeline = Pipeline(settings,store,market=market if market.enabled else None)

    async def run(ident, payload):
        try:
            await pipeline.run(SearchRequest.model_validate_json(payload),ident)
        except asyncio.CancelledError:
            store.update(ident,'interrupted',{'warnings':['Service stopped; submit a new search']})
            raise
        except Exception as exc:
            store.event(ident,'job_failed',{'type':type(exc).__name__})
            store.update(ident,'failed',{'warnings':['Pipeline failed; see server events']})

    running = set()

    async def worker():
        # Searches run side by side: one person's slow search must not hold up anyone else's.
        while True:
            for ident,payload in store.pending():
                store.update(ident,'running',{})  # claimed, so the next poll doesn't start it twice
                task = asyncio.create_task(run(ident,payload))
                running.add(task)
                task.add_done_callback(running.discard)
            await asyncio.sleep(.25)

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        task = asyncio.create_task(worker())
        yield
        for t in (task,*running):
            t.cancel()
        await asyncio.gather(task,*running,return_exceptions=True)

    app = FastAPI(title='Taste Sourcing API',version='0.1.0',lifespan=lifespan)
    app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,
        allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Content-Type','X-API-Key'])

    def authorize(x_api_key: str | None = Header(default=None)):
        if settings.sourcing_api_key and not hmac.compare_digest(x_api_key or '',settings.sourcing_api_key):
            raise HTTPException(401,'Invalid API key')

    @app.get('/health')
    def health():
        return {'status':'ok','mode':settings.sourcing_mode}

    @app.post('/v1/searches',status_code=202,dependencies=[Depends(authorize)])
    def search(request: SearchRequest):
        ident = store.create(request.model_dump(mode='json'))
        return {'search_id':ident,'status':'queued','status_url':f'/v1/searches/{ident}'}

    @app.get('/v1/searches/{ident}',dependencies=[Depends(authorize)])
    def get(ident: str):
        job = store.get(ident)
        if not job:
            raise HTTPException(404,'Search not found')
        return job

    @app.get('/v1/searches/{ident}/listings/{listing_id}/price-check',dependencies=[Depends(authorize)])
    async def price_check(ident: str, listing_id: str):
        # Snowflake market check: how this price compares with similar listings seen before (public data only).
        job = store.get(ident)
        item = next((x for x in (job or {}).get('results', []) if x['id'] == listing_id), None)
        if not item:
            raise HTTPException(404,'Listing is not a result of this search')
        return await market.price_check(ident,item)

    @app.post('/v1/searches/{ident}/feedback',status_code=201,dependencies=[Depends(authorize)])
    def feedback(ident: str, feedback: Feedback):
        job = store.get(ident)
        if not job:
            raise HTTPException(404,'Search not found')
        if feedback.listing_id not in {x['id'] for x in job.get('results',[])}:
            raise HTTPException(422,'Listing is not a result of this search')
        store.feedback(ident,feedback.model_dump())
        return {'saved':True}

    return app
