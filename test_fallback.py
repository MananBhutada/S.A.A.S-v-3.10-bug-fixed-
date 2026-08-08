import sys, os, json
sys.path.insert(0, ".")
os.environ["WAQI_TOKEN"] = "dummy"
os.environ["IQAIR_API_KEY"] = "dummy"
os.environ["OPENWEATHER_API_KEY"] = "dummy"

import services.weather_service as ws

# Prevent real cache file from interfering
ws.CACHE_FILE = __import__("pathlib").Path("/tmp/test_cache.json")
if ws.CACHE_FILE.exists():
    ws.CACHE_FILE.unlink()

# Pre-seed a fake station list so _get_delhi_stations doesn't hit network
ws._save_cache(ws._STATION_LIST_CACHE_KEY, [
    {"uid": 1, "name": "Rohini Station", "lat": 28.749, "lon": 77.063}
])

def fake_owm_weather(*a, **k):
    return {"temperature": 30, "humidity": 50, "pressure_hpa": 1000,
            "wind_speed_ms": 2.0, "wind_speed_kmh": 7.2, "wind_bearing_deg": 90,
            "visibility_m": 10000, "rain_1h_mm": 0.0, "description": "clear sky"}
ws._fetch_owm_weather = fake_owm_weather

print("=== TEST 1: WAQI has AQI + PM -> pure WAQI ===")
ws._fetch_waqi = lambda lat, lon, ward: {"aqi": 155, "pm25": 80.0, "pm10": 120.0,
    "no2": 20, "so2": 5, "co": 1, "o3": 30, "station_name": "Rohini Station",
    "last_update": "2026-08-07 10:00:00", "source": "WAQI/CPCB"}
ws._fetch_iqair = lambda lat, lon, ward: (_ for _ in ()).throw(RuntimeError("should not be called"))
env = ws.get_ward_environment("Rohini")
print("aqi_source:", env["aqi_source"], "| aqi:", env["aqi"], "| pm25:", env["pm25"], "| pm10:", env["pm10"])
assert env["aqi_source"] == "WAQI/CPCB" and env["aqi"] == 155

print("\n=== TEST 2: WAQI has PM but NO AQI -> IQAir fills AQI, WAQI PM kept ===")
ws._fetch_waqi = lambda lat, lon, ward: {"aqi": None, "pm25": 95.0, "pm10": 140.0,
    "no2": 22, "so2": None, "co": None, "o3": None, "station_name": "Rohini Station",
    "last_update": "2026-08-07 10:00:00", "source": "WAQI/CPCB"}
ws._fetch_iqair = lambda lat, lon, ward: {"aqi": 170, "pm25": None, "pm10": None,
    "no2": None, "so2": None, "co": None, "o3": None, "station_name": "New Delhi",
    "last_update": 1691400000, "source": "IQAir"}
env = ws.get_ward_environment("Rohini")
print("aqi_source:", env["aqi_source"], "| aqi:", env["aqi"], "| pm25:", env["pm25"], "| pm10:", env["pm10"], "| no2:", env["no2"])
assert env["aqi_source"] == "IQAir+WAQI-PM"
assert env["aqi"] == 170          # from IQAir
assert env["pm25"] == 95.0        # kept from WAQI
assert env["pm10"] == 140.0       # kept from WAQI
assert env["no2"] == 22           # kept from WAQI

print("\n=== TEST 3: WAQI totally fails -> pure IQAir ===")
def waqi_fail(*a, **k):
    raise RuntimeError("network down")
ws._fetch_waqi = waqi_fail
ws._fetch_iqair = lambda lat, lon, ward: {"aqi": 90, "pm25": 45.0, "pm10": None,
    "no2": None, "so2": None, "co": None, "o3": None, "station_name": "New Delhi",
    "last_update": 1691400000, "source": "IQAir"}
env = ws.get_ward_environment("Rohini")
print("aqi_source:", env["aqi_source"], "| aqi:", env["aqi"], "| pm25:", env["pm25"])
assert env["aqi_source"] == "IQAir"
assert env["aqi"] == 90

print("\n=== TEST 4: WAQI has PM only, IQAir also fails -> derive AQI from WAQI PM ===")
ws._fetch_waqi = lambda lat, lon, ward: {"aqi": None, "pm25": 65.0, "pm10": None,
    "no2": None, "so2": None, "co": None, "o3": None, "station_name": "Rohini Station",
    "last_update": "2026-08-07 10:00:00", "source": "WAQI/CPCB"}
def iqair_fail(*a, **k):
    raise RuntimeError("rate limited")
ws._fetch_iqair = iqair_fail
env = ws.get_ward_environment("Rohini")
print("aqi_source:", env["aqi_source"], "| aqi:", env["aqi"], "| pm25:", env["pm25"])
assert env["aqi_source"] == "WAQI-PM-only"
assert env["pm25"] == 65.0

print("\n=== TEST 5: everything fails -> OWM estimate ===")
ws._fetch_waqi = waqi_fail
ws._fetch_iqair = iqair_fail
ws._fetch_owm_airpoll = lambda lat, lon, ward: {"aqi": 60, "pm25": 25.0, "pm10": 40.0,
    "no2": 10, "so2": 2, "co": 1, "o3": 15, "station_name": ward, "last_update": None,
    "source": "OWM-estimate"}
env = ws.get_ward_environment("Rohini")
print("aqi_source:", env["aqi_source"], "| aqi:", env["aqi"])
assert env["aqi_source"] == "OWM-estimate"

print("\nALL TESTS PASSED")
