#!/usr/bin/env python3
"""Download F1 static archive data — dev wrapper.

Delegates to f1live.download. For dev usage, defaults output to dev/data/.

Usage:
    uv run dev/download-archive.py --path "2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race"
    uv run dev/download-archive.py --path "2026/2026-03-29_Japanese_Grand_Prix/2026-03-29_Race" -o dev/data/suzuka
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from f1live.download import download


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
        parts = args.path.strip("/").split("/")
        name = parts[-1].replace("_", "-").lower() if parts else "session"
        output_dir = os.path.join("dev", "data", name)

    print(f"Downloading F1 archive: {args.path}")
    print(f"Output: {output_dir}\n")
    download(args.path, output_dir, args.skip_telemetry)


if __name__ == "__main__":
    main()
