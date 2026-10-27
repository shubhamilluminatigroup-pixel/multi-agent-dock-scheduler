import json
import uuid
from datetime import datetime
from typing import List, Dict, Any
from backend.database import get_schedule_db_conn, get_truck_db_conn


class ExecutionCommAgent:
    """
    Agent 5: ExecutionCommAgent
    Executes validated schedule proposals across BOTH databases (schedule_db.sqlite and truck_db.sqlite),
    preserving 30/45/60m appointment durations, and dispatches structured notifications to the
    Master Scheduler and affected Truck Drivers.
    """
    name = "ExecutionCommAgent"
    role = "Schedule Executor & Scheduler/Driver Dispatcher"

    def execute_proposals(self, proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not proposals:
            return {
                "agent": self.name,
                "executed_count": 0,
                "communications": [],
                "log": f"[{self.name}] No schedule changes required; all trucks are aligned with assigned slots."
            }

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        comms_created: List[Dict[str, Any]] = []

        with get_schedule_db_conn() as s_conn, get_truck_db_conn() as t_conn:
            s_cur = s_conn.cursor()
            t_cur = t_conn.cursor()

            t_cur.execute("SELECT * FROM trucks")
            trucks_by_id = {row["truck_id"]: dict(row) for row in t_cur.fetchall()}

            for prop in proposals:
                p_type = prop["proposal_type"]
                act_type = prop.get("action_type", p_type)
                t1_id = prop["primary_truck_id"]
                t2_id = prop.get("secondary_truck_id")
                t1 = trucks_by_id.get(t1_id, {})
                t2 = trucks_by_id.get(t2_id, {}) if t2_id else {}
                dur1 = int(prop.get("duration_mins") or t1.get("duration_mins") or 60)
                dur2 = int(prop.get("secondary_duration_mins") or t2.get("duration_mins") or 60)
                t1_phone = t1.get("driver_phone") or t1.get("driver_contact") or ""
                t2_phone = t2.get("driver_phone") or t2.get("driver_contact") or ""

                if p_type == "SLOT_SWAP":
                    s_cur.execute("""
                        UPDATE schedule_records
                        SET assigned_truck_id = ?, cargo_type = ?, slot_end = ?, duration_mins = ?,
                            slot_status = 'OCCUPIED', change_type = 'SLOT_SWAP',
                            allocation_note = ?, updated_at = ?
                        WHERE dock_id = ? AND slot_start = ?
                    """, (
                        t1_id, t1.get("cargo_type"), prop["new_slot_end"], dur1,
                        f"Swapped with {t2_id} ({dur1}m via ExecutionCommAgent)", now_str,
                        prop["new_dock_id"], prop["new_slot_start"]
                    ))

                    s_cur.execute("""
                        UPDATE schedule_records
                        SET assigned_truck_id = ?, cargo_type = ?, slot_end = ?, duration_mins = ?,
                            slot_status = 'OCCUPIED', change_type = 'SLOT_SWAP',
                            allocation_note = ?, updated_at = ?
                        WHERE dock_id = ? AND slot_start = ?
                    """, (
                        t2_id, t2.get("cargo_type"), prop["secondary_new_slot_end"], dur2,
                        f"Swapped with {t1_id} ({dur2}m via ExecutionCommAgent)", now_str,
                        prop["secondary_new_dock_id"], prop["secondary_new_slot_start"]
                    ))

                    t_cur.execute("""
                        UPDATE trucks
                        SET scheduled_dock_id = ?, scheduled_slot_start = ?, scheduled_slot_end = ?,
                            eta_status = 'RESCHEDULED_SWAP', last_updated = ?
                        WHERE truck_id = ?
                    """, (prop["new_dock_id"], prop["new_slot_start"], prop["new_slot_end"], now_str, t1_id))

                    t_cur.execute("""
                        UPDATE trucks
                        SET scheduled_dock_id = ?, scheduled_slot_start = ?, scheduled_slot_end = ?,
                            eta_status = 'RESCHEDULED_SWAP', last_updated = ?
                        WHERE truck_id = ?
                    """, (
                        prop["secondary_new_dock_id"],
                        prop["secondary_new_slot_start"],
                        prop["secondary_new_slot_end"],
                        now_str,
                        t2_id
                    ))

                    comms_created.append(self._insert_comm(
                        s_cur, now_str,
                        recipient_role="MASTER_SCHEDULER",
                        recipient_name="Dock Control Tower / Master Scheduler",
                        action_type="SLOT_SWAP_EXECUTED",
                        truck_id=f"{t1_id},{t2_id}",
                        summary=(
                            f"[SWAP EXECUTED] {t1_id} ({dur1}m) moved to {prop['new_dock_id']} "
                            f"({prop['new_slot_start']}-{prop['new_slot_end']}) <-> "
                            f"{t2_id} ({dur2}m) moved to {prop['secondary_new_dock_id']} "
                            f"({prop['secondary_new_slot_start']}-{prop['secondary_new_slot_end']})."
                        ),
                        details=prop
                    ))

                    comms_created.append(self._insert_comm(
                        s_cur, now_str,
                        recipient_role="TRUCK_DRIVER",
                        recipient_name=f"{t1.get('driver_name', 'Driver')} ({t1_id} / {t1_phone})",
                        action_type="DRIVER_SLOT_UPDATE",
                        truck_id=t1_id,
                        summary=(
                            f"Proceed directly to {prop['new_dock_id']} for updated {dur1}-min early slot "
                            f"{prop['new_slot_start']}-{prop['new_slot_end']} (swapped due to early arrival ETA {t1.get('current_eta')})."
                        ),
                        details=prop
                    ))

                    comms_created.append(self._insert_comm(
                        s_cur, now_str,
                        recipient_role="TRUCK_DRIVER",
                        recipient_name=f"{t2.get('driver_name', 'Driver')} ({t2_id} / {t2_phone})",
                        action_type="DRIVER_SLOT_UPDATE",
                        truck_id=t2_id,
                        summary=(
                            f"Your {dur2}-min slot has been shifted to {prop['secondary_new_dock_id']} "
                            f"{prop['secondary_new_slot_start']}-{prop['secondary_new_slot_end']} matching your delayed ETA {t2.get('current_eta')}."
                        ),
                        details=prop
                    ))

                elif p_type == "REASSIGN_FREE_SLOT":
                    if prop.get("old_dock_id") and prop.get("old_slot_start"):
                        old_hour = int(prop["old_slot_start"].split(":")[0])
                        base_end = f"{old_hour + 1:02d}:00"
                        s_cur.execute("""
                            UPDATE schedule_records
                            SET assigned_truck_id = NULL, cargo_type = NULL, slot_end = ?, duration_mins = 60,
                                slot_status = 'FREE', change_type = 'NONE',
                                allocation_note = ?, updated_at = ?
                            WHERE dock_id = ? AND slot_start = ? AND assigned_truck_id = ?
                        """, (
                            base_end,
                            f"Vacated by delayed/reassigned {t1_id}",
                            now_str,
                            prop["old_dock_id"],
                            prop["old_slot_start"],
                            t1_id
                        ))

                    s_cur.execute("""
                        UPDATE schedule_records
                        SET assigned_truck_id = ?, cargo_type = ?, slot_end = ?, duration_mins = ?,
                            slot_status = 'OCCUPIED', change_type = ?,
                            allocation_note = ?, updated_at = ?
                        WHERE dock_id = ? AND slot_start = ?
                    """, (
                        t1_id, t1.get("cargo_type"), prop["new_slot_end"], dur1, act_type,
                        f"Reassigned {t1_id} ({dur1}m, ETA {t1.get('current_eta')})", now_str,
                        prop["new_dock_id"], prop["new_slot_start"]
                    ))

                    t_cur.execute("""
                        UPDATE trucks
                        SET scheduled_dock_id = ?, scheduled_slot_start = ?, scheduled_slot_end = ?,
                            eta_status = 'RESCHEDULED', last_updated = ?
                        WHERE truck_id = ?
                    """, (prop["new_dock_id"], prop["new_slot_start"], prop["new_slot_end"], now_str, t1_id))

                    comms_created.append(self._insert_comm(
                        s_cur, now_str,
                        recipient_role="MASTER_SCHEDULER",
                        recipient_name="Dock Control Tower / Master Scheduler",
                        action_type="SLOT_REASSIGNED",
                        truck_id=t1_id,
                        summary=(
                            f"[REASSIGNED] {t1_id} ({dur1}m) moved from {prop['old_dock_id']} "
                            f"[{prop['old_slot_start']}-{prop['old_slot_end']}] to {prop['new_dock_id']} "
                            f"[{prop['new_slot_start']}-{prop['new_slot_end']}]."
                        ),
                        details=prop
                    ))

                    comms_created.append(self._insert_comm(
                        s_cur, now_str,
                        recipient_role="TRUCK_DRIVER",
                        recipient_name=f"{t1.get('driver_name', 'Driver')} ({t1_id} / {t1_phone})",
                        action_type="DRIVER_SLOT_UPDATE",
                        truck_id=t1_id,
                        summary=(
                            f"New {dur1}-min dock assignment confirmed: {prop['new_dock_id']} window "
                            f"{prop['new_slot_start']}-{prop['new_slot_end']} (aligned with your live ETA {t1.get('current_eta')})."
                        ),
                        details=prop
                    ))

                elif p_type == "ASSIGN_UNBOOKED_TRUCK":
                    s_cur.execute("""
                        UPDATE schedule_records
                        SET assigned_truck_id = ?, cargo_type = ?, slot_end = ?, duration_mins = ?,
                            slot_status = 'OCCUPIED', change_type = 'BOOK_NEW_APPOINTMENT',
                            allocation_note = ?, updated_at = ?
                        WHERE dock_id = ? AND slot_start = ?
                    """, (
                        t1_id, t1.get("cargo_type"), prop["new_slot_end"], dur1,
                        f"Allocated to unbooked {t1.get('priority_level')} truck {t1_id} ({dur1}m)", now_str,
                        prop["new_dock_id"], prop["new_slot_start"]
                    ))

                    t_cur.execute("""
                        UPDATE trucks
                        SET scheduled_dock_id = ?, scheduled_slot_start = ?, scheduled_slot_end = ?,
                            eta_status = 'BOOKED_OPTIMIZED', last_updated = ?
                        WHERE truck_id = ?
                    """, (prop["new_dock_id"], prop["new_slot_start"], prop["new_slot_end"], now_str, t1_id))

                    comms_created.append(self._insert_comm(
                        s_cur, now_str,
                        recipient_role="MASTER_SCHEDULER",
                        recipient_name="Dock Control Tower / Master Scheduler",
                        action_type="NEW_ARRIVAL_ALLOCATED",
                        truck_id=t1_id,
                        summary=(
                            f"[NEW ALLOCATION] Unbooked {t1.get('priority_level')} carrier {t1_id} ({dur1}m) "
                            f"assigned to {prop['new_dock_id']} [{prop['new_slot_start']}-{prop['new_slot_end']}]."
                        ),
                        details=prop
                    ))

                    comms_created.append(self._insert_comm(
                        s_cur, now_str,
                        recipient_role="TRUCK_DRIVER",
                        recipient_name=f"{t1.get('driver_name', 'Driver')} ({t1_id} / {t1_phone})",
                        action_type="DRIVER_BOOKING_CONFIRMED",
                        truck_id=t1_id,
                        summary=(
                            f"Dock reservation issued: report to {prop['new_dock_id']} for {dur1}-min slot "
                            f"{prop['new_slot_start']}-{prop['new_slot_end']} (ETA {t1.get('current_eta')})."
                        ),
                        details=prop
                    ))

            s_conn.commit()
            t_conn.commit()

        return {
            "agent": self.name,
            "role": self.role,
            "executed_count": len(proposals),
            "communications": comms_created,
            "log": f"[{self.name}] Committed {len(proposals)} database update(s) & dispatched {len(comms_created)} notifications."
        }

    def _insert_comm(
        self,
        s_cur,
        timestamp: str,
        recipient_role: str,
        recipient_name: str,
        action_type: str,
        truck_id: str,
        summary: str,
        details: Dict[str, Any]
    ) -> Dict[str, Any]:
        comm_id = f"COMM-{uuid.uuid4().hex[:8].upper()}"
        details_str = json.dumps(details)
        s_cur.execute("""
            INSERT INTO scheduler_communications (
                comm_id, timestamp, agent_name, recipient_role, recipient_name,
                action_type, truck_id, summary, details_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DISPATCHED')
        """, (
            comm_id, timestamp, self.name, recipient_role, recipient_name,
            action_type, truck_id, summary, details_str
        ))
        return {
            "comm_id": comm_id,
            "timestamp": timestamp,
            "agent_name": self.name,
            "recipient_role": recipient_role,
            "recipient_name": recipient_name,
            "action_type": action_type,
            "truck_id": truck_id,
            "summary": summary,
            "details": details,
            "status": "DISPATCHED"
        }
