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
- ~~**Trump Truth Social:** posts containing links show opaque URLs instead of readable content~~ — FIXED: `extract_text_with_links()` now shows destination URLs inline. Empty media-only/retruth posts are filtered out.
- Core value delivered: all key breaking news was surfaced

## Feed Architecture
- Each feed has: fetcher function, cache entry, error state, last_updated timestamp
- `update_all_feeds()` runs all fetchers concurrently via ThreadPoolExecutor
- Twitter uses 3-tier fallback: syndication API → Nitter RSS → Nitter HTML scraping
- Polymarket filters out closed/resolved markets and sorts by soonest deadline
- Shabbos snapshot captures Polymarket probability at candle lighting for delta display
- Trump RSS (`trumpstruth.org/feed`): many entries are media-only (`<p></p>` body) — always extract text before deciding to include

## AI Summary
- Prompt requires `[Category] HH:MM - description` format for per-event timestamps
- Parser uses regex with fallback: extracts event time if present, otherwise uses generation time
- Dash variants `[-–—]` handled in regex since LLMs sometimes emit typographic dashes
- Valid categories: Military, Diplomatic, Political, Breaking, Markets

## Lessons & Best Practices
- **Truthy-but-empty HTML**: RSS fields like `<p></p>` are truthy strings that yield nothing after stripping. Always validate *processed* output, not raw input, before using it.
- **Dashboard grid**: 5 columns with `repeat(5, 1fr)` at ≥1600px; responsive breakpoints collapse to 2 columns then 1. AI Summary is the 5th column, not a separate section.
- **LLM output parsing**: When asking an LLM for structured output, always include a fallback for when it doesn't follow the format exactly. The regex-with-fallback pattern is robust.
- **Preview in worktrees**: The main repo may already have a server on port 8080. Use a different port when testing from a worktree.
