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
- `config.py` — HOST, PORT, REFRESH_INTERVAL, feed URLs, OSINT account lists, think tank feeds, AI prompts, Yom Tov settings
- `start.sh` — production launcher with crash recovery
- `launcher.applescript` — macOS one-click startup (health-polls, reuses Safari tabs, error dialog)
- `templates/index.html` — dashboard template

## Known Issues (from first Shabbos run, Feb 27 2026 — grade: B-)
- ~~**Polymarket:** resolved markets vanish from feed with no fallback~~ — REMOVED: Polymarket fully removed in PR #7.
- ~~**Twitter:** hours-long gaps with no updates~~ — FIXED: 4-tier fallback (syndication → BlueSky → Nitter RSS → Nitter HTML), xcancel.com with "mistique" UA, Google News as last resort with source attribution
- ~~**Times of Israel liveblog:** went silent for hours~~ — FIXED: Israel timezone for date URLs, zero-padded format variant, structural CSS fallback, stale cache clearing
- ~~**Trump Truth Social:** posts containing links show opaque URLs instead of readable content~~ — FIXED: `extract_text_with_links()` now shows destination URLs inline. Empty media-only/retruth posts are filtered out.
- Core value delivered: all key breaking news was surfaced

## Known Issues (from second Shabbos run, Mar 7 2026 — grade: F)
- ~~**CRITICAL: Zombie start.sh processes**~~ — FIXED: `start.sh` now checks if port 8080 is in use before starting (refuses with PID + kill command). Crash-loop also re-checks port before each restart.
- ~~**server.py does expensive work before port binding**~~ — FIXED: Socket bind test in `__main__` runs before scheduler/watchdog/update_all_feeds(). Doomed instances exit immediately via `sys.exit(1)`.
- ~~**Cache race condition**~~ — RESOLVED by zombie fix: only one process can run, so no concurrent writers.
- ~~**TOI permanent 429**~~ — FIXED: Exponential backoff (5→10→20→30min cap) on 429 responses. `RateLimitError` in `safe_request(raise_on_429=True)` lets TOI fetcher skip cycles when rate-limited. Backoff resets on successful fetch.
- ~~**OSINT degraded to 3/13 accounts**~~ — RESOLVED by zombie fix: single instance stays within TwStalker's Semaphore(2) rate limit.
- ~~**Trump raw URLs**: Some Truth Social posts still show opaque `truthsocial.com/...` URLs instead of text content.~~ — FIXED: `extract_text_with_links()` strips bare truthsocial.com URLs via regex. Empty posts filtered by existing guard.
- ~~**TOI liveblog showing 2020 content**~~ — FIXED: Base `/liveblog/` URL is a frozen 2020 COVID archive. Date-specific URLs now tried first, base URL is last resort.
- ~~**AI summary paused/confused**~~ — RESOLVED by zombie fix: only one scheduler instance runs.
- ~~**Logs lost**~~ — RESOLVED by zombie fix: no more crash-loop flood generating 35K lines in 10min.
- ~~**TOI clears cache on failure**~~ — FIXED: `fetch_toi()` now preserves last-good items with "Showing cached content (fetch failed)" error instead of clearing to empty.

## Known Issues (from third Shabbos run, Mar 14 2026 — grade: B-)
- ~~**Feed timestamps in UTC, not ET**: TOI RSS, Trump, Reuters, BlueSky all displayed UTC times (4+ hours ahead of ET). User sees "Sat 11:08 PM" when it's 7:08 PM ET.~~ — FIXED: `format_timestamp()` now converts all timezone-aware datetimes to ET via `.astimezone()`. Optional `source_tz` param for naive datetimes (TOI liveblog → "Asia/Jerusalem").
- ~~**AI summaries showed stale content from previous days**: 21 entries spanning 6 days (Sun–Sat) accumulated in cache. Monday's 8:05 AM morning summary visible on Saturday. No date filtering existed.~~ — FIXED: `_prune_old_summaries()` removes entries not from today (ET). Called at cache load, before generation, and on dashboard render. Summary cap reduced 24→14.
- AI summaries may still reference old events when today's news articles discuss earlier events — LLM summarizes those references. Mitigated by feed digest timestamps now being in ET (consistent with "Current time" header sent to LLM).
- Core value delivered: morning summary was good, big stories communicated

