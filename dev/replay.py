#!/usr/bin/env python3
"""Replay F1 static archive data — dev wrapper.

Delegates to f1live.replay. Defaults to 50x speed for quick testing.

Usage:
    uv run dev/replay.py dev/data/suzuka-race/ --speed 50
    uv run dev/replay.py dev/data/suzuka-race/ --speed 100 --events-only
"""
# /// script
# requires-python = ">=3.10"
# ///

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time

from f1live.events import EventBatcher, EventDetector
from f1live.replay import load_all_messages
from f1live.state import F1State


def replay_dev(data_dir: str, speed: float = 50.0, events_only: bool = False, dump_md: bool = False):
    """Dev-oriented replay with timestamp prefixes and optional markdown dumps."""
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
    detect_interval = 3.0

    for i, (ts, topic, content) in enumerate(messages):
        elapsed_sim = ts - start_sim
        target_real = start_real + elapsed_sim / speed
        now = time.monotonic()
        if target_real > now:
            time.sleep(target_real - now)

        state.process_message(topic, content, None)

        if ts - last_detect_time >= detect_interval:
            last_detect_time = ts

            state_dict = state.to_dict()
            events = detector.detect(state_dict)
            batcher.add(events)

            line = batcher.flush()
            if line:
                h = int(elapsed_sim // 3600)
                m = int((elapsed_sim % 3600) // 60)
                s = int(elapsed_sim % 60)
                prefix = f"[{h:02d}:{m:02d}:{s:02d}]"
                print(f"{prefix} {line}", flush=True)

            if dump_md and not events_only:
                print(f"\n--- Lap {state.session.get('lap', '?')} ---", file=sys.stderr)
                print(state.to_markdown()[:500], file=sys.stderr)

    remaining = batcher.flush()
    if remaining:
        print(f"[FINAL] {remaining}", flush=True)

    print(f"\nReplay complete. {len(messages):,} messages processed.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Replay F1 archive data (dev)")
    parser.add_argument("data_dir", help="Directory with .jsonStream files")
    parser.add_argument("--speed", type=float, default=50.0,
                        help="Playback speed multiplier (default: 50)")
    parser.add_argument("--events-only", action="store_true",
                        help="Only show detected events (no state dumps)")
    parser.add_argument("--dump-md", action="store_true",
                        help="Periodically dump markdown state to stderr")
    args = parser.parse_args()

    replay_dev(args.data_dir, speed=args.speed, events_only=args.events_only, dump_md=args.dump_md)


if __name__ == "__main__":
    main()
