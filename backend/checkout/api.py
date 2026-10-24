"""Purchases happen on the store's own site (Niche doesn't sell items). After buying there, the shopper marks the
item as bought so their budget and (mock) bank stay accurate for the shopping agent."""
import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from finance.budget import Budgets
from finance.nessie import NessieError
from sourcing.store import Store

log = logging.getLogger(__name__)


class MarkBought(BaseModel):
    model_config = ConfigDict(extra='forbid')
    search_id: str
    listing_id: str


def create_router(settings, store: Store, budgets: Budgets):
    router = APIRouter(prefix='/v1/checkout', tags=['checkout'])

    def listing(search_id, listing_id):
        # The price comes from the stored search result, never from the browser.
        job = store.get(search_id)
        item = next((x for x in (job or {}).get('results', []) if x['id'] == listing_id), None)
        if not item:
            raise HTTPException(404, 'Listing is not a result of this search')
        return item

    def profile_for(search_id):
        with store.connect() as db:
            row = db.execute('SELECT request FROM jobs WHERE id=?', (search_id,)).fetchone()
        return json.loads(row[0]).get('profile_id') if row else None

    def already_marked(search_id, listing_id):
        with store.connect() as db:
            rows = db.execute("SELECT payload FROM events WHERE job_id=? AND kind='purchase_marked'", (search_id,)).fetchall()
        return any(json.loads(r[0]).get('listing_id') == listing_id for r in rows)

    @router.post('/mark-bought')
    async def mark_bought(body: MarkBought):
        item = listing(body.search_id, body.listing_id)
        if already_marked(body.search_id, body.listing_id):
            return {'recorded': False, 'reason': 'already_marked'}
        profile_id = profile_for(body.search_id)
        store_name = item.get('retailer') or item.get('seller') or item['source']
        ledger = None
        if profile_id:
            try:
                ledger = await budgets.record_purchase(profile_id, store_name, item['price'], item['title'][:80])
            except (NessieError, OSError) as exc:
                log.warning('nessie purchase failed: %s', exc)
                raise HTTPException(502, "Couldn't reach your bank to record this purchase; try again")
        store.event(body.search_id, 'purchase_marked',
                    {'listing_id': item['id'], 'amount': item['price'], 'store': store_name, 'recorded': bool(ledger)})
        # ledger is None when the profile has no linked (mock) bank account: the purchase is noted, not budgeted.
        return {'recorded': bool(ledger), 'reason': None if ledger else 'no_linked_bank', 'ledger': ledger}

    return router
