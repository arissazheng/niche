"""Apify entry point, using platform REST API and runtime environment."""
import asyncio
import json
import os
import httpx
from .config import Settings
from .models import SearchRequest
from .store import Store
from .pipeline import Pipeline

async def main():
    settings = Settings()
    settings.validate_live()
    token = settings.apify_token
    kv = os.environ['APIFY_DEFAULT_KEY_VALUE_STORE_ID']
    dataset = os.environ['APIFY_DEFAULT_DATASET_ID']
    async with httpx.AsyncClient(base_url='https://api.apify.com/v2/',
            headers={'Authorization':f'Bearer {token}'},timeout=60) as client:
        response = await client.get(f'key-value-stores/{kv}/records/INPUT')
        response.raise_for_status()
        request = SearchRequest.model_validate(response.json())
        store = Store(settings.database_path)
        ident = store.create(request.model_dump(mode='json'))
        await Pipeline(settings,store).run(request,ident)
        output = store.get(ident)
        response = await client.put(f'key-value-stores/{kv}/records/OUTPUT',json=output)
        response.raise_for_status()
        if output.get('results'):
            response = await client.post(f'datasets/{dataset}/items',json=output['results'])
            response.raise_for_status()
        if output['status']=='failed':
            raise RuntimeError('All sources failed; inspect OUTPUT')

if __name__ == '__main__':
    asyncio.run(main())
