# 🌬️ Project S.A.A.S.

## Smart Atmospheric Analysis & Suppression

> A modular AI + IoT platform for ward-level air-quality intelligence, pollution forecasting, governance decision support, multi-agent coordination, and targeted mitigation.

Project S.A.A.S. is designed as a layered atmospheric intelligence and mitigation platform. It combines real-world pollution and weather data, machine-learning forecasting, ward-level governance logic, agentic AI, communication bridges, dashboards, and IoT hardware interfaces into a single extensible system.

The current implementation is configured around a **10-ward Delhi pilot**.

---

# 🚀 What the System Does

Project S.A.A.S. combines five major layers:

```text
┌─────────────────────────────────────────────────────────────┐
│                    PROJECT S.A.A.S.                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  01 — INGESTION                                             │
│  Pollution / Weather / External Data                        │
│                         ↓                                   │
│  02 — INTELLIGENCE                                          │
│  Forecasting / ML / Vision                                  │
│                         ↓                                   │
│  03 — GOVERNANCE                                            │
│  P-GRAP / Ward Decisions / Mitigation Logic                 │
│                         ↓                                   │
│  04 — BRIDGE                                                │
│  State / Communication / Hardware Interface                 │
│                         ↓                                   │
│  05 — AGENTIC AI                                            │
│  Specialized Agents / Coordination / Alerts                 │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│             API │ Dashboard │ Database │ IoT                │
└─────────────────────────────────────────────────────────────┘

The system is intended to move beyond simple AQI visualization by connecting:

observation → prediction → governance → decision → communication → mitigation

🧠 Core Capabilities
Environmental Intelligence
Ward-level AQI monitoring
PM2.5 / PM10 / NO₂ data handling
Weather and atmospheric feature ingestion
Wind-aware pollution analysis
External environmental data integration
Machine Learning
Temporal forecasting infrastructure
Temporal Fusion Transformer (TFT) model integration
Model artifact management
Feature metadata and quantile-model support
Vision-processing pipeline
Governance
P-GRAP stage evaluation
AQI-based mitigation decisions
Ward-level decision logic
Pollution-spread reasoning
Targeted mitigation selection
Agentic AI
Specialized AQI agent
Weather agent
AURA agent
Multi-agent orchestration
Agent communication
Alert dispatch
LLM-assisted decision workflows
IoT / Hardware
ESP32-based hardware interface
Sensor calibration support
MQTT communication
Scrubber control interface
Hardware command bridge
Platform
FastAPI backend
HTML dashboard
Database / state-management layer
Docker support
Automated CI workflow
Automated tests
🏗️ Repository Architecture
Project S.A.A.S.
│
├── 01_Ingestion/
│   ├── met_vector_sync.py
│   ├── sentinel_fetcher.py
│   └── cache/
│
├── _02_Intelligence/
│   ├── tft_engine.py
│   ├── vision_extinction.py
│   └── models/
│       ├── model artifacts
│       ├── feature metadata
│       └── model documentation
│
├── 03_Governance/
│   ├── orchestrator.py
│   ├── p_grap_logic.py
│   └── ward_agents.py
│
├── 04_Bridge/
│   ├── config.json
│   ├── init_bridge.py
│   └── state_manager.py
│
├── _05_Agent/
│   ├── aqi_agent.py
│   ├── aura_agent.py
│   ├── mqtt_client.py
│   ├── multi_agent_system.py
│   ├── telegram_dispatch.py
│   └── weather_agent.py
│
├── api/
│   └── main.py
│
├── dashboard/
│   └── index.html
│
├── data/
│   └── data_pipeline.py
│
├── db/
│   ├── memory_store.py
│   ├── models.py
│   └── session.py
│
├── Hardware/
│   ├── esp32_scrubber.ino
│   └── sensor_calibration.h
│
├── monitoring/
│   └── logger.py
│
├── services/
│   └── weather_service.py
│
├── tests/
│   ├── test_agent.py
│   ├── test_all.py
│   └── test_smoke.py
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── pyrightconfig.json
├── refresh_data.py
└── agent_loader.py
🔄 System Data Flow
                    External Data
                         │
             ┌───────────┴───────────┐
             ↓                       ↓
        WAQI / AQI              Weather APIs
             │                       │
             └───────────┬───────────┘
                         ↓
                 01 — Ingestion
                         │
                         ↓
              Data Normalization
                         │
                         ↓
                02 — Intelligence
                 ┌───────┴────────┐
                 ↓                ↓
              TFT Model        Vision
                 │                │
                 └───────┬────────┘
                         ↓
                03 — Governance
                         │
                  P-GRAP Logic
                         │
                  Ward Analysis
                         │
                         ↓
                 05 — Agent Layer
              ┌──────────┼──────────┐
              ↓          ↓          ↓
           AQI Agent  Weather    AURA Agent
                         │
                         ↓
                 Multi-Agent System
                         │
                         ↓
                  04 — Bridge
                         │
             ┌───────────┴───────────┐
             ↓                       ↓
        Dashboard/API             MQTT
                                     │
                                     ↓
                               IoT Hardware
🌍 Current Delhi Pilot

The current configuration contains 10 representative Delhi wards/areas:

Ward / Area	Zone	Type
Narela	North	Industrial
Rohini	North-West	Residential
Dwarka	South-West	Residential
Connaught Place	Central	Commercial
Chandni Chowk	Central	Mixed
Saket	South	Commercial
Lajpat Nagar	South	Commercial
Karawal Nagar	North-East	Industrial
Mustafabad	East	Industrial
Wazirpur	North-West	Industrial

The architecture is intended to be extensible beyond these initial wards.

📡 Data Sources

The current implementation integrates external environmental data sources including:

Data	Source	Purpose
AQI	WAQI	AQI monitoring
PM2.5 / PM10 / NO₂	WAQI	Pollutant intelligence
Wind speed / direction	OpenWeatherMap	Atmospheric analysis
Temperature	OpenWeatherMap	Weather features
Humidity	OpenWeatherMap	Weather features
Satellite / meteorological inputs	Ingestion modules	Extended environmental intelligence

API availability and exact pollutant coverage depend on the configured external service and location.

🏛️ P-GRAP Governance Layer

The governance layer evaluates pollution conditions and maps them to mitigation logic.

The current implementation uses AQI-based decision thresholds:

Stage	AQI	Example Response
Normal	≤ 100	Monitoring
Advisory	101–200	Advisory actions
Action	201–300	Targeted mitigation
Emergency	301–400	Stronger restrictions
Severe	401+	Emergency-level response

The governance layer is designed to separate:

Environmental observation
        ↓
Pollution assessment
        ↓
Governance stage
        ↓
Ward-level decision
        ↓
Mitigation / alert
🤖 Multi-Agent System

The agent layer provides specialized components for different responsibilities.

AQI Agent

Responsible for AQI-related environmental analysis and decision inputs.

Weather Agent

Handles weather information relevant to pollution analysis.

AURA Agent

Coordinates higher-level environmental intelligence and agent workflows.

Multi-Agent System

Provides orchestration between specialized agents.

MQTT Client

Provides communication between software agents and IoT components.

Telegram Dispatcher

Provides an external notification/alert channel.

The architecture allows additional specialist agents to be added without restructuring the entire system.

🧠 Intelligence Layer

The intelligence layer contains the machine-learning components of the platform.

Temporal Fusion Transformer

The repository contains a TFT-based forecasting pipeline for temporal environmental prediction.

The intelligence layer includes:

TFT inference engine
trained model artifacts
feature metadata
quantile model artifacts
forecasting support

The model layer is designed to provide predictive information that can subsequently be consumed by governance and agentic components.

👁️ Vision Intelligence

The intelligence layer also contains a vision-processing component intended to extend the platform beyond purely numerical pollution data.

This provides an architectural path toward incorporating visual environmental observations into the overall decision pipeline.

🔌 IoT & Hardware Layer

Project S.A.A.S. includes an embedded hardware component for connecting software decisions to physical mitigation infrastructure.

Current repository components include:

Hardware/
├── esp32_scrubber.ino
└── sensor_calibration.h

The ESP32 layer is designed to interface with environmental sensing and mitigation hardware.

Communication can be integrated through MQTT:

Agent Decision
      ↓
MQTT
      ↓
ESP32
      ↓
Mitigation Hardware

This creates the foundation for a closed-loop:

Sense → Predict → Decide → Act

architecture.

🌐 API & Dashboard

The repository contains an API layer and browser-based dashboard.

API

Located in:

api/main.py

The API provides the backend interface for exposing system functionality.

Dashboard

Located in:

dashboard/index.html

The dashboard provides a lightweight interface for visualizing environmental and system information.

💾 Database & State Management

The repository contains a dedicated database layer:

db/
├── memory_store.py
├── models.py
└── session.py

The bridge layer additionally provides state management for inter-module communication and persistent runtime state.

Runtime-generated state and cache files are intentionally excluded from version control where appropriate.

🛡️ Reliability & Bug Fixes

The current version includes fixes for several identified reliability issues.

Issue	Resolution
Empty JSON state causing crashes	Safe state loading
Ward key corruption	Ward-key normalization
Duplicate alerts	Cooldown / deduplication logic
Wind unit mismatch	Explicit unit conversion
Unsafe JSON writes	Atomic file replacement
Incorrect pollutant field	Correct WAQI data handling
Incomplete pollutant retrieval	Multi-pollutant handling
Raw PM2.5 treated directly as AQI	AQI conversion logic

These fixes were introduced to improve runtime stability and data correctness.

🧪 Testing

Tests are located under:

tests/

Additional test modules exist at the repository root.

Run the test suite with:

pytest
🐳 Docker

The project contains:

Dockerfile
docker-compose.yml

Docker can be used to provide a reproducible environment for running the application and its supporting services.

⚙️ Installation
1. Clone the repository
git clone https://github.com/MananBhutada/S.A.A.S-v-3.10-bug-fixed-.git
cd S.A.A.S-v-3.10-bug-fixed-
2. Create a virtual environment
Windows
python -m venv venv
venv\Scripts\activate
Linux / macOS
python3 -m venv venv
source venv/bin/activate
3. Install dependencies
pip install -r requirements.txt
🔐 Environment Variables

Create a local .env file.

Do not commit .env to Git.

Example:

WAQI_TOKEN=your_token
OPENWEATHER_API_KEY=your_key
GROQ_API_KEY=your_key

A .env.example file should be used as the template for contributors.

▶️ Running the System
Refresh environmental data
python refresh_data.py
Run continuous refresh
python refresh_data.py --loop
Start the dashboard
python -m http.server 8080

Then open:

http://localhost:8080/dashboard/
Run the AURA agent
python _05_Agent/aura_agent.py
🧩 Development Architecture

The project is intentionally modular.

A contributor working on one subsystem should generally be able to work within its corresponding module:

Ingestion       → 01_Ingestion/
Intelligence    → _02_Intelligence/
Governance      → 03_Governance/
Bridge          → 04_Bridge/
Agents          → _05_Agent/
API             → api/
Dashboard       → dashboard/
Hardware        → Hardware/
Database        → db/
Testing         → tests/

This allows multiple development tracks to progress independently.

🌿 Contribution Workflow

The repository is intended to support collaborative development.

Recommended workflow:

                 master
                    │
       ┌────────────┼────────────┐
       ↓            ↓            ↓
 feature/AI   feature/agents   feature/API
       │            │            │
       └──────── Pull Request ──┘
                    ↓
                 master
Create a feature branch
git checkout master
git pull origin master
git checkout -b feature/your-feature
Commit changes
git add .
git commit -m "feat: describe your change"
Push the branch
git push -u origin feature/your-feature

Then open a Pull Request against master.

🗺️ Development Roadmap

Potential future development areas include:

Improved hyper-local forecasting
Expanded satellite-data integration
More advanced pollution-dispersion modeling
Additional specialized agents
Stronger multi-agent coordination
Production-grade message queues
Real-time streaming pipelines
Expanded IoT actuator control
Authentication and authorization
Production database deployment
Observability and metrics
Cloud deployment
Automated model retraining
Larger geographic coverage
📌 Current Project Status

Project S.A.A.S. currently provides a modular prototype/pilot architecture combining:

Environmental data ingestion
AQI monitoring
Weather integration
ML forecasting infrastructure
P-GRAP governance logic
Multi-agent AI components
State management
API and dashboard components
MQTT communication
ESP32 hardware integration
Automated tests
Docker configuration
CI workflow

The system is structured to evolve from a research/prototype environment toward a deployable environmental intelligence platform.

🔬 Research & Innovation Direction

The platform is designed around the concept of predictive atmospheric governance:

Traditional monitoring

Measure → Display → React


Project S.A.A.S.

Measure → Predict → Reason → Govern → Act

The long-term objective is to combine predictive environmental intelligence with ward-level governance and targeted physical mitigation.

📄 License

This project is licensed under the Apache License 2.0.

See LICENSE for details.


### One correction I'd make before you paste it

I deliberately changed the title from:

> **Smart Air Quality Agent System**

to:

> **Smart Atmospheric Analysis & Suppression**

because your repository has evolved beyond just an AQI agent. The **ingestion → intelligence → governance → agents → hardware** architecture deserves a name that reflects the broader system.

Also, I would **not keep this line from your old README**:

```text
# .env (already configured)
