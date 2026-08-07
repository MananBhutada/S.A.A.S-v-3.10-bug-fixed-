"""
tests/test_agent.py
Project S.A.A.S. — Weather Agent smoke test
============================================
Run with:
    python -m pytest tests/test_agent.py -v
or standalone:
    python tests/test_agent.py

Fixes applied:
  - Added sys.path setup so _05_Agent is importable from any CWD.
  - Wrapped bare script code into a proper test function.
  - Added assertions to verify the response structure.
"""

import sys
import os

# Ensure project root is on sys.path regardless of where pytest is launched from
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)


def test_weather_agent_returns_valid_structure():
    """weather_agent must return the expected keys for a known city."""
    from _05_Agent.weather_agent import weather_agent

    report = weather_agent("Pune")

    assert "weather_data" in report, "Missing 'weather_data' key"
    assert "environmental_analysis" in report, "Missing 'environmental_analysis' key"

    wd = report["weather_data"]
    for key in ("city", "temperature", "humidity", "weather", "wind_speed"):
        assert key in wd, f"weather_data missing '{key}'"

    ea = report["environmental_analysis"]
    for key in ("mosquito_risk", "heat_alert", "flood_risk", "wind_condition"):
        assert key in ea, f"environmental_analysis missing '{key}'"

    assert ea["mosquito_risk"] in ("Low", "High")
    assert isinstance(ea["heat_alert"], bool)
    assert ea["flood_risk"] in ("Low", "Moderate")

    print("\n[test_weather_agent] PASSED")
    print(f"  City fetched : {wd['city']}")
    print(f"  Temperature  : {wd['temperature']} °C")
    print(f"  Humidity     : {wd['humidity']} %")
    print(f"  Condition    : {wd['weather']}")
    print(f"  Wind speed   : {wd['wind_speed']} m/s")
    print(f"  Mosquito risk: {ea['mosquito_risk']}")
    print(f"  Heat alert   : {ea['heat_alert']}")
    print(f"  Flood risk   : {ea['flood_risk']}")


if __name__ == "__main__":
    test_weather_agent_returns_valid_structure()
