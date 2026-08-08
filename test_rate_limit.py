import sys, os, time, json
sys.path.insert(0, ".")
os.environ["IQAIR_API_KEY"] = "dummy"

import services.weather_service as ws
ws.CACHE_FILE = __import__("pathlib").Path("/tmp/test_cache2.json")
if ws.CACHE_FILE.exists():
    ws.CACHE_FILE.unlink()
ws._last_call_ts.clear()

class FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.ok = status_code == 200
        self._payload = payload
    def json(self):
        return self._payload

print("=== TEST A: throttling enforces min_interval between calls ===")
call_times = []
def fake_get(url, params=None, timeout=15):
    call_times.append(time.monotonic())
    return FakeResp(200, {"status": "success", "data": {"city": "TestCity",
        "current": {"pollution": {"aqius": 80, "mainus": "p2", "ts": "x"}}}})
ws.requests.get = fake_get

ws._fetch_iqair(28.7, 77.1, "WardA")
ws._fetch_iqair(28.8, 77.2, "WardB")
gap = call_times[1] - call_times[0]
print(f"gap between calls: {gap:.2f}s (expected >= ~1.1s)")
assert gap >= 1.0, "Throttle did not enforce min interval!"

print("\n=== TEST B: 429 triggers retry then succeeds ===")
ws._last_call_ts.clear()
attempts = {"n": 0}
def fake_get_429_then_ok(url, params=None, timeout=15):
    attempts["n"] += 1
    if attempts["n"] < 2:
        return FakeResp(429, {})
    return FakeResp(200, {"status": "success", "data": {"city": "TestCity2",
        "current": {"pollution": {"aqius": 55, "mainus": "p2", "ts": "y"}}}})
ws.requests.get = fake_get_429_then_ok
result = ws._fetch_iqair(28.9, 77.3, "WardC")
print("attempts made:", attempts["n"], "| result aqi:", result["aqi"])
assert attempts["n"] == 2
assert result["aqi"] == 55

print("\n=== TEST C: persistent 429 exhausts retries and raises ===")
ws._last_call_ts.clear()
def fake_get_always_429(url, params=None, timeout=15):
    return FakeResp(429, {})
ws.requests.get = fake_get_always_429
try:
    ws._fetch_iqair(29.0, 77.4, "WardD")
    print("ERROR: should have raised")
except RuntimeError as e:
    print("correctly raised:", e)

print("\nALL RATE-LIMIT TESTS PASSED")
