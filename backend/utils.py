from typing import Optional, Tuple


def time_to_minutes(t_str: Optional[str]) -> Optional[int]:
    if not t_str or t_str == "HOLD":
        return None
    parts = t_str.strip().split(":")
    if len(parts) < 2:
        return None
    return int(parts[0]) * 60 + int(parts[1])


def minutes_to_time(mins: int) -> str:
    mins = max(0, min(24 * 60, mins))
    if mins == 24 * 60:
        return "24:00"
    h = mins // 60
    m = mins % 60
    return f"{h:02d}:{m:02d}"


def add_minutes_to_time(t_str: str, duration_mins: int) -> str:
    base = time_to_minutes(t_str)
    if base is None:
        return t_str
    return minutes_to_time(base + int(duration_mins))


def intervals_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    """Returns True if [start_a, end_a) and [start_b, end_b) have a positive overlap."""
    return max(start_a, start_b) < min(end_a, end_b)


def target_slot_for_eta(eta_str: str, duration_mins: int = 60) -> Tuple[str, str]:
    """
    Maps a HH:MM ETA string across the full 24-hour day (00:00 through 23:00)
    to the appropriate hourly slot start, and computes slot_end = slot_start + duration_mins.
    If ETA is within 10 mins before the next hour (e.g. 08:55), rounds to 09:00 slot.
    """
    m = time_to_minutes(eta_str)
    duration = int(duration_mins) if duration_mins in (30, 45, 60) else 60
    if m is None:
        return ("08:00", add_minutes_to_time("08:00", duration))
    hour = m // 60
    rem = m % 60
    if rem >= 50:
        hour += 1
    hour = max(0, min(23, hour))
    slot_start = f"{hour:02d}:00"
    slot_end = add_minutes_to_time(slot_start, duration)
    return (slot_start, slot_end)
