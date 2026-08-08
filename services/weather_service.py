"""
services/weather_service.py
Project S.A.A.S. — Hybrid Data Service (WAQI + IQAir + OWM)
=============================================================
WAQI   → real CPCB AQI, PM2.5, PM10, NO2 (primary)
IQAir  → AQI fallback if WAQI has no overall AQI / is unreachable
         (WAQI's own PM2.5/PM10 are kept even when its AQI is missing)
OWM    → wind, temperature, humidity (always)
OWM Air Pollution → final fallback if both WAQI and IQAir fail
"""
from __future__ import annotations
import os, time, json, logging, math
from pathlib import Path
from typing import Any
import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("WEATHER-SERVICE")

OWM_WEATHER  = "https://api.openweathermap.org/data/2.5/weather"
OWM_AIR_POLL = "https://api.openweathermap.org/data/2.5/air_pollution"

CACHE_DIR  = Path(__file__).parent.parent / "data"
CACHE_FILE = CACHE_DIR / "owm_cache.json"
CACHE_TTL  = 600

def _load_cache() -> dict:
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text())
    except Exception:
        pass
    return {}

# FIX: cache stores dicts (AQI/weather feeds) AND lists (station list) —
# typed as Any instead of dict so callers can store/retrieve either shape.
def _save_cache(key: str, data: Any) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache = _load_cache()
        cache[key] = {"ts": time.time(), "data": data}
        CACHE_FILE.write_text(json.dumps(cache))
    except Exception as e:
        log.warning("Cache save failed: %s", e)

def _get_cache(key: str, ttl: int = CACHE_TTL) -> Any | None:
    entry = _load_cache().get(key)
    if not entry or time.time() - entry["ts"] > ttl:
        return None
    return entry["data"]

# ── Simple per-source rate limiting ────────────────────────────────────────────
# IQAir's free Community plan allows ~1 request/second. Looping over 10 wards
# back-to-back can burst past that and trigger HTTP 429s, so we (a) space
# calls out to respect the limit and (b) retry once with backoff if a 429
# slips through anyway (e.g. another process using the same key).
_last_call_ts: dict[str, float] = {}

def _throttle(rate_key: str, min_interval: float) -> None:
    last = _last_call_ts.get(rate_key)
    if last is not None:
        wait = min_interval - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _last_call_ts[rate_key] = time.monotonic()

def _api_get(
    url: str,
    params: dict | None = None,
    cache_key: str = "",
    rate_key: str | None = None,
    min_interval: float = 0.0,
    retry_on_429: int = 0,
    retry_backoff: float = 1.5,
) -> dict:
    if cache_key:
        cached = _get_cache(cache_key)
        if cached is not None:
            log.debug("Cache HIT: %s", cache_key)
            return cached
    attempts = retry_on_429 + 1
    last_exc: Exception | None = None
    for attempt in range(attempts):
        if rate_key:
            _throttle(rate_key, min_interval)
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 429 and attempt < attempts - 1:
                log.warning("HTTP 429 (rate limited) on %s — retrying in %.1fs (attempt %d/%d)",
                            rate_key or url, retry_backoff, attempt + 1, attempts)
                time.sleep(retry_backoff)
                last_exc = RuntimeError("HTTP 429")
                continue
            if not r.ok:
                raise RuntimeError(f"HTTP {r.status_code}")
            data = r.json()
            if cache_key:
                _save_cache(cache_key, data)
            return data
        except (requests.ConnectionError, requests.Timeout) as e:
            if cache_key:
                entry = _load_cache().get(cache_key)
                if entry:
                    log.warning("Network error — serving stale cache for %s", cache_key)
                    return entry["data"]
            raise RuntimeError(f"Network error: {e}") from e
    raise RuntimeError(f"Rate limited after {attempts} attempts: {last_exc}")

def _owm_key() -> str:
    key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if not key:
        raise EnvironmentError("OPENWEATHER_API_KEY not set in .env")
    return key

def _waqi_token() -> str:
    token = os.getenv("WAQI_TOKEN", "").strip()
    if not token:
        raise EnvironmentError("WAQI_TOKEN not set in .env")
    return token

