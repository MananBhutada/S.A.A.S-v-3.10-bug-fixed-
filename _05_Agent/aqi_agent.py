"""
_05_Agent/aqi_agent.py
Project S.A.A.S. — Environmental Agent (WAQI + OWM)
"""
from __future__ import annotations
import logging, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from services.weather_service import get_ward_environment

log = logging.getLogger("AQI-AGENT")

def aqi_agent(ward_name: str) -> dict:
    try:
        env = get_ward_environment(ward_name)
    except Exception as exc:
        log.warning("[%s] fetch failed: %s", ward_name, exc)
        env = {
            "ward": ward_name, "aqi": None, "pm25": None, "pm10": None,
            "no2": None, "co": None, "temperature": None, "humidity": None,
            "wind_speed_ms": None, "wind_speed_kmh": 5.0, "wind_bearing_deg": 270,
            "description": "", "heat_alert": False, "flood_risk": "Low",
            "mosquito_risk": "Low", "mie_index": 0.5,
            "aqi_category": "Unknown", "source": "unavailable", "error": str(exc),
        }

    aqi_cat  = env.get("aqi_category", "Unknown")
    wind_kmh = env.get("wind_speed_kmh", 5.0)
    advisory = {
        "Good":         "Air quality good. No restrictions.",
        "Satisfactory": "Sensitive groups reduce prolonged outdoor exertion.",
        "Moderate":     "Children & elderly limit outdoor activity.",
        "Poor":         "Avoid outdoor activity. Use N95 masks.",
        "Very Poor":    "Stay indoors. Close windows. Scrubbers ON.",
        "Severe":       "EMERGENCY. Health alert for all. Lockdown advised.",
        "Unknown":      "AQI unavailable. Monitor manually.",
    }
    return {
        "ward":       ward_name,
        "aqi_data":   env,
        "weather_data": {
            "city":        env.get("ward"),
            "temperature": env.get("temperature"),
            "humidity":    env.get("humidity"),
            "weather":     env.get("description"),
            "wind_speed":  env.get("wind_speed_ms"),
        },
        "environmental_analysis": {
            "aqi_category":    aqi_cat,
            "mosquito_risk":   env.get("mosquito_risk", "Low"),
            "heat_alert":      env.get("heat_alert", False),
            "flood_risk":      env.get("flood_risk", "Low"),
            "wind_condition":  "Strong" if wind_kmh > 15 else "Normal",
            "health_advisory": advisory.get(aqi_cat, "Monitor conditions."),
        },
    }
