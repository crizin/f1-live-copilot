#!/usr/bin/env python3
"""Replay F1 static archive data through the daemon for testing.

Reads jsonStream files, feeds them to F1State with correct timing,
and runs event detection — simulating a real race at adjustable speed.

Usage:
    uv run dev/replay.py dev/data/suzuka-race/ --speed 50
    uv run dev/replay.py dev/data/suzuka-race/ --speed 100 --events-only
"""
# /// script
# requires-python = ">=3.10"
# ///

import argparse
import json
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from f1live.events import EventBatcher, EventDetector
from f1live.state import F1State


def parse_timestamp(ts: str) -> float:
    """Parse 'HH:MM:SS.mmm' timestamp to seconds."""
    ts = ts.strip().lstrip("\ufeff")
    parts = ts.split(":")
    if len(parts) != 3:
        return 0.0
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def load_all_messages(data_dir: str) -> list[tuple[float, str, dict]]:
    """Load all jsonStream files and merge into time-sorted message list."""
    messages = []

    for filename in os.listdir(data_dir):
        if not filename.endswith(".jsonStream"):
            continue
        topic = filename.replace(".jsonStream", "")

        filepath = os.path.join(data_dir, filename)
        with open(filepath, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Find where JSON starts
                brace_idx = line.find("{")
                if brace_idx < 0:
                    continue
                ts_str = line[:brace_idx]
                try:
                    ts = parse_timestamp(ts_str)
                    content = json.loads(line[brace_idx:])
                    messages.append((ts, topic, content))
                except (ValueError, json.JSONDecodeError):
                    continue

    messages.sort(key=lambda x: x[0])
    return messages


def replay(data_dir: str, speed: float = 1.0, events_only: bool = False, dump_md: bool = False):
    messages = load_all_messages(data_dir)
    if not messages:
        print("No messages found!", file=sys.stderr)
        return

    print(f"Loaded {len(messages):,} messages from {data_dir}", file=sys.stderr)
    print(f"Time range: {messages[0][0]:.1f}s — {messages[-1][0]:.1f}s", file=sys.stderr)
    print(f"Speed: {speed}x\n", file=sys.stderr)

    state = F1State()
    detector = EventDetector()
    batcher = EventBatcher(window=5.0 / speed, cooldown=3.0 / speed)

    start_real = time.monotonic()
    start_sim = messages[0][0]
    last_detect_time = 0.0
    detect_interval = 3.0  # Same as daemon dump interval

    for i, (ts, topic, content) in enumerate(messages):
        # Timing: wait until this message's time (scaled by speed)
        elapsed_sim = ts - start_sim
        target_real = start_real + elapsed_sim / speed
        now = time.monotonic()
        if target_real > now:
            time.sleep(target_real - now)

        # Feed to state
        state.process_message(topic, content, None)

        # Run detection every ~3 simulated seconds
        if ts - last_detect_time >= detect_interval:
            last_detect_time = ts

            state_dict = state.to_dict()
            events = detector.detect(state_dict)
            batcher.add(events)

            line = batcher.flush()
            if line:
                # Format timestamp for readability
                h = int(elapsed_sim // 3600)
                m = int((elapsed_sim % 3600) // 60)
                s = int(elapsed_sim % 60)
                prefix = f"[{h:02d}:{m:02d}:{s:02d}]"
                print(f"{prefix} {line}", flush=True)

            if dump_md and not events_only:
                print(f"\n--- Lap {state.session.get('lap', '?')} ---", file=sys.stderr)
                print(state.to_markdown()[:500], file=sys.stderr)

    # Final flush
    remaining = batcher.flush()
    if remaining:
        print(f"[FINAL] {remaining}", flush=True)

    print(f"\nReplay complete. {len(messages):,} messages processed.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Replay F1 archive data")
    parser.add_argument("data_dir", help="Directory with .jsonStream files")
    parser.add_argument("--speed", type=float, default=50.0,
                        help="Playback speed multiplier (default: 50)")
    parser.add_argument("--events-only", action="store_true",
                        help="Only show detected events (no state dumps)")
    parser.add_argument("--dump-md", action="store_true",
                        help="Periodically dump markdown state to stderr")
    args = parser.parse_args()

    replay(args.data_dir, speed=args.speed, events_only=args.events_only, dump_md=args.dump_md)


if __name__ == "__main__":
    main()
