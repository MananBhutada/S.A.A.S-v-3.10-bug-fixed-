"""
refresh_data.py — S.A.A.S. Data Refresh Script
===============================================
Fetches LIVE data from OpenWeatherMap for all 10 real-named Delhi wards
and updates aura_master_state.json.

FIXES in this version:
  - Clears ALL old ward keys (Ward-1, Ward-2, Alipur etc.) before writing
  - Correct P-GRAP thresholds (Stage 2 = AQI>200, not AQI>150)
  - Scrubber only activates at Stage 2+ (AQI>200), not Stage 0

Usage:
    python refresh_data.py          # fetch once
    python refresh_data.py --loop   # fetch every 5 minutes
"""
import sys, time, json, logging
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR    = Path(__file__).parent
BRIDGE_PATH = BASE_DIR / "04_Bridge" / "aura_master_state.json"
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "04_Bridge"))

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("REFRESH")

from services.weather_service import get_ward_environment, WARD_COORDS
from state_manager import load_state, save_state

# ── P-GRAP stage — CPCB official thresholds ──────────────────────────────────
# Stage 0: AQI   0–100  Good/Satisfactory — No action
# Stage 1: AQI 101–200  Moderate/Poor     — Public advisory
# Stage 2: AQI 201–300  Very Poor         — Scrubbers ON
# Stage 3: AQI 301–400  Severe            — Emergency measures
# Stage 4: AQI 401+     Severe+           — Lockdown
def pgrap_stage(aqi: float) -> int:
    if not aqi or aqi <= 100: return 0
    if aqi <= 200: return 1
    if aqi <= 300: return 2
    if aqi <= 400: return 3
    return 4

def aqi_category(aqi: float) -> str:
    if not aqi or aqi <= 50:  return "Good"
    if aqi <= 100: return "Satisfactory"
    if aqi <= 200: return "Moderate"
    if aqi <= 300: return "Poor"
    if aqi <= 400: return "Very Poor"
    return "Severe"

def classify_intent(pm25, pm10, no2, co) -> str:
    pm25 = pm25 or 0; pm10 = pm10 or 0; no2 = no2 or 0; co = co or 0
    if pm25 == 0: return "unknown"
    mie = pm10 / pm25 if pm25 > 0 else 1.5
    combustion = no2 + co / 1000
    if mie > 1.7 and combustion < 50:  return "dust"
    if combustion > 80:                return "combustion"
    return "mixed"

def optimal_droplet(pm25: float) -> float:
    if pm25 < 60:  return 18.0
    if pm25 < 120: return 28.0
    return 42.0


