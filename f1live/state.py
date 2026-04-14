"""F1 Live State Manager — merges SignalR deltas into full state."""

import base64
import json
import logging
import zlib
from collections import deque
from datetime import datetime, timezone

logger = logging.getLogger("f1live.state")

MAX_EVENTS = 100


class F1State:
    def __init__(self):
        self.session = {
            "type": None,
            "status": None,
            "lap": 0,
            "total_laps": None,
            "meeting": None,
            "circuit": None,
        }
        self.drivers: dict[str, dict] = {}
        self.timing: dict[str, dict] = {}
        self.positions: dict[str, dict] = {}
        self.intervals: dict[str, dict] = {}
        self.race_control: deque = deque(maxlen=MAX_EVENTS)
        self.team_radio: deque = deque(maxlen=MAX_EVENTS)
        self.pit_times: dict[str, dict] = {}
        self.pit_status: dict[str, bool] = {}  # driver_number -> True if in pit
        self.weather: dict = {}
        self.track_status: str = ""
        self.retirements: list[str] = []
        self.updated_at: str = ""
        self._session_path: str = ""

    def process_message(self, topic: str, content, timestamp: str | None):
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                try:
                    raw = base64.b64decode(content)
                    content = json.loads(
                        zlib.decompress(raw, -zlib.MAX_WBITS).decode("utf-8-sig")
                    )
                except Exception:
                    return

        if not isinstance(content, dict):
            return

        self.updated_at = datetime.now(timezone.utc).isoformat()

        handler = {
            "SessionInfo": self._on_session_info,
            "SessionData": self._on_session_data,
            "SessionStatus": self._on_session_status,
            "DriverList": self._on_driver_list,
            "TimingData": self._on_timing_data,
            "TimingAppData": self._on_timing_app_data,
            "DriverRaceInfo": self._on_driver_race_info,
            "LapCount": self._on_lap_count,
            "TrackStatus": self._on_track_status,
            "RaceControlMessages": self._on_race_control,
            "TeamRadio": self._on_team_radio,
            "PitLaneTimeCollection": self._on_pit_lane_time,
            "WeatherData": self._on_weather,
        }.get(topic)

        if handler:
            handler(content)

    # --- Session ---

    def _on_session_info(self, data: dict):
        meeting = data.get("Meeting", {})
        self.session["meeting"] = meeting.get("Name") or meeting.get("OfficialName")
        circuit = meeting.get("Circuit", {})
        self.session["circuit"] = circuit.get("ShortName")
        self.session["type"] = data.get("Type") or data.get("Name")
        self._session_path = data.get("Path", "")

    def _on_session_data(self, data: dict):
        status_series = data.get("StatusSeries")
        if status_series:
            items = list(status_series.values()) if isinstance(status_series, dict) else status_series
            for item in items:
                if isinstance(item, dict) and "SessionStatus" in item:
                    self.session["status"] = item["SessionStatus"]

        series = data.get("Series")
        if series:
            items = list(series.values()) if isinstance(series, dict) else series
            for item in items:
                if isinstance(item, dict) and "Lap" in item:
                    self.session["lap"] = item["Lap"]

    def _on_session_status(self, data: dict):
        if "Status" in data:
            self.session["status"] = data["Status"]

    def _on_lap_count(self, data: dict):
        if "CurrentLap" in data:
            self.session["lap"] = data["CurrentLap"]
        if "TotalLaps" in data:
            self.session["total_laps"] = data["TotalLaps"]

    # --- Drivers ---

    def _on_driver_list(self, data: dict):
        for num_str, info in data.items():
            if num_str.startswith("_") or not isinstance(info, dict):
                continue
            existing = self.drivers.get(num_str, {
                "number": num_str,
                "abbreviation": "",
                "first_name": "",
                "last_name": "",
                "team": "",
                "team_colour": "",
            })
            for src, dst in [
                ("Tla", "abbreviation"), ("FirstName", "first_name"),
                ("LastName", "last_name"), ("TeamName", "team"),
                ("TeamColour", "team_colour"),
            ]:
                if src in info:
                    existing[dst] = info[src]
            self.drivers[num_str] = existing

    # --- Timing ---

    def _on_timing_data(self, data: dict):
        lines = data.get("Lines")
        if not lines:
            return
        for num_str, driver_data in lines.items():
            if not isinstance(driver_data, dict):
                continue
            if num_str not in self.timing:
                self.timing[num_str] = {}
            _deep_merge(self.timing[num_str], driver_data)

            if "Line" in driver_data:
                pos = driver_data["Line"]
                self.positions = {
                    k: v for k, v in self.positions.items()
                    if v.get("driver_number") != num_str
                }
                drv = self.drivers.get(num_str, {})
                self.positions[str(pos)] = {
                    "position": pos,
                    "driver_number": num_str,
                    "abbreviation": drv.get("abbreviation", num_str),
                    "team": drv.get("team", ""),
                }

            # Track pit status
            if "InPit" in driver_data:
                self.pit_status[num_str] = bool(driver_data["InPit"])
            if "PitOut" in driver_data and driver_data["PitOut"]:
                self.pit_status[num_str] = False

            if driver_data.get("Retired") or driver_data.get("Stopped"):
                if num_str not in self.retirements:
                    self.retirements.append(num_str)

    def _on_timing_app_data(self, data: dict):
        lines = data.get("Lines")
        if not lines:
            return
        for num_str, info in lines.items():
            if not isinstance(info, dict):
                continue
            stints = info.get("Stints")
            if stints:
                if num_str not in self.timing:
                    self.timing[num_str] = {}
                if "Stints" not in self.timing[num_str]:
                    self.timing[num_str]["Stints"] = {}
                if isinstance(stints, list):
                    for i, s in enumerate(stints):
                        self.timing[num_str]["Stints"][str(i)] = s
                else:
                    _deep_merge(self.timing[num_str]["Stints"], stints)

    def _on_driver_race_info(self, data: dict):
        for num_str, info in data.items():
            if not isinstance(info, dict):
                continue
            if num_str not in self.intervals:
                self.intervals[num_str] = {}
            for field in ("Gap", "Interval", "Catching", "OvertakeState", "IsOut"):
                if field in info:
                    self.intervals[num_str][field] = info[field]

    # --- Events ---

    def _on_track_status(self, data: dict):
        self.track_status = data.get("Message", "")

    def _on_race_control(self, data: dict):
        messages = data.get("Messages")
        if not messages:
            return
        items = list(messages.values()) if isinstance(messages, dict) else messages
        for msg in items:
            if not isinstance(msg, dict):
                continue
            self.race_control.append({
                "time": msg.get("Utc", ""),
                "lap": msg.get("Lap"),
                "message": msg.get("Message", ""),
                "flag": msg.get("Flag"),
                "category": msg.get("Category"),
                "scope": msg.get("Scope"),
                "driver_number": msg.get("RacingNumber"),
            })

    def _on_team_radio(self, data: dict):
        captures = data.get("Captures")
        if not captures:
            return
        items = list(captures.values()) if isinstance(captures, dict) else captures
        for cap in items:
            if not isinstance(cap, dict):
                continue
            num = str(cap.get("RacingNumber", ""))
            drv = self.drivers.get(num, {})
            path = cap.get("Path", "")
            self.team_radio.append({
                "time": cap.get("Utc", ""),
                "driver_number": num,
                "abbreviation": drv.get("abbreviation", num),
                "url": f"https://livetiming.formula1.com/static/{self._session_path}{path}" if path else "",
            })

    def _on_pit_lane_time(self, data: dict):
        pit_times = data.get("PitTimes")
        if not pit_times:
            return
        for key, val in pit_times.items():
            if key == "_deleted":
                for num in val:
                    self.pit_times.pop(str(num), None)
            elif isinstance(val, dict):
                self.pit_times[str(val.get("RacingNumber", key))] = {
                    "duration": val.get("Duration", ""),
                    "lap": val.get("Lap", ""),
                }

    def _on_weather(self, data: dict):
        self.weather = {
            "air_temp": data.get("AirTemp", ""),
            "track_temp": data.get("TrackTemp", ""),
            "humidity": data.get("Humidity", ""),
            "rainfall": data.get("Rainfall", ""),
            "wind_speed": data.get("WindSpeed", ""),
            "wind_dir": data.get("WindDirection", ""),
        }

    # --- Output ---

    def to_dict(self) -> dict:
        sorted_positions = []
        for pos_key in sorted(self.positions.keys(), key=lambda x: int(x) if x.isdigit() else 999):
            entry = dict(self.positions[pos_key])
            num_str = entry["driver_number"]
            timing = self.timing.get(num_str, {})
            drv = self.drivers.get(num_str, {})
            interval_data = self.intervals.get(num_str, {})

            entry["abbreviation"] = drv.get("abbreviation") or num_str
            entry["team"] = drv.get("team", "")
            entry["gap"] = timing.get("GapToLeader", "")
            entry["interval"] = timing.get("IntervalToPositionAhead", {})
            if isinstance(entry["interval"], dict):
                entry["interval"] = entry["interval"].get("Value", "")
            entry["last_lap"] = timing.get("LastLapTime", {})
            if isinstance(entry["last_lap"], dict):
                entry["last_lap"] = entry["last_lap"].get("Value", "")
            entry["best_lap"] = timing.get("BestLapTime", {})
            if isinstance(entry["best_lap"], dict):
                entry["best_lap"] = entry["best_lap"].get("Value", "")

            # Tire
            stints = timing.get("Stints", {})
            if stints:
                last_stint = max(stints.keys(), key=lambda x: int(x) if x.isdigit() else 0, default=None)
                if last_stint:
                    stint_data = stints[last_stint]
                    entry["tire"] = stint_data.get("Compound", "")
                    entry["tire_age"] = stint_data.get("TotalLaps", "")
                    entry["stint_number"] = int(last_stint) + 1

            # Catching / OvertakeState from DriverRaceInfo
            entry["catching"] = interval_data.get("Catching")
            entry["overtake_state"] = interval_data.get("OvertakeState")
            entry["in_pit"] = self.pit_status.get(num_str, False)

            sorted_positions.append(entry)

        return {
            "session": self.session,
            "positions": sorted_positions,
            "race_control": list(self.race_control),
            "team_radio": list(self.team_radio),
            "weather": self.weather,
            "track_status": self.track_status,
            "retirements": self.retirements,
            "updated_at": self.updated_at,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)

    def to_markdown(self) -> str:
        d = self.to_dict()
        s = d["session"]
        lines = []

        meeting = s.get("meeting") or "Unknown"
        stype = s.get("type") or "?"
        status = s.get("status") or "?"
        lap = s.get("lap") or 0
        total = s.get("total_laps") or "?"
        track = d.get("track_status") or ""
        track_str = f" | {track}" if track and track != "AllClear" else ""
        lines.append(f"# {meeting} — {stype} | {status} | Lap {lap}/{total}{track_str}")

        # Weather
        w = d.get("weather", {})
        if w.get("air_temp"):
            rain = " | RAIN" if w.get("rainfall", "0") != "0" else ""
            lines.append(f"Air {w['air_temp']}°C Track {w.get('track_temp', '?')}°C Wind {w.get('wind_speed', '?')}km/h{rain}")
        lines.append("")

        # Positions
        lines.append("| P | # | Team | Gap | Int | Last | Best | Tire | C |")
        lines.append("|---|---|------|-----|-----|------|------|------|---|")
        for p in d["positions"]:
            abbr = p.get("abbreviation") or p["driver_number"]
            team = (p.get("team") or "")[:3].upper()
            gap = p.get("gap", "")
            interval = p.get("interval", "")
            last = p.get("last_lap", "")
            best = p.get("best_lap", "")
            tire = p.get("tire", "")
            age = p.get("tire_age", "")
            tire_str = f"{tire[0]}{age}" if tire else ""
            catching = p.get("catching")
            catch_str = "^" if catching == 2 else ""
            lines.append(f"| {p['position']} | {abbr} | {team} | {gap} | {interval} | {last} | {best} | {tire_str} | {catch_str} |")

        # Race control (last 10)
        rc_msgs = d.get("race_control", [])
        if rc_msgs:
            lines.append("")
            lines.append("## RC")
            for rc in rc_msgs[-10:]:
                t = (rc.get("time") or "")
                if "T" in t:
                    t = t.split("T")[-1][:8]
                flag = f"[{rc['flag']}] " if rc.get("flag") else ""
                lap_str = f"L{rc['lap']} " if rc.get("lap") else ""
                lines.append(f"- {t} {lap_str}{flag}{rc.get('message', '')}")

        # Team radio (last 5)
        radio = d.get("team_radio", [])
        if radio:
            lines.append("")
            lines.append("## Radio")
            for tr in radio[-5:]:
                t = (tr.get("time") or "")
                if "T" in t:
                    t = t.split("T")[-1][:8]
                lines.append(f"- {t} {tr.get('abbreviation', '?')}: {tr.get('url', '')}")

        if d.get("retirements"):
            abbrs = [self.drivers.get(n, {}).get("abbreviation", n) for n in d["retirements"]]
            lines.append(f"\nDNF: {', '.join(abbrs)}")

        return "\n".join(lines)


def _deep_merge(base: dict, update):
    if not isinstance(update, dict):
        return
    for key, value in update.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
