import logging
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
import json
from finance.budget import Budgets
from finance.nessie import NessieError
from sourcing.store import Store

log = logging.getLogger(__name__)
STRIPE = 'https://api.stripe.com/v1/'


class IntentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    search_id: str
    listing_id: str


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    payment_intent_id: str


def create_router(settings, store: Store, budgets: Budgets):
    router = APIRouter(prefix='/v1/checkout', tags=['checkout'])

    def stripe():
        return httpx.AsyncClient(base_url=STRIPE, auth=(settings.stripe_secret_key, ''), timeout=20)

    def listing(search_id, listing_id):
        # Price comes from the stored search result, never from the browser.
        job = store.get(search_id)
        item = next((x for x in (job or {}).get('results', []) if x['id'] == listing_id), None)
        if not item:
            raise HTTPException(404, 'Listing is not a result of this search')
        return item

    @router.post('/intents', status_code=201)
    async def intent(body: IntentRequest):
        item = listing(body.search_id, body.listing_id)
        amount = round(item['price'] * 100)
        summary = {'listing_id': item['id'], 'title': item['title'], 'amount': amount, 'currency': item['currency']}
        if not settings.stripe_secret_key:
            return {**summary, 'mode': 'fixture', 'client_secret': None}
        if item.get('is_fixture') and not settings.stripe_secret_key.startswith('sk_test_'):
            raise HTTPException(409, 'Synthetic fixture items can only be bought with a Stripe test key')
        async with stripe() as client:
            response = await client.post('payment_intents', data={
                'amount': amount, 'currency': item['currency'].lower(),
                'automatic_payment_methods[enabled]': 'true',
                'metadata[search_id]': body.search_id, 'metadata[listing_id]': item['id'],
                'metadata[listing_url]': item['url'][:500]})
            response.raise_for_status()
            data = response.json()
        return {**summary, 'mode': 'stripe', 'payment_intent_id': data['id'], 'client_secret': data['client_secret']}

    @router.post('/confirm')
    async def confirm(body: ConfirmRequest):
        # The browser's success redirect is not proof of payment; re-read the PaymentIntent server-side.
        if not settings.stripe_secret_key:
            raise HTTPException(409, 'Stripe is not configured')
        async with stripe() as client:
            response = await client.get(f'payment_intents/{body.payment_intent_id}')
            response.raise_for_status()
            data = response.json()
        if data['status'] != 'succeeded':
            return {'status': data['status'], 'ledger': None}
        store.event(data['metadata'].get('search_id', ''), 'purchase',
            {'payment_intent_id': data['id'], 'listing_id': data['metadata'].get('listing_id'), 'amount': data['amount']})
        item = listing(data['metadata'].get('search_id', ''), data['metadata'].get('listing_id', ''))
        return {'status': 'succeeded', 'ledger': await record(data['metadata'].get('search_id', ''), item)}

    def profile_for(search_id):
        with store.connect() as db:
            row = db.execute('SELECT request FROM jobs WHERE id=?', (search_id,)).fetchone()
        return json.loads(row[0]).get('profile_id') if row else None

    async def record(search_id, item):
        # Agentic-finance: mirror the purchase into the shopper's (mock) bank so the agent's budget updates.
        profile_id = profile_for(search_id)
        if not profile_id:
            return None
        store_name = item.get('retailer') or item.get('seller') or item['source']
        try:
            return await budgets.record_purchase(profile_id, store_name, item['price'], item['title'][:80])
        except (NessieError, OSError) as exc:
            log.warning('nessie purchase failed: %s', exc)
            return {'provider': 'nessie', 'error': type(exc).__name__}

    @router.post('/demo-purchase')
    async def demo_purchase(body: IntentRequest):
        # Without Stripe there is no real payment; record a clearly labelled demo purchase in the mock bank so
        # the budget-aware agent can be shown reacting to it.
        if settings.stripe_secret_key:
            raise HTTPException(409, 'Stripe is configured; use the real checkout')
        item = listing(body.search_id, body.listing_id)
        ledger = await record(body.search_id, item)
        if not ledger or 'error' in ledger:
            raise HTTPException(409, 'No linked bank account for this profile (run python -m finance.seed)')
        return {'status': 'demo', 'ledger': ledger}

    return router