## Feed Architecture
- Each feed has: fetcher function, cache entry, error state, last_updated timestamp
- `update_all_feeds()` runs all fetchers concurrently via ThreadPoolExecutor
- **Dashboard layout**: Strategic Analysis | Middle East | TOI | Raw Feeds (OSINT+Trump merged) | AI Summary
- **Think tank feed** (`think_tanks` cache key): FDD (direct RSS), CSIS (scrape `csis.org/analysis`), ISW (scrape `understandingwar.org/publications`). Google News RSS article URLs don't work (JS-only redirect). Each article is AI-summarized via Haiku (cached by URL, max 5 new/cycle). Recency filter: `THINK_TANK_MAX_AGE_HOURS = 36`.
- **Raw Feeds column**: OSINT + Trump pre-merged in `dashboard()` route, sorted by timestamp, tagged with `feed_source` key
- **OSINT** backed by `twitter_list` cache key — internal names kept for cache compatibility
- OSINT uses 5-tier fallback: syndication → TwStalker → BlueSky → Nitter RSS → Nitter HTML → Google News
- **TwStalker** (`twstalker.com`): primary source, works for 11 active accounts. Uses `curl` subprocess (not Python `requests`) because TwStalker blocks via TLS fingerprinting. `threading.Semaphore(2)` rate-limits concurrent requests. IsraelRadar_ and YoavLimor use JS-rendered pages (unfetchable without headless browser)
- BlueSky (`public.api.bsky.app`): open API, no auth. Only Faytuks is active on BlueSky (others dormant). `BLUESKY_HANDLES` in config
- Nitter: only xcancel.com remains (5 dead instances removed Mar 2026). RSS returns "not whitelisted"; HTML scraping rate-limited
- When all Twitter methods fail, Google News fallback fires — extracts actual source name from title, marks `source: "google_news"` for dynamic column header
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
- **Two-model strategy**: Haiku for regular 2-hour summaries (fast/cheap), Opus for morning summary (best quality)
- Prompt requires `[Category] Day H:MM AM/PM - description` format. Parser regex handles both old 24-hour and new AM/PM formats, dash variants `[-–—]`
- All times in ET. Feed digest includes timezone context header for the LLM
- Valid categories: Military, Diplomatic, Political, Breaking, Markets, Strategic
- Each regular summary includes a `[Market Signal]` line — one-sentence market implications
- `_parse_ai_bullets()` returns `(bullets, market_signal)` tuple
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
- **Worktree venv access**: Worktree can't run `bash ./start.sh` via preview_start (permission errors). Use absolute path to main repo's venv python: `/Users/Yitzi/Desktop/shabbos situation monitor/venv/bin/python3`
- **TLS fingerprinting**: Some sites (twstalker.com) block Python `requests` via JA3 TLS fingerprint but allow `curl`. Use `subprocess.run(["curl", ...])` as workaround. macOS curl uses BoringSSL which passes
- **Deploying worktree changes**: After merging PRs on GitHub, must `git pull origin main` in the main repo AND kill ALL server processes (see below) — start.sh auto-restarts with new code
- **Kill ALL processes, not just port 8080**: `kill $(lsof -i :8080 -t)` only kills the one server holding the port. Zombie `start.sh` processes survive and keep crash-looping. Use: `pkill -f 'start.sh' ; pkill -f 'server.py'` then start fresh with ONE `./start.sh`
- ~~**start.sh needs a PID/lock guard**~~ — DONE: Port check at startup + inside crash-loop
- ~~**server.py must check port BEFORE doing work**~~ — DONE: Socket bind test in `__main__` before any fetching
- ~~**Failed fetches should preserve last-good cache**~~ — DONE for TOI: preserves old items on failure
- **Rate-limit backoff pattern**: `RateLimitError` exception + `safe_request(raise_on_429=True)` + per-source `_backoff_until`/`_backoff_minutes` globals. Exponential: doubles on each 429, resets on success, caps at 30min. Now on TOI, xcancel, Trump, and Reuters. Backoff state persists in `feed_cache.json` across restarts.
- **TOI liveblog URL ordering**: Date-specific URLs must be tried before the base `/liveblog/` URL, which points to a frozen 2020 archive. The structural fallback is too good — it finds entries on stale pages, so URL priority matters.
- **Always test with live data**: Import validation and syntax checks don't catch data-quality bugs like stale URLs returning old content. Run the actual fetcher and inspect the output.
- **Polymarket Gamma API**: Public REST, no auth. `events?slug=...` returns array of events with nested `markets[]`. Each market has `outcomePrices` (JSON string `'["0.40","0.60"]'`, index 0 = Yes probability). Multi-outcome events (e.g., "by March 31" / "by Dec 31") need sub-market slug targeting.
- **Metaculus API requires auth**: Returns 403 without API token. Free account needed. Not used currently.
- **Pending branch**: `feature/prediction-markets-ai-summary` — prediction market odds in AI summaries + candle-lighting Friday summary. Not yet deployed. WARNING: has regressions (lost ET timestamp fix, removed pruning). Must cherry-pick, not merge.
- **Think tank RSS**: FDD has working WordPress RSS with `content:encoded`. CSIS direct RSS (`/rss.xml`) is stale 2016 data — use Google News site-scoped instead. ISW direct RSS redirects to HTML — use Google News `site:understandingwar.org`.
- **Google News RSS site-scoping**: `https://news.google.com/rss/search?q=site:example.com+keywords` returns fresh articles from a specific domain. Title format is "Article Title - Source Name" — split on last " - " to extract source.
- **AI toggle persistence**: `ai_summary_enabled` must be saved to disk (feed_cache.json). Default is `False`; if not persisted, any server restart during unattended operation silently kills AI summaries.
- **ThreadPoolExecutor TimeoutError**: `as_completed(timeout=N)` raises `TimeoutError` when the deadline passes. Must wrap in try-except or the entire update cycle silently fails, abandoning pending futures.
- **caffeinate for long-running processes**: `caffeinate -i -w $$` prevents macOS idle sleep, tied to parent process lifetime. Essential for 72hr+ unattended operation.
- **Crash-loop detection**: Track restart timestamps in a sliding window. After N rapid restarts, exit instead of looping forever — prevents disk-filling log spam from fatal bugs.
