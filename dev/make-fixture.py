#!/usr/bin/env python3
"""Generate a synthetic race archive for the smoke test.

F1's timing archive cannot be committed (not ours to redistribute) and cannot be
downloaded from CI (their CDN 403s cloud egress), so the smoke test replays an
invented race instead: fictional drivers on fictional teams, in the jsonStream
wire format `state.py` parses. The point is to exercise the pipeline, not to be
a faithful race — the script drives every event type the detector emits.

Output is deterministic: the same input arguments always produce byte-identical
files, so the event counts the smoke test asserts stay stable.

Usage:
    uv run dev/make-fixture.py /tmp/fixture
    uv run -m f1live.replay /tmp/fixture --speed 200
"""

import argparse
import json
import os

TOTAL_LAPS = 30
LAP_SECONDS = 90.0
GREEN_AT = 30.0  # lights out, in simulated seconds

# Fictional grid — no resemblance to any real championship is intended.
DRIVERS = [
    ("1", "VKR", "Ada", "Vakker", "Northwind", "1B6F8C"),
    ("2", "RSO", "Ilse", "Rosso", "Northwind", "1B6F8C"),
    ("3", "MTL", "Bo", "Mistral", "Aurora", "C43B2F"),
    ("4", "HAV", "Nils", "Haven", "Aurora", "C43B2F"),
    ("5", "QRN", "Yuki", "Quiron", "Vulcan", "E2A03F"),
    ("6", "DLM", "Théo", "Delmar", "Vulcan", "E2A03F"),
    ("7", "BRN", "Sam", "Berrino", "Meridian", "2F7A4F"),
    ("8", "OKW", "Adaeze", "Okonkwo", "Meridian", "2F7A4F"),
    ("9", "STV", "Lena", "Stavros", "Halcyon", "7B4FA3"),
    ("10", "FNL", "Rui", "Fennel", "Halcyon", "7B4FA3"),
    ("11", "KRS", "Ivo", "Kiraso", "Zenith", "3C4A55"),
    ("12", "AMD", "Nour", "Almeida", "Zenith", "3C4A55"),
    ("14", "TSK", "Kai", "Tsuki", "Kestrel", "B85C9E"),
    ("16", "GRV", "Pia", "Grieve", "Kestrel", "B85C9E"),
    ("18", "NVR", "Emil", "Navarro", "Onyx", "555555"),
    ("20", "LDB", "Sena", "Lindberg", "Onyx", "555555"),
    ("22", "PRC", "Ana", "Pereira", "Solace", "4FA3A0"),
    ("23", "WLD", "Otto", "Wilde", "Solace", "4FA3A0"),
    ("27", "ZHR", "Mei", "Zhara", "Tempest", "8C6239"),
    ("31", "CVL", "Ruben", "Corvale", "Tempest", "8C6239"),
]

COMPOUNDS = ["SOFT", "MEDIUM", "HARD"]

# (lap, category, message, extras) — scope "Sector" entries exercise the noise
# filter and are expected NOT to surface as events.
RACE_CONTROL = [
    (1, "Other", "FORMATION LAP WILL START AT 14:00", {}),
    (1, "Flag", "GREEN LIGHT - PIT EXIT OPEN", {"Flag": "GREEN", "Scope": "Track"}),
    (2, "Drs", "DRS ENABLED", {}),
    (4, "Flag", "YELLOW IN TRACK SECTOR 7", {"Flag": "YELLOW", "Scope": "Sector", "Sector": 7}),
    (4, "Flag", "CLEAR IN TRACK SECTOR 7", {"Flag": "CLEAR", "Scope": "Sector", "Sector": 7}),
    (6, "Other", "TRACK LIMITS TURN 4 LAP 5 - CAR 16 (GRV)", {"RacingNumber": "16"}),
    (9, "Other", "PIT ENTRY IS OPEN", {}),
    (12, "Other", "CAR 20 (LDB) 5 SECOND TIME PENALTY - UNSAFE RELEASE", {"RacingNumber": "20"}),
    (14, "Drs", "DRS DISABLED", {}),
    (18, "Flag", "YELLOW", {"Flag": "YELLOW", "Scope": "Track"}),
    (18, "SafetyCar", "SAFETY CAR DEPLOYED", {}),
    (19, "Other", "CAR 23 (WLD) RETIRED", {"RacingNumber": "23"}),
    (21, "SafetyCar", "SAFETY CAR IN THIS LAP", {}),
    (21, "Flag", "CLEAR", {"Flag": "CLEAR", "Scope": "Track"}),
    (22, "Drs", "DRS ENABLED IN ALL ZONES", {}),
    (25, "Other", "TIME 1:29.104 DELETED - CAR 5 (QRN) TRACK LIMITS TURN 11", {"RacingNumber": "5"}),
    (28, "Other", "BLUE FLAG FOR CAR 31 (CVL)", {"RacingNumber": "31"}),
    (30, "Flag", "CHEQUERED FLAG", {"Flag": "CHEQUERED", "Scope": "Track"}),
]

