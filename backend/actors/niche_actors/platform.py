"""Apify platform I/O: read INPUT, push rows to the default dataset, save a run summary as OUTPUT.

Handlers may push rows while they run (the backend reads the dataset during the run), then return the rest.

Run locally with a JSON file instead: python -m niche_actors.mainstream input.json
"""
import asyncio
import json
import os
import sys

from .core import client


async def read_input():
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            return json.load(f)
    async with client() as http:
        response = await http.get(f'key-value-stores/{os.environ["APIFY_DEFAULT_KEY_VALUE_STORE_ID"]}/records/INPUT')
        response.raise_for_status()
        return response.json()


async def push(rows):
    if rows and len(sys.argv) == 1:
        async with client() as http:
            response = await http.post(f'datasets/{os.environ["APIFY_DEFAULT_DATASET_ID"]}/items', json=rows)
            response.raise_for_status()


async def write_output(rows, summary):
    if len(sys.argv) > 1:
        print(json.dumps({**summary, 'results': rows}, indent=1))
        return
    async with client() as http:
        response = await http.put(
            f'key-value-stores/{os.environ["APIFY_DEFAULT_KEY_VALUE_STORE_ID"]}/records/OUTPUT', json=summary)
        response.raise_for_status()


def run(handler):
    async def main():
        pushed = []

        async def stream(rows):
            await push(rows)
            pushed.extend(rows)
        rows, summary = await handler(await read_input(), stream)
        await push(rows[len(pushed):])  # streamed rows come first, in the order they were pushed
        await write_output(rows, summary)
        print(json.dumps(summary))
        if summary['sources'] and all(s['status'] == 'failed' for s in summary['sources'].values()):
            raise SystemExit('All marketplaces failed; see OUTPUT')
    asyncio.run(main())
