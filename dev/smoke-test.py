#!/usr/bin/env python3
"""Smoke test — proves the package still works after a dependency bump.

Replaying alone only exercises state/events off local files, so a bump to
openai, httpx, requests or websockets sails straight through it. Each client
whose breaking change would otherwise surface mid-race is constructed here
too. Nothing reaches the network: the archive is downloaded by the caller.

With no archive given it generates a synthetic one (dev/make-fixture.py) and
replays that, so the whole run is hermetic. Pass a real downloaded archive to
replay actual session data instead.

Usage:
    uv run --extra dev dev/smoke-test.py
    uv run --extra dev dev/smoke-test.py dev/data/suzuka-race/
"""

import argparse
import inspect
import json
import os
import subprocess
import sys
import tempfile

MODULES = [
    "signalr", "state", "events", "main",
    "replay", "download", "latest_session", "radio_stt",
]

# Topics without which a replay is not a race — an archive missing any of these
# is an incomplete download, not a broken build.
REQUIRED_TOPICS = [
    "TimingData", "DriverList", "LapCount",
    "SessionStatus", "SessionInfo", "RaceControlMessages",
]

# Floors, not counts: well under what a full race emits, so the numbers survive
# detection tuning and only a pipeline that has actually gone quiet trips them.
MIN_EVENTS = {
    "SESSION": 2, "LAP": 20, "OVERTAKE": 20,
    "PIT_IN": 5, "PIT_OUT": 5, "RC": 10, "FASTEST_LAP": 1,
}

REPLAY_SPEED = 3000
REPLAY_TIMEOUT = 600

UNREACHABLE = "http://127.0.0.1:9/nothing.mp3"


class Failure(Exception):
    pass


def check_imports():
    import importlib

    for name in MODULES:
        importlib.import_module(f"f1live.{name}")
    return f"{len(MODULES)} modules import"


def check_openai():
    os.environ.setdefault("OPENAI_API_KEY", "sk-smoke-test-not-a-real-key")

    from openai import OpenAI

    client = OpenAI()
    params = inspect.signature(client.audio.transcriptions.create).parameters
    missing = [p for p in ("model", "file", "prompt") if p not in params]
    if missing:
        raise Failure(f"audio.transcriptions.create lost parameters: {missing}")

    import openai

    return f"openai {openai.__version__} client + transcription signature"


def check_radio_stt_degrades():
    from f1live import radio_stt

    if not radio_stt.enabled():
        raise Failure("enabled() false despite OPENAI_API_KEY being set")
    if radio_stt._transcribe_sync(UNREACHABLE) is not None:
        raise Failure("unreachable clip returned a transcript instead of None")
    return "radio transcription degrades to None offline"


def check_httpx():
    import httpx

    with httpx.Client() as client:
        if client.is_closed:
            raise Failure("httpx.Client closed on construction")
    return f"httpx {httpx.__version__} client (dev/update-standings.py)"


def archive_is_usable(archive: str) -> str | None:
    """Return the reason the archive cannot be replayed, or None if it can."""
    if not os.path.isdir(archive):
        return f"not a directory: {archive}"
    for topic in REQUIRED_TOPICS:
        path = os.path.join(archive, f"{topic}.jsonStream")
        if not os.path.exists(path):
            return f"missing {topic}.jsonStream"
        if os.path.getsize(path) == 0:
            return f"empty {topic}.jsonStream"
    return None


def make_fixture(out_dir: str) -> str:
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "make-fixture.py")
    proc = subprocess.run([sys.executable, script, out_dir],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise Failure(f"fixture generation failed\n{proc.stderr[-2000:]}")
    return proc.stdout.strip()


def run_replay(archive: str, dump_json: str) -> str:
    env = {**os.environ, "F1LIVE_OUTPUT": dump_json}
    proc = subprocess.run(
        [sys.executable, "-m", "f1live.replay", archive, "--speed", str(REPLAY_SPEED)],
        capture_output=True, text=True, timeout=REPLAY_TIMEOUT, env=env,
    )
    if proc.returncode != 0:
        raise Failure(f"replay exited {proc.returncode}\n{proc.stderr[-2000:]}")
    if "[SESSION] Replay complete" not in proc.stdout:
        raise Failure(f"replay never completed\n{proc.stderr[-2000:]}")
    return proc.stdout


def check_events(stdout: str) -> str:
    counts = {}
    for token in stdout.split():
        if token.startswith("[") and token.endswith("]"):
            tag = token[1:-1]
            if tag.isupper():
                counts[tag] = counts.get(tag, 0) + 1

    short = {
        tag: (floor, counts.get(tag, 0))
        for tag, floor in MIN_EVENTS.items()
        if counts.get(tag, 0) < floor
    }
    if short:
        detail = ", ".join(f"{t} {got}/{floor}" for t, (floor, got) in short.items())
        raise Failure(f"too few events — {detail}")

    total = sum(counts.values())
    return f"{total} events across {len(counts)} types"


def check_dumps(dump_json: str) -> str:
    dump_md = os.path.splitext(dump_json)[0] + ".md"
    for path in (dump_json, dump_md):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise Failure(f"missing or empty dump: {path}")

    with open(dump_json, encoding="utf-8") as f:
        state = json.load(f)

    positions = state.get("positions") or []
    if len(positions) < 10:
        raise Failure(f"only {len(positions)} drivers in the final dump")

    session = state.get("session") or {}
    lap, total_laps = session.get("lap"), session.get("total_laps")
    if not total_laps or lap != total_laps:
        raise Failure(f"session did not run to the end — lap {lap}/{total_laps}")

    return f"state dump: {len(positions)} drivers, lap {lap}/{total_laps}"


def main():
    parser = argparse.ArgumentParser(description="Smoke-test the F1 Live Copilot package")
    parser.add_argument("archive", nargs="?",
                        help="Directory with .jsonStream files (default: a generated fixture)")
    args = parser.parse_args()

    checks = [check_imports, check_openai, check_radio_stt_degrades, check_httpx]
    failed = []

    for check in checks:
        try:
            print(f"ok    {check()}")
        except Exception as e:
            failed.append(f"{check.__name__}: {e}")
            print(f"FAIL  {check.__name__}: {e}", file=sys.stderr)

    with tempfile.TemporaryDirectory() as d:
        try:
            archive = args.archive
            if not archive:
                archive = os.path.join(d, "fixture")
                print(f"ok    {make_fixture(archive)}")

            reason = archive_is_usable(archive)
            if reason:
                raise Failure(reason)

            dump_json = os.path.join(d, "f1-live.json")
            stdout = run_replay(archive, dump_json)
            print(f"ok    {check_events(stdout)}")
            print(f"ok    {check_dumps(dump_json)}")
        except Exception as e:
            failed.append(f"replay: {e}")
            print(f"FAIL  replay: {e}", file=sys.stderr)

    if failed:
        print(f"\n{len(failed)} check(s) failed.", file=sys.stderr)
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
