import asyncio
from datetime import date, timedelta
from fastapi.testclient import TestClient
from app import create_app
from finance.budget import Budgets
from sourcing.config import Settings
from sourcing.store import Store


class FakeNessie:
    """In-memory stand-in matching the live API's shapes (see finance/nessie.py)."""
    def __init__(self):
        self.purchases_made, self.merchants = [], {}
        month = date.today().strftime('%Y-%m')
        self.rows = [
            {'merchant_id': 'm-depop', 'amount': 42, 'status': 'completed', 'purchase_date': f'{month}-01'},
            {'merchant_id': 'm-food', 'amount': 68, 'status': 'completed', 'purchase_date': f'{month}-01'},
            {'merchant_id': 'm-depop', 'amount': 53, 'status': 'cancelled', 'purchase_date': f'{month}-01'},
            {'merchant_id': 'm-depop', 'amount': 30, 'status': 'completed', 'purchase_date': '2020-01-01'},
        ]
        soon = (date.today() + timedelta(days=3)).isoformat()
        later = (date.today() + timedelta(days=40)).isoformat()
        self.bill_rows = [{'status': 'pending', 'nickname': 'Rent', 'payment_amount': 1200.0, 'payment_date': soon},
                          {'status': 'pending', 'nickname': 'Insurance', 'payment_amount': 90.0, 'payment_date': later}]

    async def account(self, account_id):
        return {'_id': account_id, 'balance': 1000}

    async def purchases(self, account_id):
        return self.rows

    async def bills(self, account_id):
        return self.bill_rows

    async def merchant(self, merchant_id):
        return {'m-depop': {'category': 'clothing'}, 'm-food': {'category': 'groceries'}}.get(
            merchant_id, {'category': self.merchants.get(merchant_id, '')})

    async def create_merchant(self, name, category):
        ident = f'm-{name.lower()}'
        self.merchants[ident] = category
        return {'_id': ident}

    async def create_purchase(self, account_id, merchant_id, amount, date_, description, status='completed'):
        row = {'merchant_id': merchant_id, 'amount': round(amount), 'status': status,
               'purchase_date': date_, '_id': f'p{len(self.rows)}'}
        self.rows.append(row)
        return row


def budgets_for(tmp_path):
    settings = Settings(database_path=str(tmp_path/'f.sqlite'), nessie_api_key='k')
    budgets = Budgets(settings, Store(settings.database_path))
    budgets.nessie = FakeNessie()
    return budgets


def test_snapshot_counts_this_months_clothing_and_upcoming_bills(tmp_path):
    budgets = budgets_for(tmp_path)
    assert asyncio.run(budgets.snapshot('p1')) is None  # not linked
    budgets.save_link('p1', 'c1', 'a1', 150)
    snap = asyncio.run(budgets.snapshot('p1'))
    # Only this month's non-cancelled clothing purchases count; Nessie never deducts, so balance = 1000 - live purchases.
    assert snap.month_spent == 42 and snap.remaining == 108 and snap.balance == 1000 - 42 - 68 - 30
    assert [b.payee for b in snap.upcoming_bills] == ['Rent']


def test_recorded_purchase_updates_budget(tmp_path):
    budgets = budgets_for(tmp_path)
    budgets.save_link('p1', 'c1', 'a1', 150)
    asyncio.run(budgets.snapshot('p1'))
    ledger = asyncio.run(budgets.record_purchase('p1', 'Depop2', 49.6, 'skirt'))
    assert ledger['amount'] == 50
    assert asyncio.run(budgets.snapshot('p1')).month_spent == 92  # cache cleared, new merchant categorised


def test_chat_caps_search_at_remaining_budget_and_demo_purchase(tmp_path):
    import io
    from PIL import Image
    settings = Settings(database_path=str(tmp_path/'api.sqlite'), upload_dir=str(tmp_path/'u'), nessie_api_key='k')
    app = create_app(settings)
    with TestClient(app) as client:
        budgets = app.state.budgets
        budgets.nessie = FakeNessie()
        pid = client.post('/v1/taste/profiles', json={'budget_max': 80}).json()['profile']['id']
        out = io.BytesIO(); Image.new('RGB', (40, 40), (10, 10, 10)).save(out, format='PNG')
        client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', out.getvalue())})
        client.post(f'/v1/taste/profiles/{pid}/build')
        assert client.get(f'/v1/taste/profiles/{pid}/budget').json() == {'linked': False}
        budgets.save_link(pid, 'c1', 'a1', 100)  # 42 spent -> 58 left, below the profile's 80 default
        assert client.get(f'/v1/taste/profiles/{pid}/budget').json()['remaining'] == 58
        first = [{'role': 'user', 'text': 'black skirt'}]
        proposal = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': first}).json()
        assert proposal['action'] == 'propose' and proposal['max_item_price'] == 58 and proposal['budget']['remaining'] == 58
        accepted = first + [{'role': 'agent', 'text': proposal['reply'], 'proposed': proposal['brief'],
                             'proposed_price': proposal['max_item_price']}, {'role': 'user', 'text': 'yes'}]
        reply = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': accepted}).json()
        assert reply['action'] == 'search' and reply['max_item_price'] == 58
        search = client.get(reply['status_url']).json()
        for _ in range(40):
            if search['status'] in ('completed', 'partial'):
                break
            import time; time.sleep(.05); search = client.get(reply['status_url']).json()
        item = search['results'][0]
        bought = client.post('/v1/checkout/mark-bought', json={'search_id': reply['search_id'], 'listing_id': item['id']})
        assert bought.status_code == 200 and bought.json()['recorded'] and bought.json()['ledger']['provider'] == 'nessie'
        assert client.get(f'/v1/taste/profiles/{pid}/budget').json()['month_spent'] == 42 + round(item['price'])
