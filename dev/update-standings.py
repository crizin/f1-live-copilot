#!/usr/bin/env python3
"""Update data/standings.md from jolpica-f1 (Ergast successor) API.

Usage:
    uv run dev/update-standings.py [--year 2026] [--recent 5] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

API_BASE = "https://api.jolpi.ca/ergast/f1"
ROOT = Path(__file__).resolve().parents[1]

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

RACE_CODE = {
    "Australian Grand Prix": "AUS",
    "Chinese Grand Prix": "CHN",
    "Japanese Grand Prix": "JPN",
    "Bahrain Grand Prix": "BHR",
    "Saudi Arabian Grand Prix": "SAU",
    "Miami Grand Prix": "MIA",
    "Emilia Romagna Grand Prix": "EMI",
    "Monaco Grand Prix": "MON",
    "Spanish Grand Prix": "ESP",
    "Canadian Grand Prix": "CAN",
    "Austrian Grand Prix": "AUT",
    "British Grand Prix": "GBR",
    "Hungarian Grand Prix": "HUN",
    "Belgian Grand Prix": "BEL",
    "Dutch Grand Prix": "NED",
    "Italian Grand Prix": "ITA",
    "Azerbaijan Grand Prix": "AZE",
    "Singapore Grand Prix": "SGP",
    "United States Grand Prix": "USA",
    "Mexico City Grand Prix": "MEX",
    "São Paulo Grand Prix": "BRA",
    "Sao Paulo Grand Prix": "BRA",
    "Brazilian Grand Prix": "BRA",
    "Las Vegas Grand Prix": "LAS",
    "Qatar Grand Prix": "QAT",
    "Abu Dhabi Grand Prix": "ABU",
}


def race_code(name: str) -> str:
    return RACE_CODE.get(name) or name.split()[0][:3].upper()


def short_team(name: str) -> str:
    return TEAM_DISPLAY.get(name, name)


def fetch(client: httpx.Client, path: str, **params) -> dict:
    r = client.get(f"{API_BASE}/{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()["MRData"]


def fetch_driver_standings(client: httpx.Client, year: int):
    # The `round` field in this response can be ahead of the actual completed
    # race count (jolpica increments it pre-race). Trust results endpoint instead.
    data = fetch(client, f"{year}/driverstandings/")
    lists = data["StandingsTable"]["StandingsLists"]
    return lists[0]["DriverStandings"] if lists else []


def fetch_constructor_standings(client: httpx.Client, year: int):
    data = fetch(client, f"{year}/constructorstandings/")
    lists = data["StandingsTable"]["StandingsLists"]
    return lists[0]["ConstructorStandings"] if lists else []


def fetch_all_races_with_results(client: httpx.Client, year: int):
    # Pagination is over individual Result rows, not Races — same race can
    # span multiple pages, so merge by round.
    races_by_round: dict[int, dict] = {}
    offset = 0
    while True:
        data = fetch(client, f"{year}/results/", limit=100, offset=offset)
        page = data["RaceTable"]["Races"]
        if not page:
            break
        for race in page:
            rnd = int(race["round"])
            if rnd in races_by_round:
                races_by_round[rnd]["Results"].extend(race["Results"])
            else:
                races_by_round[rnd] = race
        offset += int(data["limit"])
        if offset >= int(data["total"]):
            break
    return [races_by_round[r] for r in sorted(races_by_round)]


def fetch_schedule(client: httpx.Client, year: int):
    data = fetch(client, f"{year}/")
    return data["RaceTable"]["Races"]


def build_driver_rows(standings, races, recent_n):
    recent_races = races[-recent_n:] if len(races) > recent_n else races
    headers = ["P", "Driver", "Team", "Pts"] + [race_code(r["raceName"]) for r in recent_races]

    finishes: dict[str, dict[int, str]] = {}
    for race in races:
        rnd = int(race["round"])
        for result in race["Results"]:
            finishes.setdefault(result["Driver"]["driverId"], {})[rnd] = result["position"]

    rows = []
    for s in standings:
        d = s["Driver"]
        constructor = s["Constructors"][0]["name"]
        code = d.get("code") or d["familyName"][:3].upper()
        recent_cols = []
        for r in recent_races:
            pos = finishes.get(d["driverId"], {}).get(int(r["round"]))
            recent_cols.append(f"P{pos}" if pos else "—")
        rows.append([s["position"], code, short_team(constructor), s["points"], *recent_cols])
    return headers, rows


def build_constructor_rows(standings):
    rows = [
        [s["position"], short_team(s["Constructor"]["name"]), s["points"]]
        for s in standings
    ]
    return ["P", "Team", "Pts"], rows


def render_table(headers, rows) -> str:
    sep = "|".join(["---"] * len(headers))
    lines = ["| " + " | ".join(headers) + " |", "|" + sep + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def find_next_race(schedule, last_round: int):
    for r in schedule:
        if int(r["round"]) > last_round:
            return r
    return None


def render_doc(year, drivers_table, constructors_table, last_race, next_race, recent_n):
    next_line = ""
    if next_race:
        next_line = (
            f"\n> Next race: Round {next_race['round']}, "
            f"{next_race['raceName']} ({next_race['date']})"
        )
    return (
        f"# {year} Championship Standings\n\n"
        f"> Last update: Round {last_race['round']} "
        f"({last_race['raceName']}, {last_race['date']}){next_line}\n"
        f">\n"
        f"> Auto-generated from jolpica-f1 API by `dev/update-standings.py`.\n"
        f"> Edit storylines.md for narrative context — do not hand-edit this file.\n\n"
        f"## Drivers' Championship\n\n"
        f"{drivers_table}\n\n"
        f"> Showing recent {recent_n} rounds. Full history: "
        f"https://api.jolpi.ca/ergast/f1/{year}/results/\n\n"
        f"## Constructors' Championship\n\n"
        f"{constructors_table}\n"
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=datetime.now(timezone.utc).year)
    p.add_argument("--recent", type=int, default=5)
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    output = args.output or ROOT / "data" / "standings.md"

    with httpx.Client() as client:
        drivers = fetch_driver_standings(client, args.year)
        constructors = fetch_constructor_standings(client, args.year)
        races = fetch_all_races_with_results(client, args.year)
        schedule = fetch_schedule(client, args.year)

    # Pre-season or off-season: jolpica returns empty lists. Exit cleanly so
    # scheduled runs don't fail every day waiting for round 1.
    if not drivers or not races:
        print(
            f"No race results yet for {args.year} — skipping update.",
            file=sys.stderr,
        )
        return

    last_race = races[-1]
    last_round = int(last_race["round"])
    next_race = find_next_race(schedule, last_round)

    d_headers, d_rows = build_driver_rows(drivers, races, args.recent)
    c_headers, c_rows = build_constructor_rows(constructors)

    doc = render_doc(
        args.year,
        render_table(d_headers, d_rows),
        render_table(c_headers, c_rows),
        last_race,
        next_race,
        args.recent,
    )

    if args.dry_run:
        sys.stdout.write(doc)
    else:
        output.write_text(doc, encoding="utf-8")
        print(
            f"Wrote {output.relative_to(ROOT)} — round {last_round}, "
            f"{len(drivers)} drivers, {len(constructors)} teams"
        )


if __name__ == "__main__":
    main()
