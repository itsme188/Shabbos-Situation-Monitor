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
- `config.py` — HOST, PORT, REFRESH_INTERVAL, feed URLs, account lists
- `start.sh` — production launcher with crash recovery
- `launcher.applescript` — macOS one-click startup
- `templates/index.html` — dashboard template

## Known Issues (from first Shabbos run, Feb 27 2026 — grade: B-)
- **Polymarket:** resolved markets vanish from feed with no fallback. Need graceful handling when a market resolves mid-Shabbos (show resolved state, or swap to next market)
- **Twitter:** hours-long gaps with no updates. Nitter instances and syndication API are unreliable. Needs better fallback/retry or alternative data source
- **Times of Israel liveblog:** went silent for hours. Possible causes: liveblog URL changes on day rollover, Shabbos in Israel = less publishing, or CSS selectors broke. Investigate liveblog URL pattern across days
- **Trump Truth Social:** posts containing links show opaque URLs instead of readable content. Need to resolve/expand link previews or at least show the destination domain
- Core value delivered: all key breaking news was surfaced

## Feed Architecture
- Each feed has: fetcher function, cache entry, error state, last_updated timestamp
- `update_all_feeds()` runs all fetchers concurrently via ThreadPoolExecutor
- Twitter uses 3-tier fallback: syndication API → Nitter RSS → Nitter HTML scraping
- Polymarket filters out closed/resolved markets and sorts by soonest deadline
- Shabbos snapshot captures Polymarket probability at candle lighting for delta display
