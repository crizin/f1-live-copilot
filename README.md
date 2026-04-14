# 🏎️ F1 Live Copilot

> [한국어 README](README.ko.md)

**Watch Formula 1 races with AI — not as a commentator, but as a friend on the couch.**

F1 Live Copilot connects directly to F1's official live timing data and turns your Claude Code session into a real-time race companion. It reacts to overtakes, pit strategies, safety cars, and all the drama — with genuine excitement, frustration, and analysis.

> ⚠️ **Early Development** — This plugin is under active development. First public release planned mid-2026 season.

## Why?

Watching sports alone is boring. You want someone to yell at the screen with, someone who notices the undercut working perfectly, someone who groans when your driver gets a 5-second penalty.

F1 Live Copilot is that someone.

**What it's NOT:**
- A stats dashboard (use F1's official app for that)
- A robotic feed that recites every position change
- A replacement for TV commentary

**What it IS:**
- A friend who watches the race with you and actually *gets it*
- Someone who spots strategic moves and shares their take
- A companion who matches your energy — hyped when you're hyped, analytical when you want depth

## How It Works

```
You: /f1-live-copilot:start-f1

Copilot: Connecting to F1 Live Timing... Miami GP Race, Lap 1/57. Let's go! 🏁

  [15 laps later]

Copilot: Oh SC is out!! And look — NOR just pitted 2 laps ago on fresh mediums.
         That's insane luck. Everyone ahead still needs to stop...
         This could be a free jump to P3 if McLaren plays it right.

You: Hamilton's had a rough day huh

Copilot: Yeah the undercut completely didn't work — LEC pitted one lap earlier
         and came out right in front. Sector 2 times are decent though,
         it's more the strategy call than pace. Ferrari might split strategies
         for the second stint to cover both options.
```

## Architecture

```
No server. Everything runs locally.

/start-f1
  → Local daemon connects to F1's official SignalR WebSocket
  → Maintains full race state from delta messages
  → Detects events (overtakes, pits, flags, fastest laps)
  → Events → Claude Code Monitor → AI reacts naturally
  → Full state snapshot available on demand (f1-live.md)
```

- **Zero API keys** — F1's live timing is a public endpoint
- **Zero server costs** — runs entirely on your machine
- **Zero data redistribution** — you connect directly, like opening F1's timing page

## Installation

```bash
# Add the plugin
/plugin marketplace add crizin/f1-live-copilot

# Install
/plugin install f1-live-copilot
```

**Requirements:** Python 3.10+, [uv](https://docs.astral.sh/uv/)

## Usage

```bash
# Start during a live F1 session
/f1-live-copilot:start-f1

# (Future) With persona
/f1-live-copilot:start-f1 expert     # Deep tactical analysis
/f1-live-copilot:start-f1 casual     # Just the highlights
```

## Event Detection

The daemon detects and pushes these events:

| Event | What it catches |
|-------|----------------|
| Overtakes | Real on-track passes (filters out pit-cycle position changes) |
| Pit In/Out | Who pitted, what tire they took, stint number |
| Safety Car / VSC | Immediate alert + strategic implications |
| Fastest Lap | New overall fastest, who beat whom |
| DNF / Retirement | Driver out of the race |
| Race Control | Penalties, investigations, track limits, flags |
| Track Status | Yellow, SC deployed, red flag, all clear |

Events are batched (5-second window) so Claude isn't overwhelmed during busy moments like SC restarts.

## Development

```bash
git clone https://github.com/crizin/f1-live-copilot
cd f1-live-copilot
uv sync

# Download past race data for testing
uv run dev/download-archive.py \
  --path "2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race" \
  -o dev/data/suzuka --skip-telemetry

# Replay at 50x speed
uv run dev/replay.py dev/data/suzuka/ --speed 50 --events-only

# Test plugin locally
claude --plugin-dir .
```

## Legal

This plugin connects to F1's publicly available live timing endpoint — the same data source
that powers the official F1 timing page. No data is redistributed; each user connects directly.
Similar to projects like [openf1.org](https://openf1.org) and [Fast-F1](https://github.com/theOehrly/Fast-F1).

## License

MIT
