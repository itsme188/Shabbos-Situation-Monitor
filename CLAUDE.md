# Shabbos Situation Monitor

## Quick Start
- `preview_start("shabbos-monitor")` — preferred in Claude Code sessions
- `./start.sh` in standalone Terminal — for unattended/Shabbos operation
- AppleScript launcher — double-click from Desktop, opens Terminal + Safari
- NEVER start via `Bash` tool for long-running use — dies when Claude Code exits

## Architecture
- Flask on Python 3, port 8080, binds 0.0.0.0
- APScheduler refreshes feeds every 5 min; watchdog checks per-feed staleness (not aggregate)
- `feed_cache.json` persists across restarts (max 2hr age, atomic writes, `schema_version: 1`, backoff state, AI toggle state)
- `start.sh` has auto-restart loop, venv management, graceful SIGINT handling, **port-check guard**, **caffeinate** (sleep prevention), **crash-loop limit** (10 in 10min)

## Key Files
- `server.py` — main app (~1900 lines), routes, scheduler, all feed fetchers
- `config.py` — HOST, PORT, REFRESH_INTERVAL, feed URLs, Live Wire sources (Telegram + RSS), think tank feeds, AI prompts, Yom Tov settings
- `start.sh` — production launcher with crash recovery
- `launcher.applescript` — macOS one-click startup (health-polls, reuses Safari tabs, error dialog)
- `templates/index.html` — dashboard template

## Current Known Issues

- AI summaries may reference old events when today's news articles discuss earlier events — the LLM summarizes those references. Mitigated by feed digest timestamps being in ET (consistent with the "Current time" header sent to the LLM).
- Run-by-run Shabbos history (three graded runs, all fixed issues) archived in `docs/reference/run-history.md`.

## Feed Architecture
- Each feed has: fetcher function, cache entry, error state, last_updated timestamp
- `update_all_feeds()` runs all fetchers concurrently via ThreadPoolExecutor
- **Dashboard layout**: Situation Board | Middle East | TOI | Live Wire (Telegram+RSS+Trump) | AI Summary
- **Situation Board** (`situation_board` cache key, 1st column, replaced the Strategic Analysis display Oct 2026): Haiku returns a JSON array of per-region cards (`SITUATION_BOARD_REGIONS`, `SITUATION_BOARD_PROMPT`) — region, trend, headline, summary, last major event + time. Regenerated after every scheduled/forced AI summary and once at startup if AI is on. `_parse_board()` validates; on failure the previous board stays up. Excluded from the watchdog and from the feed digest. Think tanks are still fetched and fed to the LLM as background.
- **Think tank feed** (`think_tanks` cache key): FDD (direct RSS), CSIS (scrape `csis.org/analysis`), ISW (scrape `understandingwar.org/publications`). Google News RSS article URLs don't work (JS-only redirect). Each article is AI-summarized via Haiku (cached by URL, max 5 new/cycle). Recency filter: `THINK_TANK_MAX_AGE_HOURS = 36`.
- **Live Wire column** (was "Raw Feeds"/OSINT): Telegram channels (`t.me/s/<channel>` public HTML) + outlet RSS, merged with Trump posts in `dashboard()`. Config: `LIVE_WIRE_TELEGRAM`, `LIVE_WIRE_RSS`, `LIVE_WIRE_REGION_KEYWORDS`. Each item gets a region tag (keyword match, else source default). `_balance_wire()` sorts, dedupes, caps per region (`LIVE_WIRE_PER_REGION`) so one busy front can't crowd out others.
- Live Wire still uses the `twitter_list` cache key and `fetch_twitter_accounts()` name for cache compatibility
- **Twitter scraping removed (Oct 2026)**: TwStalker went behind Cloudflare, xcancel returns 451, syndication 429, BlueSky accounts dormant. Don't resurrect without a paid API or headless browser.
- **Freshness rules**: `_is_fresh()` treats undated items as stale. Every fetcher age-filters and sorts by epoch; `dashboard()` and `_build_feed_digest()` re-filter via `_FEED_MAX_AGE_HOURS` so preserved last-good cache can never show or feed stale items.
- Scraped think tank items (CSIS) get the real date from `<meta name="citation_publication_date">` (date only, shown as "Thu Oct 15") — never the fetch time.
- Blocked as of Oct 2026 (403 even with browser UA): TOI liveblog (RSS still works), ISW publications page.
- ~~Polymarket~~ — fully removed in PR #7
- Trump RSS (`trumpstruth.org/feed`): many entries are media-only (`<p></p>` body) — always extract text before deciding to include
- Reuters has BBC World Middle East RSS (`REUTERS_FALLBACK_RSS`) as fallback source
- Trump and Reuters have exponential backoff (same pattern as TOI/xcancel)
- AI summary retries once on transient API errors (529, connection, rate limit); auth errors fail immediately

