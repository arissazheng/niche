"""Load every listing from past searches into Snowflake, so the price check has comparables from day one.

    python -m market.backfill
"""
import asyncio
from sourcing.config import Settings
from sourcing.store import Store
from .service import Market, from_jobs


async def main():
    settings = Settings()
    market = Market(settings)
    if not market.enabled:
        raise SystemExit('Set SNOWFLAKE_ACCOUNT_URL and SNOWFLAKE_PAT in backend/.env first')
    listings = from_jobs(Store(settings.database_path))
    print(f'loading {len(listings)} listings')
    print(f'merged {await market.ingest(listings)}')
    rows = await market.db.sql('SELECT COUNT(*), COUNT(EMBEDDING) FROM LISTINGS')
    print('table now holds', rows[0][0], 'listings,', rows[0][1], 'with embeddings')


if __name__ == '__main__':
    asyncio.run(main())
