# content-schedule

A reusable **Claude Code / Claude Agent skill** — the **editorial calendar / scheduling** layer for a content map. It scores each drafted article by importance and books it into a CMS publish slot (`future`), then writes the schedule back to the map so every publisher shares one calendar and nothing collides.

> Part of a 4-skill content-ops toolkit:
> **[content-map-builder](https://github.com/wolfganghuang0083/content-map-builder)** (plan *what* to write) →
> **[content-pipeline](https://github.com/wolfganghuang0083/content-pipeline)** (write & draft it) →
> **content-schedule** (decide *when* it goes live) →
> **[internal-linking](https://github.com/wolfganghuang0083/internal-linking)** (weave the cluster).

## What it does

- **Scores importance 0–100** from your content-map columns (strategic role, funnel stage, search opportunity / quick-wins, decision intent, timeliness).
- **Books the highest-impact drafts first** into the earliest free slots (P0 jumps the queue).
- **One shared calendar** — reads already-occupied slots (the map's schedule column + existing CMS `future` posts) so multiple publishers never double-book.
- **Writes back** status / scheduled-time / admin-edit link to the map.

## Quick start

```bash
git clone https://github.com/wolfganghuang0083/content-schedule.git ~/.claude/skills/content-schedule

SHEET=<your content-map sheet id>
BASE=https://your-site.com/wp-json
SITE=https://your-site.com

# 1) See current rows + importance scores (writes nothing)
python3 ~/.claude/skills/content-schedule/scripts/schedule.py --list --sheet-id "$SHEET"

# 2) Plan the calendar (prints, writes nothing)
python3 ~/.claude/skills/content-schedule/scripts/schedule.py --plan --sheet-id "$SHEET" --start 2026-06-13 --per-day 1

# 3) Apply — set CMS future + write back to the map (needs CMS creds in env)
WP_USER=<user> WP_APP_PW='xxxx xxxx xxxx' \
  python3 ~/.claude/skills/content-schedule/scripts/schedule.py --apply \
  --sheet-id "$SHEET" --base "$BASE" --site "$SITE" --start 2026-06-13 --per-day 1
```

## Setup

- **Google access**: an OAuth token JSON with the `spreadsheets` scope (default `~/.config/google/token.json`, override `--token` / `GOOGLE_TOKEN`). Requires `google-api-python-client`.
- **CMS auth**: env vars `WP_USER` / `WP_APP_PW` (WordPress application password). **Never hardcoded.**
- **Column mapping**: `scripts/schedule.py` has a `COL` block at the top — line it up with your content map (the [content-map-builder](https://github.com/wolfganghuang0083/content-map-builder) template layout is the default).
- **CMS swap**: WordPress REST is the reference implementation; to use another CMS, replace the `wp()` calls.

## Scoring rubric (tweak in the CONFIG block)

| Signal | Weight |
|---|---|
| Strategic role | core +35 / blue-ocean +28 / flank +22 / long-tail +12 |
| Funnel stage (time-to-value) | BOFU +25 / MOFU +18 / TOFU +8 |
| Search quick-win | +min(20, impressions/80); +10 if impressions≥200 & CTR<2% |
| Has conversion goal | +6 |
| Decision-intent keyword | +10 |
| Timely topic | +6 |

→ **P0 ≥70 · P1 55–69 · P2 40–54 · P3 <40**. P0 books the earliest slot; P3 goes to the backlog tail.

## License

MIT.
