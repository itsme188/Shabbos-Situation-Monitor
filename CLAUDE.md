# Shabbos Situation Monitor

## Quick Start
- `preview_start("shabbos-monitor")` — preferred in Claude Code sessions
- `./start.sh` in standalone Terminal — for unattended/Shabbos operation
- AppleScript launcher — double-click from Desktop, opens Terminal + Safari
- NEVER start via `Bash` tool for long-running use — dies when Claude Code exits

## Architecture
- Flask on Python 3, port 8080, binds 0.0.0.0
- APScheduler refreshes feeds every 5 min; watchdog thread recovers silent failures
- `feed_cache.json` persists across restarts (max 2hr age, atomic writes)
- `start.sh` has auto-restart loop, venv management, graceful SIGINT handling

## Key Files
- `server.py` — main app (~1020 lines), routes, scheduler, all feed fetchers
- `config.py` — HOST, PORT, REFRESH_INTERVAL, feed URLs, OSINT account lists (13 accounts)
- `start.sh` — production launcher with crash recovery
- `launcher.applescript` — macOS one-click startup
- `templates/index.html` — dashboard template

## Known Issues (from first Shabbos run, Feb 27 2026 — grade: B-)
- ~~**Polymarket:** resolved markets vanish from feed with no fallback~~ — FIXED: Resolved markets now show with YES/NO badge. Display capped to all active + 1 most-recently-resolved. Delta matches by market title, not array position.
- ~~**Twitter:** hours-long gaps with no updates~~ — FIXED: 4-tier fallback (syndication → BlueSky → Nitter RSS → Nitter HTML), xcancel.com with "mistique" UA, Google News as last resort with source attribution
- ~~**Times of Israel liveblog:** went silent for hours~~ — FIXED: Israel timezone for date URLs, zero-padded format variant, structural CSS fallback, stale cache clearing
- ~~**Trump Truth Social:** posts containing links show opaque URLs instead of readable content~~ — FIXED: `extract_text_with_links()` now shows destination URLs inline. Empty media-only/retruth posts are filtered out.
- Core value delivered: all key breaking news was surfaced

## Known Issues (from second Shabbos run, Mar 7 2026 — grade: F)
- **CRITICAL: Zombie start.sh processes**: 8 concurrent start.sh instances were running (some from days earlier). Each crash-loops server.py every ~6s, generating 1000+ feed cycles in 10 min. This hammered all sources into rate-limiting and caused every other failure.
- **server.py does expensive work before port binding**: `update_all_feeds()` fires 30+ HTTP requests BEFORE `app.run()` tries to bind port 8080. Doomed instances still flood all external sources.
- **Cache race condition**: Multiple processes writing `feed_cache.json` simultaneously — stale data overwrites fresh data randomly.
- **TOI permanent 429**: Flood from zombie processes caused Times of Israel to block our IP for entire Shabbos.
- **OSINT degraded to 3/13 accounts**: TwStalker rate-limited by concurrent curl floods. 5,509 "All methods failed" logged.
- **Trump raw URLs**: Some Truth Social posts still show opaque `truthsocial.com/...` URLs instead of text content.
- **AI summary paused/confused**: Multiple competing scheduler instances from zombie processes.
- **Logs lost**: 35K lines in 10 min from crash-loop caused log rotation, wiping actual Shabbos hours.

## Feed Architecture
- Each feed has: fetcher function, cache entry, error state, last_updated timestamp
- `update_all_feeds()` runs all fetchers concurrently via ThreadPoolExecutor
- **OSINT column** (UI label) backed by `twitter_list` cache key — internal names kept for cache compatibility
- OSINT uses 5-tier fallback: syndication → TwStalker → BlueSky → Nitter RSS → Nitter HTML → Google News
- **TwStalker** (`twstalker.com`): primary source, works for 11/13 accounts. Uses `curl` subprocess (not Python `requests`) because TwStalker blocks via TLS fingerprinting. `threading.Semaphore(2)` rate-limits concurrent requests. IsraelRadar_ and YoavLimor use JS-rendered pages (unfetchable without headless browser)
- BlueSky (`public.api.bsky.app`): open API, no auth. Only Faytuks is active on BlueSky (others dormant). `BLUESKY_HANDLES` in config
- Nitter: only xcancel.com remains (5 dead instances removed Mar 2026). RSS returns "not whitelisted"; HTML scraping rate-limited
- When all Twitter methods fail, Google News fallback fires — extracts actual source name from title, marks `source: "google_news"` for dynamic column header
- Polymarket filters out closed/resolved markets and sorts by soonest deadline
- Shabbos snapshot captures Polymarket probability at candle lighting for delta display
- Trump RSS (`trumpstruth.org/feed`): many entries are media-only (`<p></p>` body) — always extract text before deciding to include

## AI Summary
- **Hourly accumulation**: Each hour generates a summary (max 24 stored). Prepended to list, capped at 24 entries
- **12-hour overview**: Opus generates a paragraph every 3 hours from accumulated hourly summaries. Pinned at top of column
- **Two-model strategy**: Haiku for hourly (fast/cheap), Opus for overview (best quality)
- Prompt requires `[Category] HH:MM - description` format. Parser regex handles dash variants `[-–—]`
- All times in ET. Feed digest includes timezone context header for the LLM
- Valid categories: Military, Diplomatic, Political, Breaking, Markets
- Cache fields: `hourly_summaries[]`, `overview`, `overview_updated` — all persisted to `feed_cache.json`

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
- **CRITICAL — Kill ALL processes, not just port 8080**: `kill $(lsof -i :8080 -t)` only kills the one server holding the port. Zombie `start.sh` processes survive and keep crash-looping. Use: `pkill -f 'start.sh' ; pkill -f 'server.py'` then start fresh with ONE `./start.sh`
- **start.sh needs a PID/lock guard**: Currently has no dedup — launching it multiple times (from Terminal, AppleScript, Claude Code) creates parallel crash-loops. Must add port check or lock file before starting server.py
- **server.py must check port BEFORE doing work**: Move `update_all_feeds()` to AFTER successful port bind, or add early port-availability check. Currently every doomed startup wastes 30+ HTTP requests
- **Failed fetches should preserve last-good cache**: Currently `fetch_toi()` and others clear items on failure. Should keep stale items with a "stale" flag rather than showing empty columns
