> Archived from CLAUDE.md on 2026-08-10. All facts preserved; read for run-by-run Shabbos history.

# Shabbos Run History (Known Issues per run)

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

## Resolved lessons (formerly struck-through in Lessons)

- ~~**start.sh needs a PID/lock guard**~~ — DONE: Port check at startup + inside crash-loop
- ~~**server.py must check port BEFORE doing work**~~ — DONE: Socket bind test in `__main__` before any fetching
- ~~**Failed fetches should preserve last-good cache**~~ — DONE for TOI: preserves old items on failure
