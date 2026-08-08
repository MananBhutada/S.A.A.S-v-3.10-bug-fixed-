"""
03_Governance/orchestrator.py
Project S.A.A.S. — Autonomous Orchestrator (Multi-Agent Integrated)
=====================================================================
Runs three parallel systems:
  1. Rule-based heartbeat loop (fast, deterministic, every 60s)
  2. AURA single-agent (Claude tool-use, every 5 min, for complex reasoning)
  3. Multi-Agent System (Commander/Intel/Governance/Alert/Field, every 60s)

The flow is unchanged:
  TROPOMI Ingest → Met Sync → TFT Inference → Ward Agents → P-GRAP → IoT Dispatch

  Now each arrow is a logged inter-agent message with full audit trail.
"""

import json
import logging
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

log = logging.getLogger("ORCH")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
    datefmt="%H:%M:%S",
)

BASE_DIR    = Path(__file__).parent.parent
BRIDGE_PATH = BASE_DIR / "04_Bridge" / "aura_master_state.json"

import sys as _sys
_BRIDGE_MODULE_DIR = str(BASE_DIR / "04_Bridge")
if _BRIDGE_MODULE_DIR not in _sys.path:
    _sys.path.insert(0, _BRIDGE_MODULE_DIR)
from state_manager import load_state as _safe_load, save_state as _safe_save  # type: ignore[import]

_shutdown_event = threading.Event()