def _iqair_key() -> str:
    key = os.getenv("IQAIR_API_KEY", "").strip()
    if not key:
        raise EnvironmentError("IQAIR_API_KEY not set in .env")
    return key

WARD_COORDS: dict[str, dict] = {
    "Narela":          {"lat": 28.852, "lon": 77.094, "zone": "North",     "type": "Industrial",  "gateway": True},
    "Rohini":          {"lat": 28.749, "lon": 77.063, "zone": "NorthWest", "type": "Residential", "gateway": False},
    "Dwarka":          {"lat": 28.593, "lon": 77.046, "zone": "SouthWest", "type": "Residential", "gateway": False},
    "Connaught Place": {"lat": 28.634, "lon": 77.219, "zone": "Central",   "type": "Commercial",  "gateway": False},
    "Chandni Chowk":   {"lat": 28.657, "lon": 77.230, "zone": "Central",   "type": "Mixed",       "gateway": False},
    "Saket":           {"lat": 28.524, "lon": 77.215, "zone": "South",     "type": "Commercial",  "gateway": False},
    "Lajpat Nagar":    {"lat": 28.569, "lon": 77.243, "zone": "South",     "type": "Commercial",  "gateway": False},
    "Karawal Nagar":   {"lat": 28.754, "lon": 77.310, "zone": "NorthEast", "type": "Industrial",  "gateway": True},
    "Mustafabad":      {"lat": 28.731, "lon": 77.304, "zone": "East",      "type": "Industrial",  "gateway": True},
    "Wazirpur":        {"lat": 28.704, "lon": 77.161, "zone": "NorthWest", "type": "Industrial",  "gateway": False},
}

def _pm25_to_aqi(pm25: float) -> int:
    bp = [(0,30,0,50),(30,60,51,100),(60,90,101,200),
          (90,120,201,300),(120,250,301,400),(250,500,401,500)]
    for c_lo,c_hi,i_lo,i_hi in bp:
        if c_lo <= pm25 <= c_hi:
            return round(((i_hi-i_lo)/(c_hi-c_lo))*(pm25-c_lo)+i_lo)
    return 500 if pm25>500 else 0

def _pm10_to_aqi(pm10: float) -> int:
    bp = [(0,50,0,50),(50,100,51,100),(100,250,101,200),
          (250,350,201,300),(350,430,301,400),(430,600,401,500)]
    for c_lo,c_hi,i_lo,i_hi in bp:
        if c_lo <= pm10 <= c_hi:
            return round(((i_hi-i_lo)/(c_hi-c_lo))*(pm10-c_lo)+i_lo)
    return 500 if pm10>600 else 0

# ── WAQI station resolution ───────────────────────────────────────────────────
_STATION_LIST_CACHE_KEY = "waqi_delhi_stations"
_STATION_LIST_TTL = 60 * 60 * 24 * 7  # 1 week

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * r * math.asin(math.sqrt(a))

def _get_delhi_stations() -> list[dict]:
    cached = _get_cache(_STATION_LIST_CACHE_KEY, ttl=_STATION_LIST_TTL)
    if cached is not None:
        return cached
    token = _waqi_token()
    r = requests.get(
        "https://api.waqi.info/search/",
        params={"keyword": "Delhi", "token": token},
        timeout=15,
    )
    if not r.ok:
        raise RuntimeError(f"WAQI search HTTP {r.status_code}")
    data = r.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"WAQI search error: {data.get('data')}")
    stations = []
    for item in data.get("data", []):
        st  = item.get("station", {})
        geo = st.get("geo")
        if item.get("uid") is not None and geo and len(geo) == 2:
            stations.append({
                "uid":  item["uid"],
                "name": st.get("name"),
                "lat":  geo[0],
                "lon":  geo[1],
            })
    if not stations:
        raise RuntimeError("WAQI search returned no usable Delhi stations")
    _save_cache(_STATION_LIST_CACHE_KEY, stations)
    log.info("WAQI: found %d Delhi stations, cached for 1 week", len(stations))
    return stations

def _nearest_station(lat: float, lon: float) -> dict:
    stations = _get_delhi_stations()
    return min(stations, key=lambda s: _haversine_km(lat, lon, s["lat"], s["lon"]))

