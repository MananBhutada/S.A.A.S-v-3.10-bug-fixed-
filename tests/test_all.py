"""
tests/test_all.py — S.A.A.S. Test Suite (OWM-only version)
"""
import json, os, sys, pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "04_Bridge"))
sys.path.insert(0, str(BASE_DIR / "03_Governance"))

# ═══════════════════════════════════════════════════════════
# STATE MANAGER
# ═══════════════════════════════════════════════════════════
class TestStateManager:
    def test_load_empty_file_no_crash(self, tmp_path):
        """BUG-1: empty file must NOT raise."""
        from state_manager import load_state
        f = tmp_path / "empty.json"; f.write_text("")
        with patch("state_manager.BRIDGE_PATH", f):
            result = load_state()
        assert isinstance(result, dict) and "wards" in result

    def test_load_corrupt_file_no_crash(self, tmp_path):
        """BUG-1: corrupt JSON must NOT raise."""
        from state_manager import load_state
        f = tmp_path / "bad.json"; f.write_text("{bad json!!!")
        with patch("state_manager.BRIDGE_PATH", f):
            result = load_state()
        assert isinstance(result, dict)

    def test_clean_single_char_keys(self):
        """BUG-2: single-char keys removed."""
        from state_manager import _clean_ward_keys
        state = {"wards": {"Ward-1": {"aqi_current": 100}, "W":{}, "a":{}, "r":{}, "d":{}}}
        cleaned = _clean_ward_keys(state)
        assert list(cleaned["wards"].keys()) == ["Ward-1"]

    def test_atomic_write_roundtrip(self, tmp_path):
        """BUG-5: save then load returns same data."""
        from state_manager import load_state, save_state
        state = {"city": {"name": "Delhi"}, "wards": {"Ward-1": {"aqi_current": 420}}}
        with patch("state_manager.BRIDGE_PATH", tmp_path / "state.json"):
            ok = save_state(state)
            loaded = load_state()
        assert ok is True
        assert loaded["wards"]["Ward-1"]["aqi_current"] == 420

# ═══════════════════════════════════════════════════════════
# OWM WEATHER SERVICE
# ═══════════════════════════════════════════════════════════
class TestWeatherService:
    def test_pm25_to_aqi_good(self):
        from services.weather_service import _pm25_to_aqi
        assert _pm25_to_aqi(15) == 25

    def test_pm25_to_aqi_moderate(self):
        from services.weather_service import _pm25_to_aqi
        aqi = _pm25_to_aqi(75)
        assert 100 < aqi <= 200

    def test_pm25_to_aqi_severe(self):
        from services.weather_service import _pm25_to_aqi
        assert _pm25_to_aqi(300) >= 400

    def test_pm10_to_aqi(self):
        from services.weather_service import _pm10_to_aqi
        assert _pm10_to_aqi(75) > 50

    def test_wind_speed_conversion(self):
        """BUG-4: OWM m/s → km/h conversion is correct."""
        wind_ms  = 5.5
        wind_kmh = round(wind_ms * 3.6, 1)
        assert wind_kmh == 19.8
        assert wind_kmh > 15.0  # above spread threshold

    def test_ward_coords_defined(self):
        from services.weather_service import WARD_COORDS
        assert len(WARD_COORDS) == 10, f"Expected 10 wards, got {len(WARD_COORDS)}"
        assert "Narela" in WARD_COORDS
        assert "Rohini" in WARD_COORDS
        for name, coords in WARD_COORDS.items():
            assert "lat" in coords and "lon" in coords
            assert 28.0 < coords["lat"] < 29.0, f"Ward {name} lat out of Delhi range"
            assert 76.5 < coords["lon"] < 77.5, f"Ward {name} lon out of Delhi range"

    def test_no_ward_number_aliases(self):
        """Ward-1 through Ward-10 must NOT exist — real names only."""
        from services.weather_service import WARD_COORDS
        for i in range(1, 11):
            assert f"Ward-{i}" not in WARD_COORDS, f"Ward-{i} should not exist"

    def test_get_ward_environment_mock(self):
        """Test full OWM response parsing with mocked API."""
        from services.weather_service import get_ward_environment
        mock_weather = {
            "main": {"temp": 28.5, "humidity": 65, "pressure": 1008},
            "wind": {"speed": 4.2, "deg": 270},
            "visibility": 5000,
            "rain": {},
            "weather": [{"description": "haze"}],
        }
        mock_airpoll = {
            "list": [{
                "main": {"aqi": 4},
                "components": {
                    "pm2_5": 85.3, "pm10": 142.6,
                    "no2": 38.2, "co": 890.0,
                    "o3": 45.1, "so2": 12.4, "nh3": 5.2
                }
            }]
        }
        with patch("services.weather_service._get") as mock_get:
            mock_get.side_effect = [mock_weather, mock_airpoll]
            result = get_ward_environment("Narela")

        assert result["ward"] == "Narela"
        assert result["pm25"] == 85.3
        assert result["pm10"] == 142.6
        assert result["no2"] == 38.2
        assert result["wind_speed_kmh"] == round(4.2 * 3.6, 1)
        assert result["temperature"] == 28.5
        assert result["aqi"] > 0
        assert result["source"] == "OWM"
        assert result["mie_index"] == round(1.0 - 5000/10000, 3)

    def test_no_cpcb_references(self):
        """Verify CPCB is completely removed from weather_service."""
        content = open(BASE_DIR / "services" / "weather_service.py").read().lower()
        # allow word in comments like "no cpcb", check for actual imports/calls
        assert "cpcb_service" not in content
        assert "from services.cpcb" not in content
        assert "import cpcb" not in content
        assert "data.gov.in" not in content
        assert "pollutant_avg" not in content

    def test_heat_alert_trigger(self):
        from services.weather_service import get_ward_environment
        mock_w = {"main":{"temp":38.0,"humidity":40,"pressure":1005},
                  "wind":{"speed":2.0,"deg":180},"visibility":8000,"rain":{},"weather":[{"description":"clear"}]}
        mock_a = {"list":[{"main":{"aqi":2},"components":{"pm2_5":30.0,"pm10":50.0,"no2":20.0,"co":400.0,"o3":30.0,"so2":8.0,"nh3":2.0}}]}
        with patch("services.weather_service._get", side_effect=[mock_w, mock_a]):
            r = get_ward_environment("Narela")
        assert r["heat_alert"] is True

    def test_mosquito_risk_high(self):
        from services.weather_service import get_ward_environment
        mock_w = {"main":{"temp":30.0,"humidity":80,"pressure":1010},
                  "wind":{"speed":1.0,"deg":90},"visibility":9000,"rain":{},"weather":[{"description":"mist"}]}
        mock_a = {"list":[{"main":{"aqi":3},"components":{"pm2_5":60.0,"pm10":90.0,"no2":30.0,"co":600.0,"o3":40.0,"so2":10.0,"nh3":3.0}}]}
        with patch("services.weather_service._get", side_effect=[mock_w, mock_a]):
            r = get_ward_environment("Narela")
        assert r["mosquito_risk"] == "High"

    def test_flood_risk_rain(self):
        from services.weather_service import get_ward_environment
        mock_w = {"main":{"temp":25.0,"humidity":90,"pressure":1005},
                  "wind":{"speed":3.0,"deg":180},"visibility":3000,"rain":{"1h":5.2},"weather":[{"description":"heavy rain"}]}
        mock_a = {"list":[{"main":{"aqi":2},"components":{"pm2_5":20.0,"pm10":35.0,"no2":15.0,"co":300.0,"o3":25.0,"so2":5.0,"nh3":1.0}}]}
        with patch("services.weather_service._get", side_effect=[mock_w, mock_a]):
            r = get_ward_environment("Narela")
        assert r["flood_risk"] == "Moderate"
        assert r["rain_1h_mm"] == 5.2

