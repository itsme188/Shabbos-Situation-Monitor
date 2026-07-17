---
name: test-feeds
description: Use after modifying any feed fetcher code in server.py, when the user says "test the feeds", "check if feeds work", "verify the changes", or after fixing a feed-related bug. Runs each feed source with live data and validates output quality. Also use proactively after any change to fetch_*, safe_request, or feed parsing logic.
---

# Test All Feed Sources (Live Data)

You are running a live validation of every feed source in the Shabbos Situation Monitor. This catches data-quality bugs that syntax checks miss (stale URLs, empty responses, wrong content).

## Important Notes
- Use the **main repo venv**: `/Users/Yitzi/code/shabbos-situation-monitor/venv/bin/python3`
- Run from the **main repo directory**: `/Users/Yitzi/code/shabbos-situation-monitor`
- Do NOT start the Flask server. Use `python3 -c "..."` one-liners to call fetchers directly.
- If the production server is running on port 8080, that's fine — these tests don't bind any port.
- TOI may return 429 if the production server is also hitting it. That's expected — note it and move on.

## Test Procedure

For each feed, run the fetcher function and inspect the `cache` dict afterward. Use this pattern:

```bash
cd "/Users/Yitzi/code/shabbos-situation-monitor"
/Users/Yitzi/code/shabbos-situation-monitor/venv/bin/python3 -c "
import sys; sys.path.insert(0, '.')
from server import cache, fetch_FUNCTION_NAME
fetch_FUNCTION_NAME()
data = cache['CACHE_KEY']
items = data.get('items', [])
print(f'Items: {len(items)}')
print(f'Error: {data.get(\"error\", \"none\")}')
print(f'Last updated: {data.get(\"last_updated\", \"never\")}')
if items:
    latest = items[0]
    print(f'Latest title: {latest.get(\"title\", latest.get(\"text\", \"?\"))[:100]}')
    print(f'Latest time: {latest.get(\"published\", latest.get(\"time\", \"?\"))}')
"
```

### Feeds to test (in order):

| Feed | Function | Cache Key | Expected Items |
|------|----------|-----------|----------------|
| Reuters/Middle East | `fetch_reuters` | `reuters` | 5-15 |
| Trump Truth Social | `fetch_trump` | `trump` | 3-10 |
| Times of Israel | `fetch_toi` | `toi_liveblog` | 5-15 |
| Think Tanks | `fetch_think_tanks` | `think_tanks` | 5-15 |
| Prediction Markets | `fetch_prediction_markets` | `prediction_markets` | 1-5 (AI context only, no UI) |
| Oil Price | `fetch_oil_price` | — (module global `server._oil_context`) | price + change_pct populated |
| OSINT/Twitter | `fetch_twitter_accounts` | `twitter_list` | 15 (capped at MAX_ITEMS_PER_FEED) |

**Test OSINT last** — it's the slowest (60s timeout, semaphore-limited TwStalker requests).

Notes:
- **OSINT item count is capped at 15** (`MAX_ITEMS_PER_FEED`): ~13 accounts × 5 tweets are merged, sorted by recency, and truncated. Seeing only 4-6 accounts represented is normal during high-volume periods — the freshest posts crowd out quieter accounts. Check `cache["twitter_list"]["account_status"]` to distinguish "crowded out" from "failed to fetch".
- **Prediction market items with probability 0 or 100 are suspect** — likely a resolved market that slipped through the `closed` filter. Flag it.
- `fetch_think_tanks` calls Haiku to summarize new articles (cached by URL, max 5/cycle) — costs a few cents, that's expected.
- Skip `fetch_ai_summary` — it's schedule-gated and costs more; test it via the running server's `/api/refresh-ai` endpoint instead when doing end-to-end validation.
- **NEVER call `update_all_feeds()` from a direct-import test**: it ends with `save_cache_to_disk()`, which persists the process's in-memory defaults for state it never loaded — notably resetting `ai_summary_enabled` to False on disk (`load_cache_from_disk()` only runs in `__main__`). If you must run it, call `server.load_cache_from_disk()` first and re-check the toggle in `feed_cache.json` afterward.

## Report Format

After testing all feeds, summarize in a table:

| Feed | Items | Freshest Entry | Errors | Status |
|------|-------|----------------|--------|--------|
| Reuters | 12 | 15 min ago | none | OK |
| Trump | 5 | 2 hours ago | none | OK |
| TOI | 8 | 30 min ago | none | OK |
| Think Tanks | 12 | 1 hour ago | none | OK |
| Prediction Markets | 5 | live | none | OK |
| Oil | — | live ($81.77 +4.5%) | none | OK |
| OSINT | 15 | 5 min ago | 2/13 accounts failed | OK (cap reached) |

Flag anything concerning:
- 0 items = FAILED
- All items older than 6 hours = STALE
- Error message present = note it
- Fewer items than expected = DEGRADED
