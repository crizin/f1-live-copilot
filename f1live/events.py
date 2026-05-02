"""Event detection — compares previous vs current state and emits events.

Events are batched into time windows and printed to stdout as single lines.
Each stdout line = one Monitor notification to Claude.
"""

import copy
import logging
import time

logger = logging.getLogger("f1live.events")

P0 = 0  # Immediate (SC, red flag, DNF)
P1 = 1  # Normal (overtake, pit, fastest lap)
P2 = 2  # Low (lap count — only emitted when quiet)


class Event:
    __slots__ = ("priority", "tag", "text")

    def __init__(self, priority: int, tag: str, text: str):
        self.priority = priority
        self.tag = tag
        self.text = text

    def __repr__(self):
        return f"[{self.tag}] {self.text}"


class EventDetector:
    """Detects events by diffing F1State snapshots."""

    def __init__(self, warmup_seconds: float = 0.0):
        self._prev: dict | None = None
        self._race_started = False
        self._warmup_laps = 0  # suppress overtakes until lap 2 complete
        self._recent_pit_out: dict[str, int] = {}  # driver -> lap of pit out
        self._recent_rc: list[str] = []  # last N RC messages for dedup
        # Initial-burst absorption. SignalR sends a full snapshot of the
        # session's accumulated state on connect; without this, the first
        # diff against an empty baseline emits dozens of stale events as if
        # they just happened. While warming up, _prev still updates so the
        # post-warmup baseline is current.
        self._warmup_seconds = warmup_seconds
        self._warmup_started_at: float | None = None
        self._warmup_logged = False

    def detect(self, state_dict: dict) -> list[Event]:
        events = []
        curr = state_dict

        if self._prev is None:
            self._prev = copy.deepcopy(curr)
            if self._warmup_seconds > 0:
                self._warmup_started_at = time.monotonic()
            return events

        prev = self._prev
        curr_session = curr.get("session", {})
        prev_session = prev.get("session", {})
        curr_lap = curr_session.get("lap", 0)

        # --- Session status ---
        curr_status = curr_session.get("status")
        if curr_status != prev_session.get("status"):
            events.append(Event(P0, "SESSION", str(curr_status)))
            if curr_status == "Started":
                self._race_started = True
                # Grid-shuffle filter only applies at actual race start.
                # If curr_lap > 1 the status flip is a mid-session connect,
                # not lights out — overtakes should fire immediately.
                self._warmup_laps = (curr_lap + 2) if curr_lap <= 1 else 0

        # --- Lap change ---
        prev_lap = prev_session.get("lap", 0)
        total = curr_session.get("total_laps") or "?"
        if curr_lap != prev_lap and curr_lap > 0:
            events.append(Event(P2, "LAP", f"{curr_lap}/{total}"))

        # --- Track status ---
        if curr.get("track_status") != prev.get("track_status"):
            ts = curr.get("track_status", "")
            if ts:
                events.append(Event(P0, "TRACK", ts))

        # --- Race control (new, deduplicated) ---
        self._detect_race_control(prev, curr, events)

        # --- Pit in/out ---
        self._detect_pits(prev, curr, curr_lap, events)

        # --- Overtakes (filtered) ---
        if self._race_started and curr_lap >= self._warmup_laps:
            self._detect_overtakes(prev, curr, curr_lap, events)

        # --- Retirements ---
        prev_ret = set(prev.get("retirements", []))
        curr_ret = set(curr.get("retirements", []))
        for num in curr_ret - prev_ret:
            abbr = _get_abbr(curr, num)
            events.append(Event(P0, "DNF", abbr))

        # --- Fastest lap ---
        self._detect_fastest_lap(prev, curr, events)

        self._prev = copy.deepcopy(curr)

        if self._warmup_started_at is not None:
            if time.monotonic() - self._warmup_started_at < self._warmup_seconds:
                if events and not self._warmup_logged:
                    logger.info("Warmup: absorbing %d initial events as baseline", len(events))
                    self._warmup_logged = True
                return []
            self._warmup_started_at = None
            if self._warmup_logged:
                logger.info("Warmup complete, emitting events live")

        return events

    def _detect_race_control(self, prev: dict, curr: dict, events: list):
        prev_rc_count = len(prev.get("race_control", []))
        curr_rc = curr.get("race_control", [])

        for rc in curr_rc[prev_rc_count:]:
            cat = rc.get("category", "")
            msg = rc.get("message", "")
            lap = rc.get("lap", "")
            scope = rc.get("scope", "")

            # Skip sector-level flags (too noisy)
            if cat == "Flag" and scope == "Sector":
                continue

            # Deduplicate: skip if same message appeared recently
            msg_key = f"{cat}:{msg}"
            if msg_key in self._recent_rc:
                continue
            self._recent_rc.append(msg_key)
            if len(self._recent_rc) > 20:
                self._recent_rc = self._recent_rc[-20:]

            prio = P0 if cat in ("SafetyCar", "Flag") else P1
            events.append(Event(prio, "RC", f"L{lap} {msg}"))

    def _detect_pits(self, prev: dict, curr: dict, curr_lap: int, events: list):
        # Don't detect pits before race starts
        if not self._race_started:
            return

        prev_pit = {p["driver_number"] for p in prev.get("positions", []) if p.get("in_pit")}
        curr_pit = {p["driver_number"] for p in curr.get("positions", []) if p.get("in_pit")}

        # Pit in
        for num in curr_pit - prev_pit:
            abbr = _get_abbr(curr, num)
            pos = _get_position(curr, num)
            events.append(Event(P0, "PIT_IN", f"{abbr} (P{pos})"))
            self._recent_pit_out[num] = curr_lap  # mark as pit-cycle for overtake filter

        # Pit out
        for num in prev_pit - curr_pit:
            abbr = _get_abbr(curr, num)
            tire = _get_tire(curr, num)
            events.append(Event(P0, "PIT_OUT", f"{abbr} → {tire}"))
            self._recent_pit_out[num] = curr_lap

    def _detect_overtakes(self, prev: dict, curr: dict, curr_lap: int, events: list):
        prev_pos = {p["driver_number"]: p for p in prev.get("positions", [])}
        curr_pos = {p["driver_number"]: p for p in curr.get("positions", [])}

        # Collect who just pitted (in or out) — their position changes affect others
        pit_cycle_drivers = set()
        for num in curr_pos:
            pit_out_lap = self._recent_pit_out.get(num, -10)
            if curr_lap - pit_out_lap <= 1:
                pit_cycle_drivers.add(num)
            if curr_pos[num].get("in_pit") or prev_pos.get(num, {}).get("in_pit"):
                pit_cycle_drivers.add(num)

        # Count how many drivers gained position this tick
        gainers = []
        for num, curr_p in curr_pos.items():
            prev_p = prev_pos.get(num)
            if prev_p and curr_p["position"] < prev_p["position"]:
                gainers.append(num)

        # If many drivers gained 1 position simultaneously, it's likely a pit cycle
        # (one car pits, everyone behind moves up 1)
        is_mass_shuffle = len(gainers) > 4

        for num, curr_p in curr_pos.items():
            prev_p = prev_pos.get(num)
            if prev_p is None:
                continue

            new_pos = curr_p["position"]
            old_pos = prev_p["position"]

            if new_pos >= old_pos:
                continue

            # Filter: driver is in pit
            if curr_p.get("in_pit"):
                continue

            # Filter: driver in pit cycle
            if num in pit_cycle_drivers:
                continue

            jump = old_pos - new_pos

            # Filter: huge jumps → pit cycle artifact
            if jump > 5:
                continue

            # Filter: mass shuffle (+1 position only) → likely pit-induced
            if is_mass_shuffle and jump == 1:
                continue

            abbr = _get_abbr(curr, num)
            events.append(Event(P1, "OVERTAKE", f"{abbr} P{old_pos}→P{new_pos}"))

    def _detect_fastest_lap(self, prev: dict, curr: dict, events: list):
        prev_best = {}
        for p in prev.get("positions", []):
            bl = p.get("best_lap", "")
            if bl:
                prev_best[p["driver_number"]] = bl

        curr_best = {}
        for p in curr.get("positions", []):
            bl = p.get("best_lap", "")
            if bl:
                curr_best[p["driver_number"]] = bl

        if not curr_best:
            return

        overall_prev = min(prev_best.values()) if prev_best else ""
        overall_curr = min(curr_best.values())

        if overall_curr and overall_curr != overall_prev and (not overall_prev or overall_curr < overall_prev):
            for num, bl in curr_best.items():
                if bl == overall_curr and prev_best.get(num) != bl:
                    abbr = _get_abbr(curr, num)
                    events.append(Event(P1, "FASTEST_LAP", f"{abbr} {bl}"))
                    break


