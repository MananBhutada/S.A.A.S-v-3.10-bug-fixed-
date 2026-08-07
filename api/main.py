"""
api/main.py — FastAPI REST Backend for S.A.A.S.
================================================
Endpoints:
  GET  /                        — Welcome + API info
  GET  /health                  — System health check
  GET  /api/state               — Live bridge state (for dashboard)
  GET  /api/wards               — All wards with current readings
  GET  /api/wards/{ward_id}     — Single ward detail
  GET  /api/alerts              — Recent alerts (paginated)
  GET  /api/pgrap               — P-GRAP status all wards
  GET  /api/history/{ward_id}   — Historical readings from DB
  GET  /api/analytics/summary   — Aggregated analytics
  POST /api/refresh             — Trigger manual data refresh

Run: uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "04_Bridge"))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from state_manager import load_state
from monitoring.logger import get_logger

log = get_logger("API")

app = FastAPI(
    title="S.A.A.S. API",
    description="Smart Air Quality Agent System — Delhi Ward-Level AQI API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── helpers ───────────────────────────────────────────────────────────────────

def _load_json_safe(path: Path) -> list | dict:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []

def _aqi_category(aqi: float | None) -> str:
    if aqi is None: return "Unknown"
    if aqi <= 50:   return "Good"
    if aqi <= 100:  return "Satisfactory"
    if aqi <= 200:  return "Moderate"
    if aqi <= 300:  return "Poor"
    if aqi <= 400:  return "Very Poor"
    return "Severe"

def _stage_name(s: int) -> str:
    return ["Normal","Advisory","Action","Emergency","Lockdown"][s] if 0<=s<=4 else "?"

# ── root ──────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "project": "S.A.A.S. — Smart Air Quality Agent System",
        "version": "1.0.0",
        "city":    "NCT of Delhi",
        "docs":    "/docs",
        "health":  "/health",
        "endpoints": ["/api/state", "/api/wards", "/api/alerts", "/api/pgrap",
                      "/api/analytics/summary"],
    }

# ── health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    state      = load_state()
    wards      = state.get("wards", {})
    last_cycle = state.get("city", {}).get("last_full_cycle_utc")
    comms_path = BASE_DIR / "04_Bridge" / "agent_comms_log.json"
    audit_path = BASE_DIR / "04_Bridge" / "pgrap_audit_trail.json"

    # Check DB
    try:
        from db.session import check_db_health
        db_health = check_db_health()
    except Exception as e:
        db_health = {"status": "unavailable", "error": str(e)}

    # Data age
    age_secs = None
    if last_cycle:
        try:
            lc = datetime.fromisoformat(last_cycle.replace("Z", "+00:00"))
            age_secs = (datetime.now(timezone.utc) - lc).total_seconds()
        except Exception:
            pass

    triggered = [k for k, v in wards.items() if (v.get("pgrap_stage") or 0) >= 2]
    scrubbers  = [k for k, v in wards.items() if v.get("scrubber_active")]

    return {
        "status":              "healthy",
        "timestamp":           datetime.now(timezone.utc).isoformat(),
        "last_cycle_utc":      last_cycle,
        "data_age_seconds":    round(age_secs, 0) if age_secs else None,
        "wards_loaded":        len(wards),
        "pgrap_triggered":     triggered,
        "scrubbers_active":    scrubbers,
        "comms_messages":      len(_load_json_safe(comms_path)),
        "audit_events":        len(_load_json_safe(audit_path)),
        "database":            db_health,
        "api_keys": {
            "owm":  bool(os.getenv("OPENWEATHER_API_KEY")),
            "owm":   bool(os.getenv("OWM_API_KEY")),
            "groq":  bool(os.getenv("GROQ_API_KEY")),
        },
    }

# ── live state ────────────────────────────────────────────────────────────────
@app.get("/api/state")
def get_state():
    """Full bridge state — used by dashboard fetch()."""
    return load_state()

# ── wards ─────────────────────────────────────────────────────────────────────
@app.get("/api/wards")
def get_wards(triggered_only: bool = Query(False)):
    state = load_state()
    wards = state.get("wards", {})
    result = []
    for name, w in wards.items():
        aqi   = w.get("aqi_current")
        stage = w.get("pgrap_stage", 0)
        if triggered_only and stage < 2:
            continue
        result.append({
            "ward_id":           name,
            "aqi":               aqi,
            "aqi_category":      _aqi_category(aqi),
            "effective_aqi":     w.get("effective_aqi"),
            "pm25":              w.get("pm25"),
            "pm10":              w.get("pm10"),
            "no2":               w.get("no2_ppb"),
            "co":                w.get("co_ppb"),
            "wind_speed_kmh":    w.get("wind_speed_kmh"),
            "wind_bearing_deg":  w.get("wind_bearing_deg"),
            "pgrap_stage":       stage,
            "stage_name":        _stage_name(stage),
            "intent":            w.get("intent"),
            "vsn_mode":          w.get("vsn_mode"),
            "scrubber_active":   w.get("scrubber_active", False),
            "droplet_um":        w.get("droplet_um"),
            "credit_score":      w.get("credit_score"),
            "forecast_p10":      w.get("forecast_p10"),
            "forecast_p50":      w.get("forecast_p50"),
            "forecast_p90":      w.get("forecast_p90"),
            "pre_alert":         w.get("pre_alert", False),
            "source_ward":       w.get("source_ward"),
            "data_complete":     w.get("data_complete", False),
            "last_evaluated":    w.get("last_evaluated"),
        })
    result.sort(key=lambda x: (x.get("aqi") or 0), reverse=True)
    return {"count": len(result), "wards": result}

@app.get("/api/wards/{ward_id}")
def get_ward(ward_id: str):
    state = load_state()
    w = state.get("wards", {}).get(ward_id)
    if not w:
        raise HTTPException(404, f"Ward '{ward_id}' not found in bridge state")
    return {"ward_id": ward_id, **w}

# ── alerts ────────────────────────────────────────────────────────────────────
@app.get("/api/alerts")
def get_alerts(limit: int = Query(50, le=200), severity: Optional[str] = None):
    audit_path = BASE_DIR / "04_Bridge" / "pgrap_audit_trail.json"
    events = _load_json_safe(audit_path)
    if not isinstance(events, list):
        events = []
    # Sort newest first
    events = sorted(events, key=lambda e: e.get("timestamp",""), reverse=True)
    if severity:
        stage_map = {"critical":4,"warning":3,"info":1}
        min_stage = stage_map.get(severity, 0)
        events = [e for e in events if (e.get("stage") or 0) >= min_stage]
    return {
        "count":  len(events[:limit]),
        "total":  len(events),
        "alerts": events[:limit],
    }

# ── pgrap ─────────────────────────────────────────────────────────────────────
@app.get("/api/pgrap")
def get_pgrap():
    state  = load_state()
    wards  = state.get("wards", {})
    stages = {0:[], 1:[], 2:[], 3:[], 4:[]}
    for name, w in wards.items():
        s = w.get("pgrap_stage", 0)
        stages[s].append({
            "ward": name, "aqi": w.get("aqi_current"),
            "intent": w.get("intent"), "scrubber": w.get("scrubber_active"),
        })
    return {
        "summary": {s: len(v) for s, v in stages.items()},
        "by_stage": stages,
        "highest_stage": max((w.get("pgrap_stage",0) for w in wards.values()), default=0),
        "scrubbers_active": sum(1 for w in wards.values() if w.get("scrubber_active")),
    }

# ── analytics ─────────────────────────────────────────────────────────────────
@app.get("/api/analytics/summary")
def analytics_summary():
    state = load_state()
    wards = list(state.get("wards", {}).values())
    audit = _load_json_safe(BASE_DIR / "04_Bridge" / "pgrap_audit_trail.json")
    if not isinstance(audit, list): audit = []

    aqis  = [w.get("aqi_current") for w in wards if w.get("aqi_current")]
    p90s  = [w.get("forecast_p90") for w in wards if w.get("forecast_p90")]

    try:
        from db.session import check_db_health, get_session
        from db.models import WardReading, Alert
        from sqlalchemy import func
        db_ok = check_db_health()["status"] == "healthy"
        if db_ok:
            with get_session() as s:
                total_readings = s.query(func.count(WardReading.id)).scalar()
                total_alerts   = s.query(func.count(Alert.id)).scalar()
                avg_aqi_db     = s.query(func.avg(WardReading.aqi)).scalar()
        else:
            total_readings = total_alerts = avg_aqi_db = None
    except Exception:
        total_readings = total_alerts = avg_aqi_db = None

    return {
        "live": {
            "ward_count":      len(wards),
            "city_peak_aqi":   max(aqis) if aqis else None,
            "city_avg_aqi":    round(sum(aqis)/len(aqis),1) if aqis else None,
            "max_p90_forecast":max(p90s) if p90s else None,
            "pgrap_triggered": sum(1 for w in wards if (w.get("pgrap_stage",0))>=2),
            "scrubbers_active":sum(1 for w in wards if w.get("scrubber_active")),
            "audit_events":    len(audit),
        },
        "historical_db": {
            "total_readings": total_readings,
            "total_alerts":   total_alerts,
            "avg_aqi":        round(avg_aqi_db, 1) if avg_aqi_db else None,
        },
    }

# ── manual refresh ────────────────────────────────────────────────────────────
@app.post("/api/refresh")
def trigger_refresh():
    """Reload bridge state from disk (useful for testing)."""
    state = load_state()
    return {
        "status":    "refreshed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wards":     list(state.get("wards", {}).keys()),
    }
