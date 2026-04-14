# F1 Live Copilot — Development Guide

## Project Overview

A Claude Code plugin that lets users watch F1 races with an AI companion.
Not a commentator bot — a friend who watches alongside you, reacting and chatting.

## Architecture

```
F1 SignalR WebSocket → f1live daemon → stdout events → Monitor → Claude → user
                                     → file dumps (f1-live.md/json) → Read on demand
```

- **signalr.py**: WebSocket connection to livetiming.formula1.com/signalr
- **state.py**: Delta merge engine (F1 sends changes only, we maintain full state)
- **events.py**: State diff → event detection + batching (5s window, 5s cooldown)
- **main.py**: Daemon entry point (Monitor-compatible: stdout=events, stderr=logs)

## Seasonal Updates

At the start of each F1 season (typically late February):

### 1. Update `skills/start-f1/references/season-2026.md`
- Rename file to new year (e.g., `season-2027.md`)
- Update the teams & drivers table (check formula1.com for official lineup)
- Update regulation changes (if any major rule changes)
- Update the calendar (check formula1.com/en/racing/2027.html)
- Update SKILL.md reference path if filename changed

### 2. Check SignalR compatibility
- F1's SignalR endpoint is unofficial — it may change between seasons
- Test with the first practice session of the new season
- Compare topic structure with previous year's archive data
- If topics change, update `signalr.py` TOPICS lists and `state.py` handlers

### 3. Download new season archive data
```bash
# After first race weekend, download archive for testing
uv run dev/download-archive.py --path "2027/2027-XX-XX_Race_Name/2027-XX-XX_Race" -o dev/data/new-race
uv run dev/replay.py dev/data/new-race/ --speed 50 --events-only
```

## Development

```bash
# Install dependencies
uv sync

# Download archive data for testing
uv run dev/download-archive.py --path "2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race" -o dev/data/suzuka-race --skip-telemetry

# Replay at 100x speed (events only)
uv run dev/replay.py dev/data/suzuka-race/ --speed 100 --events-only

# Replay with markdown state dumps
uv run dev/replay.py dev/data/suzuka-race/ --speed 50 --dump-md

# Test plugin locally
claude --plugin-dir .
```

## Event Detection Tuning

When adjusting event detection, replay against archive data to verify.
Key filters in `events.py`:
- **Warmup suppression**: Overtakes suppressed for 2 laps after session start
  (grid → race position shuffle is not real overtaking)
- **Pit cycle filter**: Drivers in pit or recently out (1 lap) are excluded from overtakes
- **Mass shuffle filter**: When 5+ drivers gain position simultaneously,
  single-position gains are suppressed (likely pit-induced, not on-track)
- **RC dedup**: Recent race control messages are deduplicated (last 20)

## Plugin Structure

```
.claude-plugin/plugin.json  ← Plugin metadata for marketplace
skills/start-f1/SKILL.md    ← Main skill (how Claude should behave)
skills/start-f1/references/  ← Season data, personas (loaded on demand)
bin/                         ← Executables (added to PATH)
f1live/                      ← Python daemon package
dev/                         ← Development tools (not needed by end users)
```