## Timestamps
- All timestamps use `format_timestamp()` → converts to ET via `.astimezone()` → `strftime('%a %-I:%M %p')` → "Fri 2:30 PM"
- `format_timestamp(ts, source_tz=None)`: optional `source_tz` for naive datetimes (e.g. TOI liveblog uses "Asia/Jerusalem")
- `%-I` is macOS/POSIX only (no leading zero on 12-hour time)
- Candle lighting time in header status bar
- **Hebcal API** auto-detects Yom Tov: `get_yom_tov_info()` queries `hebcal.com/hebcal` for holidays/candles/havdalah. Cached 24h. Header shows holiday name + candle lighting (before) or havdalah (during). `_effective_retention_days()` auto-extends AI summary retention during active Yom Tov.
- `YOM_TOV_END` config defaults to `None` (auto-detected). Can override manually with ISO datetime string.

## AI Summary
- **Schedule-aware generation** (cron at :05 past each hour, ET timezone):
  - 1-7 AM: quiet hours, no generation
  - 8 AM: morning summary (Opus, multi-paragraph prose covering last 8 hours)
  - 10 AM, 12 PM, 2 PM, 4 PM, 6 PM, 8 PM, 10 PM, 12 AM: regular 2-hour bullet summaries (Haiku)
- **Two-model strategy**: Haiku 5.5 for regular 2-hour summaries + think tank summaries, Opus 5.5 for morning summary
- 5.5 models may return a `thinking` block before text — always read responses via `_message_text()`, never `content[0].text`. Token budgets raised (4000 / 1000) to leave room for thinking.
- Prompt requires `[Category] Day H:MM AM/PM - description` format. Parser regex handles both old 24-hour and new AM/PM formats, dash variants `[-–—]`
- All times in ET. Feed digest includes timezone context header for the LLM
- Valid categories: Military, Diplomatic, Political, Breaking, Strategic
- `_parse_ai_bullets()` returns a list of bullet dicts
- **Oil price as background signal**: WTI crude price fetched via Yahoo Finance chart API each cycle. Not displayed in UI. Fed to LLM in a hidden context section so it can gauge event significance (large oil moves = markets reacting, flat = noise/priced in). No explicit market/financial copy in output.
- Cache fields: `summaries[]`, `morning_summary`, `ai_summary_enabled` — all persisted to `feed_cache.json`
- Manual refresh (`/api/refresh-ai`) uses `force=True` to bypass schedule check
- **Yom Tov mode** (`AI_SUMMARY_RETENTION_DAYS > 1`): keeps N days of summaries, disables auto-pause, increases cap to `AI_SUMMARY_MAX_ENTRIES` (30). Day separators in template for multi-day viewing.
- `YOM_TOV_END` config: set to ISO datetime string to show "Yom Tov ends ..." in header instead of Shabbos times. Reset to `None` after holiday.

