"""Create a demo bank account in Nessie for a profile and link it.

    python -m finance.seed <profile_id> [--balance 1450] [--budget 150]

Writes only to the Nessie mock bank (fake money) and the local bank_links table. Each run creates a fresh
customer and account, since Nessie purchases can't be edited or deleted.
"""
import argparse
import asyncio
from datetime import date, timedelta
from sourcing.config import Settings
from sourcing.store import Store
from taste.store import TasteStore
from .budget import CLOTHING, Budgets


def this_month(day):
    today = date.today()
    return today.replace(day=min(day, today.day)).isoformat()


async def seed(profile_id, balance, budget):
    settings = Settings()
    if not settings.nessie_api_key:
        raise SystemExit('Set NESSIE_API_KEY in backend/.env first')
    store = Store(settings.database_path)
    profile = TasteStore(store).profile(profile_id)
    if not profile:
        raise SystemExit(f'No profile {profile_id}')
    budgets = Budgets(settings, store)
    nessie = budgets.nessie
    first = profile.onboarding.name.strip() or 'Niche'
    customer = await nessie.create_customer(first, 'Shopper')
    account = await nessie.create_account(customer['_id'], balance)
    history = [  # (store, category, amount, day of month, description)
        ('Depop', CLOTHING, 42, 3, 'vintage pleated skirt'),
        ('Madewell', CLOTHING, 53, 9, 'ribbed tank'),
        ("Trader Joe's", 'groceries', 68, 6, 'groceries'),
        ('Blue Bottle Coffee', 'food', 14, 11, 'coffee'),
    ]
    for name, category, amount, day, description in history:
        merchant = await budgets.merchant_id(name, category)
        await nessie.create_purchase(account['_id'], merchant, amount, this_month(day), description)
    today = date.today()
    rent_due, phone_due = today + timedelta(days=5), today + timedelta(days=10)
    await nessie.create_bill(account['_id'], 'Berkeley Apartments', 'Rent', rent_due.isoformat(), 1200, rent_due.day)
    await nessie.create_bill(account['_id'], 'Mint Mobile', 'Phone', phone_due.isoformat(), 45, phone_due.day)
    budgets.save_link(profile_id, customer['_id'], account['_id'], budget)
    snapshot = await budgets.snapshot(profile_id)
    print(f'Linked profile {profile_id} to Nessie account {account["_id"]}')
    print(snapshot.model_dump_json(indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('profile_id')
    parser.add_argument('--balance', type=float, default=1450)
    parser.add_argument('--budget', type=float, default=150, help='monthly clothing budget in dollars')
    args = parser.parse_args()
    asyncio.run(seed(args.profile_id, args.balance, args.budget))
