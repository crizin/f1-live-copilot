"""F1 Live Copilot daemon — connects to F1 SignalR, detects events, prints to stdout.

stdout: event lines (one per batch) → picked up by Claude Code Monitor
stderr: logging → goes to log file
File dumps: f1-live.md + f1-live.json every 3 seconds
"""

import asyncio
import json
import logging
import os
import signal
import sys
import tempfile

from f1live.events import EventBatcher, EventDetector
from f1live.signalr import connect_and_stream
from f1live.state import F1State

DUMP_INTERVAL = 3
OUTPUT_JSON = os.environ.get("F1LIVE_OUTPUT", os.path.join(tempfile.gettempdir(), "f1-live.json"))
OUTPUT_MD = os.path.splitext(OUTPUT_JSON)[0] + ".md"
TIMEOUT = int(os.environ.get("F1LIVE_TIMEOUT", "5400"))
WARMUP_SECONDS = float(os.environ.get("F1LIVE_WARMUP", "10"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("f1live")

state = F1State()
detector = EventDetector(warmup_seconds=WARMUP_SECONDS)
batcher = EventBatcher(window=5.0, cooldown=5.0)
_running = True


async def on_message(topic: str, content, timestamp: str | None):
    state.process_message(topic, content, timestamp)


async def dump_and_detect_loop():
    """Periodically dump state and run event detection."""
    while _running:
        try:
            state_dict = state.to_dict()

            # Dump files
            md_tmp = OUTPUT_MD + ".tmp"
            with open(md_tmp, "w") as f:
                f.write(state.to_markdown())
            os.replace(md_tmp, OUTPUT_MD)

            json_tmp = OUTPUT_JSON + ".tmp"
            with open(json_tmp, "w") as f:
                f.write(json.dumps(state_dict, indent=2, ensure_ascii=False, default=str))
            os.replace(json_tmp, OUTPUT_JSON)

            # Detect events
            events = detector.detect(state_dict)
            batcher.add(events)

            # Try flushing
            line = batcher.flush()
            if line:
                print(line, flush=True)  # stdout → Monitor

        except Exception:
            logger.exception("Error in dump/detect loop")

        await asyncio.sleep(DUMP_INTERVAL)


async def status_monitor():
    while _running:
        status = state.session.get("status", "")
        if status in ("Finalised", "Ends"):
            logger.info(f"Session {status}. Exiting in 60s...")
            print(f"[SESSION] {status} — race over!", flush=True)
            await asyncio.sleep(60)
            return
        await asyncio.sleep(5)


async def run():
    global _running

    logger.info("F1 Live Copilot daemon starting")
    logger.info(f"Output: {OUTPUT_MD} + {OUTPUT_JSON}")

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: setattr(sys.modules[__name__], '_running', False))

    dump_task = asyncio.create_task(dump_and_detect_loop())
    monitor_task = asyncio.create_task(status_monitor())

    # Signal ready
    print("[SESSION] Connecting to F1 Live Timing...", flush=True)

    try:
        await connect_and_stream(callback=on_message, timeout=TIMEOUT)
    except asyncio.CancelledError:
        pass
    finally:
        _running = False
        dump_task.cancel()
        monitor_task.cancel()

        # Final dump
        try:
            with open(OUTPUT_MD, "w") as f:
                f.write(state.to_markdown())
            with open(OUTPUT_JSON, "w") as f:
                f.write(state.to_json())
        except Exception:
            logger.exception("Error saving final state")

        logger.info("Daemon stopped.")


def main():
    print("[SESSION] F1 Live Copilot v0.1.0", flush=True)
    asyncio.run(run())


if __name__ == "__main__":
    main()