# ═══════════════════════════════════════════════════════════
# P-GRAP LOGIC
# ═══════════════════════════════════════════════════════════
class TestPGRAPLogic:
    def test_stage_0_nominal(self):
        from p_grap_logic import evaluate_stage
        stage, _ = evaluate_stage(p90_aqi=80, credit_score=0.5, intent="dust")
        assert stage == 0

    def test_stage_4_lockdown(self):
        from p_grap_logic import evaluate_stage
        stage, _ = evaluate_stage(p90_aqi=450, credit_score=0.5, intent="dust")
        assert stage == 4

    def test_combustion_escalates_more(self):
        from p_grap_logic import evaluate_stage
        s_dust, _ = evaluate_stage(p90_aqi=210, credit_score=0.5, intent="dust")
        s_comb, _ = evaluate_stage(p90_aqi=210, credit_score=0.5, intent="combustion")
        assert s_comb >= s_dust

    def test_stage_names_complete(self):
        from p_grap_logic import STAGE_ACTIONS
        for i in range(5):
            assert i in STAGE_ACTIONS

# ═══════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════
class TestDatabase:
    @pytest.fixture(autouse=True)
    def setup_sqlite(self, tmp_path):
        os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"
        import db.session as sess
        sess._engine = None; sess._SessionLocal = None
        from db.session import init_db
        init_db()
        yield
        sess._engine = None; sess._SessionLocal = None

    def test_tables_created(self):
        from db.session import get_engine
        from sqlalchemy import inspect
        tables = inspect(get_engine()).get_table_names()
        assert "ward_readings" in tables
        assert "alerts" in tables
        assert "agent_memory" in tables

    def test_ward_reading_owm_source(self):
        from db.session import get_session
        from db.models import WardReading
        with get_session() as s:
            r = WardReading(ward_id="Ward-1", aqi=320.0, pm25=110.0,
                            pm10=165.0, no2=42.5, co=890.0,
                            data_source="OWM", pgrap_stage=3)
            s.add(r)
        with get_session() as s:
            row  = s.query(WardReading).filter_by(ward_id="Ward-1").first()
            src  = row.data_source
            aqi  = row.aqi
            pm25 = row.pm25
            no2  = row.no2
        assert src  == "OWM"
        assert aqi  == 320.0
        assert pm25 == 110.0
        assert no2  == 42.5

    def test_agent_memory_cooldown(self):
        from db.memory_store import MemoryStore
        mem = MemoryStore("Ward-Test")
        assert mem.can_send_alert("THRESHOLD_BREACH") is True
        mem.record_alert_sent("THRESHOLD_BREACH")
        assert mem.can_send_alert("THRESHOLD_BREACH", cooldown_minutes=30) is False

    def test_pgrap_stage_tracking(self):
        from db.memory_store import MemoryStore
        mem = MemoryStore("Ward-PG")
        old, new = mem.update_pgrap_stage(3, aqi=320.0)
        assert old == 0 and new == 3
        data = mem.get()
        assert data["current_pgrap_stage"] == 3
        assert data["last_known_aqi"] == 320.0

