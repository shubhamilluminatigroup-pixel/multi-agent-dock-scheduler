import os
from typing import Dict, Any
from backend.database import get_schedule_db_conn, get_active_sqlite_path, SCHEDULE_DB_PATH
from backend.connectors import load_connections_config


class ScheduleDataAgent:
    """
    Agent 2: Connects via the configured Schedule DB / WMS Connection Link
    (schedule_db.sqlite, external SQLite DB, or WMS REST API) to fetch active dock definitions,
    cargo compatibility rules, committed schedule slots, open slots, and communications.
    """
    name = "ScheduleDataAgent"
    role = "Master Dock & Slot Schedule DB Specialist"

    def fetch_schedule_state(self) -> Dict[str, Any]:
        cfg = load_connections_config().get("schedule_connection", {})
        c_type = cfg.get("connector_type", "SQLITE_DB")
        c_link = cfg.get("connection_link", f"sqlite:///{SCHEDULE_DB_PATH}")
        active_db_file = os.path.basename(get_active_sqlite_path("schedule_connection", SCHEDULE_DB_PATH))

        with get_schedule_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM docks WHERE is_active = 1 ORDER BY dock_id")
            docks = [dict(r) for r in cur.fetchall()]
            for d in docks:
                d["supported_cargo_list"] = [c.strip() for c in d["supported_cargo"].split(",") if c.strip()]

            cur.execute("SELECT * FROM schedule_records ORDER BY slot_start, dock_id")
            records = [dict(r) for r in cur.fetchall()]

            cur.execute("SELECT * FROM scheduler_communications ORDER BY timestamp DESC LIMIT 50")
            comms = [dict(r) for r in cur.fetchall()]

        open_slots = [r for r in records if r["assigned_truck_id"] is None]
        booked_slots = [r for r in records if r["assigned_truck_id"] is not None]

        return {
            "agent": self.name,
            "database": active_db_file,
            "connector_type": c_type,
            "connection_link": c_link,
            "docks": docks,
            "schedule_records": records,
            "communications": comms,
            "open_slot_count": len(open_slots),
            "booked_slot_count": len(booked_slots),
            "log": f"[{self.name}] Connected via {c_type} ({active_db_file}) -> {len(docks)} docks, {len(booked_slots)} booked, {len(open_slots)} open slots."
        }
