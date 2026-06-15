"""
smoke_context.py — end-to-end check for the living-context write-back layer.

Exercises the full path against the LIVE Supabase: add a client, move its pipeline
stage, record a fact, read everything back, then DELETE all the test data so nothing
is left behind. Run AFTER migration 004 has been applied.

    cd apps/boschai-backend
    python scripts/smoke_context.py

A clean run prints "ALL CHECKS PASSED" and removes its own test rows.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.client import supabase  # noqa: E402
from services import context_store as cs  # noqa: E402

TEST_CLIENT = "ZZ Smoke Test Co"      # leading ZZ keeps it out of the way + easy to spot
TEST_KEY = "zz_smoke_test_fact"


def _cleanup():
    """Remove anything this script may have created. Safe to call twice."""
    existing = cs._find_client_by_name(TEST_CLIENT)
    if existing:
        supabase.table("business_events").delete().eq("client_id", existing["id"]).execute()
        supabase.table("clients").delete().eq("id", existing["id"]).execute()
    supabase.table("connie_context").delete().eq("key", TEST_KEY).execute()
    # context_updated events have no client_id — clear the ones this run wrote
    supabase.table("business_events").delete().eq("summary", f"Context '{TEST_KEY}' updated").execute()


def main():
    _cleanup()  # start from a clean slate in case a previous run died mid-way
    try:
        # 1. add a client as a lead
        c = cs.upsert_client(TEST_CLIENT, stage="lead", industry="Testing",
                             notes="created by smoke_context.py", source="seed")
        assert c["name"] == TEST_CLIENT and c["pipeline_stage"] == "lead", c
        print(f"1. added client → stage '{c['pipeline_stage']}'  ✓")

        # 2. move it to anchor (the KPI stage)
        c = cs.set_client_stage(TEST_CLIENT, "anchor", source="seed")
        assert c["pipeline_stage"] == "anchor", c
        print("2. moved stage lead → anchor  ✓")

        # 3. update only the next_step, leave everything else intact
        c = cs.upsert_client(TEST_CLIENT, next_step="send proposal", source="seed")
        assert c["next_step"] == "send proposal" and c["pipeline_stage"] == "anchor", c
        print("3. partial update (next_step) preserved stage  ✓")

        # 4. record a freeform business fact
        f = cs.update_context_fact(TEST_KEY, "smoke test value", source="seed")
        assert f["key"] == TEST_KEY and f["value"] == "smoke test value", f
        print("4. context fact upserted  ✓")

        # 5. read-backs
        anchors = cs.list_clients(stage="anchor")
        assert any(x["name"] == TEST_CLIENT for x in anchors), anchors
        summary = cs.pipeline_summary()
        assert summary["anchor"] >= 1, summary
        events = cs.recent_events(limit=10)
        kinds = {e["event_type"] for e in events}
        assert {"client_added", "stage_changed"} <= kinds, kinds
        print(f"5. read-back: {summary['anchor']} anchor client(s), "
              f"{len(events)} recent events, kinds={sorted(kinds)}  ✓")

        print("\nALL CHECKS PASSED")
    finally:
        _cleanup()
        print("cleaned up test data ✓")


if __name__ == "__main__":
    main()
