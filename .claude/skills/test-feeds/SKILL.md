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
| Times of Israel | `fetch_toi` | `toi` | 5-15 |
| Polymarket | `fetch_polymarket` | `polymarket` | 1-5 |
| OSINT/Twitter | `fetch_twitter_accounts` | `twitter_list` | 10-50 (13 accounts) |

**Test OSINT last** — it's the slowest (60s timeout, semaphore-limited TwStalker requests).

Skip `fetch_ai_summary` — it requires the Anthropic API key and costs money.

## Report Format

After testing all feeds, summarize in a table:

| Feed | Items | Freshest Entry | Errors | Status |
|------|-------|----------------|--------|--------|
| Reuters | 12 | 15 min ago | none | OK |
| Trump | 5 | 2 hours ago | none | OK |
| TOI | 8 | 30 min ago | none | OK |
| Polymarket | 3 | live | none | OK |
| OSINT | 35 | 5 min ago | 2/13 failed | DEGRADED |

Flag anything concerning:
- 0 items = FAILED
- All items older than 6 hours = STALE
- Error message present = note it
- Fewer items than expected = DEGRADED
