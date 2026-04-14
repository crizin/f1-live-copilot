#!/usr/bin/env python3
"""Download F1 static archive data for a given GP session.

Usage:
    uv run dev/download-archive.py --path "2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race"
    uv run dev/download-archive.py --path "2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race" -o dev/data/suzuka

The --path argument is the session path from F1's static archive.
You can find it in SessionInfo data or construct it from the F1 schedule.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///

import argparse
import os
import sys

import requests

BASE_URL = "https://livetiming.formula1.com/static"

TOPICS = [
    "TimingData", "TimingAppData", "TimingStats", "DriverList",
    "DriverRaceInfo", "LapCount", "SessionInfo", "SessionData",
    "TrackStatus", "RaceControlMessages", "RcmSeries", "TeamRadio",
    "WeatherData", "ExtrapolatedClock", "TopThree", "Heartbeat",
    "AudioStreams", "ContentStreams",
    "SessionStatus", "TyreStintSeries", "LapSeries", "PitLaneTimeCollection",
    # Telemetry (large)
    "Position.z", "CarData.z",
]


def download(session_path: str, output_dir: str, skip_telemetry: bool = False):
    os.makedirs(output_dir, exist_ok=True)

    topics = [t for t in TOPICS if not skip_telemetry or t not in ("Position.z", "CarData.z")]

    for topic in topics:
        url = f"{BASE_URL}/{session_path}/{topic}.jsonStream"
        out_file = os.path.join(output_dir, f"{topic}.jsonStream")

        sys.stdout.write(f"  {topic}... ")
        sys.stdout.flush()

        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                with open(out_file, "wb") as f:
                    f.write(resp.content)
                print(f"{len(resp.content):,} bytes")
            elif resp.status_code == 403:
                print("FORBIDDEN (not available)")
            else:
                print(f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            print(f"ERROR: {e}")

    print(f"\nDone! Files saved to {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Download F1 static archive data")
    parser.add_argument("--path", required=True,
                        help="Session path, e.g. '2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race'")
    parser.add_argument("-o", "--output", default=None,
                        help="Output directory (default: dev/data/<auto-name>)")
    parser.add_argument("--skip-telemetry", action="store_true",
                        help="Skip Position.z and CarData.z (saves ~100MB)")
    args = parser.parse_args()

    if args.output:
        output_dir = args.output
    else:
        # Auto-name from path: "2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race" → "2026-japanese-race"
        parts = args.path.strip("/").split("/")
        name = parts[-1].replace("_", "-").lower() if parts else "session"
        output_dir = os.path.join("dev", "data", name)

    print(f"Downloading F1 archive: {args.path}")
    print(f"Output: {output_dir}\n")
    download(args.path, output_dir, args.skip_telemetry)


if __name__ == "__main__":
    main()