# ── Health-check server ───────────────────────────────────────────────────────

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        state = _load_state()
        body = json.dumps({
            "status":        "ok",
            "cycle":         state.get("city", {}).get("cycle_count", 0),
            "agents":        ["COMMANDER", "INTEL", "GOVERNANCE", "ALERT", "FIELD"],
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _start_health_server(port: int = 8765):
    srv = HTTPServer(("0.0.0.0", port), _HealthHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("Health endpoint → http://localhost:%d/", port)


# ── State helpers ─────────────────────────────────────────────────────────────

def _load_state() -> dict:
    # BUG-1 FIX: Safe atomic read — no crash on empty/corrupt file
    state = _safe_load()
    state.setdefault("city", {"cycle_count": 0})
    return state


def _save_state(state: dict):
    # BUG-5 FIX: Atomic write
    _safe_save(state)


# ── Open-Claw: parallel dispatch ──────────────────────────────────────────────

def open_claw_dispatch(ward_name: str, stage: int, aqi: int, state: dict):
    def _telegram():
        log.info("Telegram → Ward %s | Stage %d | AQI %d", ward_name, stage, aqi)

    def _dashboard():
        log.info("Dashboard synced — %d wards", len(state.get("wards", {})))

    def _iot():
        log.info("IoT dispatch → %s | activate scrubber", ward_name)

    with ThreadPoolExecutor(max_workers=3) as pool:
        pool.submit(_telegram)
        pool.submit(_dashboard)
        if stage >= 2:
            pool.submit(_iot)


# ── Ward tick (rule-based, always runs) ───────────────────────────────────────

GATEWAY_WARDS = ["Narela", "Alipur"]
INNER_WARDS   = ["Rohini", "Dwarka", "Karawal Nagar", "Mustafabad"]
CORE_WARDS    = ["Saket", "Lajpat Nagar", "Connaught Place", "Chandni Chowk"]
ALL_WARDS     = GATEWAY_WARDS + INNER_WARDS + CORE_WARDS


def _tick_ward(ward_name: str, state: dict):
    import random
    w = state["wards"].setdefault(ward_name, {})
    w["aqi_current"]      = round(random.uniform(80, 350))
    w["pm25"]             = round(random.uniform(20, 160))
    w["pm10"]             = round(random.uniform(40, 280))
    w["no2_ppb"]          = round(random.uniform(10, 110))
    w["co_ppb"]           = round(random.uniform(200, 1600))
    w["mie_index"]        = round(random.uniform(0.2, 0.9), 2)
    w["wind_speed_kmh"]   = round(random.uniform(2, 22), 1)
    w["wind_bearing_deg"] = round(random.uniform(0, 360))
    w["last_tick_utc"]    = datetime.now(timezone.utc).isoformat()
    aqi   = w["aqi_current"]
    stage = 0 if aqi < 100 else 1 if aqi < 200 else 2 if aqi < 300 else 3
    w["pgrap_stage"]     = stage
    w["scrubber_active"] = stage >= 2
    return stage, aqi


def _heartbeat_loop():
    cycle = 0
    log.info("Rule-based heartbeat started")
    while not _shutdown_event.is_set():
        cycle += 1
        state = _load_state()
        state.setdefault("city", {})
        state["city"]["cycle_count"]    = cycle
        state["city"]["last_cycle_utc"] = datetime.now(timezone.utc).isoformat()

        triggered = []
        for ward in ALL_WARDS:
            stage, aqi = _tick_ward(ward, state)
            if stage >= 2:
                triggered.append((ward, stage, aqi))

        for ward, stage, aqi in triggered:
            open_claw_dispatch(ward, stage, aqi, state)

        _save_state(state)
        log.info("Heartbeat #%d — %d wards ticked, %d P-GRAP triggered", cycle, len(ALL_WARDS), len(triggered))
        _shutdown_event.wait(60)


# ── Graceful shutdown ─────────────────────────────────────────────────────────

def _shutdown_handler(signum, frame):
    log.warning("Signal %s received — shutting down gracefully", signum)
    _shutdown_event.set()


signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT,  _shutdown_handler)


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def run_aura_autonomous_engine(
    mode:               str  = "production",
    p_grap:             bool = True,
    enable_ai_agent:    bool = True,
    enable_multi_agent: bool = True,
    health_port:        int  = 8765,
):
    """
    Launch the full AURA engine.

    Parameters
    ----------
    mode                : 'production' | 'dry_run'
    p_grap              : Enable P-GRAP trigger logic
    enable_ai_agent     : Start AURA single-agent daemon (Claude tool-use)
    enable_multi_agent  : Start 5-agent system (Commander/Intel/Governance/Alert/Field)
    health_port         : HTTP health-check port (0 to disable)
    """
    log.info("══ AURA Autonomous Engine ══  mode=%s  p_grap=%s  multi_agent=%s",
             mode, p_grap, enable_multi_agent)

    if health_port:
        _start_health_server(health_port)

    # 1. Rule-based heartbeat (always on)
    threading.Thread(target=_heartbeat_loop, name="heartbeat", daemon=True).start()

    # 2. Multi-Agent System
    mas = None
    if enable_multi_agent:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from _05_Agent.multi_agent_system import MultiAgentSystem
            mas = MultiAgentSystem()
            mas.start()

            def _mas_trigger():
                while not _shutdown_event.is_set():
                    _shutdown_event.wait(60)
                    if not _shutdown_event.is_set():
                        mas.trigger_cycle()

            threading.Thread(target=_mas_trigger, name="mas-trigger", daemon=True).start()
            log.info("Multi-agent system running — CommanderAgent leading 5 agents")
        except Exception as exc:
            log.warning("Multi-agent system could not start: %s", exc)

    # 3. AURA single-agent (deeper Claude reasoning, slower cadence)
    if enable_ai_agent:
        try:
            from _05_Agent.aura_agent import run_aura_agent
            run_aura_agent(mode="daemon")
            log.info("AURA AI Agent daemon started (5 min cadence)")
        except Exception as exc:
            log.warning("AURA agent could not start: %s", exc)

    log.info("All systems online — press Ctrl+C to stop")
    try:
        _shutdown_event.wait()
    except KeyboardInterrupt:
        _shutdown_event.set()

    if mas:
        mas.stop()
    log.info("AURA engine shutdown complete.")
    return mas


if __name__ == "__main__":
    run_aura_autonomous_engine()