def _safe_int(val: object) -> int | None:
    """
    BUG FIX: WAQI sometimes returns "-" instead of a number when
    a station has no current reading. This converts safely.
    """
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None

def _safe_float(val: object) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

# ── WAQI fetch ────────────────────────────────────────────────────────────────
def _fetch_waqi(lat: float, lon: float, ward_name: str) -> dict:
    """
    Fetch real CPCB AQI via WAQI.
    Uses /search/ + /feed/@uid/ — more reliable than geo:lat;lon.
    Tries up to 3 nearest stations in case closest has no data ("-").

    NOTE: Unlike before, a station with a missing overall AQI ("-") but valid
    PM2.5/PM10 readings is NOT skipped — it's returned with aqi=None so the
    caller (get_ward_environment) can fill just the AQI gap from IQAir while
    still keeping WAQI's own PM2.5/PM10 values (ground-truth CPCB data).
    A station is only skipped if it has neither an AQI nor any PM reading.
    """
    token = _waqi_token()
    stations = _get_delhi_stations()

    # Sort by distance — try up to 3 nearest stations
    sorted_stations = sorted(
        stations,
        key=lambda s: _haversine_km(lat, lon, s["lat"], s["lon"])
    )

    last_error = None
    for station in sorted_stations[:3]:
        try:
            url  = f"https://api.waqi.info/feed/@{station['uid']}/?token={token}"
            r    = requests.get(url, timeout=15)
            if not r.ok:
                raise RuntimeError(f"HTTP {r.status_code}")
            data = r.json()

            if data.get("status") != "ok":
                raise RuntimeError(f"WAQI status error: {data.get('data')}")

            d    = data["data"]
            iaqi = d.get("iaqi", {})

            def _v(key: str) -> float | None:
                return _safe_float(iaqi.get(key, {}).get("v"))

            # BUG FIX: use _safe_int — WAQI returns "-" when station offline
            aqi  = _safe_int(d.get("aqi"))
            pm25 = _v("pm25")
            pm10 = _v("pm10")

            # Only move to the next station if there is truly nothing usable
            # here (no overall AQI AND no PM readings at all).
            if aqi is None and pm25 is None and pm10 is None:
                log.debug("Station %s (%s) has no AQI or PM data — trying next",
                          station["uid"], station["name"])
                last_error = RuntimeError(f"Station {station['name']} returned no usable data")
                continue

            station_name = d.get("city", {}).get("name", station["name"])
            last_update  = d.get("time", {}).get("s")

            result = {
                "aqi":          aqi,   # may be None — filled from IQAir upstream if so
                "pm25":         pm25,
                "pm10":         pm10,
                "no2":          _v("no2"),
                "so2":          _v("so2"),
                "co":           _v("co"),
                "o3":           _v("o3"),
                "station_name": station_name,
                "last_update":  last_update,
                "source":       "WAQI/CPCB",
            }

            log.info("[%s] WAQI/CPCB → AQI=%s PM2.5=%s PM10=%s NO2=%s | Station: %s",
                     ward_name, aqi, pm25, pm10, result["no2"], station_name)
            return result

        except RuntimeError as e:
            last_error = e
            continue

    raise RuntimeError(f"All WAQI stations returned no data for {ward_name}: {last_error}")

# ── IQAir (secondary fallback) ──────────────────────────────────────────────────
IQAIR_NEAREST_CITY = "https://api.airvisual.com/v2/nearest_city"
# Community plan = 5 calls/minute max → 1 call per 12s minimum, not per-second.
# (Earlier 1.1s assumed a 1 req/sec limit — that was wrong and still hit 429s.)
IQAIR_MIN_INTERVAL_S = 12.5
IQAIR_RATE_KEY       = "iqair_nearest_city"

# Community/free IQAir plan returns only the AQI index + dominant pollutant code
# (mainus), not raw PM concentrations. These invert the same EPA breakpoint
# tables used by _pm25_to_aqi / _pm10_to_aqi so we can back out an approximate
# concentration when PM2.5/PM10 is the dominant pollutant. This is an estimate,
# same spirit as the existing OWM fallback — not exact ground-truth data.
def _aqi_to_pm25(aqi: int) -> float:
    bp = [(0,30,0,50),(30,60,51,100),(60,90,101,200),
          (90,120,201,300),(120,250,301,400),(250,500,401,500)]
    for c_lo,c_hi,i_lo,i_hi in bp:
        if i_lo <= aqi <= i_hi:
            return round(((c_hi-c_lo)/(i_hi-i_lo))*(aqi-i_lo)+c_lo, 1)
    return 500.0 if aqi > 500 else 0.0

