import os
from backend.database import init_and_seed_databases, SCHEDULE_DB_PATH, TRUCK_DB_PATH
from backend.agents import (
    TruckDataAgent,
    ScheduleDataAgent,
    ETAFinderAgent,
    SlotCheckingAgent,
    ExecutionCommAgent,
    MultiAgentOrchestrator,
)


def run_verification():
    print("=== 1. Initializing & Seeding Dual SQLite Databases ===")
    init_and_seed_databases(reset=True)
    assert os.path.exists(SCHEDULE_DB_PATH), "schedule_db.sqlite missing!"
    assert os.path.exists(TRUCK_DB_PATH), "truck_db.sqlite missing!"
    print(f" -> Created Schedule DB: {SCHEDULE_DB_PATH}")
    print(f" -> Created Truck DB:    {TRUCK_DB_PATH}")

    orchestrator = MultiAgentOrchestrator()

    print("\n=== 2. Running 5-Agent Preview (Before Execution) ===")
    preview = orchestrator.run_pipeline(auto_execute=False, trigger_source="TEST_SUITE_PREVIEW")
    for s in preview["steps"]:
        print(f" [Step {s['step']} - {s['agent']}] {s['summary']}")

    print("\n=== 3. Checking Proposed Slot Swaps, Dock Swaps & New Bookings ===")
    proposals = preview["proposals"]
    assert len(proposals) > 0, "Expected optimization proposals for synthetic ETA deviations!"
    for p in proposals:
        print(f" * [{p['action_type']}] {p['reason']}")

    print("\n=== 4. Executing Proposals & Communicating with Scheduler ===")
    executed = orchestrator.run_pipeline(auto_execute=True, trigger_source="TEST_SUITE_EXECUTION")
    assert len(executed["communications"]) == len(proposals)
    for c in executed["communications"]:
        print(f" -> Dispatched {c['comm_id']}: {c['summary']}")

    print("\n=== 5. Testing Dynamic UI ETA Modification on TRK-104 ===")
    orchestrator.truck_agent.update_truck_eta("TRK-104", "12:15", notes="Simulated highway delay to 12:15")
    after_mod = orchestrator.run_pipeline(auto_execute=True, trigger_source="TEST_ETA_MOD")
    for c in after_mod["communications"]:
        print(f" -> Post-Modification Dispatch: {c['summary']}")

    # Reset back to rich default synthetic dataset so UI starts with interactive pending swaps ready to inspect/execute
    init_and_seed_databases(reset=True)
    print("\nALL MULTI-AGENT TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_verification()
