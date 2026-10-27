import os
import json
import sqlite3
from datetime import datetime
from backend.utils import add_minutes_to_time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

SCHEDULE_DB_PATH = os.path.join(DATA_DIR, "schedule_db.sqlite")
TRUCK_DB_PATH = os.path.join(DATA_DIR, "truck_db.sqlite")
CONNECTIONS_CONFIG_PATH = os.path.join(DATA_DIR, "connections_config.json")


def get_active_sqlite_path(target_key: str, default_path: str) -> str:
    """
    Checks connections_config.json to see if the user pointed `truck_connection` or `schedule_connection`
    to an alternative SQLite DB path. Falls back to `default_path`.
    """
    try:
        if os.path.exists(CONNECTIONS_CONFIG_PATH):
            with open(CONNECTIONS_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            entry = cfg.get(target_key, {})
            if entry.get("connector_type") == "SQLITE_DB":
                link = (entry.get("connection_link") or "").strip()
                if link.startswith("sqlite:///"):
                    link = link[len("sqlite:///"):]
                elif link.startswith("sqlite://"):
                    link = link[len("sqlite://"):]
                if link:
                    if not os.path.isabs(link):
                        link = os.path.join(BASE_DIR, link)
                    norm_p = os.path.normpath(link)
                    if os.path.exists(norm_p):
                        return norm_p
    except Exception:
        pass
    return default_path


def get_schedule_db_conn() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    active_path = get_active_sqlite_path("schedule_connection", SCHEDULE_DB_PATH)
    conn = sqlite3.connect(active_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_truck_db_conn() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    active_path = get_active_sqlite_path("truck_connection", TRUCK_DB_PATH)
    conn = sqlite3.connect(active_path)
    conn.row_factory = sqlite3.Row
    return conn


def _needs_schema_upgrade(s_cur: sqlite3.Cursor, t_cur: sqlite3.Cursor) -> bool:
    """Checks if existing SQLite tables lack duration_mins or 24-hour (48 slot) schedule records."""
    try:
        s_cur.execute("PRAGMA table_info(schedule_records)")
        s_cols = {r[1] for r in s_cur.fetchall()}
        if "duration_mins" not in s_cols or "cargo_type" not in s_cols or "change_type" not in s_cols:
            return True

        t_cur.execute("PRAGMA table_info(trucks)")
        t_cols = {r[1] for r in t_cur.fetchall()}
        if "duration_mins" not in t_cols or "carrier_name" not in t_cols or "original_dock_id" not in t_cols:
            return True

        s_cur.execute("SELECT COUNT(*) FROM schedule_records")
        slot_count = s_cur.fetchone()[0]
        if slot_count < 48:
            return True

        return False
    except Exception:
        return True


def init_and_seed_databases(reset: bool = False) -> None:
    """
    Initializes TWO distinct SQLite databases:
    1. schedule_db.sqlite -> Warehouse docks (2 docks: DOCK-A & DOCK-B), 24-hour master dock schedule
       slots (00:00 - 24:00) supporting 30, 45, and 60 min appointment durations, & communication audit logs
    2. truck_db.sqlite    -> Carrier fleet, cargo priority, appointment duration (30/45/60m), & live GPS/ETA telemetry
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    with sqlite3.connect(SCHEDULE_DB_PATH) as s_conn, sqlite3.connect(TRUCK_DB_PATH) as t_conn:
        s_conn.row_factory = sqlite3.Row
        t_conn.row_factory = sqlite3.Row
        s_cur = s_conn.cursor()
        t_cur = t_conn.cursor()

        if not reset and _needs_schema_upgrade(s_cur, t_cur):
            reset = True

        if reset:
            s_cur.execute("DROP TABLE IF EXISTS docks")
            s_cur.execute("DROP TABLE IF EXISTS schedule_records")
            s_cur.execute("DROP TABLE IF EXISTS scheduler_communications")
            s_cur.execute("DROP TABLE IF EXISTS agent_runs")
            t_cur.execute("DROP TABLE IF EXISTS trucks")

        # ---------------------------------------------------------
        # 1. CREATE TABLES IN schedule_db.sqlite
        # ---------------------------------------------------------
        s_cur.execute("""
            CREATE TABLE IF NOT EXISTS docks (
                dock_id TEXT PRIMARY KEY,
                dock_name TEXT NOT NULL,
                supported_cargo TEXT NOT NULL,
                max_weight_tons REAL NOT NULL DEFAULT 25.0,
                equipment_notes TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ONLINE',
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)

        s_cur.execute("""
            CREATE TABLE IF NOT EXISTS schedule_records (
                slot_id TEXT PRIMARY KEY,
                dock_id TEXT NOT NULL,
                slot_start TEXT NOT NULL,
                slot_end TEXT NOT NULL,
                duration_mins INTEGER NOT NULL DEFAULT 60,
                assigned_truck_id TEXT,
                cargo_type TEXT,
                slot_status TEXT NOT NULL DEFAULT 'FREE',
                change_type TEXT NOT NULL DEFAULT 'NONE',
                allocation_note TEXT,
                updated_at TEXT NOT NULL
            )
        """)

        s_cur.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_communications (
                comm_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                recipient_role TEXT NOT NULL,
                recipient_name TEXT NOT NULL,
                action_type TEXT NOT NULL,
                truck_id TEXT,
                summary TEXT NOT NULL,
                details_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'DISPATCHED'
            )
        """)

        s_cur.execute("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                trigger_source TEXT NOT NULL,
                steps_json TEXT NOT NULL
            )
        """)

        # ---------------------------------------------------------
        # 2. CREATE TABLES IN truck_db.sqlite
        # ---------------------------------------------------------
        t_cur.execute("""
            CREATE TABLE IF NOT EXISTS trucks (
                truck_id TEXT PRIMARY KEY,
                carrier_name TEXT NOT NULL,
                driver_name TEXT NOT NULL,
                driver_phone TEXT NOT NULL,
                cargo_type TEXT NOT NULL,
                weight_tons REAL NOT NULL DEFAULT 18.0,
                priority_level TEXT NOT NULL DEFAULT 'HIGH',
                priority_score INTEGER NOT NULL DEFAULT 80,
                duration_mins INTEGER NOT NULL DEFAULT 45,
                original_dock_id TEXT,
                original_slot_start TEXT,
                original_slot_end TEXT,
                scheduled_dock_id TEXT,
                scheduled_slot_start TEXT,
                scheduled_slot_end TEXT,
                original_eta TEXT NOT NULL,
                current_eta TEXT NOT NULL,
                distance_km REAL NOT NULL DEFAULT 25.0,
                avg_speed_kmh REAL NOT NULL DEFAULT 70.0,
                traffic_delay_mins INTEGER NOT NULL DEFAULT 0,
                telemetry_source TEXT NOT NULL,
                eta_status TEXT NOT NULL,
                notes TEXT,
                last_updated TEXT NOT NULL
            )
        """)

        s_cur.execute("SELECT COUNT(*) as cnt FROM docks")
        if s_cur.fetchone()["cnt"] > 0 and not reset:
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ---------------------------------------------------------
        # SEED DOCKS (schedule_db.sqlite) - 2 Docks
        # ---------------------------------------------------------
        docks_seed = [
            (
                "DOCK-A",
                "Dock A (Cold Chain & Heavy Bay)",
                "REFRIGERATED,DRY_VAN,HAZMAT",
                26.0,
                "Cryo-seal + Hazmat containment + Heavy forklift",
                "ONLINE",
                1,
            ),
            (
                "DOCK-B",
                "Dock B (High-Velocity Multi-Cargo Bay)",
                "REFRIGERATED,DRY_VAN,HAZMAT",
                24.0,
                "High-speed conveyor + Dual pallet jack + Reefer plug",
                "ONLINE",
                1,
            ),
        ]
        s_cur.executemany(
            """
            INSERT INTO docks (
                dock_id, dock_name, supported_cargo, max_weight_tons, equipment_notes, status, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            docks_seed,
        )

        # ---------------------------------------------------------
        # SEED 24-HOUR SLOTS (00:00 to 24:00 across 2 docks = 48 slots)
        # Sample test appointments with 30, 45, and 60 min durations:
        #   - TRK-101: DOCK-A 08:00-09:00 (60 min) -> Live ETA 10:10 (Delayed +130m, OVERLAPS TRK-103 10:00-10:30!)
        #   - TRK-102: DOCK-A 09:00-09:45 (45 min) -> Live ETA 11:05 (Delayed +125m, OVERLAPS TRK-104 11:00-11:45!)
        #   - TRK-103: DOCK-A 10:00-10:30 (30 min) -> Live ETA 08:05 (Early -115m, OVERLAPS TRK-101 08:00-09:00!)
        #   - TRK-104: DOCK-A 11:00-11:45 (45 min) -> Live ETA 12:10 (Delayed +70m, OVERLAPS TRK-105 12:00-13:00!)
        #   - TRK-105: DOCK-A 12:00-13:00 (60 min) -> Live ETA 12:05 (On Time, 60m)
        #   - TRK-106: DOCK-B 08:00-08:45 (45 min) -> Live ETA 08:05 (On Time, 45m)
        #   - TRK-107: DOCK-B 10:00-10:30 (30 min) -> Live ETA 10:05 (On Time, 30m)
        #   - TRK-108: Unbooked (30 min)           -> Live ETA 09:10 (New 30m Appointment -> DOCK-A 09:00-09:30)
        # ---------------------------------------------------------
        hours_24 = [(f"{h:02d}:00", f"{h + 1:02d}:00") for h in range(24)]

        initial_bookings = {
            ("DOCK-A", "08:00"): ("TRK-101", 60, "REFRIGERATED", "Booked 60m appointment (08:00-09:00)"),
            ("DOCK-A", "09:00"): ("TRK-102", 45, "DRY_VAN", "Booked 45m appointment (09:00-09:45)"),
            ("DOCK-A", "10:00"): ("TRK-103", 30, "REFRIGERATED", "Booked 30m appointment (10:00-10:30)"),
            ("DOCK-A", "11:00"): ("TRK-104", 45, "HAZMAT", "Booked 45m appointment (11:00-11:45)"),
            ("DOCK-A", "12:00"): ("TRK-105", 60, "DRY_VAN", "Booked 60m appointment (12:00-13:00)"),
            ("DOCK-B", "08:00"): ("TRK-106", 45, "DRY_VAN", "Booked 45m appointment (08:00-08:45)"),
            ("DOCK-B", "10:00"): ("TRK-107", 30, "HAZMAT", "Booked 30m appointment (10:00-10:30)"),
        }

        schedule_rows = []
        for dock_id, *_ in docks_seed:
            for start_h, base_end_h in hours_24:
                slot_id = f"{dock_id}_{start_h.replace(':', '')}"
                booking = initial_bookings.get((dock_id, start_h))
                if booking:
                    truck_id, dur_mins, cargo_t, note = booking
                    slot_status = "OCCUPIED"
                    actual_end = add_minutes_to_time(start_h, dur_mins)
                else:
                    truck_id, dur_mins, cargo_t, note = (None, 60, None, "Open 24h dock window")
                    slot_status = "FREE"
                    actual_end = base_end_h
                schedule_rows.append(
                    (
                        slot_id,
                        dock_id,
                        start_h,
                        actual_end,
                        dur_mins,
                        truck_id,
                        cargo_t,
                        slot_status,
                        "NONE",
                        note,
                        now_str,
                    )
                )

        s_cur.executemany(
            """
            INSERT INTO schedule_records (
                slot_id, dock_id, slot_start, slot_end, duration_mins,
                assigned_truck_id, cargo_type, slot_status, change_type, allocation_note, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            schedule_rows,
        )

        # ---------------------------------------------------------
        # SEED TRUCKS IN truck_db.sqlite (30m, 45m, 60m durations + Overlapping ETAs)
        # ---------------------------------------------------------
        trucks_seed = [
            # TRK-101: 60m appointment on DOCK-A [08:00-09:00], delayed to 10:10 -> OVERLAPS TRK-103 [10:00-10:30] on DOCK-A!
            (
                "TRK-101", "PolarCold Logistics", "Marcus Vance", "+1-555-0101",
                "REFRIGERATED", 19.5, "HIGH", 88, 60,
                "DOCK-A", "08:00", "09:00",
                "DOCK-A", "08:00", "09:00",
                "08:00", "10:10", 118.0, 62.0, 130, "Samsara-GPS-Live", "DELAYED",
                "60m cold-chain load. Highway closure (+130m); live ETA 10:10-11:10 overlaps TRK-103 on DOCK-A.", now_str
            ),
            # TRK-102: 45m appointment on DOCK-A [09:00-09:45], delayed to 11:05 -> OVERLAPS TRK-104 [11:00-11:45] on DOCK-A!
            (
                "TRK-102", "Apex National Freight", "Elena Rostova", "+1-555-0102",
                "DRY_VAN", 15.0, "MEDIUM", 65, 45,
                "DOCK-A", "09:00", "09:45",
                "DOCK-A", "09:00", "09:45",
                "09:00", "11:05", 94.0, 65.0, 125, "Motive-ELD-Stream", "DELAYED",
                "45m dry van unload. Delayed to 11:05-11:50; overlaps TRK-104 on DOCK-A -> swaps to DOCK-B.", now_str
            ),
            # TRK-103: 30m appointment on DOCK-A [10:00-10:30], arriving early at 08:05 -> OVERLAPS TRK-101 [08:00-09:00] on DOCK-A!
            (
                "TRK-103", "BioMed Express ColdChain", "Devon Brooks", "+1-555-0103",
                "REFRIGERATED", 12.0, "CRITICAL", 98, 30,
                "DOCK-A", "10:00", "10:30",
                "DOCK-A", "10:00", "10:30",
                "10:00", "08:05", 11.5, 78.0, -115, "Starlink-Fleet-GPS", "EARLY",
                "30m express biologic unload. Arriving early at 08:05-08:35; overlaps TRK-101 [08:00-09:00] -> swaps with TRK-101.", now_str
            ),
            # TRK-104: 45m appointment on DOCK-A [11:00-11:45], delayed to 13:05 -> moves to open 13:00-13:45 slot on DOCK-A
            (
                "TRK-104", "Titan Hazmat Carriers", "Hector Salamanca", "+1-555-0104",
                "HAZMAT", 21.0, "HIGH", 82, 45,
                "DOCK-A", "11:00", "11:45",
                "DOCK-A", "11:00", "11:45",
                "11:00", "13:05", 104.0, 64.0, 125, "Garmin-Fleet-Telemetry", "DELAYED",
                "45m Hazmat unload. Delayed to 13:05-13:50; shifts to open 13:00-13:45 slot on DOCK-A.", now_str
            ),
            # TRK-105: 60m appointment on DOCK-A [12:00-13:00], on time at 12:05
            (
                "TRK-105", "Metro Retail Cargo", "Sarah Jenkins", "+1-555-0105",
                "DRY_VAN", 17.5, "MEDIUM", 60, 60,
                "DOCK-A", "12:00", "13:00",
                "DOCK-A", "12:00", "13:00",
                "12:00", "12:05", 68.0, 72.0, 5, "Samsara-GPS-Live", "ON_TIME",
                "60m full trailer retail pallet unload; on schedule.", now_str
            ),
            # TRK-106: 45m appointment on DOCK-B [08:00-08:45], on time at 08:05
            (
                "TRK-106", "SwiftLine Distribution", "Liam O'Connor", "+1-555-0106",
                "DRY_VAN", 14.0, "MEDIUM", 58, 45,
                "DOCK-B", "08:00", "08:45",
                "DOCK-B", "08:00", "08:45",
                "08:00", "08:05", 8.5, 70.0, 5, "Motive-ELD-Stream", "ON_TIME",
                "45m cross-dock parcel unload; ready at yard gate.", now_str
            ),
            # TRK-107: 30m appointment on DOCK-B [10:00-10:30], on time at 10:05
            (
                "TRK-107", "Nova Hazmat Express", "Priya Patel", "+1-555-0107",
                "HAZMAT", 16.0, "HIGH", 84, 30,
                "DOCK-B", "10:00", "10:30",
                "DOCK-B", "10:00", "10:30",
                "10:00", "10:05", 39.0, 74.0, 5, "Samsara-GPS-Live", "ON_TIME",
                "30m fast drum offload on DOCK-B.", now_str
            ),
            # TRK-108: UNBOOKED 30m urgent arrival at 09:10 -> overlaps DOCK-A 09:00-09:45 before TRK-102 vacates it!
            (
                "TRK-108", "Vanguard Priority ColdChain", "Carlos Mendez", "+1-555-0108",
                "REFRIGERATED", 13.5, "CRITICAL", 95, 30,
                None, None, None,
                None, None, None,
                "09:10", "09:10", 29.0, 76.0, 0, "Starlink-Fleet-GPS", "UNBOOKED",
                "Unbooked 30m urgent cold-chain load arriving at 09:10; requests new dock appointment.", now_str
            ),
        ]

        t_cur.executemany(
            """
            INSERT INTO trucks (
                truck_id, carrier_name, driver_name, driver_phone,
                cargo_type, weight_tons, priority_level, priority_score, duration_mins,
                original_dock_id, original_slot_start, original_slot_end,
                scheduled_dock_id, scheduled_slot_start, scheduled_slot_end,
                original_eta, current_eta, distance_km, avg_speed_kmh, traffic_delay_mins,
                telemetry_source, eta_status, notes, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            trucks_seed,
        )

        s_conn.commit()
        t_conn.commit()

        # Keep external demo DBs in sync if reset was triggered
        if reset:
            ext_truck = os.path.join(DATA_DIR, "external_tms_trucks.sqlite")
            ext_sched = os.path.join(DATA_DIR, "external_wms_schedule.sqlite")
            for p in (ext_truck, ext_sched):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
