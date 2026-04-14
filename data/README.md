# data/ — Live Season Data

Files in this directory are fetched via WebFetch during race sessions.
They contain frequently-updated information that changes throughout the season.

## Files

| File | Purpose | Update frequency |
|------|---------|-----------------|
| `standings-2026.md` | Championship standings (WDC + WCC) | After each race weekend |
| `storylines.md` | Season narratives, drama, memes | After notable events |

## Update Rules

### standings-2026.md

**Trigger**: "update standings" or "update standings after [GP name]"

**Sources**:
1. https://www.formula1.com/en/results/2026/drivers — Official WDC standings
2. https://www.formula1.com/en/results/2026/team — Official WCC standings

**Steps**:
1. WebFetch both URLs above
2. Replace Drivers' Championship table (keep per-race result columns, add new round)
3. Replace Constructors' Championship table
4. Update "Last update" line at the top
5. Update "Season Notes" (next race, notable changes)

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
