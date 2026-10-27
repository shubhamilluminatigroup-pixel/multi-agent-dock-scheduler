import json
import uuid
from datetime import datetime
from typing import Dict, Any

from backend.database import get_schedule_db_conn, get_truck_db_conn
from backend.agents.truck_agent import TruckDataAgent
from backend.agents.schedule_agent import ScheduleDataAgent
from backend.agents.eta_agent import ETAFinderAgent
from backend.agents.slot_agent import SlotCheckingAgent
from backend.agents.exec_comm_agent import ExecutionCommAgent


class MultiAgentOrchestrator:
    """
    Coordinates the 5 specialized agents sequentially:
    1. TruckDataAgent -> 2. ScheduleDataAgent -> 3. ETAFinderAgent -> 4. SlotCheckingAgent -> 5. ExecutionCommAgent
    """
    def __init__(self):
        self.truck_agent = TruckDataAgent()
        self.schedule_agent = ScheduleDataAgent()
        self.eta_agent = ETAFinderAgent()
        self.slot_agent = SlotCheckingAgent()
        self.exec_agent = ExecutionCommAgent()

    def approve_single_proposal(self, truck_id: str) -> Dict[str, Any]:
        """
        Approves and executes a specific proposal matching `truck_id` (plus any prerequisite proposal
        if the target slot is currently being vacated by another pending proposal).
        """
        step1 = self.truck_agent.fetch_all_trucks()
        step2 = self.schedule_agent.fetch_schedule_state()
        step3 = self.eta_agent.analyze_etas(step1["trucks"])
        step4 = self.slot_agent.compute_optimal_schedule(
            docks=step2["docks"],
            schedule_records=step2["schedule_records"],
            eta_analyses=step3["analyses"]
        )
        proposals = step4["proposals"]

        target_prop = None
        for p in proposals:
            if p["primary_truck_id"] == truck_id or p.get("secondary_truck_id") == truck_id:
                target_prop = p
                break

        if not target_prop:
            raise ValueError(f"No pending proposal found for truck {truck_id}.")

        # Check if target slot is vacated by an earlier proposal in the chain (e.g. TRK-108 taking TRK-104's vacated slot)
        to_execute = []
        for p in proposals:
            if (
                p["old_dock_id"] == target_prop["new_dock_id"]
                and p["old_slot_start"] == target_prop["new_slot_start"]
                and p["primary_truck_id"] != target_prop["primary_truck_id"]
            ):
                to_execute.append(p)
        to_execute.append(target_prop)

        exec_res = self.exec_agent.execute_proposals(to_execute)
        return {
            "approved_truck_id": truck_id,
            "executed_proposals": to_execute,
            "execution_result": exec_res,
        }

    def reject_single_proposal(self, truck_id: str) -> Dict[str, Any]:
        """
        Rejects a proposed reschedule for `truck_id` and locks its current schedule in truck_db.sqlite,
        or removes an unbooked truck request if unbooked. Logs the decision in scheduler_communications.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_truck_db_conn() as t_conn, get_schedule_db_conn() as s_conn:
            t_cur = t_conn.cursor()
            s_cur = s_conn.cursor()

            t_cur.execute("SELECT * FROM trucks WHERE truck_id = ?", (truck_id,))
            row = t_cur.fetchone()
            if not row:
                raise ValueError(f"Truck {truck_id} not found.")
            truck = dict(row)

            if truck.get("scheduled_dock_id") and truck.get("scheduled_slot_start"):
                t_cur.execute(
                    "UPDATE trucks SET eta_status = 'MANUAL_KEEP_SLOT', last_updated = ? WHERE truck_id = ?",
                    (now_str, truck_id)
                )
                summary = (
                    f"[SCHEDULER REJECTED SWAP] Kept {truck_id} in original slot "
                    f"{truck['scheduled_dock_id']} [{truck['scheduled_slot_start']}-{truck['scheduled_slot_end']}] "
                    f"(ETA {truck['current_eta']})."
                )
            else:
                # For an unbooked truck, set eta_status to MANUAL_HOLD and align note
                t_cur.execute(
                    "UPDATE trucks SET scheduled_dock_id = 'HOLD', scheduled_slot_start = 'HOLD', scheduled_slot_end = 'HOLD', eta_status = 'MANUAL_KEEP_SLOT', last_updated = ? WHERE truck_id = ?",
                    (now_str, truck_id)
                )
                summary = f"[SCHEDULER REJECTED NEW BOOKING] Placed unbooked truck {truck_id} (ETA {truck['current_eta']}) on manual hold."

            comm_id = f"COMM-{uuid.uuid4().hex[:8].upper()}"
            s_cur.execute("""
                INSERT INTO scheduler_communications (
                    comm_id, timestamp, agent_name, recipient_role, recipient_name,
                    action_type, truck_id, summary, details_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                comm_id,
                now_str,
                self.exec_agent.name,
                "MASTER_SCHEDULER_DECISION",
                f"Scheduler Override ({truck_id})",
                "PROPOSAL_REJECTED",
                truck_id,
                summary,
                json.dumps({"truck_id": truck_id, "decision": "REJECTED"}),
                "REJECTED_BY_USER"
            ))
            t_conn.commit()
            s_conn.commit()

        return {"rejected_truck_id": truck_id, "summary": summary}

    def run_pipeline(self, auto_execute: bool = True, trigger_source: str = "MANUAL_OR_UI") -> Dict[str, Any]:
        steps = []

        step1 = self.truck_agent.fetch_all_trucks()
        steps.append({
            "step": 1,
            "agent": self.truck_agent.name,
            "role": self.truck_agent.role,
            "database": "truck_db.sqlite",
            "summary": step1["log"],
            "items_processed": step1["truck_count"]
        })

        step2 = self.schedule_agent.fetch_schedule_state()
        steps.append({
            "step": 2,
            "agent": self.schedule_agent.name,
            "role": self.schedule_agent.role,
            "database": "schedule_db.sqlite",
            "summary": step2["log"],
            "items_processed": len(step2["schedule_records"])
        })

        step3 = self.eta_agent.analyze_etas(step1["trucks"])
        steps.append({
            "step": 3,
            "agent": self.eta_agent.name,
            "role": self.eta_agent.role,
            "database": "In-Memory Telemetry Correlation",
            "summary": step3["log"],
            "items_processed": step3["actionable_count"],
            "analyses": step3["analyses"]
        })

        step4 = self.slot_agent.compute_optimal_schedule(
            docks=step2["docks"],
            schedule_records=step2["schedule_records"],
            eta_analyses=step3["analyses"]
        )
        steps.append({
            "step": 4,
            "agent": self.slot_agent.name,
            "role": self.slot_agent.role,
            "database": "schedule_db.sqlite (Constraint Solver)",
            "summary": step4["log"],
            "items_processed": step4["proposal_count"],
            "proposals": step4["proposals"]
        })

        if auto_execute:
            step5 = self.exec_agent.execute_proposals(step4["proposals"])
        else:
            step5 = {
                "agent": self.exec_agent.name,
                "executed_count": 0,
                "communications": [],
                "log": f"[{self.exec_agent.name}] Preview mode: {step4['proposal_count']} proposals ready for execution."
            }

        steps.append({
            "step": 5,
            "agent": self.exec_agent.name,
            "role": self.exec_agent.role,
            "database": "schedule_db.sqlite + truck_db.sqlite",
            "summary": step5["log"],
            "items_processed": step5["executed_count"],
            "communications": step5["communications"]
        })

        run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_schedule_db_conn() as s_conn:
            s_cur = s_conn.cursor()
            s_cur.execute(
                "INSERT INTO agent_runs (run_id, timestamp, trigger_source, steps_json) VALUES (?, ?, ?, ?)",
                (run_id, now_str, trigger_source, json.dumps(steps))
            )
            s_conn.commit()

        return {
            "run_id": run_id,
            "timestamp": now_str,
            "trigger_source": trigger_source,
            "steps": steps,
            "proposals": step4["proposals"],
            "eta_analyses": step3["analyses"],
            "communications": step5["communications"],
        }