# Drivers who pit, and on which lap. Kept off the overtake schedule so the
# detector's pit-cycle filter never has to arbitrate between the two.
PIT_STOPS = [
    (10, "5"), (10, "18"), (11, "9"), (11, "22"),
    (12, "6"), (13, "10"), (13, "27"), (14, "31"),
]

RETIREMENT = (18, "23")


def lap_start(lap: int) -> float:
    return GREEN_AT + (lap - 1) * LAP_SECONDS


def fmt_time(seconds: float) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def fmt_lap(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:06.3f}"


def utc(seconds: float) -> str:
    return f"2026-01-01T{fmt_time(seconds)}"


class Fixture:
    def __init__(self):
        self.lines: dict[str, list[tuple[float, str]]] = {}
        self._rc_index = 0

    def add(self, ts: float, topic: str, payload: dict):
        self.lines.setdefault(topic, []).append((ts, json.dumps(payload, separators=(",", ":"))))

    def add_rc(self, ts: float, lap: int, category: str, message: str, extras: dict):
        self._rc_index += 1
        msg = {"Utc": utc(ts), "Lap": lap, "Category": category, "Message": message}
        msg.update(extras)
        self.add(ts, "RaceControlMessages", {"Messages": {str(self._rc_index): msg}})

    def write(self, out_dir: str):
        os.makedirs(out_dir, exist_ok=True)
        for topic, entries in sorted(self.lines.items()):
            path = os.path.join(out_dir, f"{topic}.jsonStream")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                for ts, payload in sorted(entries, key=lambda e: e[0]):
                    f.write(f"{fmt_time(ts)}{payload}\n")
        return sorted(self.lines)


