"""Download F1 static archive data for replay.

Downloads jsonStream files from F1's public static archive for a given session.
Used to replay past races with the F1 Live Copilot.

Usage:
    uv run -m f1live.download --path "2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race"
    uv run -m f1live.download --path "2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race" -o ~/f1-data/suzuka
"""

import argparse
import os
import sys
import tempfile

import requests

BASE_URL = "https://livetiming.formula1.com/static"

TOPICS = [
    "TimingData", "TimingAppData", "TimingStats", "DriverList",
    "DriverRaceInfo", "LapCount", "SessionInfo", "SessionData",
    "TrackStatus", "RaceControlMessages", "RcmSeries", "TeamRadio",
    "WeatherData", "ExtrapolatedClock", "TopThree", "Heartbeat",
    "AudioStreams", "ContentStreams",
    "SessionStatus", "TyreStintSeries", "LapSeries", "PitLaneTimeCollection",
    # Telemetry (large — skippable)
    "Position.z", "CarData.z",
]


def download(session_path: str, output_dir: str, skip_telemetry: bool = False) -> str:
    """Download archive data and return output directory path."""
    os.makedirs(output_dir, exist_ok=True)

    topics = [t for t in TOPICS if not skip_telemetry or t not in ("Position.z", "CarData.z")]

    for topic in topics:
        url = f"{BASE_URL}/{session_path}/{topic}.jsonStream"
        out_file = os.path.join(output_dir, f"{topic}.jsonStream")

        sys.stderr.write(f"  {topic}... ")
        sys.stderr.flush()

        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                with open(out_file, "wb") as f:
                    f.write(resp.content)
                print(f"{len(resp.content):,} bytes", file=sys.stderr)
            elif resp.status_code == 403:
                print("FORBIDDEN (not available)", file=sys.stderr)
            else:
                print(f"HTTP {resp.status_code}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"ERROR: {e}", file=sys.stderr)

    print(f"\nDone! Files saved to {output_dir}", file=sys.stderr)
    return output_dir


def auto_output_dir(session_path: str) -> str:
    """Generate output directory from session path.

    "2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race"
    → $TMPDIR/f1-replay/2026-03-29-japanese-grand-prix-race/
    """
    parts = session_path.strip("/").split("/")
    if len(parts) >= 2:
        # Use GP folder + session type: "2026-03-29_Japanese_Grand_Prix/2026-03-29_Race"
        gp = parts[-2].replace("_", "-").lower()
        session = parts[-1].split("_")[-1].lower() if "_" in parts[-1] else parts[-1].lower()
        name = f"{gp}-{session}"
    else:
        name = parts[-1].replace("_", "-").lower() if parts else "session"

    return os.path.join(tempfile.gettempdir(), "f1-replay", name)


def main():
    parser = argparse.ArgumentParser(description="Download F1 static archive data for replay")
    parser.add_argument("--path", required=True,
                        help="Session path, e.g. '2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race'")
    parser.add_argument("-o", "--output", default=None,
                        help="Output directory (default: $TMPDIR/f1-replay/<auto-name>)")
    parser.add_argument("--skip-telemetry", action="store_true",
                        help="Skip Position.z and CarData.z (saves ~100MB)")
    args = parser.parse_args()

    output_dir = args.output or auto_output_dir(args.path)

    print(f"Downloading F1 archive: {args.path}", file=sys.stderr)
    print(f"Output: {output_dir}\n", file=sys.stderr)

    download(args.path, output_dir, args.skip_telemetry)

    # Print output path to stdout (for scripting / skill consumption)
    print(output_dir)


if __name__ == "__main__":
    main()