## Lessons & Best Practices
- **Truthy-but-empty HTML**: RSS fields like `<p></p>` are truthy strings that yield nothing after stripping. Always validate *processed* output, not raw input, before using it.
- **Dashboard grid**: 5 columns with `repeat(5, 1fr)` at ≥1600px; responsive breakpoints collapse to 2 columns then 1. AI Summary is the 5th column, not a separate section.
- **LLM output parsing**: When asking an LLM for structured output, always include a fallback for when it doesn't follow the format exactly. The regex-with-fallback pattern is robust.
- **Preview in worktrees**: The main repo may already have a server on port 8080. Use a different port when testing from a worktree.
- **TOI rate limiting**: Times of Israel returns 429 if hit from multiple processes (e.g., main server + worktree). Expect this during testing; RSS fallback handles it gracefully
- **test_server.py import conflict**: Test file starts Flask server on import, causing port conflicts. Run `python -c "from server import ..."` for import validation instead of pytest
- **Display-only renames**: When renaming a UI concept (e.g., "Twitter" → "OSINT"), keep internal cache keys/function names unchanged to avoid cache file incompatibility and reduce blast radius
- **Truncation ellipsis**: All text truncation points (300/500 char limits) append `...` when content is cut. Use lambda wrapper for chained expressions: `(lambda t: t[:300] + ("..." if len(t) > 300 else ""))(expr)`
- **Worktree venv access**: Worktree can't run `bash ./start.sh` via preview_start (permission errors). Use absolute path to main repo's venv python: `/Users/Yitzi/code/shabbos-situation-monitor/venv/bin/python3`
- **TLS fingerprinting**: Some sites (twstalker.com) block Python `requests` via JA3 TLS fingerprint but allow `curl`. Use `subprocess.run(["curl", ...])` as workaround. macOS curl uses BoringSSL which passes
- **Deploying worktree changes**: After merging PRs on GitHub, must `git pull origin main` in the main repo AND kill ALL server processes (see below) — start.sh auto-restarts with new code
- **Kill ALL processes, not just port 8080**: `kill $(lsof -i :8080 -t)` only kills the one server holding the port. Zombie `start.sh` processes survive and keep crash-looping. Use: `pkill -f 'start.sh' ; pkill -f 'server.py'` then start fresh with ONE `./start.sh`
- **Rate-limit backoff pattern**: `RateLimitError` exception + `safe_request(raise_on_429=True)` + per-source `_backoff_until`/`_backoff_minutes` globals. Exponential: doubles on each 429, resets on success, caps at 30min. Now on TOI, xcancel, Trump, and Reuters. Backoff state persists in `feed_cache.json` across restarts.
- **TOI liveblog URL ordering**: Date-specific URLs must be tried before the base `/liveblog/` URL, which points to a frozen 2020 archive. The structural fallback is too good — it finds entries on stale pages, so URL priority matters.
- **Always test with live data**: Import validation and syntax checks don't catch data-quality bugs like stale URLs returning old content. Run the actual fetcher and inspect the output.
- **Polymarket Gamma API**: Public REST, no auth. `events?slug=...` returns array of events with nested `markets[]`. Each market has `outcomePrices` (JSON string `'["0.40","0.60"]'`, index 0 = Yes probability). Multi-outcome events (e.g., "by March 31" / "by Dec 31") need sub-market slug targeting.
- **Resolved Polymarket markets freeze at 0/100**: Always filter `markets[]` on the `closed` flag before selecting. A resolved market looks like live data but is history — feeding "Nuclear Deal: 100%" to the LLM misleads it. Never substitute a differently-dated sub-market for a named slug (wrong label). Date-scoped slugs ("by June 30") have built-in expiry — refresh `PREDICTION_MARKETS` in config.py periodically.
- **Metaculus API requires auth**: Returns 403 without API token. Free account needed. Not used currently.
- **Pending branch**: `feature/prediction-markets-ai-summary` — prediction market odds in AI summaries + candle-lighting Friday summary. Not yet deployed. WARNING: has regressions (lost ET timestamp fix, removed pruning). Must cherry-pick, not merge.
- **Think tank RSS**: FDD has working WordPress RSS with `content:encoded`. CSIS direct RSS (`/rss.xml`) is stale 2016 data — use Google News site-scoped instead. ISW direct RSS redirects to HTML — use Google News `site:understandingwar.org`.
- **Google News RSS site-scoping**: `https://news.google.com/rss/search?q=site:example.com+keywords` returns fresh articles from a specific domain. Title format is "Article Title - Source Name" — split on last " - " to extract source.
- **AI toggle persistence**: `ai_summary_enabled` must be saved to disk (feed_cache.json). Default is `False`; if not persisted, any server restart during unattended operation silently kills AI summaries.
- **ThreadPoolExecutor TimeoutError**: `as_completed(timeout=N)` raises `TimeoutError` when the deadline passes. Must wrap in try-except or the entire update cycle silently fails, abandoning pending futures.
- **caffeinate for long-running processes**: `caffeinate -i -w $$` prevents macOS idle sleep, tied to parent process lifetime. Essential for 72hr+ unattended operation.
- **Crash-loop detection**: Track restart timestamps in a sliding window. After N rapid restarts, exit instead of looping forever — prevents disk-filling log spam from fatal bugs.
- **Mixed timestamp format sorting**: Never sort feed timestamps as raw strings — different sources use different formats (ISO 8601, RFC 2822, display formats). Use `_parse_timestamp_to_epoch()` to normalize to epoch before sorting.
- **Cache loading for long-running unattended ops**: `load_cache_from_disk()` uses two-phase loading: AI summaries/backoff/toggle always restore (have their own retention), feed items only load if cache <2h old. Prevents losing days of AI summaries on server restart during multi-day Yom Tov.
- **Direct-import tests clobber persisted state**: `load_cache_from_disk()` only runs in `__main__`, but `update_all_feeds()` ends with `save_cache_to_disk()` — so a `python -c "from server import ..."` test that runs a full update cycle persists in-memory defaults (notably `ai_summary_enabled: False`) over the real file. Call `load_cache_from_disk()` first in such tests, and re-check the toggle on disk afterward.
- **In-process smoke testing**: Use Flask's `app.test_client()` for end-to-end route testing (dashboard render, /health, /api/refresh-ai) — exercises the real routes/templates without binding port 8080 or leaving a long-running process. The Bash-launch hook blocks `server.py` as a background process for this reason.
- **Collapsible day groups**: AI summary column auto-collapses older days during multi-day Yom Tov. Click day separator to expand. CSS `.day-group.collapsed` + JS click handler on `.day-separator`.
- **Yom Tov → Shabbat merge bug**: The 36-hour window merge in `get_yom_tov_info()` incorrectly absorbs a regular Shabbat that follows a Yom Tov (gap ~23h < 36h threshold). Fix: only merge a "Shabbos" window if it's sandwiched (followed by another Yom Tov window within 36h). Also skip plain "Shabbos" windows in the return logic — `get_shabbos_times()` handles regular Shabbat.

## Reference Docs

- `docs/reference/run-history.md` — run-by-run Shabbos history (graded runs, fixed issues). Read when investigating a past regression or grading pattern.