def _aqi_to_pm10(aqi: int) -> float:
    bp = [(0,50,0,50),(50,100,51,100),(100,250,101,200),
          (250,350,201,300),(350,430,301,400),(430,600,401,500)]
    for c_lo,c_hi,i_lo,i_hi in bp:
        if i_lo <= aqi <= i_hi:
            return round(((c_hi-c_lo)/(i_hi-i_lo))*(aqi-i_lo)+c_lo, 1)
    return 600.0 if aqi > 500 else 0.0

def _fetch_iqair(lat: float, lon: float, ward_name: str) -> dict:
    """
    Fetch AQI from IQAir (AirVisual) nearest_city endpoint — used only when
    WAQI fails entirely or has no overall AQI for its nearest stations.
    NOTE: aqius is the US-EPA-scale AQI, which may differ slightly from
    WAQI's CPCB-based AQI for the same location — used here only as the
    best available fallback, not a like-for-like replacement.
    """
    key  = _iqair_key()
    data = _api_get(
        IQAIR_NEAREST_CITY,
        params={"lat": lat, "lon": lon, "key": key},
        cache_key=f"iqair_{ward_name}",
        rate_key=IQAIR_RATE_KEY,
        min_interval=IQAIR_MIN_INTERVAL_S,
        retry_on_429=1,
        retry_backoff=IQAIR_MIN_INTERVAL_S,
    )
    if data.get("status") != "success":
        raise RuntimeError(f"IQAir error: {data.get('data')}")

    payload   = data.get("data", {})
    pollution = payload.get("current", {}).get("pollution", {})
    aqius     = _safe_int(pollution.get("aqius"))
    main_us   = pollution.get("mainus")  # e.g. 'p2' = PM2.5, 'p1' = PM10 dominant

    if aqius is None:
        raise RuntimeError("IQAir returned no AQI data")

    pm25 = _aqi_to_pm25(aqius) if main_us == "p2" else None
    pm10 = _aqi_to_pm10(aqius) if main_us == "p1" else None

    station_name = payload.get("city", ward_name)
    last_update  = pollution.get("ts")

    result = {
        "aqi":          aqius,
        "pm25":         pm25,
        "pm10":         pm10,
        "no2":          None,
        "so2":          None,
        "co":           None,
        "o3":           None,
        "station_name": station_name,
        "last_update":  last_update,
        "source":       "IQAir",
    }
    log.info("[%s] IQAir → AQI(US)=%s dominant=%s | City: %s",
             ward_name, aqius, main_us, station_name)
    return result

# ── OWM weather ───────────────────────────────────────────────────────────────
def _fetch_owm_weather(lat: float, lon: float, ward_name: str) -> dict:
    key  = _owm_key()
    data = _api_get(
        OWM_WEATHER,
        params={"lat": lat, "lon": lon, "appid": key, "units": "metric"},
        cache_key=f"owm_w_{ward_name}",
    )
    wind_ms  = data.get("wind", {}).get("speed", 0.0)
    wind_deg = data.get("wind", {}).get("deg", 0)
    return {
        "temperature":      data.get("main", {}).get("temp"),
        "humidity":         data.get("main", {}).get("humidity"),
        "pressure_hpa":     data.get("main", {}).get("pressure"),
        "wind_speed_ms":    round(wind_ms, 2),
        "wind_speed_kmh":   round(wind_ms * 3.6, 1),
        "wind_bearing_deg": wind_deg,
        "visibility_m":     data.get("visibility", 10000),
        "rain_1h_mm":       data.get("rain", {}).get("1h", 0.0),
        "description":      data.get("weather", [{}])[0].get("description", ""),
    }

