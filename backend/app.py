"""Single API process: sourcing (prior Person 3 service) + taste engine + checkout."""
import hmac
from pathlib import Path
from fastapi import Depends, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from sourcing.api import create_app as create_sourcing_app
from sourcing.config import Settings
from sourcing.store import Store
from taste.api import create_router as taste_router
from checkout.api import create_router as checkout_router


def create_app(settings=None):
    settings = settings or Settings()
    app = create_sourcing_app(settings)
    store = Store(settings.database_path)

    def authorize(x_api_key: str | None = Header(default=None)):
        if settings.sourcing_api_key and not hmac.compare_digest(x_api_key or '', settings.sourcing_api_key):
            raise HTTPException(401, 'Invalid API key')

    app.include_router(taste_router(settings, store), dependencies=[Depends(authorize)])
    app.include_router(checkout_router(settings, store), dependencies=[Depends(authorize)])
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    app.mount('/uploads', StaticFiles(directory=settings.upload_dir), name='uploads')
    return app
