# S.A.A.S. — Smart Atmospheric Analysis & Suppression

S.A.A.S. is an experimental environmental-intelligence platform that brings together ward-level air-quality data, pollution forecasting, policy evaluation, multi-agent coordination, and an operational dashboard.

**Live dashboard:** https://saas-v-310-bug-fixed-production.up.railway.app/  
**3D Digital Twin:** https://saas-v-310-bug-fixed-production.up.railway.app/digital-twin

## What it does

The platform is organized around a simple workflow:

1. **Observe** environmental readings and meteorological context.
2. **Predict** possible near-term pollution trends and expose quantile forecasts (P10/P50/P90) where available.
3. **Govern** by evaluating ward conditions against configured P-GRAP policy logic.
4. **Coordinate** work through specialized agents and a message bus.
5. **Inspect** current state, alerts, audit events, and spatial context through the dashboard and Digital Twin.

The project is a research and engineering prototype. The dashboard and 3D scene present backend state alongside geographic context; contextual roads, buildings, parks, and river geometry are not model predictions. Hardware and MQTT components are present in the repository, but a displayed software state should not be interpreted as proof that a physical mitigation device has actuated or that an intervention has been independently verified.

## Main components

| Path | Responsibility |
| --- | --- |
| `01_Ingestion/` | Environmental and meteorological data ingestion |
| `_02_Intelligence/` | Forecasting and environmental analysis |
| `03_Governance/` / `_03_Governance/` | Policy and ward-level governance logic |
| `04_Bridge/` | Shared JSON state, communication logs, and audit trail |
| `_05_Agent/` | Agent orchestration and inter-agent messaging |
| `api/main.py` | FastAPI service and dashboard-facing endpoints |
| `dashboard/` | Main dashboard and interactive 3D Digital Twin |
| `db/` | Database models and session utilities |
| `Hardware/` | ESP32 firmware and sensor calibration assets |
| `tests/` | Automated test suite |

Folder names with leading underscores are intentional in this repository.

## Forecasting note

The current forecasting engine in `_02_Intelligence/tft_engine.py` loads gradient-boosting quantile models and returns P10/P50/P90 estimates. If the trained model files are unavailable, the configured statistical fallback may be used unless `SAAS_REQUIRE_FORECAST_MODEL=true` is set. The module retains the historical TFT naming, but the active quantile-model path should not be described as a running Temporal Fusion Transformer inference path.

## API overview

The FastAPI application is defined in `api/main.py`. Useful routes include:

| Route | Purpose |
| --- | --- |
| `/` | Main dashboard |
| `/dashboard` | Dashboard alias |
| `/digital-twin` | Interactive 3D city view |
| `/health` | Service, data-age, and dependency status |
| `/api/state` | Current bridge state |
| `/api/wards` | Ward readings and forecast fields |
| `/api/wards/{ward_id}` | One ward's state |
| `/api/alerts` | Recent audit-backed alerts |
| `/api/pgrap` | P-GRAP summary grouped by stage |
| `/api/analytics/summary` | Live and historical summary |
| `/api/comms` | Agent communication log |
| `/api/audit` | P-GRAP audit trail |
| `/api/refresh` | Reloads bridge state from disk |

**Important:** `POST /api/refresh` reads the existing bridge state; it does not itself fetch fresh data or start an agent cycle. Data freshness depends on the ingestion/worker process that updates the bridge.

Interactive API documentation is available at `/docs` when the FastAPI service is running.

## Run locally

Use Python 3.11 or newer.

```bash
git clone https://github.com/MananBhutada/S.A.A.S-v-3.10-bug-fixed-.git
cd S.A.A.S-v-3.10-bug-fixed-
python -m venv .venv
```

Activate the environment:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

Install dependencies and configure credentials:

```bash
pip install -r requirements.txt
```

Create a local `.env` file for the integrations you intend to run. Common variables include:

```dotenv
WAQI_TOKEN=your_token
OPENWEATHER_API_KEY=your_key
GROQ_API_KEY=your_key
```

Never commit real credentials. Check `.gitignore` and use environment-specific secrets in deployed environments.

Start the API and dashboard:

```bash
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ . The API docs are at http://127.0.0.1:8000/docs.

The API process serves the dashboard and reads the bridge state. It does not automatically start every ingestion or agent worker; start those separately according to the relevant module's configuration and deployment setup.

## Docker

The repository includes a `Dockerfile` and `docker-compose.yml`. The Dockerfile builds the FastAPI service and starts Uvicorn with two workers. Treat the autonomous data/agent worker as a separate process unless your chosen runtime explicitly configures it.

## Development

- Keep changes scoped to the component being modified.
- Do not commit API tokens, private keys, or local environment files.
- Run the relevant tests before opening a pull request.
- Keep observed backend values distinct from forecast values and geographic visualization context.
- Avoid describing a simulated, queued, or displayed device action as verified physical actuation.

## License

See [LICENSE](LICENSE) for the Apache License 2.0 terms.
