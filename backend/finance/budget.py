"""The shopper's money picture from their (mock) bank: balance, clothing spend this month, upcoming bills.

A profile is linked to one Nessie checking account (see finance/seed.py). The shopping agent reads a short
snapshot each chat turn so it can keep searches inside the monthly clothing budget and flag bills due soon.
"""
import asyncio
import logging
import time
from datetime import date, timedelta
from pydantic import BaseModel
from sourcing.store import Store, now
from .nessie import Nessie, NessieError

log = logging.getLogger(__name__)
CLOTHING = 'clothing'
CACHE_SECONDS = 60
BILL_HORIZON_DAYS = 14


class Bill(BaseModel):
    payee: str
    amount: float
    due: str


class BudgetSnapshot(BaseModel):
    balance: float
    monthly_budget: float
    month_spent: float
    remaining: float
    upcoming_bills: list[Bill]


class Budgets:
    def __init__(self, settings, store: Store):
        self.nessie = Nessie(settings.nessie_api_key) if settings.nessie_api_key else None
        self.store = store
        self._cache: dict[str, tuple[float, BudgetSnapshot]] = {}
        self._categories: dict[str, str] = {}
        with store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS bank_links (profile_id TEXT PRIMARY KEY, customer_id TEXT, account_id TEXT,
                monthly_budget REAL, created_at TEXT);
            CREATE TABLE IF NOT EXISTS nessie_merchants (name TEXT PRIMARY KEY, merchant_id TEXT);
            ''')

    def link(self, profile_id):
        with self.store.connect() as db:
            row = db.execute('SELECT customer_id, account_id, monthly_budget FROM bank_links WHERE profile_id=?',
                             (profile_id,)).fetchone()
        return None if row is None else {'customer_id': row[0], 'account_id': row[1], 'monthly_budget': row[2]}

    def save_link(self, profile_id, customer_id, account_id, monthly_budget):
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO bank_links VALUES (?,?,?,?,?)',
                       (profile_id, customer_id, account_id, monthly_budget, now()))
        self._cache.pop(profile_id, None)

    async def snapshot(self, profile_id) -> BudgetSnapshot | None:
        """None when Nessie isn't configured, the profile isn't linked, or the bank is unreachable."""
        link = self.link(profile_id)
        if not (self.nessie and link):
            return None
        cached = self._cache.get(profile_id)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
        try:
            snap = await self._read(link)
        except (NessieError, OSError) as exc:
            log.warning('nessie snapshot failed: %s', exc)
            return cached[1] if cached else None
        self._cache[profile_id] = (time.monotonic(), snap)
        return snap

    async def _read(self, link) -> BudgetSnapshot:
        account, purchases, bills = await asyncio.gather(self.nessie.account(link['account_id']),
            self.nessie.purchases(link['account_id']), self.nessie.bills(link['account_id']))
        live = [p for p in purchases if p.get('status') != 'cancelled']
        await asyncio.gather(*(self._category(p['merchant_id']) for p in live))
        month = date.today().strftime('%Y-%m')
        spent = sum(p['amount'] for p in live if self._categories.get(p['merchant_id']) == CLOTHING
                    and str(p.get('purchase_date', '')).startswith(month))
        today, horizon = date.today(), date.today() + timedelta(days=BILL_HORIZON_DAYS)
        upcoming = []
        for bill in bills:
            if bill.get('status') != 'pending':
                continue
            dates = [date.fromisoformat(d) for d in (bill.get('payment_date'), bill.get('upcoming_payment_date')) if d]
            due = min((d for d in dates if d >= today), default=None)
            if due and due <= horizon:
                upcoming.append(Bill(payee=bill.get('nickname') or bill.get('payee', 'Bill'),
                                     amount=float(bill['payment_amount']), due=due.isoformat()))
        balance = float(account['balance']) - sum(p['amount'] for p in live)  # Nessie never deducts purchases
        budget = float(link['monthly_budget'])
        return BudgetSnapshot(balance=balance, monthly_budget=budget, month_spent=float(spent),
                              remaining=max(0.0, budget - spent), upcoming_bills=sorted(upcoming, key=lambda b: b.due))

    async def _category(self, merchant_id):
        if merchant_id not in self._categories:
            try:
                self._categories[merchant_id] = (await self.nessie.merchant(merchant_id)).get('category', '')
            except NessieError:
                self._categories[merchant_id] = ''
        return self._categories[merchant_id]

    async def merchant_id(self, name, category=CLOTHING):
        with self.store.connect() as db:
            row = db.execute('SELECT merchant_id FROM nessie_merchants WHERE name=?', (name,)).fetchone()
        if row:
            return row[0]
        merchant = await self.nessie.create_merchant(name, category)
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO nessie_merchants VALUES (?,?)', (name, merchant['_id']))
        self._categories[merchant['_id']] = category
        return merchant['_id']

    async def record_purchase(self, profile_id, store_name, amount, description):
        """Mirror a Niche purchase into the shopper's bank so the agent's budget reflects it immediately."""
        link = self.link(profile_id)
        if not (self.nessie and link):
            return None
        merchant = await self.merchant_id(store_name or 'Niche')
        purchase = await self.nessie.create_purchase(link['account_id'], merchant, amount, date.today().isoformat(),
                                                     f'niche:{description}')
        self._cache.pop(profile_id, None)
        return {'provider': 'nessie', 'purchase_id': purchase['_id'], 'amount': purchase['amount']}
