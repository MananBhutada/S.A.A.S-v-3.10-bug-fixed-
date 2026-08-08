"""
tests/test_smoke.py
Project S.A.A.S. — Smoke Tests
================================
Run before any deployment:
    python -m pytest tests/ -v
    # or standalone:
    python tests/test_smoke.py
"""
import sys, os, json
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)


def test_data_files_exist():
    assert os.path.exists(os.path.join(BASE,"data","delhi_aqi_clean.csv")), "Clean dataset missing"
    assert os.path.exists(os.path.join(BASE,"02_Intelligence","models","quantile_models.pkl")), "quantile_models.pkl missing"
    assert os.path.exists(os.path.join(BASE,"02_Intelligence","models","feature_cols.pkl")), "feature_cols.pkl missing"
    assert os.path.exists(os.path.join(BASE,"04_Bridge","aura_master_state.json")), "Bridge state missing"


def test_model_loads():
    import joblib
    models = joblib.load(os.path.join(BASE,"02_Intelligence","models","quantile_models.pkl"))
    assert set(models.keys()) == {"p10","p50","p90"}, "Expected p10/p50/p90 keys"
    assert hasattr(models["p50"], "predict"), "Model must have predict()"


def test_tft_engine_predict():
    from _02_Intelligence import tft_engine as eng
    # Inject fake ward state so predict() doesn't need bridge
    result = eng.predict("Narela", horizon_hours=6)
    assert "p10" in result and "p50" in result and "p90" in result
    assert result["p10"] <= result["p50"] <= result["p90"], "Quantile ordering violated"
    assert 0 <= result["p90"] <= 500, f"P90={result['p90']} out of range"


def test_pgrap_stages():
    sys.path.insert(0, os.path.join(BASE,"03_Governance"))
    from p_grap_logic import evaluate_stage
    # Combustion + gateway + high AQI must be Stage 3+
    stage, action = evaluate_stage(350, 0.91, "combustion", is_gateway=True)
    assert stage >= 3, f"Expected >=3, got {stage}"
    # Clean air should be Stage 0
    stage0, _ = evaluate_stage(80, 0.5, "dust", is_gateway=False)
    assert stage0 == 0, f"Expected 0, got {stage0}"
    # Lockdown threshold
    stage4, _ = evaluate_stage(420, 0.95, "combustion", is_gateway=True)
    assert stage4 == 4, f"Expected 4, got {stage4}"


def test_vsn_reweighting():
    from _02_Intelligence.tft_engine import vsn_weights
    hw = vsn_weights(20.0)   # high wind
    lw = vsn_weights(5.0)    # low wind
    assert hw["trans_boundary"] > lw["trans_boundary"], "High wind must elevate trans-boundary weight"
    assert hw["local_vehicular"] < lw["local_vehicular"], "High wind must lower vehicular weight"


def test_bridge_state_schema():
    with open(os.path.join(BASE,"04_Bridge","aura_master_state.json")) as f:
        state = json.load(f)
    assert "wards" in state, "Bridge missing 'wards' key"
    assert "Narela" in state["wards"], "Narela ward not in bridge"
    assert "city" in state, "Bridge missing 'city' key"


def test_message_bus_roundtrip():
    from _05_Agent.multi_agent_system import AgentMessageBus, AgentMessage, MessageType, Priority
    bus = AgentMessageBus()
    bus.register("sender"); bus.register("receiver")
    bus.send(AgentMessage(
        priority=Priority.HIGH.value,
        message_type=MessageType.DATA_SHARE,
        sender="sender", recipient="receiver",
        payload={"test_key": "test_val"},
    ))
    msg = bus.receive("receiver", timeout=1.0)
    assert msg is not None, "No message received"
    assert msg.payload["test_key"] == "test_val"
    assert msg.message_type == MessageType.DATA_SHARE


def test_stokes_validation():
    """FieldAgent must reject droplets outside 10-50μm."""
    from _05_Agent.aura_agent import dispatch_tool
    import json
    result = json.loads(dispatch_tool("trigger_scrubber", {
        "ward_name": "Narela", "action": "activate",
        "droplet_um": 120.0,   # too large — should fail
    }))
    assert "error" in result, "Expected error for oversized droplet"

    result_ok = json.loads(dispatch_tool("trigger_scrubber", {
        "ward_name": "Narela", "action": "activate",
        "droplet_um": 28.0,    # valid
    }))
    assert "status" in result_ok, "Expected success for valid droplet"


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    print(f"\nRunning {len(tests)} smoke tests...\n")
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓  {name}")
            passed += 1
        except Exception as e:
            print(f"  ✗  {name}:  {e}")
            failed += 1
    print(f"\n{passed} passed  {failed} failed")
    sys.exit(1 if failed else 0)
