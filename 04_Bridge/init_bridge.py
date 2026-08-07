"""
04_Bridge/init_bridge.py
Project S.A.A.S. — Bridge Initialization
=========================================
Initializes the aura_master_state.json bridge with fresh ward data.
Also starts the bridge sync server for Colab ↔ local edge communication.

Usage:
    python 04_Bridge/init_bridge.py              # local init only
    python 04_Bridge/init_bridge.py --serve      # start sync server
    python 04_Bridge/init_bridge.py --reset      # wipe and re-initialize
"""

import json
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

log = logging.getLogger("BRIDGE-INIT")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

BASE_DIR    = Path(__file__).parent.parent
BRIDGE_PATH = BASE_DIR / "04_Bridge" / "aura_master_state.json"
CONFIG_PATH = BASE_DIR / "04_Bridge" / "config.json"

ALL_WARDS = {
    "Narela":          {"lat": "gateway", "credit_score": 0.91},
    "Alipur":          {"lat": "gateway", "credit_score": 0.78},
    "Rohini":          {"lat": "inner",   "credit_score": 0.65},
    "Dwarka":          {"lat": "inner",   "credit_score": 0.70},
    "Karawal Nagar":   {"lat": "inner",   "credit_score": 0.55},
    "Mustafabad":      {"lat": "inner",   "credit_score": 0.50},
    "Saket":           {"lat": "core",    "credit_score": 0.82},
    "Lajpat Nagar":    {"lat": "core",    "credit_score": 0.75},
    "Connaught Place": {"lat": "core",    "credit_score": 0.95},
    "Chandni Chowk":   {"lat": "core",    "credit_score": 0.88},
}

WARD_TEMPLATE = {
    "aqi_current": 0, "pm25": 0, "pm10": 0,
    "no2_ppb": 0, "co_ppb": 0, "mie_index": 0.5,
    "wind_speed_kmh": 5.0, "wind_bearing_deg": 270.0,
    "pgrap_stage": 0, "intent": "unknown",
    "scrubber_active": False, "droplet_um": 0,
    "forecast_p10": 0, "forecast_p50": 0, "forecast_p90": 0,
    "last_evaluated": None,
}


def initialize_state(reset: bool = False) -> dict:
    if BRIDGE_PATH.exists() and not reset:
        log.info("Bridge already exists at %s (use --reset to wipe)", BRIDGE_PATH)
        with open(BRIDGE_PATH) as f:
            return json.load(f)

    state = {
        "schema_version": "2.1",
        "initialized_utc": datetime.now(timezone.utc).isoformat(),
        "city": {
            "name": "Delhi",
            "total_wards": 272,
            "cycle_count": 0,
            "engine_status": "initialized",
            "pgrap_city_stage": 0,
        },
        "wards": {},
        "open_claw": {
            "telegram_last_sent": None,
            "dashboard_last_synced": None,
            "iot_last_dispatch": None,
        },
        "model_versions": {
            "tft": "darts-TFT-v1.3",
            "vision_dcp": "koschmieder-mie-v2.1",
            "pgrap_logic": "v3.0-credit-ledger",
            "multi_agent": "v1.0-commander-pattern",
        },
        "agent_log": [],
    }

    for ward_name, meta in ALL_WARDS.items():
        state["wards"][ward_name] = {**WARD_TEMPLATE, **meta}

    BRIDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BRIDGE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)

    log.info("Bridge initialized — %d wards seeded at %s", len(ALL_WARDS), BRIDGE_PATH)
    return state


class _BridgeSyncHandler(BaseHTTPRequestHandler):
    """Simple HTTP server for Colab ↔ edge sync."""

    def do_GET(self):
        if self.path == "/state":
            with open(BRIDGE_PATH) as f:
                body = f.read().encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/state":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                new_state = json.loads(body)
                with open(BRIDGE_PATH, "w") as f:
                    json.dump(new_state, f, indent=2, default=str)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            except Exception as exc:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


def start_sync_server(port: int = 5050):
    srv = HTTPServer(("0.0.0.0", port), _BridgeSyncHandler)
    log.info("Bridge sync server → http://0.0.0.0:%d/state", port)
    srv.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset",  action="store_true", help="Wipe and re-initialize state")
    parser.add_argument("--serve",  action="store_true", help="Start bridge sync server")
    parser.add_argument("--port",   type=int, default=5050)
    args = parser.parse_args()

    initialize_state(reset=args.reset)

    if args.serve:
        start_sync_server(port=args.port)