# ── OWM fallback ──────────────────────────────────────────────────────────────
def _fetch_owm_airpoll(lat: float, lon: float, ward_name: str) -> dict:
    key  = _owm_key()
    data = _api_get(
        OWM_AIR_POLL,
        params={"lat": lat, "lon": lon, "appid": key},
        cache_key=f"owm_ap_{ward_name}",
    )
    item       = data.get("list", [{}])[0]
    components = item.get("components", {})
    pm25 = components.get("pm2_5", 0.0)
    pm10 = components.get("pm10",  0.0)
    return {
        "aqi":          _pm25_to_aqi(pm25) if pm25 else _pm10_to_aqi(pm10),
        "pm25":         round(pm25, 2),
        "pm10":         round(pm10, 2),
        "no2":          round(components.get("no2", 0.0), 2),
        "so2":          round(components.get("so2", 0.0), 2),
        "co":           round(components.get("co",  0.0), 2),
        "o3":           round(components.get("o3",  0.0), 2),
        "station_name": ward_name,
        "last_update":  None,
        "source":       "OWM-estimate",
    }

# ── Main public function ──────────────────────────────────────────────────────
def get_ward_environment(ward_name: str) -> dict:
    coords = WARD_COORDS.get(ward_name)
    if not coords:
        raise ValueError(
            f"Ward '{ward_name}' not in WARD_COORDS. "
            f"Available: {list(WARD_COORDS.keys())}"
        )
    lat, lon = coords["lat"], coords["lon"]

    # 1. AQI — WAQI (primary) → IQAir (fallback for AQI) → OWM (last resort)
    #
    # WAQI's own PM2.5/PM10 are always kept when present, even if its AQI
    # is missing — IQAir/OWM are only used to fill genuine gaps, never to
    # override real WAQI ground-station PM readings.
    waqi_data: dict | None = None
    try:
        waqi_data = _fetch_waqi(lat, lon, ward_name)
    except Exception as e:
        log.warning("[%s] WAQI failed entirely (%s)", ward_name, e)
        waqi_data = None

    aqi_data   = {}
    aqi_source = "unknown"

    if waqi_data and waqi_data.get("aqi") is not None:
        # WAQI gave a full reading — nothing else needed.
        aqi_data   = waqi_data
        aqi_source = "WAQI/CPCB"
    else:
        # WAQI missing entirely, or gave PM without an overall AQI — try IQAir.
        if waqi_data:
            log.warning("[%s] WAQI has no overall AQI — filling gap from IQAir", ward_name)
        try:
            iqair_data = _fetch_iqair(lat, lon, ward_name)
            merged = dict(iqair_data)
            if waqi_data:
                # Keep WAQI's own PM2.5/PM10/other pollutants wherever present.
                for key in ("pm25", "pm10", "no2", "so2", "co", "o3"):
                    if waqi_data.get(key) is not None:
                        merged[key] = waqi_data[key]
                if waqi_data.get("station_name"):
                    merged["station_name"] = waqi_data["station_name"]
                merged["source"] = "IQAir+WAQI-PM" if (
                    waqi_data.get("pm25") is not None or waqi_data.get("pm10") is not None
                ) else "IQAir"
            aqi_data   = merged
            aqi_source = merged["source"]
        except Exception as e2:
            log.warning("[%s] IQAir also failed (%s)", ward_name, e2)
            if waqi_data and (waqi_data.get("pm25") is not None or waqi_data.get("pm10") is not None):
                # No IQAir, no OWM needed — derive AQI from WAQI's own PM readings.
                pm25 = waqi_data.get("pm25")
                pm10 = waqi_data.get("pm10")
                derived_aqi = _pm25_to_aqi(pm25) if pm25 else (_pm10_to_aqi(pm10) if pm10 else None)
                aqi_data = {
                    "aqi":          derived_aqi,
                    "pm25":         pm25,
                    "pm10":         pm10,
                    "no2":          waqi_data.get("no2"),
                    "so2":          waqi_data.get("so2"),
                    "co":           waqi_data.get("co"),
                    "o3":           waqi_data.get("o3"),
                    "station_name": waqi_data.get("station_name", ward_name),
                    "last_update":  waqi_data.get("last_update"),
                    "source":       "WAQI-PM-only",
                }
                aqi_source = "WAQI-PM-only"
            else:
                try:
                    aqi_data   = _fetch_owm_airpoll(lat, lon, ward_name)
                    aqi_source = "OWM-estimate"
                except Exception as e3:
                    log.error("[%s] All three AQI sources failed: %s", ward_name, e3)
                    aqi_data   = {"aqi": None, "pm25": None, "pm10": None,
                                  "no2": None, "so2": None, "co": None, "o3": None,
                                  "station_name": ward_name, "source": "unavailable"}
                    aqi_source = "unavailable"

    # 2. Weather from OWM
    weather = {}
    try:
        weather = _fetch_owm_weather(lat, lon, ward_name)
    except Exception as e:
        log.warning("[%s] OWM weather failed: %s", ward_name, e)
        weather = {"wind_speed_kmh": 0.0, "wind_bearing_deg": 0,
                   "temperature": None, "humidity": None,
                   "visibility_m": 10000, "rain_1h_mm": 0.0,
                   "description": "", "pressure_hpa": None,
                   "wind_speed_ms": 0.0}

    # 3. Analysis
    temp       = weather.get("temperature")
    humidity   = weather.get("humidity")
    desc       = weather.get("description", "")
    visibility = weather.get("visibility_m", 10000)
    wind_kmh   = weather.get("wind_speed_kmh", 0)

    heat_alert    = bool(temp and temp > 35)
    flood_risk    = "Moderate" if any(
        kw in desc.lower() for kw in ["rain","storm","flood","drizzle","shower"]
    ) else "Low"
    mosquito_risk = "High" if (humidity and humidity > 70 and temp and temp > 25) else "Low"
    mie_index     = round(max(0.0, min(1.0, 1.0 - (visibility or 10000) / 10000.0)), 3)

    aqi = aqi_data.get("aqi")

    def _cat(a: int | None) -> str:
        if not a:    return "Unknown"
        if a <= 50:  return "Good"
        if a <= 100: return "Satisfactory"
        if a <= 200: return "Moderate"
        if a <= 300: return "Poor"
        if a <= 400: return "Very Poor"
        return "Severe"

    return {
        "ward":             ward_name,
        "lat":              lat,
        "lon":              lon,
        "aqi":              aqi,
        "aqi_category":     _cat(aqi),
        "pm25":             aqi_data.get("pm25"),
        "pm10":             aqi_data.get("pm10"),
        "no2":              aqi_data.get("no2"),
        "so2":              aqi_data.get("so2"),
        "co":               aqi_data.get("co"),
        "o3":               aqi_data.get("o3"),
        "station_name":     aqi_data.get("station_name", ward_name),
        "aqi_last_update":  aqi_data.get("last_update"),
        "aqi_source":       aqi_source,
        "temperature":      temp,
        "humidity":         humidity,
        "pressure_hpa":     weather.get("pressure_hpa"),
        "wind_speed_ms":    weather.get("wind_speed_ms"),
        "wind_speed_kmh":   wind_kmh,
        "wind_bearing_deg": weather.get("wind_bearing_deg"),
        "visibility_m":     visibility,
        "rain_1h_mm":       weather.get("rain_1h_mm", 0.0),
        "description":      desc,
        "mie_index":        mie_index,
        "heat_alert":       heat_alert,
        "flood_risk":       flood_risk,
        "mosquito_risk":    mosquito_risk,
        "source":           aqi_source,
        "weather_source":   "OWM",
        "last_update":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

# ── Legacy ────────────────────────────────────────────────────────────────────
def get_weather(city_or_ward: str) -> dict:
    if city_or_ward in WARD_COORDS:
        env = get_ward_environment(city_or_ward)
        return {"city": env["ward"], "temperature": env["temperature"],
                "humidity": env["humidity"], "weather": env["description"],
                "wind_speed": env["wind_speed_ms"]}
    key = _owm_key()
    r = _api_get(OWM_WEATHER, params={"q": city_or_ward, "appid": key, "units": "metric"})
    return {"city": r.get("name"), "temperature": r.get("main", {}).get("temp"),
            "humidity": r.get("main", {}).get("humidity"),
            "weather": r.get("weather", [{}])[0].get("description", ""),
            "wind_speed": r.get("wind", {}).get("speed", 0)}