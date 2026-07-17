# Shabbos Situation Monitor — TODO

Items are dated when added. Tick with `- [x]` plus date + commit hash when shipped.

## Open

- [ ] (2026-07-17) Post-Shabbat postmortem for the Jul 17–18 run — grade it, log issues in CLAUDE.md Known Issues, and check whether the two date-scoped prediction markets ("by July 31") resolved and need replacing.
- [ ] (2026-07-17) Surface per-account OSINT health in the UI or logs — `cache["twitter_list"]["account_status"]` already distinguishes "crowded out by the freshest-15 cap" from "all fetch methods failed", but nothing displays it. Would have saved a false alarm during this session's health check.
- [ ] (2026-07-17) Consider auto-refreshing PREDICTION_MARKETS: a fetcher fallback that queries the Gamma API for active Iran-related events by volume when a configured market is closed, instead of requiring manual slug refresh.
- [ ] (2026-07-17) IsraelRadar_ and YoavLimor remain unfetchable (JS-rendered TwStalker pages) — evaluate a headless-browser tier or drop them from OSINT_ACCOUNTS.

## Shipped

- [x] (2026-07-17, b53558b) Trailing Yom Tov→Shabbat merge fix — plain Shabbos windows no longer absorbed into Yom Tov windows; verified against tonight's regular Shabbos.
- [x] (2026-07-17, b53558b) Filter resolved Polymarket markets on the `closed` flag; no silent substitution of differently-dated sub-markets.
- [x] (2026-07-17, aafa9c0) Refresh PREDICTION_MARKETS with 5 live Iran-conflict markets (slugs verified against Gamma API).
- [x] (2026-07-17, aafa9c0) Morning summary model upgraded claude-opus-4-6 → claude-opus-4-8.
- [x] (2026-07-17, aafa9c0) test-feeds skill corrected (toi_liveblog cache key, think tanks/markets/oil rows, OSINT cap note, update_all_feeds() state-clobber warning).
