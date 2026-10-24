"""Single API process: sourcing (prior Person 3 service) + taste engine + checkout + voice."""
import hmac
from pathlib import Path
from fastapi import Depends, Header, HTTPException
from fastapi.responses import FileResponse
from sourcing.api import create_app as create_sourcing_app
from sourcing.config import Settings
from sourcing.store import Store
from taste.api import create_router as taste_router
from taste.signing import Signer
from checkout.api import create_router as checkout_router
from finance.budget import Budgets
from voice.api import create_router as voice_router


def create_app(settings=None):
    settings = settings or Settings()
    app = create_sourcing_app(settings)
    store = Store(settings.database_path)

    def authorize(x_api_key: str | None = Header(default=None)):
        if settings.sourcing_api_key and not hmac.compare_digest(x_api_key or '', settings.sourcing_api_key):
            raise HTTPException(401, 'Invalid API key')

    budgets = Budgets(settings, store)  # the shopper's mock bank (Capital One Nessie)
    app.state.budgets = budgets
    signer = Signer(settings)
    app.include_router(taste_router(settings, store, budgets, signer), dependencies=[Depends(authorize)])
    app.include_router(checkout_router(settings, store, budgets), dependencies=[Depends(authorize)])
    app.include_router(voice_router(settings, store), dependencies=[Depends(authorize)])
    uploads = Path(settings.upload_dir)
    uploads.mkdir(parents=True, exist_ok=True)

    @app.get('/uploads/{name}', include_in_schema=False)
    def upload(name: str, exp: int = 0, sig: str = ''):
        # Lookbook photos need a signed, unexpired link (taste/signing.py); a bare or stale URL is refused.
        if not signer.valid(name, exp, sig) or not (uploads / name).is_file():
            raise HTTPException(404, 'Not found')
        return FileResponse(uploads / name, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=3600'})
    return app
