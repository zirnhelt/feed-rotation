# TODO

## AUTO — feed errors (regenerated on every run)

<!-- AUTO-GENERATED: do not edit this section manually -->
_Last regenerated: never — run `python generate_podcast_feed.py` to populate_

No feed errors recorded yet.

## Notes

_Record disabled sources, manual changes, and follow-ups here. This section is preserved across runs._

### Disabled sources

| Source | Disabled | Reason | Fallback |
|---|---|---|---|
| My Cariboo Now | March 2026 | 403 Forbidden — blocking GitHub Actions user-agent. Same network as My East Kootenay Now; watch that one too. | GN fallback URL in feeds.opml comment |

### Pending source checks (from FEEDS_MAINTENANCE.md)

- [ ] **Haida Gwaii Observer** (Friday) — check whether `https://www.haidagwaiiobserver.com/feed/` exists. If yes, add direct feed and remove GN fallback note in feeds.opml.
- [ ] **Connecting BC broadband** (Sunday) — check `https://www.connectingbc.ca` for a public RSS feed.
- [ ] **My East Kootenay Now** — watch for 403 errors (same network as My Cariboo Now, which 403-ed in March 2026).
- [ ] **CBC Arts RSS URL** — CBC RSS URLs change occasionally. Verify `https://www.cbc.ca/cmlink/rss-arts` still resolves.
- [ ] **GN feeds volume** — after first week of runs, check that GN BC Wildfire, GN BC Working Lands, and GN Rural BC Infrastructure are producing articles with `_is_bonus: false`.

### Keyword tuning notes

- APTN News mentions "guardian program" and "UNDRIP" frequently but Thursday only matched on "indigenous" and "first nations" initially. Added "guardian program" and "UNDRIP" to Thursday keywords in March 2026.
- "community" was considered for Wednesday but is too generic — omitted to avoid pulling in off-topic matches.
