import argparse
import asyncio
import json
from pathlib import Path
from .config import Settings
from .models import SearchRequest
from .pipeline import Pipeline
from .store import Store

async def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    settings = Settings()
    settings.validate_live()
    request = SearchRequest.model_validate_json(args.input.read_text())
    store = Store(settings.database_path)
    ident = store.create(request.model_dump(mode='json'))
    await Pipeline(settings,store).run(request,ident)
    output = json.dumps(store.get(ident),indent=2)
    if args.output:
        args.output.write_text(output)
    else:
        print(output)

asyncio.run(run())
