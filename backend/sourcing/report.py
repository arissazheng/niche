"""What Niche did across the searches in this machine's log: how much it checked, what it left out and why, how fast
the first listings came in, and who the results came from. Read-only; numbers come from the jobs and events tables.

    python -m sourcing.report            # live searches only
    python -m sourcing.report --fixture  # include fixture-mode searches
"""
import argparse
import json
from datetime import datetime
from statistics import median
from .config import Settings
from .store import Store

SMALL = ('secondhand', 'indie', 'web')  # everything that isn't the big-store (mainstream) actor


def summarize(store, fixture=False):
    with store.connect() as db:
        jobs = db.execute("SELECT id,status,result,created_at FROM jobs WHERE status IN ('completed','partial')").fetchall()
        firsts = dict(db.execute("SELECT job_id, MIN(at) FROM events WHERE kind='source_normalized' GROUP BY job_id"))
        usage = db.execute("SELECT job_id, payload FROM events WHERE kind='model_usage'").fetchall()
    tokens = {}
    for job_id, payload in usage:
        u = json.loads(payload).get('usage') or {}
        tokens[job_id] = tokens.get(job_id, 0) + (u.get('input_tokens') or 0) + (u.get('output_tokens') or 0)
    searches, retrieved, shown, small, waits, left_out = 0, 0, 0, 0, [], {}
    per_search_tokens = []
    for ident, status, result, created in jobs:
        result = json.loads(result)
        if (result.get('mode') == 'fixture') and not fixture:
            continue
        searches += 1
        counts = result.get('counts') or {}
        retrieved += counts.get('retrieved') or 0
        for reason, n in (counts.get('left_out') or {}).items():
            left_out[reason] = left_out.get(reason, 0) + (n or 0)
        results = result.get('results') or []
        shown += len(results)
        small += sum(x.get('source') in SMALL for x in results)
        if ident in firsts:
            waits.append((datetime.fromisoformat(firsts[ident]) - datetime.fromisoformat(created)).total_seconds())
        if ident in tokens:
            per_search_tokens.append(tokens[ident])
    return {
        'searches': searches,
        'listings_checked': retrieved,
        'results_shown': shown,
        'left_out': left_out,
        'small_seller_share': round(small / shown, 3) if shown else None,
        'median_seconds_to_first_listings': round(median(waits), 1) if waits else None,
        'median_claude_tokens_per_search': int(median(per_search_tokens)) if per_search_tokens else None,
    }


def describe(s):
    if not s['searches']:
        return 'No finished searches in the log yet.'
    noun = 'search' if s['searches'] == 1 else 'searches'
    out = [f"{s['searches']} {noun} checked {s['listings_checked']:,} listings and showed {s['results_shown']:,}."]
    reasons = [f"{n:,} {k.replace('_', ' ')}" for k, n in s['left_out'].items() if n]
    if reasons:
        out.append('Left out: ' + ', '.join(reasons) + '.')
    if s['small_seller_share'] is not None:
        out.append(f"{s['small_seller_share']:.0%} of results came from independent labels and secondhand sellers.")
    if s['median_seconds_to_first_listings'] is not None:
        out.append(f"First listings arrived after {s['median_seconds_to_first_listings']} s (median).")
    if s['median_claude_tokens_per_search'] is not None:
        out.append(f"Claude used {s['median_claude_tokens_per_search']:,} tokens per search (median).")
    return '\n'.join(out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', action='store_true', help='include fixture-mode searches')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    summary = summarize(Store(Settings().database_path), args.fixture)
    print(json.dumps(summary, indent=2) if args.json else describe(summary))
