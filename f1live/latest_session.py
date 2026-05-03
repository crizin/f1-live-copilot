#!/usr/bin/env python3
"""Fetch latest race weekend results from jolpica-f1 API and print as markdown.

Usage:
    uv run -m f1live.latest_session [--year 2026]

Stdout = markdown summary of the most recent round's race / qualifying / sprint.
The start-f1 skill calls this at startup so Claude has up-to-the-minute results
that the daily cron-updated standings.md hasn't picked up yet (e.g., Saturday
qualifying before Sunday's race).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

import requests

API_BASE = "https://api.jolpi.ca/ergast/f1"

TEAM_DISPLAY = {
    "Mercedes": "Mercedes",
    "Ferrari": "Ferrari",
    "McLaren": "McLaren",
    "Red Bull": "Red Bull",
    "Haas F1 Team": "Haas",
    "Alpine F1 Team": "Alpine",
    "RB F1 Team": "Racing Bulls",
    "Audi": "Audi",
    "Williams": "Williams",
    "Cadillac F1 Team": "Cadillac",
    "Aston Martin": "Aston Martin",
}


def short_team(name: str) -> str:
    return TEAM_DISPLAY.get(name, name)


def driver_code(d: dict) -> str:
    return d.get("code") or d["familyName"][:3].upper()


def fetch(session: requests.Session, path: str, **params) -> dict:
    r = session.get(f"{API_BASE}/{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()["MRData"]


def fetch_qualifying_paginated(session: requests.Session, year: int):
    # Pagination is over individual QualifyingResult rows, not Races, so the
    # same round can span multiple pages — merge by round number.
    races_by_round: dict[int, dict] = {}
    offset = 0
    while True:
        data = fetch(session, f"{year}/qualifying/", limit=100, offset=offset)
        page = data["RaceTable"]["Races"]
        if not page:
            break
        for race in page:
            rnd = int(race["round"])
            if rnd in races_by_round:
                races_by_round[rnd]["QualifyingResults"].extend(race["QualifyingResults"])
            else:
                races_by_round[rnd] = race
        offset += int(data["limit"])
        if offset >= int(data["total"]):
            break
    return [races_by_round[r] for r in sorted(races_by_round)]


def render_table(headers, rows) -> str:
    sep = "|".join(["---"] * len(headers))
    lines = ["| " + " | ".join(headers) + " |", "|" + sep + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def race_time_field(result: dict) -> str:
    # Winner: full time. Others: "+gap". DNF / lapped / DSQ: status string.
    time = result.get("Time", {}).get("time")
    return time or result.get("status", "")


def render_race(results) -> tuple[str, tuple[str, str] | None]:
    headers = ["P", "Driver", "Team", "Time/Gap", "Laps"]
    rows = []
    fastest = None
    for r in results:
        rows.append([
            r["positionText"],
            driver_code(r["Driver"]),
            short_team(r["Constructor"]["name"]),
            race_time_field(r),
            r.get("laps", ""),
        ])
        if r.get("FastestLap", {}).get("rank") == "1":
            fastest = (driver_code(r["Driver"]), r["FastestLap"]["Time"]["time"])
    return render_table(headers, rows), fastest


def render_qualifying(results) -> str:
    headers = ["P", "Driver", "Team", "Q1", "Q2", "Q3"]
    rows = [
        [
            r["position"],
            driver_code(r["Driver"]),
            short_team(r["Constructor"]["name"]),
            r.get("Q1") or "—",
            r.get("Q2") or "—",
            r.get("Q3") or "—",
        ]
        for r in results
    ]
    return render_table(headers, rows)


def render_sprint(results) -> str:
    headers = ["P", "Driver", "Team", "Time/Gap", "Laps"]
    rows = [
        [
            r["positionText"],
            driver_code(r["Driver"]),
            short_team(r["Constructor"]["name"]),
            race_time_field(r),
            r.get("laps", ""),
        ]
        for r in results
    ]
    return render_table(headers, rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=datetime.now(timezone.utc).year)
    args = p.parse_args()

    try:
        with requests.Session() as session:
            quali_races = fetch_qualifying_paginated(session, args.year)
            if not quali_races:
                sys.stdout.write(
                    f"# Latest Session — no qualifying data yet for {args.year}\n"
                )
                return

            latest = quali_races[-1]
            rnd = int(latest["round"])
            race_name = latest["raceName"]
            race_date = latest["date"]

            race_data = fetch(session, f"{args.year}/{rnd}/results/")
            race_block = race_data["RaceTable"]["Races"]
            race_results = race_block[0]["Results"] if race_block else None

            sprint_data = fetch(session, f"{args.year}/{rnd}/sprint/")
            sprint_block = sprint_data["RaceTable"]["Races"]
            sprint_results = (
                sprint_block[0]["SprintResults"] if sprint_block else None
            )
    except (requests.RequestException, KeyError, ValueError) as e:
        sys.stderr.write(f"latest_session: failed to fetch — {e}\n")
        sys.stdout.write("# Latest Session — fetch failed (jolpica-f1 unreachable)\n")
        sys.exit(0)

    parts = [
        f"# Latest Session — Round {rnd}, {race_name} ({race_date})",
        "",
        f"> Fetched live: {datetime.now(timezone.utc).isoformat(timespec='minutes')}",
        f"> Source: jolpica-f1 API ({API_BASE}/{args.year}/{rnd}/)",
        "",
    ]

    if race_results:
        table, fastest = render_race(race_results)
        parts += ["## Race", "", table]
        if fastest:
            parts += ["", f"> Fastest lap: {fastest[0]} — {fastest[1]}"]
        parts.append("")
    else:
        parts += ["## Race", "", "> Not yet run.", ""]

    if sprint_results:
        parts += ["## Sprint", "", render_sprint(sprint_results), ""]

    parts += ["## Qualifying", "", render_qualifying(latest["QualifyingResults"]), ""]

    sys.stdout.write("\n".join(parts))


if __name__ == "__main__":
    main()