def fetch_all_wards():
    log.info("=" * 55)
    log.info("S.A.A.S. Refresh — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 55)

    # Load existing state
    state = load_state()

    # ── KEY FIX: wipe ALL old ward keys before writing ────────────────────────
    # This removes Ward-1, Ward-2, Alipur and any other stale entries
    state["wards"] = {}
    state.setdefault("city", {"name": "Delhi"})
    log.info("Cleared old ward state — writing fresh 10-ward data")

    success = 0
    failed  = 0

    for ward_name in WARD_COORDS:
        try:
            env   = get_ward_environment(ward_name)
            aqi   = env.get("aqi") or 0
            pm25  = env.get("pm25") or 0
            pm10  = env.get("pm10") or 0
            no2   = env.get("no2")  or 0
            co    = env.get("co")   or 0
            stage = pgrap_stage(aqi)
            # Scrubber ONLY when stage >= 2 (AQI > 200)
            scrubber = stage >= 2
            drop     = optimal_droplet(pm25) if scrubber else 0.0
            intent   = classify_intent(pm25, pm10, no2, co)
            credit   = WARD_COORDS[ward_name].get("gateway", False) and 0.75 or 0.85

            state["wards"][ward_name] = {
                # ── Real OWM values ─────────────────────────────────────────
                "aqi_current":      aqi,
                "aqi_category":     aqi_category(aqi),
                "pm25":             round(pm25, 2),
                "pm10":             round(pm10, 2),
                "no2_ppb":          round(no2, 2),
                "co_ppb":           round(co, 2),
                "o3":               round(env.get("o3") or 0, 2),
                "so2":              round(env.get("so2") or 0, 2),
                "owm_aqi_index":    env.get("owm_aqi_index"),
                # ── Real OWM weather ────────────────────────────────────────
                "temperature":      env.get("temperature"),
                "humidity":         env.get("humidity"),
                "wind_speed_kmh":   env.get("wind_speed_kmh"),
                "wind_speed_ms":    env.get("wind_speed_ms"),
                "wind_bearing_deg": env.get("wind_bearing_deg"),
                "visibility_m":     env.get("visibility_m"),
                "rain_1h_mm":       env.get("rain_1h_mm"),
                "description":      env.get("description"),
                "pressure_hpa":     env.get("pressure_hpa"),
                "mie_index":        env.get("mie_index"),
                "heat_alert":       env.get("heat_alert"),
                "flood_risk":       env.get("flood_risk"),
                "mosquito_risk":    env.get("mosquito_risk"),
                # ── Agent decisions (calculated) ────────────────────────────
                "pgrap_stage":      stage,
                "intent":           intent,
                "scrubber_active":  scrubber,
                "droplet_um":       drop,
                "credit_score":     credit,
                # ── Forecast (fallback formula — P90 = AQI × 1.2) ──────────
                # NOTE: This is a formula estimate, NOT a real TFT forecast
                "forecast_p10":     round(aqi * 0.72),
                "forecast_p50":     round(aqi * 1.0),
                "forecast_p90":     round(aqi * 1.20),
                # ── Metadata ────────────────────────────────────────────────
                "source":           "OWM",
                "lat":              env.get("lat"),
                "lon":              env.get("lon"),
                "last_evaluated":   datetime.now(timezone.utc).isoformat(),
            }

            status = "🔴 SCRUBBER ON" if scrubber else "✓ Normal"
            log.info("✓ %-18s AQI=%-4d PM2.5=%-6.1f PM10=%-6.1f "
                     "NO2=%-5.1f Wind=%-5.1fkm/h Stage=%d %s",
                     ward_name, aqi, pm25, pm10, no2,
                     env.get("wind_speed_kmh", 0), stage, status)
            success += 1

        except Exception as exc:
            log.error("✗ %-18s failed: %s", ward_name, exc)
            failed += 1

    # ── City summary ──────────────────────────────────────────────────────────
    ward_aqis = [v["aqi_current"] for v in state["wards"].values() if v.get("aqi_current")]
    state["city"].update({
        "name":                "Delhi",
        "last_full_cycle_utc": datetime.now(timezone.utc).isoformat(),
        "city_peak_aqi":       max(ward_aqis) if ward_aqis else 0,
        "city_avg_aqi":        round(sum(ward_aqis)/len(ward_aqis), 1) if ward_aqis else 0,
        "wards_total":         len(state["wards"]),
        "wards_triggered":     sum(1 for v in state["wards"].values() if (v.get("pgrap_stage",0))>=2),
        "scrubbers_active":    sum(1 for v in state["wards"].values() if v.get("scrubber_active")),
        "data_source":         "OWM Air Pollution + Weather API",
    })

    save_state(state)

    log.info("=" * 55)
    log.info("✓ %d wards written | %d failed", success, failed)
    log.info("✓ Ward keys in state: %s", list(state["wards"].keys()))
    log.info("✓ City peak AQI: %s", state["city"]["city_peak_aqi"])
    log.info("✓ Scrubbers active: %d (only when AQI > 200)", state["city"]["scrubbers_active"])
    log.info("✓ Dashboard: http://localhost:8080/dashboard/")
    log.info("=" * 55)

    return success, failed


if __name__ == "__main__":
    loop_mode = "--loop" in sys.argv
    if loop_mode:
        interval = 300
        log.info("Loop mode — refreshing every %ds. Ctrl+C to stop.", interval)
        while True:
            try:
                fetch_all_wards()
                log.info("Next refresh in %ds...", interval)
                time.sleep(interval)
            except KeyboardInterrupt:
                log.info("Stopped.")
                break
    else:
        fetch_all_wards()
