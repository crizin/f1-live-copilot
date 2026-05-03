# data/ — Live Season Data

Files in this directory are fetched via WebFetch during race sessions.
They contain frequently-updated information that changes throughout the season.

## Files

| File | Purpose | Update frequency |
|------|---------|-----------------|
| `standings.md` | Championship standings (WDC + WCC) | After each race weekend |
| `storylines.md` | Season narratives, drama, memes | After notable events |

## Update Rules

### standings.md

**Trigger**: After every race weekend.

**Update method**: Run the auto-update script — do NOT hand-edit.

```bash
uv run --extra dev dev/update-standings.py
```

This pulls live data from the jolpica-f1 API (Ergast successor) and rewrites
the file in place. Default columns: most recent 5 rounds + total points.
Override with `--recent 10`, `--year 2027`, or `--dry-run` to preview.

**Source**: `https://api.jolpi.ca/ergast/f1/{year}/` (no API key required)

**Why a script**: Hand-curated standings drift fast and silently — the previous
version of this file was a placeholder for a month before being noticed.

### storylines.md

**Trigger**: "update storylines" or "update storylines after [GP name]"

**Sources**:
- Race recap: WebSearch "[GP name] 2026 F1 race recap highlights"
- Controversies: WebSearch "F1 2026 [topic] controversy"
- Driver/team news: WebSearch "F1 2026 [driver/team] news"
- Fan culture: WebSearch "F1 2026 memes viral moments reddit"

**Steps**:
1. WebSearch for recent F1 news since the last update date
2. Add new items to relevant sections (Big Stories, Rivalries, Memes, Incidents)
3. Update existing storylines if status changed
4. Remove stale items no longer relevant
5. Update "Last update" line at the top

**Writing guidelines**:
- Only include things Claude wouldn't know from training data
- Write conversationally — this feeds a race-watching companion, not a news article
- Focus on context useful during live commentary
  (e.g., "Hamilton and Leclerc collided last race" matters for their next battle)

## After Updating

Commit and push to `main` so the plugin can WebFetch the latest version.
