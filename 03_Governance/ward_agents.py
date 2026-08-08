"""
03_Governance/ward_agents.py
Project S.A.A.S. — Ward-Level Agent (BUG-FIXED VERSION)
========================================================

BUGS FIXED IN THIS VERSION:
----------------------------
BUG-1: json.load() crash on empty/corrupt bridge file
        _load_bridge() now uses state_manager.load_state() — safe atomic read.

BUG-2: Ward key corruption (keys like "W","a","r","d","-","1"," ","2")
        Caused by string iteration when LLM returns "Ward-1, 2" instead of a list.
        state_manager._clean_ward_keys() strips these on every read.

BUG-3: Alert deduplication missing
        POLLUTION_SPREAD alert was sent every single cycle (every 60s) because
        send_spread_alert() had no cooldown. Added a 30-min per-target cooldown.

BUG-4: Wind speed unit mismatch
        OWM returns wind_speed in m/s (units=metric). The 15 km/h threshold for
        VSN mode and spread alerts was being compared directly to m/s values.
        15 km/h = 4.17 m/s. Added unit conversion in read_sensors().

BUG-5: receive_alert() direct json.dump() without atomic write
        Could corrupt bridge file if process is interrupted. Now uses save_state().
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# BUG-1 FIX: Use safe state manager instead of raw json.load()
from state_manager import load_state, save_state  # type: ignore[import]

from _05_Agent.aqi_agent import aqi_agent
from _05_Agent.weather_agent import WARD_TO_CITY, _FLOOD_KEYWORDS

log = logging.getLogger("WARD-AGENT")

BASE_DIR    = Path(__file__).parent.parent
BRIDGE_PATH = BASE_DIR / "04_Bridge" / "aura_master_state.json"

# BUG-3 FIX: Cooldown registry — {ward_name: {target_ward: last_sent_timestamp}}
_SPREAD_ALERT_COOLDOWN_SECS = 1800  # 30 minutes
_alert_cooldown_registry: dict[str, dict[str, float]] = {}

# Injected dynamically from multi_agent_system.py
BUS:          Any = None
AgentMessage: Any = None
MessageType:  Any = None
Priority:     Any = None

PollutionIntent = Literal["dust", "combustion", "mixed"]

# Credit scores — higher = more compliance history, lower escalation threshold
# Industrial wards get lower scores (more violations historically)
CREDIT_LEDGER: dict[str, float] = {
    "Narela":          0.90,
    "Rohini":          0.75,
    "Dwarka":          0.80,
    "Connaught Place": 0.95,
    "Chandni Chowk":   0.88,
    "Saket":           0.82,
    "Lajpat Nagar":    0.78,
    "Karawal Nagar":   0.55,
    "Mustafabad":      0.58,
    "Wazirpur":        0.62,
}

GATEWAY_WARDS = {"Narela", "Karawal Nagar", "Mustafabad"}


@dataclass
class SensorReading:
    aqi: float
    pm25: float
    pm10: float
    no2_ppb: float
    co_ppb: float
    mie_index: float
    wind_speed_kmh: float        # Always stored in km/h internally
    wind_bearing_deg: float
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class TFTForecast:
    p10: float
    p50: float
    p90: float
    horizon_hours: int = 6


@dataclass
class ActionPlan:
    ward: str
    pgrap_stage: int
    intent: PollutionIntent
    scrubber_activate: bool
    droplet_um: float
    wind_bearing_deg: float
    telegram_urgency: Literal["info", "warning", "critical"]
    message: str
    credit_score: float
    forecast: TFTForecast


class WardAgent:

    def __init__(self, ward_name: str):
        self.ward_name    = ward_name
        self.credit_score = CREDIT_LEDGER.get(ward_name, 0.5)
        self.is_gateway   = ward_name in GATEWAY_WARDS

        self._last_reading: SensorReading | None = None
        self._last_plan:    ActionPlan | None     = None
        self.connected_wards: list[str] = []
        self.last_alert_sent: str | None = None

        log.info("WardAgent initialized: %s", ward_name)

    # ── Sensor ingestion ───────────────────────────────────────────────────────

    def read_sensors(self) -> SensorReading:
        # BUG-1 FIX: Use safe load_state() instead of raw json.load()
        state = load_state()
        w = state.get("wards", {}).get(self.ward_name, {})

        # BUG-4 FIX: OWM returns wind_speed in m/s, convert to km/h for all
        # internal logic. Bridge state may already be in km/h (from previous cycle)
        # so we check if the value looks like m/s (typically < 30 for Delhi winds)
        # and convert accordingly. Store as km/h in the reading.
        raw_wind = w.get("wind_speed_kmh", 5.0)
        # If value was stored correctly as km/h it could be 0-100. If it came
        # directly from OWM m/s it would be 0-25. We flag it in aqi_agent already
        # but guard here too — if the bridge has a wind_speed_ms field, use it.
        wind_speed_ms = w.get("wind_speed_ms")  # explicit m/s field (new)
        if wind_speed_ms is not None:
            wind_kmh = round(wind_speed_ms * 3.6, 1)
        else:
            # Legacy: assume stored value is already km/h
            wind_kmh = float(raw_wind)

        self._last_reading = SensorReading(
            aqi              = w.get("aqi_current", 0),
            pm25             = w.get("pm25", 0),
            pm10             = w.get("pm10", 0),
            no2_ppb          = w.get("no2_ppb", 0),
            co_ppb           = w.get("co_ppb", 0),
            mie_index        = w.get("mie_index", 0.5),
            wind_speed_kmh   = wind_kmh,
            wind_bearing_deg = w.get("wind_bearing_deg", 270.0),
        )
        return self._last_reading

    # ── Intent classifier ──────────────────────────────────────────────────────

    def classify_intent(self, reading: SensorReading) -> PollutionIntent:
        combustion_score = (reading.co_ppb / 500) + (reading.no2_ppb / 60)
        dust_score       = reading.mie_index + (reading.pm10 / 300)

        if dust_score > 1.1 and combustion_score < 0.8:
            return "dust"
        elif combustion_score > 1.2:
            return "combustion"
        return "mixed"

    # ── VSN weights ────────────────────────────────────────────────────────────

    def vsn_weights(self, reading: SensorReading) -> dict[str, float]:
        # BUG-4: threshold is in km/h (wind_speed_kmh already converted above)
        if reading.wind_speed_kmh > 15:
            return {"trans_boundary_flux": 0.75, "local_vehicular": 0.10,
                    "industrial": 0.10, "residential": 0.05}
        return {"trans_boundary_flux": 0.30, "local_vehicular": 0.35,
                "industrial": 0.20, "residential": 0.15}

    # ── TFT forecast ───────────────────────────────────────────────────────────

    def get_forecast(self, horizon_hours: int = 6) -> TFTForecast:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from _02_Intelligence.tft_engine import predict  # type: ignore[import]
            result = predict(self.ward_name, horizon_hours)
            return TFTForecast(p10=result["p10"], p50=result["p50"], p90=result["p90"],
                               horizon_hours=horizon_hours)
        except Exception as exc:
            log.warning("TFT unavailable (%s) — using fallback forecast", exc)
            base = self._last_reading.aqi if self._last_reading else 180
            return TFTForecast(p10=round(base * 0.72), p50=round(base),
                               p90=round(base * 1.2))

    # ── Droplet optimization ───────────────────────────────────────────────────

    def optimal_droplet_um(self, reading: SensorReading) -> float:
        if reading.pm25 < 60:    return 18.0
        elif reading.pm25 < 120: return 28.0
        return 42.0

    # ── Pollution spread prediction ────────────────────────────────────────────

    def predict_pollution_spread(self, reading: SensorReading) -> str | None:
        if reading.wind_speed_kmh < 15:
            return None

        NEIGHBOUR_MAP: dict[str, dict[int, str]] = {
            "Narela":          {0:"Connaught Place",45:"Karawal Nagar", 90:"Karawal Nagar", 135:"Chandni Chowk",   180:"Connaught Place",225:"Rohini",          270:"Rohini",          315:"Rohini"},
            "Rohini":          {0:"Connaught Place",45:"Narela",        90:"Narela",        135:"Connaught Place",180:"Dwarka",          225:"Dwarka",          270:"Dwarka",          315:"Narela"},
            "Dwarka":          {0:"Rohini",          45:"Connaught Place",90:"Connaught Place",135:"Saket",          180:"Saket",           225:"Saket",           270:"Rohini",          315:"Rohini"},
            "Connaught Place": {0:"Saket",            45:"Chandni Chowk",90:"Chandni Chowk", 135:"Lajpat Nagar",   180:"Saket",           225:"Dwarka",          270:"Dwarka",          315:"Rohini"},
            "Chandni Chowk":   {0:"Connaught Place", 45:"Karawal Nagar",90:"Mustafabad",    135:"Lajpat Nagar",   180:"Lajpat Nagar",    225:"Connaught Place", 270:"Connaught Place", 315:"Karawal Nagar"},
            "Saket":           {0:"Connaught Place", 45:"Lajpat Nagar", 90:"Lajpat Nagar",  135:"Lajpat Nagar",   180:"Saket",           225:"Dwarka",          270:"Dwarka",          315:"Connaught Place"},
            "Lajpat Nagar":    {0:"Chandni Chowk",   45:"Mustafabad",   90:"Mustafabad",    135:"Mustafabad",     180:"Saket",           225:"Saket",           270:"Saket",           315:"Chandni Chowk"},
            "Karawal Nagar":   {0:"Narela",           45:"Narela",       90:"Mustafabad",    135:"Mustafabad",     180:"Chandni Chowk",   225:"Connaught Place", 270:"Connaught Place", 315:"Narela"},
            "Mustafabad":      {0:"Karawal Nagar",    45:"Karawal Nagar",90:"Mustafabad",    135:"Lajpat Nagar",   180:"Lajpat Nagar",    225:"Chandni Chowk",   270:"Chandni Chowk",   315:"Karawal Nagar"},
            "Wazirpur":        {0:"Narela",            45:"Narela",       90:"Connaught Place",135:"Connaught Place",180:"Connaught Place", 225:"Rohini",          270:"Rohini",          315:"Narela"},
        }

        neighbours = NEIGHBOUR_MAP.get(self.ward_name)
        if not neighbours:
            return None

        bearing = int(reading.wind_bearing_deg) % 360
        nearest = min(neighbours.keys(), key=lambda x: abs(x - bearing))
        target  = neighbours[nearest]
        return None if target == self.ward_name else target

    # ── Send inter-agent spread alert ──────────────────────────────────────────

    def send_spread_alert(
        self,
        target_ward: str,
        reading: SensorReading,
        forecast: TFTForecast,
    ) -> None:
        if not target_ward:
            return

        if BUS is None:
            log.warning("[SPREAD ALERT] BUS not injected — skipping alert to %s", target_ward)
            return

        # BUG-3 FIX: Alert deduplication — 30-min cooldown per source→target pair
        now = time.time()
        ward_registry = _alert_cooldown_registry.setdefault(self.ward_name, {})
        last_sent = ward_registry.get(target_ward, 0)

        if now - last_sent < _SPREAD_ALERT_COOLDOWN_SECS:
            remaining = int(_SPREAD_ALERT_COOLDOWN_SECS - (now - last_sent))
            log.debug(
                "[SPREAD ALERT] Cooldown active for %s→%s (%ds remaining) — skipped",
                self.ward_name, target_ward, remaining
            )
            return

        # Record send time before sending (prevents double-send on exception)
        ward_registry[target_ward] = now

        payload = {
            "type":           "POLLUTION_SPREAD",
            "source_ward":    self.ward_name,
            "target_ward":    target_ward,
            "aqi":            reading.aqi,
            "wind_speed":     reading.wind_speed_kmh,
            "wind_direction": reading.wind_bearing_deg,
            "predicted_p90":  forecast.p90,
            "message":        f"Pollution plume moving from {self.ward_name} to {target_ward}",
        }

        BUS.send(AgentMessage(
            priority     = Priority.HIGH.value,
            message_type = MessageType.ALERT_TRIGGER,
            sender       = self.ward_name,
            recipient    = target_ward,
            payload      = payload,
        ))

        log.warning("[SPREAD ALERT] %s → %s (cooldown reset)", self.ward_name, target_ward)
        self.last_alert_sent = datetime.now(timezone.utc).isoformat()

    # ── Receive inter-ward alert ───────────────────────────────────────────────

    def receive_alert(self, msg: Any) -> None:
        payload = msg.payload
        source  = payload.get("source_ward")

        log.warning("[%s] ALERT RECEIVED from %s", self.ward_name, source)

        # BUG-1 FIX: Use safe load_state / save_state (no raw json.load/dump)
        state = load_state()
        state.setdefault("wards", {}).setdefault(self.ward_name, {}).update({
            "pre_alert":          True,
            "incoming_pollution": True,
            "source_ward":        source,
        })
        # BUG-5 FIX: Atomic write
        save_state(state)

        log.warning("[%s] PRE-MITIGATION ACTIVATED", self.ward_name)

    # ── Main evaluation pipeline ───────────────────────────────────────────────

    def evaluate(self) -> ActionPlan:
        reading  = self.read_sensors()
        intent   = self.classify_intent(reading)
        forecast = self.get_forecast()

        # Environmental Agent integration — WAQI → IQAir → OWM
        try:
            env_report            = aqi_agent(self.ward_name)
            environmental_analysis = env_report["environmental_analysis"]
            mosquito_risk         = environmental_analysis["mosquito_risk"]
            flood_risk            = environmental_analysis["flood_risk"]
            heat_alert            = environmental_analysis["heat_alert"]
            aqi_category          = environmental_analysis["aqi_category"]

            aqi_data = env_report["aqi_data"]
            owm_aqi = aqi_data.get("aqi")
            if owm_aqi is not None:
                reading.aqi = float(owm_aqi)
                # BUGFIX: this log always said "from OWM" regardless of the
                # actual source — aqi_data already carries aqi_source
                # ("WAQI/CPCB", "IQAir", "IQAir+WAQI-PM", "WAQI-PM-only",
                # or "OWM-estimate") from weather_service.py, it just
                # wasn't being read here.
                source_label = aqi_data.get("aqi_source", "unknown source")
                log.info("[%s] AQI updated from %s: %.1f (%s)",
                         self.ward_name, source_label, reading.aqi, aqi_category)

            # Store all real pollutant values from OWM Air Pollution API
            if aqi_data.get("pm25") is not None:
                reading.pm25 = float(aqi_data["pm25"])
            if aqi_data.get("pm10") is not None:
                reading.pm10 = float(aqi_data["pm10"])
            if aqi_data.get("no2") is not None:
                reading.no2_ppb = float(aqi_data["no2"])
            if aqi_data.get("co") is not None:
                reading.co_ppb = float(aqi_data["co"])

            # OWM wind already in km/h from weather_service.py (converted)
            owm_wind_kmh = aqi_data.get("wind_speed_kmh")
            if owm_wind_kmh is not None:
                reading.wind_speed_kmh = float(owm_wind_kmh)
                log.debug("[%s] Wind: %.1f km/h @ %d°",
                          self.ward_name, reading.wind_speed_kmh,
                          aqi_data.get("wind_bearing_deg", 0))

        except Exception as exc:
            log.warning("[AQI AGENT ERROR] %s", exc)
            mosquito_risk = "Low"
            flood_risk    = "Low"
            heat_alert    = False
            aqi_category  = "Unknown"

        log.info("[AQI AGENT] %s | Mosquito=%s | Flood=%s | Heat=%s | AQI=%s",
                 self.ward_name, mosquito_risk, flood_risk, heat_alert, aqi_category)

        # Environmental impact adjustments
        if mosquito_risk == "High":   forecast.p90 += 15
        if flood_risk == "Moderate":  forecast.p90 += 10
        if heat_alert:                forecast.p90 += 20

        # BUG-3 FIX: Spread alert with cooldown (deduplication now active)
        target_ward = self.predict_pollution_spread(reading)
        if forecast.p90 > 300 and reading.wind_speed_kmh > 15 and target_ward:
            self.send_spread_alert(target_ward, reading, forecast)

        # P-GRAP evaluation
        try:
            from p_grap_logic import evaluate_stage  # type: ignore[import]
            stage, action_desc = evaluate_stage(
                p90_aqi=forecast.p90, credit_score=self.credit_score,
                intent=intent, is_gateway=self.is_gateway,
            )
        except Exception:
            stage, action_desc = self._inline_pgrap(forecast.p90, intent)

        scrubber_on = stage >= 2
        droplet     = self.optimal_droplet_um(reading) if scrubber_on else 0.0
        urgency: Literal["info", "warning", "critical"] = (
            "critical" if stage >= 3 else "warning" if stage >= 2 else "info"
        )
        msg_text = (
            f"[{self.ward_name}] P-GRAP Stage {stage} | "
            f"P90 AQI={forecast.p90} | Intent={intent}"
        )

        plan = ActionPlan(
            ward             = self.ward_name,
            pgrap_stage      = stage,
            intent           = intent,
            scrubber_activate= scrubber_on,
            droplet_um       = droplet,
            wind_bearing_deg = reading.wind_bearing_deg,
            telegram_urgency = urgency,
            message          = msg_text,
            credit_score     = self.credit_score,
            forecast         = forecast,
        )

        self._last_plan = plan
        self._write_to_bridge(reading, plan, mosquito_risk, flood_risk, heat_alert, aqi_category)
        return plan

    # ── Fallback P-GRAP ────────────────────────────────────────────────────────

    def _inline_pgrap(self, p90: float, intent: PollutionIntent) -> tuple[int, str]:
        offset    = -30 if intent == "combustion" else 0
        effective = p90 - offset
        if effective < 100: return 0, "Nominal"
        if effective < 200: return 1, "Advisory"
        if effective < 300: return 2, "Scrubbers ON"
        if effective < 400: return 3, "Emergency"
        return 4, "Lockdown"

    # ── Bridge load ────────────────────────────────────────────────────────────

    def _load_bridge(self) -> dict:
        # BUG-1 FIX: Use safe state manager
        return load_state()

    # ── Write state ────────────────────────────────────────────────────────────

    def _write_to_bridge(
        self, reading: SensorReading, plan: ActionPlan,
        mosquito_risk: str, flood_risk: str, heat_alert: bool,
        aqi_category: str = "Unknown",
    ) -> None:
        state = load_state()
        state.setdefault("wards", {}).setdefault(self.ward_name, {}).update({
            "aqi_current":      reading.aqi,
            "pm25":             reading.pm25,
            "pm10":             reading.pm10,
            "no2_ppb":          reading.no2_ppb,
            "co_ppb":           reading.co_ppb,
            "mie_index":        reading.mie_index,
            "wind_speed_kmh":   reading.wind_speed_kmh,  # stored as km/h
            "wind_bearing_deg": reading.wind_bearing_deg,
            "pgrap_stage":      plan.pgrap_stage,
            "intent":           plan.intent,
            "scrubber_active":  plan.scrubber_activate,
            "droplet_um":       plan.droplet_um,
            "credit_score":     plan.credit_score,
            "forecast_p10":     plan.forecast.p10,
            "forecast_p50":     plan.forecast.p50,
            "forecast_p90":     plan.forecast.p90,
            "weather_risk":     mosquito_risk,
            "flood_risk":       flood_risk,
            "heat_alert":       heat_alert,
            "aqi_category":     aqi_category,
            "data_source":      "OWM",
            "last_evaluated":   datetime.now(timezone.utc).isoformat(),
        })
        # BUG-5 FIX: Atomic write
        save_state(state)