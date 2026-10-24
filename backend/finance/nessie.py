"""Capital One Nessie (mock bank) client.

Behaviour verified against the live API (2026-10-24), which shapes how Niche uses it:
- Base URL is https only; amounts are whole dollars (42.50 is stored as 42).
- Purchases must be created with a status ('pending' | 'completed' | 'cancelled'), and can't be edited or
  deleted afterwards: one purchase without a status makes the account's purchase list unreadable.
- Bills need recurring_date (day of month); the API derives upcoming_payment_date.
- Balances never change: purchases and withdrawals don't touch account.balance, and balance can't be updated.
  Niche therefore treats the account balance as the opening balance and subtracts recorded purchases.
"""
import httpx

BASE = 'https://api.nessieisreal.com'


class NessieError(Exception):
    pass


class Nessie:
    def __init__(self, key):
        self.key = key

    async def request(self, method, path, json=None):
        async with httpx.AsyncClient(base_url=BASE, params={'key': self.key}, timeout=15) as client:
            response = await client.request(method, path, json=json)
        if response.status_code >= 400:
            raise NessieError(f'{method} {path} -> {response.status_code}: {response.text[:200]}')
        data = response.json()
        return data.get('objectCreated', data) if isinstance(data, dict) else data

    async def account(self, account_id):
        return await self.request('GET', f'/accounts/{account_id}')

    async def purchases(self, account_id):
        return await self.request('GET', f'/accounts/{account_id}/purchases')

    async def bills(self, account_id):
        return await self.request('GET', f'/accounts/{account_id}/bills')

    async def merchant(self, merchant_id):
        return await self.request('GET', f'/merchants/{merchant_id}')

    async def create_customer(self, first_name, last_name):
        return await self.request('POST', '/customers', {'first_name': first_name, 'last_name': last_name,
            'address': {'street_number': '2600', 'street_name': 'Bancroft Way', 'city': 'Berkeley', 'state': 'CA',
                        'zip': '94704'}})

    async def create_account(self, customer_id, balance, nickname='Everyday checking'):
        return await self.request('POST', f'/customers/{customer_id}/accounts',
            {'type': 'Checking', 'nickname': nickname, 'rewards': 0, 'balance': int(balance)})

    async def create_merchant(self, name, category):
        return await self.request('POST', '/merchants', {'name': name[:60], 'category': category,
            'address': {'street_number': '1', 'street_name': 'Market St', 'city': 'San Francisco', 'state': 'CA',
                        'zip': '94105'}, 'geocode': {'lat': 37.79, 'lng': -122.39}})

    async def create_purchase(self, account_id, merchant_id, amount, date, description, status='completed'):
        return await self.request('POST', f'/accounts/{account_id}/purchases', {
            'merchant_id': merchant_id, 'medium': 'balance', 'purchase_date': date, 'amount': round(amount),
            'status': status, 'description': description[:140]})

    async def create_bill(self, account_id, payee, nickname, payment_date, amount, recurring_day):
        return await self.request('POST', f'/accounts/{account_id}/bills', {
            'status': 'pending', 'payee': payee, 'nickname': nickname, 'payment_date': payment_date,
            'recurring_date': recurring_day, 'payment_amount': round(amount)})
