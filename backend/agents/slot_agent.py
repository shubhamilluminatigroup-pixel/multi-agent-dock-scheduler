from typing import List, Dict, Any
from backend.utils import add_minutes_to_time


class SlotCheckingAgent:
    """
    Agent 4: SlotCheckingAgent
    Matches cargo types, dock capabilities, truck priorities, and appointment durations
    (30m, 45m, 60m) across the full 24-hour schedule (00:00 - 24:00) to generate optimal
    slot swaps, dock swaps, reassignments, or unbooked allocations.
    """
    name = "SlotCheckingAgent"
    role = "24h Constraint & Dock Slot Optimization Engine"

    def _dock_supports_cargo(self, dock: Dict[str, Any], cargo_type: str) -> bool:
        if not dock.get("is_active") or dock.get("status") != "ONLINE":
            return False
        supported = [c.strip().upper() for c in dock["supported_cargo"].split(",")]
        return cargo_type.upper() in supported

    def compute_optimal_schedule(
        self,
        docks: List[Dict[str, Any]],
        schedule_records: List[Dict[str, Any]],
        eta_analyses: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        dock_map = {d["dock_id"]: d for d in docks}

        slot_grid: Dict[tuple, Dict[str, Any]] = {}
        for rec in schedule_records:
            slot_grid[(rec["dock_id"], rec["slot_start"])] = dict(rec)

        proposals: List[Dict[str, Any]] = []
        handled_trucks = set()

        actionable = [a for a in eta_analyses if a["requires_rescheduling"]]
        actionable.sort(key=lambda x: x["priority_score"], reverse=True)

        # -----------------------------------------------------------------
        # PASS 1: Detect Complementary Mutual Swaps (Early <-> Delayed)
        # -----------------------------------------------------------------
        for a in actionable:
            t1_id = a["truck_id"]
            if t1_id in handled_trucks or not a["scheduled_dock_id"]:
                continue

            for b in actionable:
                t2_id = b["truck_id"]
                if t1_id == t2_id or t2_id in handled_trucks or not b["scheduled_dock_id"]:
                    continue

                if (
                    a["ideal_slot_start"] == b["scheduled_slot_start"]
                    and b["ideal_slot_start"] == a["scheduled_slot_start"]
                ):
                    dock1 = dock_map.get(a["scheduled_dock_id"])
                    dock2 = dock_map.get(b["scheduled_dock_id"])
                    if (
                        dock1 and dock2
                        and self._dock_supports_cargo(dock2, a["cargo_type"])
                        and self._dock_supports_cargo(dock1, b["cargo_type"])
                    ):
                        dur1 = int(a.get("duration_mins") or 60)
                        dur2 = int(b.get("duration_mins") or 60)
                        t1_new_end = add_minutes_to_time(b["scheduled_slot_start"], dur1)
                        t2_new_end = add_minutes_to_time(a["scheduled_slot_start"], dur2)

                        reason_text = (
                            f"Swap {t1_id} ({dur1}m, ETA {a['current_eta']}) into "
                            f"{b['scheduled_dock_id']} [{b['scheduled_slot_start']}-{t1_new_end}] and move delayed "
                            f"{t2_id} ({dur2}m, ETA {b['current_eta']}) into "
                            f"{a['scheduled_dock_id']} [{a['scheduled_slot_start']}-{t2_new_end}] — resolves overlapping ETA conflict."
                        )

                        proposals.append({
                            "proposal_type": "SLOT_SWAP",
                            "action_type": "SLOT_SWAP",
                            "primary_truck_id": t1_id,
                            "secondary_truck_id": t2_id,
                            "duration_mins": dur1,
                            "secondary_duration_mins": dur2,
                            "old_dock_id": a["scheduled_dock_id"],
                            "old_slot_start": a["scheduled_slot_start"],
                            "old_slot_end": a["scheduled_slot_end"],
                            "new_dock_id": b["scheduled_dock_id"],
                            "new_slot_start": b["scheduled_slot_start"],
                            "new_slot_end": t1_new_end,
                            "partner_new_dock_id": a["scheduled_dock_id"],
                            "partner_new_slot_start": a["scheduled_slot_start"],
                            "partner_new_slot_end": t2_new_end,
                            "secondary_old_dock_id": b["scheduled_dock_id"],
                            "secondary_old_slot_start": b["scheduled_slot_start"],
                            "secondary_old_slot_end": b["scheduled_slot_end"],
                            "secondary_new_dock_id": a["scheduled_dock_id"],
                            "secondary_new_slot_start": a["scheduled_slot_start"],
                            "secondary_new_slot_end": t2_new_end,
                            "eta": f"{a['current_eta']} / {b['current_eta']}",
                            "reason": reason_text,
                            "rationale": reason_text,
                        })
                        handled_trucks.add(t1_id)
                        handled_trucks.add(t2_id)

                        cell1 = slot_grid[(b["scheduled_dock_id"], b["scheduled_slot_start"])]
                        cell1["assigned_truck_id"] = t1_id
                        cell1["cargo_type"] = a["cargo_type"]
                        cell1["duration_mins"] = dur1
                        cell1["slot_end"] = t1_new_end
                        cell1["slot_status"] = "OCCUPIED"
                        cell1["change_type"] = "SLOT_SWAP"

                        cell2 = slot_grid[(a["scheduled_dock_id"], a["scheduled_slot_start"])]
                        cell2["assigned_truck_id"] = t2_id
                        cell2["cargo_type"] = b["cargo_type"]
                        cell2["duration_mins"] = dur2
                        cell2["slot_end"] = t2_new_end
                        cell2["slot_status"] = "OCCUPIED"
                        cell2["change_type"] = "SLOT_SWAP"
                        break

        # -----------------------------------------------------------------
        # PASS 2: Reassign Delayed / Early Booked Trucks to Open 24h Slots
        # -----------------------------------------------------------------
        all_hours = [f"{h:02d}:00" for h in range(24)]

        for a in actionable:
            t_id = a["truck_id"]
            if t_id in handled_trucks or a["eta_classification"] == "UNBOOKED":
                continue

            dur = int(a.get("duration_mins") or 60)
            target_h = a["ideal_slot_start"]
            target_idx = all_hours.index(target_h) if target_h in all_hours else 8
            candidate_hours = all_hours[target_idx:] + all_hours[:target_idx]

            allocated = False
            preferred_docks = sorted(
                docks,
                key=lambda d: (0 if d["dock_id"] == a["scheduled_dock_id"] else 1, d["dock_id"])
            )

            for h in candidate_hours:
                for d in preferred_docks:
                    if not self._dock_supports_cargo(d, a["cargo_type"]):
                        continue
                    cell = slot_grid.get((d["dock_id"], h))
                    if cell and (cell["slot_status"] == "FREE" or not cell["assigned_truck_id"]):
                        old_dock = a["scheduled_dock_id"]
                        old_start = a["scheduled_slot_start"]
                        old_end = a["scheduled_slot_end"]
                        new_end = add_minutes_to_time(h, dur)
                        act_type = "DOCK_SWAP" if d["dock_id"] != old_dock else "SLOT_SHIFT"

                        if old_dock and old_start and (old_dock, old_start) in slot_grid:
                            old_hour_idx = int(old_start.split(":")[0])
                            old_cell = slot_grid[(old_dock, old_start)]
                            old_cell["assigned_truck_id"] = None
                            old_cell["cargo_type"] = None
                            old_cell["slot_status"] = "FREE"
                            old_cell["duration_mins"] = 60
                            old_cell["slot_end"] = f"{old_hour_idx + 1:02d}:00"

                        cell["assigned_truck_id"] = t_id
                        cell["cargo_type"] = a["cargo_type"]
                        cell["slot_status"] = "OCCUPIED"
                        cell["duration_mins"] = dur
                        cell["slot_end"] = new_end
                        cell["change_type"] = act_type

                        reason_text = (
                            f"Move {t_id} ({a['cargo_type']}, {dur}m, ETA {a['current_eta']}) "
                            f"from {old_dock} [{old_start}-{old_end}] to open bay {d['dock_id']} [{h}-{new_end}], "
                            f"freeing {old_dock} [{old_start}] and resolving ETA conflict."
                        )

                        proposals.append({
                            "proposal_type": "REASSIGN_FREE_SLOT",
                            "action_type": act_type,
                            "primary_truck_id": t_id,
                            "secondary_truck_id": None,
                            "duration_mins": dur,
                            "old_dock_id": old_dock,
                            "old_slot_start": old_start,
                            "old_slot_end": old_end,
                            "new_dock_id": d["dock_id"],
                            "new_slot_start": h,
                            "new_slot_end": new_end,
                            "eta": a["current_eta"],
                            "reason": reason_text,
                            "rationale": reason_text,
                        })
                        handled_trucks.add(t_id)
                        allocated = True
                        break
                if allocated:
                    break

        # -----------------------------------------------------------------
        # PASS 3: Allocate Unbooked Urgent Arrivals into Newly Freed or Open 24h Slots
        # -----------------------------------------------------------------
        for a in actionable:
            t_id = a["truck_id"]
            if t_id in handled_trucks or a["eta_classification"] != "UNBOOKED":
                continue

            dur = int(a.get("duration_mins") or 60)
            target_h = a["ideal_slot_start"]
            target_idx = all_hours.index(target_h) if target_h in all_hours else 8
            candidate_hours = all_hours[target_idx:] + all_hours[:target_idx]

            allocated = False
            for h in candidate_hours:
                for d in docks:
                    if not self._dock_supports_cargo(d, a["cargo_type"]):
                        continue
                    cell = slot_grid.get((d["dock_id"], h))
                    if cell and (cell["slot_status"] == "FREE" or not cell["assigned_truck_id"]):
                        new_end = add_minutes_to_time(h, dur)
                        cell["assigned_truck_id"] = t_id
                        cell["cargo_type"] = a["cargo_type"]
                        cell["slot_status"] = "OCCUPIED"
                        cell["duration_mins"] = dur
                        cell["slot_end"] = new_end
                        cell["change_type"] = "BOOK_NEW_APPOINTMENT"

                        reason_text = (
                            f"Book new {dur}m appointment for unbooked carrier {t_id} ({a['cargo_type']}, "
                            f"ETA {a['current_eta']}) in compatible bay {d['dock_id']} [{h}-{new_end}]."
                        )

                        proposals.append({
                            "proposal_type": "ASSIGN_UNBOOKED_TRUCK",
                            "action_type": "BOOK_NEW_APPOINTMENT",
                            "primary_truck_id": t_id,
                            "secondary_truck_id": None,
                            "duration_mins": dur,
                            "old_dock_id": None,
                            "old_slot_start": None,
                            "old_slot_end": None,
                            "new_dock_id": d["dock_id"],
                            "new_slot_start": h,
                            "new_slot_end": new_end,
                            "eta": a["current_eta"],
                            "reason": reason_text,
                            "rationale": reason_text,
                        })
                        handled_trucks.add(t_id)
                        allocated = True
                        break
                if allocated:
                    break

        simulated_grid = sorted(
            list(slot_grid.values()),
            key=lambda r: (r["slot_start"], r["dock_id"])
        )

        return {
            "agent": self.name,
            "role": self.role,
            "proposals": proposals,
            "proposal_count": len(proposals),
            "simulated_grid": simulated_grid,
            "log": (
                f"[{self.name}] Generated {len(proposals)} conflict-free 24h dock schedule "
                f"optimization proposal(s) supporting 30/45/60m appointment durations."
            ),
        }