def build() -> Fixture:
    fx = Fixture()
    order = [num for num, *_ in DRIVERS]  # race order, index 0 == P1

    # --- Pre-race snapshot ---
    fx.add(0.0, "SessionInfo", {
        "Meeting": {"Name": "Synthetic Grand Prix",
                    "OfficialName": "F1 Live Copilot Fixture Grand Prix",
                    "Circuit": {"ShortName": "Testbed"}},
        "Type": "Race",
        "Path": "2026/2026-01-01_Synthetic_Grand_Prix/2026-01-01_Race/",
    })
    fx.add(0.0, "SessionStatus", {"Status": "Inactive", "Started": "Inactive"})
    fx.add(0.0, "LapCount", {"CurrentLap": 1, "TotalLaps": TOTAL_LAPS})
    fx.add(0.0, "TrackStatus", {"Status": "1", "Message": "AllClear"})
    fx.add(0.0, "WeatherData", {"AirTemp": "21.4", "TrackTemp": "34.8", "Humidity": "48.0",
                                "Rainfall": "0", "WindSpeed": "1.9"})
    fx.add(0.0, "DriverList", {
        num: {"RacingNumber": num, "Tla": tla, "FirstName": first, "LastName": last,
              "FullName": f"{first} {last}", "TeamName": team, "TeamColour": colour,
              "Line": i + 1}
        for i, (num, tla, first, last, team, colour) in enumerate(DRIVERS)
    })
    fx.add(2.0, "TimingData", {"Lines": {
        num: {"Line": i + 1, "Position": str(i + 1), "InPit": False, "Retired": False,
              "GapToLeader": "" if i == 0 else f"+{i * 1.4:.3f}",
              "IntervalToPositionAhead": {"Value": "" if i == 0 else f"+{1.4:.3f}"}}
        for i, num in enumerate(order)
    }})
    fx.add(2.0, "TimingAppData", {"Lines": {
        num: {"Line": i + 1, "Stints": {"0": {"Compound": COMPOUNDS[i % 2],
                                              "New": "true", "TotalLaps": 0, "StartLaps": 0}}}
        for i, num in enumerate(order)
    }})

    for lap, category, message, extras in RACE_CONTROL:
        if lap == 1:
            fx.add_rc(5.0, lap, category, message, extras)

    # --- Lights out ---
    fx.add(GREEN_AT, "SessionStatus", {"Status": "Started", "Started": "Started"})

    # --- The race ---
    retired: set[str] = set()
    best_overall = 93.500
    pits_by_lap: dict[int, list[str]] = {}
    for lap, num in PIT_STOPS:
        pits_by_lap.setdefault(lap, []).append(num)
    rc_by_lap: dict[int, list] = {}
    for lap, category, message, extras in RACE_CONTROL:
        if lap > 1:
            rc_by_lap.setdefault(lap, []).append((category, message, extras))

    for lap in range(2, TOTAL_LAPS + 1):
        t0 = lap_start(lap)
        fx.add(t0, "LapCount", {"CurrentLap": lap})

        # Lap times for everyone, and an occasional new overall best.
        laps = {}
        for i, num in enumerate(order):
            if num in retired:
                continue
            laps[num] = {"LastLapTime": {"Value": fmt_lap(94.2 + i * 0.11)},
                         "NumberOfLaps": lap - 1}
        if lap == 2:
            for i, num in enumerate(order):
                laps.setdefault(num, {})["BestLapTime"] = {"Value": fmt_lap(95.0 + i * 0.09)}
        elif lap % 4 == 0 and lap < TOTAL_LAPS:
            best_overall -= 0.240
            leader = order[0]
            laps.setdefault(leader, {})["BestLapTime"] = {"Value": fmt_lap(best_overall)}
            laps[leader]["LastLapTime"] = {"Value": fmt_lap(best_overall)}
        fx.add(t0 + 4.0, "TimingData", {"Lines": laps})

        # Position swaps. One pair per slot, spaced well apart, so the mass-shuffle
        # filter never sees more than a single gainer per detection tick.
        if lap >= 3:
            for slot, offset in enumerate((22.0, 52.0)):
                idx = (lap * 2 + slot * 5) % (len(order) - 1)
                ahead, behind = order[idx], order[idx + 1]
                if {ahead, behind} & retired:
                    continue
                if behind in pits_by_lap.get(lap, []) or behind in pits_by_lap.get(lap - 1, []):
                    continue
                if ahead in pits_by_lap.get(lap, []) or ahead in pits_by_lap.get(lap - 1, []):
                    continue
                order[idx], order[idx + 1] = behind, ahead
                fx.add(t0 + offset, "TimingData", {"Lines": {
                    behind: {"Line": idx + 1, "Position": str(idx + 1)},
                    ahead: {"Line": idx + 2, "Position": str(idx + 2)},
                }})

        # Pit stops — in on one tick, out on another with a fresh compound.
        for num in pits_by_lap.get(lap, []):
            stint = 1 + sum(1 for pl, pn in PIT_STOPS if pn == num and pl <= lap)
            fx.add(t0 + 34.0, "TimingData", {"Lines": {num: {"InPit": True, "PitOut": False}}})
            fx.add(t0 + 62.0, "TimingData", {"Lines": {num: {"InPit": False, "PitOut": True}}})
            fx.add(t0 + 62.0, "TimingAppData", {"Lines": {num: {"Stints": {
                str(stint): {"Compound": COMPOUNDS[stint % len(COMPOUNDS)],
                             "New": "true", "TotalLaps": 0, "StartLaps": lap}}}}})

        # Retirement, and the safety car it brings out.
        if lap == RETIREMENT[0]:
            num = RETIREMENT[1]
            retired.add(num)
            fx.add(t0 + 70.0, "TimingData",
                   {"Lines": {num: {"Retired": True, "Stopped": True, "InPit": False}}})
            fx.add(t0 + 74.0, "TrackStatus", {"Status": "2", "Message": "Yellow"})
            fx.add(t0 + 78.0, "TrackStatus", {"Status": "4", "Message": "SCDeployed"})
        if lap == 21:
            fx.add(t0 + 40.0, "TrackStatus", {"Status": "1", "Message": "AllClear"})

        for i, (category, message, extras) in enumerate(rc_by_lap.get(lap, [])):
            fx.add_rc(t0 + 12.0 + i * 6.0, lap, category, message, extras)

        # Intervals, so DriverRaceInfo is exercised too.
        fx.add(t0 + 8.0, "DriverRaceInfo", {
            num: {"Gap": "" if i == 0 else f"+{i * 1.6:.3f}",
                  "Interval": "" if i == 0 else f"+{1.6:.3f}",
                  "Catching": bool(i % 3 == 0), "IsOut": num in retired}
            for i, num in enumerate(order)
        })

    # --- Chequered flag ---
    end = lap_start(TOTAL_LAPS) + LAP_SECONDS
    fx.add(end, "SessionStatus", {"Status": "Finished", "Started": "Finished"})
    fx.add(end + 20.0, "SessionStatus", {"Status": "Finalised", "Started": "Finished"})
    return fx


def main():
    parser = argparse.ArgumentParser(description="Generate a synthetic race archive")
    parser.add_argument("out_dir", help="Directory to write .jsonStream files into")
    args = parser.parse_args()

    topics = build().write(args.out_dir)
    total = sum(os.path.getsize(os.path.join(args.out_dir, f"{t}.jsonStream")) for t in topics)
    print(f"Wrote {len(topics)} topics ({total:,} bytes) to {args.out_dir}")


if __name__ == "__main__":
    main()
