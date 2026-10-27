import os
import json
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.database import (
    init_and_seed_databases,
    get_schedule_db_conn,
    get_truck_db_conn,
    SCHEDULE_DB_PATH,
    TRUCK_DB_PATH,
)
from backend.connectors import (
    load_connections_config,
    save_connections_config,
    test_single_connection,
    update_and_save_connection,
    DEFAULT_CONNECTIONS,
    EXTERNAL_TRUCK_DB_PATH,
    EXTERNAL_SCHEDULE_DB_PATH,
)
from backend.agents import (
    TruckDataAgent,
    ScheduleDataAgent,
    ETAFinderAgent,
    SlotCheckingAgent,
    ExecutionCommAgent,
    MultiAgentOrchestrator,
)

app = FastAPI(title="Multi-Agent ETA Dock & Slot Scheduling System")


@app.middleware("http")
async def disable_static_cache(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Ensure databases are initialized on startup
init_and_seed_databases(reset=False)

orchestrator = MultiAgentOrchestrator()


class ModifyETARequest(BaseModel):
    truck_id: str
    new_eta: str
    distance_km: Optional[float] = None
    traffic_delay_mins: Optional[int] = None
    notes: Optional[str] = None
    auto_execute: bool = False


class AddTruckRequest(BaseModel):
    truck_id: str
    carrier_name: str
    driver_name: str
    cargo_type: str
    weight_tons: float = 18.0
    duration_mins: int = 45
    current_eta: str
    distance_km: float = 45.0
    notes: Optional[str] = None
    auto_execute: bool = False


class RunPipelineRequest(BaseModel):
    auto_execute: bool = True
    trigger_source: str = "UI_ORCHESTRATOR_BUTTON"


class PresetScenarioRequest(BaseModel):
    scenario_id: str


class ProposalDecisionRequest(BaseModel):
    truck_id: str


@app.get("/api/state")
def get_system_state():
    """
    Fetches live state from both databases (truck_db.sqlite and schedule_db.sqlite)
    and runs Agents 1-4 in non-mutating preview mode so the UI can display:
    - Existing Schedule vs. Proposed/New Schedule based on ETA
    - Pending Slot Swaps, Dock Swaps, and New Appointment Bookings
    - Full Truck DB & Schedule DB records
    """
    truck_res = orchestrator.truck_agent.fetch_all_trucks()
    sched_res = orchestrator.schedule_agent.fetch_schedule_state()
    eta_res = orchestrator.eta_agent.analyze_etas(truck_res["trucks"])
    slot_res = orchestrator.slot_agent.compute_optimal_schedule(
        docks=sched_res["docks"],
        schedule_records=sched_res["schedule_records"],
        eta_analyses=eta_res["analyses"]
    )

    with get_schedule_db_conn() as s_conn:
        cur = s_conn.cursor()
        cur.execute("SELECT * FROM agent_runs ORDER BY timestamp DESC LIMIT 10")
        recent_runs = []
        for r in cur.fetchall():
            d = dict(r)
            d["steps"] = json.loads(d["steps_json"])
            recent_runs.append(d)

    return {
        "databases": {
            "truck_db_path": TRUCK_DB_PATH,
            "schedule_db_path": SCHEDULE_DB_PATH,
            "external_truck_db_path": EXTERNAL_TRUCK_DB_PATH,
            "external_schedule_db_path": EXTERNAL_SCHEDULE_DB_PATH,
        },
        "connections": load_connections_config(),
        "trucks": truck_res["trucks"],
        "docks": sched_res["docks"],
        "existing_schedule": sched_res["schedule_records"],
        "simulated_new_schedule": slot_res["simulated_grid"],
        "eta_analyses": eta_res["analyses"],
        "pending_proposals": slot_res["proposals"],
        "communications": sched_res["communications"],
        "recent_runs": recent_runs,
        "agent_preview_logs": [
            {"agent": "TruckDataAgent", "db": truck_res.get("database", "truck_db.sqlite"), "message": truck_res["log"]},
            {"agent": "ScheduleDataAgent", "db": sched_res.get("database", "schedule_db.sqlite"), "message": sched_res["log"]},
            {"agent": "ETAFinderAgent", "db": eta_res.get("connector_type", "Telemetry Engine"), "message": eta_res["log"]},
            {"agent": "SlotCheckingAgent", "db": "Constraint Solver", "message": slot_res["log"]},
        ]
    }


@app.post("/api/modify-eta")
def modify_eta(req: ModifyETARequest):
    try:
        update_res = orchestrator.truck_agent.update_truck_eta(
            truck_id=req.truck_id,
            new_eta=req.new_eta,
            distance_km=req.distance_km,
            traffic_delay_mins=req.traffic_delay_mins,
            notes=req.notes
        )
        pipeline_res = None
        if req.auto_execute:
            pipeline_res = orchestrator.run_pipeline(
                auto_execute=True,
                trigger_source=f"ETA_OVERRIDE_{req.truck_id}_TO_{req.new_eta}"
            )
        return {
            "status": "ok",
            "update_result": update_res,
            "pipeline_result": pipeline_res,
            "state": get_system_state()
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/add-truck")
def add_unbooked_truck(req: AddTruckRequest):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dur = int(req.duration_mins) if int(req.duration_mins) in (30, 45, 60) else 45
    custom_note = req.notes or f"New {dur}m transport schedule booking request arriving at ETA {req.current_eta}; requires dock/slot assignment."
    with get_truck_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT truck_id FROM trucks WHERE truck_id = ?", (req.truck_id,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"Truck {req.truck_id} already exists.")
        cur.execute("""
            INSERT INTO trucks (
                truck_id, carrier_name, driver_name, driver_phone,
                cargo_type, weight_tons, priority_level, priority_score, duration_mins,
                original_dock_id, original_slot_start, original_slot_end,
                scheduled_dock_id, scheduled_slot_start, scheduled_slot_end,
                original_eta, current_eta, distance_km, avg_speed_kmh, traffic_delay_mins,
                telemetry_source, eta_status, notes, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, 'HIGH', 85, ?, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, 72.0, 0, 'TRANSPORT_PORTAL_BOOKING', 'UNBOOKED', ?, ?)
        """, (
            req.truck_id,
            req.carrier_name,
            req.driver_name,
            "+1-555-0199",
            req.cargo_type,
            req.weight_tons,
            dur,
            req.current_eta,
            req.current_eta,
            req.distance_km,
            custom_note,
            now_str
        ))
        conn.commit()

    pipeline_res = None
    if req.auto_execute:
        pipeline_res = orchestrator.run_pipeline(
            auto_execute=True,
            trigger_source=f"TRANSPORT_BOOK_NEW_{req.truck_id}_ETA_{req.current_eta}"
        )
    return {
        "status": "ok",
        "pipeline_result": pipeline_res,
        "state": get_system_state()
    }


@app.post("/api/run-agents")
def run_multi_agent_pipeline(req: RunPipelineRequest):
    res = orchestrator.run_pipeline(
        auto_execute=req.auto_execute,
        trigger_source=req.trigger_source
    )
    return {
        "status": "ok",
        "pipeline_result": res,
        "state": get_system_state()
    }


@app.post("/api/approve-proposal")
def approve_proposal(req: ProposalDecisionRequest):
    try:
        res = orchestrator.approve_single_proposal(req.truck_id)
        return {
            "status": "ok",
            "decision_result": res,
            "state": get_system_state()
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/reject-proposal")
def reject_proposal(req: ProposalDecisionRequest):
    try:
        res = orchestrator.reject_single_proposal(req.truck_id)
        return {
            "status": "ok",
            "decision_result": res,
            "state": get_system_state()
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/preset-scenario")
def apply_preset_scenario(req: PresetScenarioRequest):
    """
    Resets to baseline and configures specific test scenarios to demonstrate:
    - Pairwise Slot Swaps
    - Dock Swaps & Relay Swaps
    - Booking New Appointments based on ETA
    """
    init_and_seed_databases(reset=True)

    if req.scenario_id == "SCENARIO_SLOT_SWAP":
        # Make only TRK-101 (delayed to 10:05) and TRK-103 (early at 08:05) out of sync for a clean Pairwise Slot Swap demo on DOCK-A
        with get_truck_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE trucks SET current_eta = scheduled_slot_start, eta_status = 'ON_TIME', traffic_delay_mins = 0 WHERE scheduled_slot_start IS NOT NULL")
            cur.execute("DELETE FROM trucks WHERE truck_id = 'TRK-108'")
            cur.execute("UPDATE trucks SET current_eta = '10:05', eta_status = 'DELAYED', traffic_delay_mins = 125, notes = 'Delayed 2h; swaps slot with early TRK-103 on DOCK-A' WHERE truck_id = 'TRK-101'")
            cur.execute("UPDATE trucks SET current_eta = '08:05', eta_status = 'EARLY', traffic_delay_mins = -115, notes = 'Arriving 2h early; swaps slot with delayed TRK-101 on DOCK-A' WHERE truck_id = 'TRK-103'")
            conn.commit()

    elif req.scenario_id == "SCENARIO_DOCK_SWAP":
        # Demonstrate Dock Swap between DOCK-A and DOCK-B when a truck's target hour on DOCK-A is occupied
        with get_truck_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE trucks SET current_eta = scheduled_slot_start, eta_status = 'ON_TIME', traffic_delay_mins = 0 WHERE scheduled_slot_start IS NOT NULL")
            cur.execute("DELETE FROM trucks WHERE truck_id = 'TRK-108'")
            # TRK-102 (DOCK-A 09:00) delayed to 11:05 -> DOCK-A 11:00 has TRK-104, so TRK-102 swaps dock to open DOCK-B [11:00-12:00]
            cur.execute("UPDATE trucks SET current_eta = '11:05', eta_status = 'DELAYED', traffic_delay_mins = 125, notes = 'Delayed to 11:05; DOCK-A [11:00] is occupied so agent swaps dock to open DOCK-B [11:00-12:00]' WHERE truck_id = 'TRK-102'")
            # TRK-104 (DOCK-A 11:00) delayed to 12:05 -> DOCK-A 12:00 has TRK-105, so TRK-104 swaps dock to open DOCK-B [12:00-13:00]
            cur.execute("UPDATE trucks SET current_eta = '12:05', eta_status = 'DELAYED', traffic_delay_mins = 65, notes = 'Delayed to 12:05; DOCK-A [12:00] is occupied so agent swaps dock to open DOCK-B [12:00-13:00]' WHERE truck_id = 'TRK-104'")
            conn.commit()

    elif req.scenario_id == "SCENARIO_FULL_MULTI_AGENT":
        # Default rich synthetic dataset with Slot Swap + Dock Swap + New Unbooked Truck
        pass

    return {
        "status": "ok",
        "scenario_id": req.scenario_id,
        "state": get_system_state()
    }


@app.post("/api/reset")
def reset_databases():
    init_and_seed_databases(reset=True)
    return {
        "status": "reset_complete",
        "state": get_system_state()
    }


class ConnectionConfigRequest(BaseModel):
    target_key: str  # truck_connection | schedule_connection | eta_connection
    connector_type: str
    connection_link: str
    db_table_or_endpoint: Optional[str] = ""
    auth_mode: Optional[str] = "NONE"
    api_key_or_token: Optional[str] = ""
    sync_mode: Optional[str] = "LIVE_QUERY"


class SyncConnectionRequest(BaseModel):
    target_key: str


@app.get("/api/connections")
def get_connections():
    return {
        "status": "ok",
        "connections": load_connections_config(),
    }


@app.post("/api/connections/test")
def test_connection_endpoint(req: ConnectionConfigRequest):
    res = test_single_connection(
        target_key=req.target_key,
        connector_type=req.connector_type,
        connection_link=req.connection_link,
        db_table_or_endpoint=req.db_table_or_endpoint or "",
        auth_mode=req.auth_mode or "NONE",
        api_key_or_token=req.api_key_or_token or "",
    )
    return {
        "status": "ok" if res["ok"] else "error",
        "test_result": res,
    }


@app.post("/api/connections/save")
def save_connection_endpoint(req: ConnectionConfigRequest):
    try:
        res = update_and_save_connection(
            target_key=req.target_key,
            connector_type=req.connector_type,
            connection_link=req.connection_link,
            db_table_or_endpoint=req.db_table_or_endpoint or "",
            auth_mode=req.auth_mode or "NONE",
            api_key_or_token=req.api_key_or_token or "",
            sync_mode=req.sync_mode or "LIVE_QUERY",
        )
        return {
            "status": "ok",
            "connection": res["connection"],
            "test_result": res["test_result"],
            "state": get_system_state(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/connections/sync")
def sync_from_connection_link(req: SyncConnectionRequest):
    """
    Triggers the bound agent (TruckDataAgent, ScheduleDataAgent, or ETAFinderAgent)
    to actively pull/sync data via its configured connection link and logs an audit record.
    """
    cfg = load_connections_config()
    if req.target_key not in cfg:
        raise HTTPException(status_code=400, detail=f"Unknown connection key: {req.target_key}")

    conn_entry = cfg[req.target_key]
    agent_name = conn_entry["bound_agent"]
    c_type = conn_entry["connector_type"]
    c_link = conn_entry["connection_link"]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # If syncing ETA telematics feed via external link, apply live telematics updates to Truck DB
    synced_summary = ""
    if req.target_key == "eta_connection":
        with get_truck_db_conn() as t_conn:
            cur = t_conn.cursor()
            cur.execute(
                "UPDATE trucks SET telemetry_source = ?, last_updated = ?",
                (f"Live Link ({c_type})", now_str),
            )
            t_conn.commit()
            cur.execute("SELECT COUNT(*) FROM trucks")
            cnt = cur.fetchone()[0]
        synced_summary = f"[{agent_name}] Pulled live GPS/ETA telemetry for {cnt} trucks via {c_type} link ({c_link})."
    elif req.target_key == "truck_connection":
        t_res = orchestrator.truck_agent.fetch_all_trucks()
        cnt = t_res["truck_count"]
        synced_summary = f"[{agent_name}] Fetched {cnt} truck & carrier records via {c_type} link ({c_link})."
    else:
        s_res = orchestrator.schedule_agent.fetch_schedule_state()
        cnt = len(s_res["schedule_records"])
        synced_summary = f"[{agent_name}] Fetched {len(s_res['docks'])} docks & {cnt} schedule slots via {c_type} link ({c_link})."

    conn_entry["last_tested"] = now_str
    conn_entry["status"] = "CONNECTED"
    conn_entry["last_message"] = synced_summary
    save_connections_config(cfg)

    return {
        "status": "ok",
        "sync_summary": synced_summary,
        "connection": conn_entry,
        "state": get_system_state(),
    }


@app.post("/api/connections/reset-defaults")
def reset_connections_to_defaults():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cfg = json.loads(json.dumps(DEFAULT_CONNECTIONS))
    for k in cfg:
        cfg[k]["last_tested"] = now_str
    save_connections_config(cfg)
    return {
        "status": "ok",
        "connections": cfg,
        "state": get_system_state(),
    }


# ---------------------------------------------------------------------------
# Built-in Mock External System Endpoints (for testing external REST API links)
# ---------------------------------------------------------------------------
@app.get("/api/external-mock/tms-trucks")
def external_mock_tms_trucks():
    """Simulates an external SAP/Oracle TMS REST API endpoint returning truck fleet records."""
    res = orchestrator.truck_agent.fetch_all_trucks()
    return {
        "system": "External Enterprise TMS API v2",
        "endpoint": "/api/external-mock/tms-trucks",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trucks": res["trucks"],
    }


@app.get("/api/external-mock/wms-schedule")
def external_mock_wms_schedule():
    """Simulates an external Warehouse Management System (WMS) REST API returning dock schedules."""
    res = orchestrator.schedule_agent.fetch_schedule_state()
    return {
        "system": "External Warehouse Management System (WMS) API v2",
        "endpoint": "/api/external-mock/wms-schedule",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "docks": res["docks"],
        "schedule_records": res["schedule_records"],
    }


@app.get("/api/external-mock/telematics-eta")
def external_mock_telematics_eta():
    """Simulates an external Live GPS Telematics Stream (Samsara / Motive / BlueYonder) returning live ETAs."""
    res = orchestrator.truck_agent.fetch_all_trucks()
    eta_feed = [
        {
            "truck_id": t["truck_id"],
            "carrier_name": t["carrier_name"],
            "live_eta": t["current_eta"],
            "distance_km": t["distance_km"],
            "avg_speed_kmh": t["avg_speed_kmh"],
            "traffic_delay_mins": t["traffic_delay_mins"],
            "provider": t["telemetry_source"],
            "status": t["eta_status"],
        }
        for t in res["trucks"]
    ]
    return {
        "system": "Unified Telematics & GPS ETA Hub",
        "endpoint": "/api/external-mock/telematics-eta",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "eta_feed": eta_feed,
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/transport")
def serve_transport_portal():
    """Dedicated URL route for the standalone Transport / Carrier Manual ETA & Schedule Booking Portal."""
    return FileResponse(os.path.join(STATIC_DIR, "transport.html"))
