import logging
from datetime import date
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sourcing.store import Store

log = logging.getLogger(__name__)
STRIPE = 'https://api.stripe.com/v1/'
NESSIE = 'http://api.nessieisreal.com/'


class IntentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    search_id: str
    listing_id: str


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    payment_intent_id: str


def create_router(settings, store: Store):
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
        return {'status': 'succeeded', 'ledger': await mirror_to_nessie(data)}

    async def mirror_to_nessie(intent):
        # Agentic-finance demo: record the purchase against a Capital One Nessie mock account.
        # TODO(checkout owner): verify request shape against the live Nessie docs before the demo.
        if not (settings.nessie_api_key and settings.nessie_account_id and settings.nessie_merchant_id):
            return None
        try:
            async with httpx.AsyncClient(base_url=NESSIE, timeout=10) as client:
                response = await client.post(f'accounts/{settings.nessie_account_id}/purchases',
                    params={'key': settings.nessie_api_key},
                    json={'merchant_id': settings.nessie_merchant_id, 'medium': 'balance',
                          'purchase_date': date.today().isoformat(), 'amount': intent['amount'] / 100,
                          'description': f"listing {intent['metadata'].get('listing_id', '')}"[:100]})
                response.raise_for_status()
                return {'provider': 'nessie', 'response': response.json()}
        except httpx.HTTPError as exc:
            log.warning('nessie mirror failed: %s', type(exc).__name__)
            return {'provider': 'nessie', 'error': type(exc).__name__}

    return router
