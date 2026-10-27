from typing import List, Dict, Any
from backend.utils import (
    time_to_minutes,
    add_minutes_to_time,
    intervals_overlap,
    target_slot_for_eta,
)
from backend.connectors import sync_external_eta_feed_into_trucks


class ETAFinderAgent:
    """
    Agent 3: ETAFinderAgent
    Calculates live arrival windows [current_eta, current_eta + duration_mins],
    variance_mins against booked slots (30m, 45m, 60m), and detects Overlapping ETAs
    across trucks on the same dock or target window.
    """
    name = "ETAFinderAgent"
    role = "Real-Time ETA, Duration & Overlap Conflict Analyzer"

    def analyze_etas(self, trucks: List[Dict[str, Any]]) -> Dict[str, Any]:
        ext_sync_info = sync_external_eta_feed_into_trucks(trucks)
        analyses = []
        actionable_count = 0
        overlap_count = 0

        # Precompute intervals for overlap detection across all trucks
        truck_intervals = []
        for t in trucks:
            dur = int(t.get("duration_mins") or 60)
            eta_start = time_to_minutes(t.get("current_eta"))
            eta_end = (eta_start + dur) if eta_start is not None else None
            sched_start = time_to_minutes(t.get("scheduled_slot_start"))
            sched_end = time_to_minutes(t.get("scheduled_slot_end"))
            if sched_start is not None and sched_end is None:
                sched_end = sched_start + dur
            truck_intervals.append({
                "truck_id": t["truck_id"],
                "dock_id": t.get("scheduled_dock_id"),
                "duration_mins": dur,
                "current_eta": t.get("current_eta"),
                "eta_end_str": add_minutes_to_time(t["current_eta"], dur) if t.get("current_eta") else None,
                "eta_start": eta_start,
                "eta_end": eta_end,
                "sched_start": sched_start,
                "sched_end": sched_end,
                "sched_start_str": t.get("scheduled_slot_start"),
                "sched_end_str": t.get("scheduled_slot_end"),
            })

        for idx, t in enumerate(trucks):
            dur = int(t.get("duration_mins") or 60)
            sched_start = t.get("scheduled_slot_start")
            sched_end = t.get("scheduled_slot_end")
            if sched_start and sched_start != "HOLD" and not sched_end:
                sched_end = add_minutes_to_time(sched_start, dur)

            curr_eta = t["current_eta"]
            live_eta_end = add_minutes_to_time(curr_eta, dur)
            ideal_start, ideal_end = target_slot_for_eta(curr_eta, dur)

            curr_mins = time_to_minutes(curr_eta) or 0
            sched_mins = time_to_minutes(sched_start)
            my_info = truck_intervals[idx]

            # Check for ETA overlaps against other trucks
            overlapping_trucks = []
            overlap_details = []
            for other in truck_intervals:
                if other["truck_id"] == t["truck_id"]:
                    continue
                if my_info["eta_start"] is None or my_info["eta_end"] is None:
                    continue

                same_dock = (
                    my_info["dock_id"]
                    and my_info["dock_id"] != "HOLD"
                    and my_info["dock_id"] == other["dock_id"]
                )
                unbooked_collision = (
                    (not my_info["dock_id"])
                    and other["dock_id"]
                    and other["dock_id"] != "HOLD"
                )

                # 1. My live ETA window [eta_start, eta_end) overlaps another truck's booked slot on the same dock
                if (same_dock or unbooked_collision) and other["sched_start"] is not None and other["sched_end"] is not None:
                    if intervals_overlap(my_info["eta_start"], my_info["eta_end"], other["sched_start"], other["sched_end"]):
                        if other["truck_id"] not in overlapping_trucks:
                            overlapping_trucks.append(other["truck_id"])
                            overlap_details.append(
                                f"{other['truck_id']} ({other['dock_id']} {other['sched_start_str']}-{other['sched_end_str']})"
                            )
                            continue

                # 2. My live ETA window [eta_start, eta_end) overlaps another truck's live ETA window on the same dock
                if same_dock and other["eta_start"] is not None and other["eta_end"] is not None:
                    if intervals_overlap(my_info["eta_start"], my_info["eta_end"], other["eta_start"], other["eta_end"]):
                        if other["truck_id"] not in overlapping_trucks:
                            overlapping_trucks.append(other["truck_id"])
                            overlap_details.append(
                                f"{other['truck_id']} (Live ETA {other['current_eta']}-{other['eta_end_str']})"
                            )

            has_eta_overlap = len(overlapping_trucks) > 0
            if has_eta_overlap:
                overlap_count += 1
                overlap_summary = (
                    f"OVERLAPPING ETA: {t['truck_id']} live window [{curr_eta}-{live_eta_end}] ({dur}m) "
                    f"collides with {', '.join(overlap_details)}"
                )
            else:
                overlap_summary = None

            if t.get("eta_status") == "MANUAL_KEEP_SLOT":
                delta_mins = (curr_mins - sched_mins) if sched_mins is not None else 0
                eta_classification = "KEPT_ORIGINAL"
                requires_rescheduling = False
                reason = (
                    f"Scheduler kept original slot ({sched_start}-{sched_end}, {dur}m) for {t['truck_id']}."
                )
            elif sched_mins is None:
                delta_mins = None
                eta_classification = "UNBOOKED"
                requires_rescheduling = True
                actionable_count += 1
                reason = (
                    f"Unbooked {t['cargo_type']} truck ({dur}m appointment) arriving at {curr_eta} "
                    f"(window {curr_eta}-{live_eta_end}); requires slot around {ideal_start}-{ideal_end}."
                )
                if overlap_summary:
                    reason += f" | {overlap_summary}"
            else:
                delta_mins = curr_mins - sched_mins
                if delta_mins >= 20 and ideal_start != sched_start:
                    eta_classification = "DELAYED"
                    requires_rescheduling = True
                    actionable_count += 1
                    reason = (
                        f"Delayed +{delta_mins}m (Booked {sched_start}-{sched_end} [{dur}m], "
                        f"Live ETA {curr_eta}-{live_eta_end}); misses booked window -> target {ideal_start}-{ideal_end}."
                    )
                elif delta_mins <= -25 and ideal_start != sched_start:
                    eta_classification = "EARLY"
                    requires_rescheduling = True
                    actionable_count += 1
                    reason = (
                        f"Arriving {abs(delta_mins)}m early (Booked {sched_start}-{sched_end} [{dur}m], "
                        f"Live ETA {curr_eta}-{live_eta_end}); candidate for earlier slot {ideal_start}-{ideal_end}."
                    )
                elif has_eta_overlap and abs(delta_mins) >= 15:
                    eta_classification = "OVERLAPPING_ETA"
                    requires_rescheduling = True
                    actionable_count += 1
                    reason = overlap_summary
                else:
                    eta_classification = "ON_TIME"
                    requires_rescheduling = False
                    reason = (
                        f"Arrival variance ({delta_mins:+d}m) within tolerance for {dur}m slot "
                        f"{sched_start}-{sched_end} (Live window {curr_eta}-{live_eta_end})."
                    )
                    if overlap_summary:
                        reason += f" | {overlap_summary}"

            analyses.append({
                "truck_id": t["truck_id"],
                "carrier_name": t.get("carrier_name", ""),
                "driver_name": t.get("driver_name", ""),
                "driver_phone": t.get("driver_phone", ""),
                "cargo_type": t["cargo_type"],
                "weight_tons": t.get("weight_tons", 18.0),
                "priority_level": t.get("priority_level", "HIGH"),
                "priority_score": t.get("priority_score", 80),
                "duration_mins": dur,
                "scheduled_dock_id": t.get("scheduled_dock_id"),
                "scheduled_slot_start": sched_start,
                "scheduled_slot_end": sched_end,
                "original_eta": t.get("original_eta", curr_eta),
                "current_eta": curr_eta,
                "live_eta_end": live_eta_end,
                "variance_mins": delta_mins,
                "delta_minutes": delta_mins or 0,
                "ideal_slot_start": ideal_start,
                "ideal_slot_end": ideal_end,
                "eta_classification": eta_classification,
                "classification": eta_classification,
                "requires_rescheduling": requires_rescheduling,
                "requires_reschedule": requires_rescheduling,
                "has_eta_overlap": has_eta_overlap,
                "overlapping_trucks": overlapping_trucks,
                "overlap_summary": overlap_summary,
                "reason": reason,
            })

        return {
            "agent": self.name,
            "role": self.role,
            "connector_type": ext_sync_info["source_type"],
            "analyses": analyses,
            "actionable_count": actionable_count,
            "overlap_count": overlap_count,
            "connection_info": ext_sync_info,
            "log": (
                f"[{self.name}] Evaluated {len(analyses)} trucks (30/45/60m durations) via "
                f"{ext_sync_info['source_type']}; {actionable_count} require slot reallocation, "
                f"{overlap_count} overlapping ETA conflict(s) flagged."
            ),
        }
