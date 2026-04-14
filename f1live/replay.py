"""F1 Live Copilot replay — replays archive data as if it were live.

Reads jsonStream files from a downloaded archive directory, feeds them through
the same state/event pipeline as the live daemon, and outputs events to stdout
with file dumps — fully compatible with Monitor-based skill consumption.

stdout: event lines (one per batch) → picked up by Claude Code Monitor
stderr: logging → goes to log file
File dumps: f1-live.md + f1-live.json every 3 simulated seconds

Usage:
    uv run -m f1live.replay ~/f1-data/suzuka-race --speed 1
    uv run -m f1live.replay /tmp/f1-replay/suzuka --speed 20
"""

import argparse
import json
import logging
import os
import signal
import sys
import tempfile
import time

from f1live.events import EventBatcher, EventDetector
from f1live.state import F1State

OUTPUT_JSON = os.environ.get("F1LIVE_OUTPUT", os.path.join(tempfile.gettempdir(), "f1-live.json"))
OUTPUT_MD = os.path.splitext(OUTPUT_JSON)[0] + ".md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("f1live.replay")

_running = True


def _handle_signal(signum, frame):
    global _running
    _running = False


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


def dump_state(state: F1State, state_dict: dict):
    """Atomically write f1-live.md and f1-live.json snapshot files."""
    try:
        md_tmp = OUTPUT_MD + ".tmp"
        with open(md_tmp, "w") as f:
            f.write(state.to_markdown())
        os.replace(md_tmp, OUTPUT_MD)

        json_tmp = OUTPUT_JSON + ".tmp"
        with open(json_tmp, "w") as f:
            f.write(json.dumps(state_dict, indent=2, ensure_ascii=False, default=str))
        os.replace(json_tmp, OUTPUT_JSON)
    except Exception:
        logger.exception("Error dumping state files")


def replay(data_dir: str, speed: float = 1.0):
    global _running

    messages = load_all_messages(data_dir)
    if not messages:
        print("[SESSION] No archive data found", flush=True)
        logger.error("No messages found in %s", data_dir)
        return

    logger.info("Loaded %d messages from %s", len(messages), data_dir)
    logger.info("Time range: %.1fs — %.1fs", messages[0][0], messages[-1][0])
    logger.info("Speed: %sx", speed)
    logger.info("Output: %s + %s", OUTPUT_MD, OUTPUT_JSON)

    state = F1State()
    detector = EventDetector()
    batcher = EventBatcher(window=5.0 / speed, cooldown=3.0 / speed)

    start_real = time.monotonic()
    start_sim = messages[0][0]
    last_detect_time = 0.0
    detect_interval = 3.0  # simulated seconds between detection cycles

    for ts, topic, content in messages:
        if not _running:
            break

        # Wait until this message's time (scaled by speed)
        elapsed_sim = ts - start_sim
        target_real = start_real + elapsed_sim / speed
        now = time.monotonic()
        if target_real > now:
            sleep_time = target_real - now
            # Sleep in small chunks so we can respond to signals
            while sleep_time > 0 and _running:
                time.sleep(min(sleep_time, 0.5))
                sleep_time = target_real - time.monotonic()

        if not _running:
            break

        # Feed to state
        state.process_message(topic, content, None)

        # Run detection + dump every ~3 simulated seconds
        if ts - last_detect_time >= detect_interval:
            last_detect_time = ts

            state_dict = state.to_dict()
            dump_state(state, state_dict)

            events = detector.detect(state_dict)
            batcher.add(events)

            line = batcher.flush()
            if line:
                print(line, flush=True)  # stdout → Monitor

    # Final flush
    if _running:
        state_dict = state.to_dict()
        dump_state(state, state_dict)

        remaining = batcher.flush()
        if remaining:
            print(remaining, flush=True)

    print("[SESSION] Replay complete", flush=True)
    logger.info("Replay complete. %d messages processed.", len(messages))


def main():
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    parser = argparse.ArgumentParser(description="Replay F1 archive data")
    parser.add_argument("data_dir", help="Directory with .jsonStream files")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Playback speed multiplier (default: 1.0 = real-time)")
    args = parser.parse_args()

    if not os.path.isdir(args.data_dir):
        print(f"[SESSION] Error: directory not found: {args.data_dir}", flush=True)
        sys.exit(1)

    print("[SESSION] F1 Live Copilot v0.1.0 (replay)", flush=True)
    print(f"[SESSION] Replaying from {args.data_dir} at {args.speed}x speed", flush=True)

    replay(args.data_dir, speed=args.speed)


if __name__ == "__main__":
    main()
