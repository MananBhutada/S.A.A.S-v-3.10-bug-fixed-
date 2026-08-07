"""
_05_Agent/weather_agent.py
Project S.A.A.S. — Weather Agent
=================================
Wraps OpenWeatherMap to provide environmental risk signals
(mosquito risk, heat alert, flood risk) for a ward or city.

Fixes applied:
  - Ward names (e.g. "Narela", "Rohini") mapped to their parent city
    so OpenWeatherMap can resolve them. Falls back to the raw name if
    no mapping exists, which lets real city names pass through unchanged.
  - Flood risk also triggers on "drizzle" and "thunderstorm" conditions
    (previously only "rain" was checked).
  - wind_condition threshold corrected to m/s (OWM returns m/s, not km/h).
"""

import sys
from pathlib import Path

# Ensure project root is importable regardless of launch directory
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from services.weather_service import get_weather

# ---------------------------------------------------------------------------
# Ward → City mapping
# Delhi ward names are not recognised by OpenWeatherMap; map them to Delhi.
# Add entries here if your deployment covers other cities.
# ---------------------------------------------------------------------------
WARD_TO_CITY: dict[str, str] = {
    # Delhi wards
    "Narela":           "Delhi",
    "Alipur":           "Delhi",
    "Rohini":           "Delhi",
    "Dwarka":           "Delhi",
    "Karawal Nagar":    "Delhi",
    "Mustafabad":       "Delhi",
    "Saket":            "Delhi",
    "Lajpat Nagar":     "Delhi",
    "Connaught Place":  "Delhi",
    "Chandni Chowk":    "Delhi",
    "Ward-1":           "Delhi",
    "Ward-2":           "Delhi",
}

# Precipitation keywords that indicate flood / waterlogging risk
_FLOOD_KEYWORDS = ("rain", "drizzle", "thunderstorm", "shower", "storm")


def weather_agent(ward_or_city: str) -> dict:
    """
    Fetch weather for *ward_or_city* and return environmental risk signals.

    Parameters
    ----------
    ward_or_city : str
        A ward name (e.g. "Narela") or any city recognised by OpenWeatherMap.

    Returns
    -------
    dict:
        {
            "weather_data": { city, temperature, humidity, weather, wind_speed },
            "environmental_analysis": {
                "mosquito_risk":  "Low" | "High",
                "heat_alert":     bool,
                "flood_risk":     "Low" | "Moderate",
                "wind_condition": "Normal" | "Strong",
            }
        }
    """
    # Resolve ward → city before hitting the API
    city = WARD_TO_CITY.get(ward_or_city, ward_or_city)

    weather = get_weather(city)

    temp      = weather["temperature"]   # °C
    humidity  = weather["humidity"]      # %
    wind      = weather["wind_speed"]    # m/s  (OWM default)
    condition = weather["weather"].lower()

    # ── Risk logic ────────────────────────────────────────────────────────
    mosquito_risk = "High" if (humidity > 70 and temp > 25) else "Low"
    heat_alert    = temp > 35
    flood_risk    = "Moderate" if any(kw in condition for kw in _FLOOD_KEYWORDS) else "Low"

    # OWM wind_speed is in m/s; >5 m/s (~18 km/h) is considered "Strong"
    wind_condition = "Strong" if wind > 5 else "Normal"

    return {
        "weather_data": weather,
        "environmental_analysis": {
            "mosquito_risk":  mosquito_risk,
            "heat_alert":     heat_alert,
            "flood_risk":     flood_risk,
            "wind_condition": wind_condition,
        },
    }
