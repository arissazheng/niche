import asyncio
from sourcing.config import Settings
from sourcing.models import SearchRequest
from sourcing.pipeline import Pipeline
from sourcing.report import describe, summarize
from sourcing.store import Store
from tests.test_service import request_data  # noqa: F401  (fixture)


def test_report_counts_finished_searches(request_data, tmp_path):  # noqa: F811
    store = Store(tmp_path / 'db.sqlite3')
    ident = store.create(request_data.model_dump())
    asyncio.run(Pipeline(Settings(), store).run(request_data, ident))
    assert summarize(store)['searches'] == 0  # fixture searches are left out by default
    s = summarize(store, fixture=True)
    shown = len(store.get(ident)['results'])
    assert s['searches'] == 1 and s['results_shown'] == shown and s['listings_checked'] >= shown
    assert 0 <= s['small_seller_share'] <= 1
    assert describe(s).startswith('1 search checked')
    assert describe(summarize(Store(tmp_path / 'empty.sqlite3'))) == 'No finished searches in the log yet.'