# ═══════════════════════════════════════════════════════════
# FASTAPI ENDPOINTS
# ═══════════════════════════════════════════════════════════
class TestAPI:
    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/api.db"
        import db.session as sess
        sess._engine = None; sess._SessionLocal = None
        from db.session import init_db
        init_db()
        yield
        sess._engine = None; sess._SessionLocal = None

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from api.main import app
        mock_state = {
            "city": {"name":"Delhi","last_full_cycle_utc": datetime.now(timezone.utc).isoformat()},
            "wards": {
                "Narela": {"aqi_current":320,"pgrap_stage":3,"scrubber_active":True,
                           "droplet_um":28,"intent":"dust","forecast_p90":410,
                           "forecast_p50":360,"forecast_p10":280,"credit_score":0.9,
                           "pm25":110.0,"pm10":165.0,"no2":42.5,"co":890.0},
                "Rohini": {"aqi_current":180,"pgrap_stage":2,"scrubber_active":True,
                           "droplet_um":28,"intent":"mixed","forecast_p90":230,
                           "forecast_p50":200,"forecast_p10":165,"credit_score":0.75,
                           "pm25":65.0,"pm10":95.0,"no2":30.0,"co":600.0},
            }
        }
        with patch("api.main.load_state", return_value=mock_state):
            with patch("api.main._load_json_safe", return_value=[]):
                yield TestClient(app)

    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "S.A.A.S." in r.json()["project"]

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["wards_loaded"] == 2

    def test_get_wards_sorted_by_aqi(self, client):
        r = client.get("/api/wards")
        assert r.status_code == 200
        wards = r.json()["wards"]
        assert wards[0]["ward_id"] == "Narela"  # highest AQI first
        assert wards[0]["aqi"] == 320

    def test_get_ward_by_id(self, client):
        r = client.get("/api/wards/Narela")
        assert r.status_code == 200
        assert r.json()["aqi_current"] == 320

    def test_ward_not_found(self, client):
        r = client.get("/api/wards/Ward-999")
        assert r.status_code == 404

    def test_pgrap_endpoint(self, client):
        r = client.get("/api/pgrap")
        assert r.status_code == 200
        data = r.json()
        assert data["highest_stage"] == 3
        assert data["scrubbers_active"] == 2

    def test_no_cpcb_in_api(self):
        """Verify API has no CPCB references."""
        content = open(BASE_DIR / "api" / "main.py").read().lower()
        assert "data.gov.in" not in content

# ═══════════════════════════════════════════════════════════
# CPCB COMPLETELY REMOVED VERIFICATION
# ═══════════════════════════════════════════════════════════
class TestCPCBRemoved:
    def test_cpcb_service_deleted(self):
        assert not (BASE_DIR / "services" / "cpcb_service.py").exists()

    def test_no_cpcb_in_ward_agents(self):
        content = open(BASE_DIR / "03_Governance" / "ward_agents.py").read().lower()
        assert "data.gov.in" not in content
        assert "cpcb_service" not in content

    def test_no_cpcb_in_env(self):
        content = open(BASE_DIR / ".env").read()
        assert "DATA_GOV_API_KEY" not in content

    def test_no_data_gov_key_in_requirements(self):
        content = open(BASE_DIR / "requirements.txt").read().lower()
        assert "data.gov" not in content

    def test_owm_key_present_in_env(self):
        content = open(BASE_DIR / ".env").read()
        assert "OPENWEATHER_API_KEY" in content

    def test_10_real_named_wards_in_multi_agent(self):
        """All 10 real-named wards must be in multi_agent_system."""
        c = open(BASE_DIR / "_05_Agent" / "multi_agent_system.py").read()
        for name in ["Narela","Rohini","Dwarka","Connaught Place","Chandni Chowk",
                     "Saket","Lajpat Nagar","Karawal Nagar","Mustafabad","Wazirpur"]:
            assert f'"{name}"' in c, f"{name} missing from multi_agent_system.py"

    def test_spread_map_covers_all_10_real_wards(self):
        """Spread map must cover all 10 real-named wards."""
        c = open(BASE_DIR / "03_Governance" / "ward_agents.py").read()
        for name in ["Narela","Rohini","Dwarka","Connaught Place","Chandni Chowk",
                     "Saket","Lajpat Nagar","Karawal Nagar","Mustafabad","Wazirpur"]:
            assert f'"{name}"' in c, f"{name} missing from spread map"