# --- Helpers ---

def _get_abbr(state_dict: dict, num: str) -> str:
    for p in state_dict.get("positions", []):
        if p["driver_number"] == num:
            return p.get("abbreviation") or num
    return num


def _get_position(state_dict: dict, num: str) -> int | str:
    for p in state_dict.get("positions", []):
        if p["driver_number"] == num:
            return p["position"]
    return "?"


def _get_tire(state_dict: dict, num: str) -> str:
    for p in state_dict.get("positions", []):
        if p["driver_number"] == num:
            tire = p.get("tire", "")
            if tire:
                age = p.get("tire_age", 0)
                stint = p.get("stint_number", "")
                stint_str = f" S{stint}" if stint and stint > 1 else ""
                return f"{tire}{stint_str}"
            return "?"
    return "?"


class EventBatcher:
    """Collects events over a time window and emits them as batched stdout lines."""

    def __init__(self, window: float = 5.0, cooldown: float = 5.0):
        self.window = window
        self.cooldown = cooldown
        self._buffer: list[Event] = []
        self._window_start: float = 0
        self._last_emit: float = 0

    def add(self, events: list[Event]):
        if not events:
            return
        if not self._buffer:
            self._window_start = time.monotonic()
        self._buffer.extend(events)

    def flush(self) -> str | None:
        if not self._buffer:
            return None

        now = time.monotonic()
        has_p0 = any(e.priority == P0 for e in self._buffer)
        window_expired = (now - self._window_start) >= self.window
        cooldown_ok = (now - self._last_emit) >= self.cooldown

        if (has_p0 or window_expired) and cooldown_ok:
            self._buffer.sort(key=lambda e: e.priority)
            parts = []
            seen = set()
            for e in self._buffer:
                key = f"{e.tag}:{e.text}"
                if key not in seen:
                    seen.add(key)
                    parts.append(str(e))

            self._buffer.clear()
            self._last_emit = now
            return " | ".join(parts)

        return None
