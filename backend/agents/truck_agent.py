import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
from backend.database import get_truck_db_conn, get_active_sqlite_path, TRUCK_DB_PATH
from backend.utils import time_to_minutes
from backend.connectors import load_connections_config, fetch_json_from_url


class TruckDataAgent:
    """
    Agent 1: TruckDataAgent
    Connects to truck_db.sqlite (or configured external Truck DB / REST endpoint link)
    to retrieve and update carrier profiles, priority scores, appointment durations (30/45/60m),
    and live GPS/ETA telemetry.
    """
    name = "TruckDataAgent"
    role = "Fleet & Carrier Database Specialist (truck_db.sqlite)"

    def fetch_all_trucks(self) -> Dict[str, Any]:
        cfg = load_connections_config()
        t_conn_cfg = cfg.get("truck_connection", {})
        c_type = t_conn_cfg.get("connector_type", "SQLITE_DB")
        link = t_conn_cfg.get("connection_link", "")

        trucks: List[Dict[str, Any]] = []
        active_file = os.path.basename(get_active_sqlite_path("truck_connection", TRUCK_DB_PATH))
        source_label = active_file

        if c_type == "REST_API" and (link.startswith("http://") or link.startswith("https://")):
            try:
                payload = fetch_json_from_url(link, api_key=t_conn_cfg.get("api_key_or_token", ""))
                items = payload.get("trucks", payload if isinstance(payload, list) else [])
                if isinstance(items, list) and len(items) > 0:
                    trucks = items
                    source_label = f"REST API ({link})"
            except Exception:
                trucks = []

        if not trucks:
            with get_truck_db_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM trucks ORDER BY truck_id ASC")
                trucks = [dict(r) for r in cur.fetchall()]

        return {
            "agent": self.name,
            "role": self.role,
            "database": source_label,
            "connection_link": link or f"sqlite:///{TRUCK_DB_PATH}",
            "truck_count": len(trucks),
            "trucks": trucks,
            "log": f"[{self.name}] Retrieved {len(trucks)} active carrier records (30/45/60m durations) via {source_label}."
        }

    def update_truck_eta(
        self,
        truck_id: str,
        new_eta: str,
        distance_km: Optional[float] = None,
        traffic_delay_mins: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_truck_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM trucks WHERE truck_id = ?", (truck_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Truck {truck_id} not found in truck_db.sqlite")

            truck = dict(row)
            ref_start = truck.get("scheduled_slot_start") or truck.get("original_slot_start") or truck.get("original_eta")
            orig_mins = time_to_minutes(ref_start) or 480
            new_mins = time_to_minutes(new_eta) or 480
            calc_delay = traffic_delay_mins if traffic_delay_mins is not None else (new_mins - orig_mins)
            dist_val = distance_km if distance_km is not None else truck.get("distance_km", 25.0)

            if not truck.get("scheduled_dock_id") or truck.get("scheduled_dock_id") == "HOLD":
                status = "UNBOOKED"
            elif calc_delay >= 20:
                status = "DELAYED"
            elif calc_delay <= -20:
                status = "EARLY"
            else:
                status = "ON_TIME"

            updated_notes = (
                notes
                if notes is not None
                else f"Live telemetry update: ETA adjusted to {new_eta} ({calc_delay:+d}m vs booked slot)."
            )
            cur.execute("""
                UPDATE trucks
                SET current_eta = ?, distance_km = ?, traffic_delay_mins = ?, eta_status = ?, notes = ?, last_updated = ?
                WHERE truck_id = ?
            """, (new_eta, dist_val, calc_delay, status, updated_notes, now_str, truck_id))
            conn.commit()

            cur.execute("SELECT * FROM trucks WHERE truck_id = ?", (truck_id,))
            updated_truck = dict(cur.fetchone())

        return {
            "agent": self.name,
            "updated_truck": updated_truck,
            "log": f"[{self.name}] Updated {truck_id} in truck_db.sqlite -> Current ETA {new_eta} ({status}, {calc_delay:+d}m)."
        }
