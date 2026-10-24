import asyncio
from fastapi.testclient import TestClient
from app import create_app
from market.service import Market, band, percentile, record
from market.snowflake import SnowflakeError, binding
from sourcing.config import Settings


def settings(**extra):
    return Settings(snowflake_account_url='https://example.snowflakecomputing.com', snowflake_pat='t', **extra)


class FakeSnowflake:
    enabled = True

    def __init__(self, rows=(), fail=False):
        self.rows, self.fail, self.statements, self.prompts = list(rows), fail, [], []

    async def sql(self, statement, params=(), database=True):
        self.statements.append((statement, list(params)))
        if self.fail:
            raise SnowflakeError('down')
        return self.rows if 'VECTOR_COSINE_SIMILARITY' in statement else []

    async def complete(self, prompt, max_tokens=120):
        self.prompts.append(prompt)
        return ' A fair price for this kind of skirt. '


def listing(price=24.0, **extra):
    return {'id': 'depop:1', 'source': 'secondhand', 'marketplace': 'depop', 'retailer': 'Depop', 'tier': 'resale',
            'title': 'Black pleated mini skirt', 'brand': 'Brandy Melville', 'condition': 'Good', 'price': price,
            'currency': 'USD', 'url': 'https://www.depop.com/products/1', **extra}


def comps(prices):
    # TITLE, PRICE, MARKETPLACE, RETAILER, TIER, SOURCE, CONDITION, SIM
    return [[f'mini skirt {i}', str(p), 'depop', 'Depop', 'resale', 'secondhand', 'Good', '0.7'] for i, p in enumerate(prices)]


def test_record_keeps_public_listing_fields_only():
    row = record({**listing(), 'reason': 'matches your taste', 'warnings': ['x'], 'score': 80})
    assert set(row) == {'listing_id', 'source', 'marketplace', 'retailer', 'tier', 'title', 'brand', 'category',
                        'condition', 'price', 'currency', 'url'}
    assert row['category'] == 'bottom'
    assert binding(12.5) == {'type': 'REAL', 'value': '12.5'} and binding(None)['value'] is None


def test_stats_and_band():
    assert percentile([10, 20, 30, 40], .25) == 17.5 and percentile([], .5) is None
    assert band(10, 20, 40) == 'deal' and band(30, 20, 40) == 'fair' and band(60, 20, 40) == 'high'


def test_ingest_merges_in_chunks_and_embeds_in_snowflake():
    fake = FakeSnowflake()
    market = Market(settings(), client=fake)
    n = asyncio.run(market.ingest([listing(), listing(), {**listing(), 'id': 'depop:2'}]))
    assert n == 2  # deduped by listing id
    merge = next(s for s, _ in fake.statements if s.strip().startswith('MERGE'))
    assert 'AI_EMBED' in merge and 'profile' not in merge.lower()


def test_price_check_verdict_and_cortex_sentence():
    fake = FakeSnowflake(rows=comps([18, 20, 22, 25, 30, 28, 21]))
    market = Market(settings(), client=fake)
    out = asyncio.run(market.price_check('s1', listing(price=12)))
    assert out['verdict'] == 'deal' and out['n'] == 7 and out['low'] < out['median'] < out['high']
    assert out['sentence'] == 'A fair price for this kind of skirt.' and len(out['comparables']) == 5
    assert 'Use only the numbers given' in fake.prompts[0]
    asyncio.run(market.price_check('s1', listing(price=12)))
    assert len(fake.prompts) == 1  # cached per search and listing


def test_few_comparables_or_errors_are_unknown_not_errors():
    few = asyncio.run(Market(settings(), client=FakeSnowflake(rows=comps([20, 22]))).price_check('s', listing()))
    assert few['verdict'] == 'unknown' and few['n'] == 2 and 'Not enough' in few['sentence']
    down = asyncio.run(Market(settings(), client=FakeSnowflake(fail=True)).price_check('s', listing()))
    assert down['verdict'] == 'unknown'
    off = asyncio.run(Market(Settings()).price_check('s', listing()))
    assert off['verdict'] == 'unknown'


def test_endpoint_shape(tmp_path):
    s = Settings(database_path=str(tmp_path / 'm.sqlite'), upload_dir=str(tmp_path / 'u'))
    with TestClient(create_app(s)) as client:
        job = client.post('/v1/searches', json=__import__('json').load(open('examples/search.json')))
        ident = job.json()['search_id']
        for _ in range(100):
            done = client.get(f'/v1/searches/{ident}').json()
            if done['status'] in ('completed', 'partial'):
                break
            __import__('time').sleep(.05)
        item = done['results'][0]
        out = client.get(f'/v1/searches/{ident}/listings/{item["id"]}/price-check').json()
        assert out['verdict'] == 'unknown'  # Snowflake off in tests: quiet, not an error
        assert client.get(f'/v1/searches/{ident}/listings/nope/price-check').status_code == 404
