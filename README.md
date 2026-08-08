# 🌬️ Project S.A.A.S.
### Smart Air Quality Agent System — Delhi Ward-Level AQI Monitoring

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Multi-agent Python platform for ward-level AQI monitoring and P-GRAP governance across 10 Delhi wards.
> Uses WAQI (real CPCB ground station data) for AQI + OpenWeatherMap for weather.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add API keys to .env (already configured)
#    WAQI_TOKEN=...        ← real CPCB AQI data
#    OPENWEATHER_API_KEY=  ← wind, temp, humidity

# 3. Fetch live data for all 10 wards
python refresh_data.py

# 4. Start dashboard server
python -m http.server 8080

# 5. Open dashboard
# http://localhost:8080/dashboard/

# Optional: run full LLM agent cycle
python _05_Agent/aura_agent.py

# Optional: continuous refresh every 5 min
python refresh_data.py --loop
```

---

## Data Sources

| Data | Source | Accuracy |
|------|--------|----------|
| AQI, PM2.5, PM10, NO2 | WAQI → real CPCB ground stations | ✅ Official Indian AQI |
| Wind speed/direction | OpenWeatherMap (lat/lon) | ✅ Real-time |
| Temperature, Humidity | OpenWeatherMap (lat/lon) | ✅ Real-time |
| P-GRAP stage | Calculated from real AQI | ✅ Correct formula |
| Scrubber ON/OFF | Agent decision (AQI > 200) | ✅ Correct threshold |

---

## 10 Delhi Wards

| Ward | Zone | Type | Gateway |
|------|------|------|---------|
| Narela | North | Industrial | ✅ |
| Rohini | NorthWest | Residential | |
| Dwarka | SouthWest | Residential | |
| Connaught Place | Central | Commercial | |
| Chandni Chowk | Central | Mixed | |
| Saket | South | Commercial | |
| Lajpat Nagar | South | Commercial | |
| Karawal Nagar | NorthEast | Industrial | ✅ |
| Mustafabad | East | Industrial | ✅ |
| Wazirpur | NorthWest | Industrial | |

---

## P-GRAP Thresholds (CPCB Official)

| Stage | AQI Range | Action |
|-------|-----------|--------|
| 0 — Normal | ≤ 100 | No action |
| 1 — Advisory | 101–200 | Public advisories |
| 2 — Action | 201–300 | Scrubbers ON, ban open burning |
| 3 — Emergency | 301–400 | BS-IV diesel ban |
| 4 — Lockdown | 401+ | All non-essential vehicles banned |

---

## Architecture

```
WAQI API (CPCB data) ──┐
                       ├── WardAgent × 10 ── P-GRAP Evaluation
OWM API (weather) ─────┘        │                    │
                                 │            Scrubber Command
                         Pollution Spread          │
                         (wind-based) ────── FieldAgent
                                │
                          Bus Message ──── Agent Comms Log
                                │
                         Target Ward ──── Pre-alert + Mitigation
                                │
                    aura_master_state.json
                                │
                         Dashboard (HTML)
```

---

## Bug Fixes (8 confirmed + fixed)

| Bug | Fix |
|-----|-----|
| BUG-1: json.load() crash on empty file | state_manager safe load |
| BUG-2: Ward key corruption | _clean_ward_keys() |
| BUG-3: Alert deduplication missing | 30-min cooldown registry |
| BUG-4: Wind m/s vs km/h mismatch | Explicit × 3.6 conversion |
| BUG-5: Unsafe json.dump() | Atomic write via os.replace() |
| BUG-6: Wrong CPCB field (pollutant_avg) | Replaced with WAQI |
| BUG-7: Single pollutant fetch | WAQI returns all pollutants |
| BUG-8: Raw PM2.5 used as AQI | CPCB piecewise formula |

---

## API Keys Required

```env
WAQI_TOKEN=your_token          # Free: https://aqicn.org/data-platform/token/
OPENWEATHER_API_KEY=your_key   # Free: https://openweathermap.org/api
GROQ_API_KEY=your_key          # Free: https://console.groq.com
```
