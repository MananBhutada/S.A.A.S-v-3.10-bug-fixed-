# 🌬️ Project S.A.A.S.

### Smart Atmospheric Analysis & Suppression

> **An AI-powered atmospheric intelligence and pollution mitigation platform for hyper-local environmental monitoring, predictive pollution forecasting, multi-agent governance, and targeted physical intervention.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PyTorch](https://img.shields.io/badge/PyTorch-ML-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?logo=githubactions&logoColor=white)](https://github.com/features/actions)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

---

## 🌍 Overview

**Project S.A.A.S. — Smart Atmospheric Analysis & Suppression** is a modular AI + IoT platform engineered to transform conventional air-quality monitoring into a **predictive, intelligent, coordinated, and actionable environmental management system**.

Instead of stopping at:

```text
"Air quality is bad."

S.A.A.S. is designed to answer:

Where is pollution increasing?
        ↓
Why is it increasing?
        ↓
Where is it likely to spread?
        ↓
What regulatory action is required?
        ↓
Which agents should respond?
        ↓
Which mitigation infrastructure should activate?
        ↓
Did the intervention change the situation?

The platform combines environmental intelligence, machine learning, multi-agent orchestration, governance logic, IoT communication, and physical mitigation into a single modular architecture.

Core capabilities
Real-world environmental data ingestion
Ward-level AQI intelligence
PM2.5 / PM10 and pollutant analysis
Meteorological data integration
Temporal pollution forecasting
Wind-aware pollution-spread reasoning
P-GRAP governance evaluation
Multi-agent AI orchestration
LLM-assisted reasoning workflows
MQTT-based agent communication
ESP32-based IoT integration
Targeted scrubber / mitigation control
Persistent system state
API infrastructure
Web dashboard
Database layer
Docker-based deployment
Automated testing
GitHub Actions CI
🧠 System Philosophy

S.A.A.S. follows an observe → analyze → predict → reason → govern → coordinate → act architecture.

                    ┌─────────────────────┐
                    │   ENVIRONMENT       │
                    │ Air / Weather / IoT │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │      INGESTION      │
                    │ WAQI / OWM / Data   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    INTELLIGENCE     │
                    │ Forecasting / ML    │
                    │ Pollution Analysis  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │     GOVERNANCE      │
                    │ P-GRAP / Policies   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   AGENT ORCHESTR.   │
                    │ AQI / Weather /     │
                    │ AURA / MQTT Agents  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │     MITIGATION      │
                    │ Scrubber / ESP32 /  │
                    │ Physical Actuation  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    MONITORING       │
                    │ State / Logs / API  │
                    │ Dashboard / DB      │
                    └─────────────────────┘
🚀 Key Features
1. Real-World Environmental Data

The system is designed around actual environmental data rather than static demonstration values.

AQI and pollutants

AQI-related information is obtained through WAQI, providing access to air-quality observations associated with real monitoring stations.

The system can work with pollutants including:

AQI
PM2.5
PM10
NO₂
Meteorological intelligence

OpenWeatherMap provides environmental context such as:

Wind speed
Wind direction
Temperature
Humidity

Meteorological information is important because pollution is not spatially static.

Wind conditions can influence how pollution moves between neighboring areas.

🗺️ Ward-Level Intelligence

The current system models 10 representative Delhi wards / zones for localized environmental reasoning.

Ward	Zone	Type
Narela	North	Industrial
Rohini	Northwest	Residential
Dwarka	Southwest	Residential
Connaught Place	Central	Commercial
Chandni Chowk	Central	Mixed
Saket	South	Commercial
Lajpat Nagar	South	Commercial
Karawal Nagar	Northeast	Industrial
Mustafabad	East	Industrial
Wazirpur	Northwest	Industrial

Each ward can be evaluated independently before being incorporated into broader system-level reasoning.

This provides a foundation for moving from city-wide AQI reporting toward hyper-local environmental intelligence.

📈 Predictive Intelligence

The intelligence layer contains temporal forecasting infrastructure designed to analyze environmental trends rather than simply report current measurements.

The repository includes a Temporal Fusion Transformer (TFT) based forecasting pipeline.

Historical Environmental Data
            │
            ▼
     Feature Engineering
            │
            ▼
     Temporal Processing
            │
            ▼
       TFT Engine
            │
            ▼
   Future Pollution Trend
            │
            ▼
   Governance / Agent Layer

The forecasting architecture is intended to support questions such as:

Is pollution increasing?
Is the current trend likely to persist?
Which ward may experience worsening conditions?
Can an emerging pollution event be detected before the AQI threshold is crossed?

This shifts the platform from purely reactive monitoring toward predictive environmental management.

🌬️ Meteorological Reasoning

Pollution movement is strongly influenced by atmospheric conditions.

S.A.A.S. incorporates wind information into its environmental reasoning pipeline.

A simplified representation is:

                    Wind Direction
                         →
                         →
        ┌─────────┐   ┌─────────┐
        │ Ward A  │ → │ Ward B  │
        └─────────┘   └─────────┘
                           │
                           ▼
                     Possible Spread
                           │
                           ▼
                    Ward C / Region

The system therefore does not treat every ward as an isolated point.

Instead, neighboring regions can be considered in terms of:

Pollution intensity
Wind direction
Wind speed
Relative location
Potential downstream impact
🏛️ P-GRAP Governance

The governance layer translates pollution conditions into policy-oriented actions.

The current implementation uses AQI thresholds to determine the corresponding P-GRAP stage.

Stage	AQI Range	Representative Action
Normal	≤ 100	No major intervention
Stage 1	101–200	Advisory measures
Stage 2	201–300	Strong mitigation measures
Stage 3	301–400	Emergency restrictions
Stage 4	401+	Severe emergency measures

The governance layer is deliberately separated from the machine-learning layer.

This allows:

ML predicts conditions
        ↓
Governance evaluates policy
        ↓
Agents coordinate response
        ↓
Hardware executes mitigation

This separation makes the architecture easier to modify as policy rules evolve.

🤖 Multi-Agent Architecture

One of the central components of S.A.A.S. is its multi-agent architecture.

Instead of forcing one monolithic model to perform every task, the platform separates responsibilities between specialized agents.

Current agent components include:

AQI Agent
Weather Agent
AURA Agent
MQTT Client
Multi-Agent System
Telegram Dispatch

Conceptually:

                       ┌──────────────┐
                       │ Orchestrator │
                       └───────┬──────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    ┌───────────┐        ┌───────────┐        ┌───────────┐
    │ AQI Agent │        │Weather    │        │ AURA Agent│
    │           │        │Agent      │        │           │
    └─────┬─────┘        └─────┬─────┘        └─────┬─────┘
          │                    │                    │
          └────────────────────┼────────────────────┘
                               │
                               ▼
                       Decision / Action
                               │
                               ▼
                         MQTT / Hardware

This architecture enables specialized reasoning while keeping the system modular.

🧩 LLM-Assisted Reasoning

The agent layer provides infrastructure for integrating LLM-based reasoning into environmental workflows.

Rather than positioning an LLM as the sole decision-maker, the architecture can use LLMs as a reasoning component alongside deterministic systems.

For example:

Sensor / API Data
       ↓
Deterministic Processing
       ↓
ML Forecast
       ↓
Policy Evaluation
       ↓
LLM-Assisted Reasoning
       ↓
Agent Decision
       ↓
Physical / Digital Action

This approach is intended to combine:

Deterministic systems + machine learning + agentic reasoning.

📡 MQTT & Agent Communication

The system includes MQTT-oriented communication infrastructure for connecting software agents with external or physical components.

Conceptually:

Agent
  │
  │ MQTT
  ▼
Message Broker
  │
  ├──────────────► Another Agent
  │
  └──────────────► IoT Device
                         │
                         ▼
                     ESP32
                         │
                         ▼
                  Mitigation System

This creates a bridge between the digital intelligence layer and physical infrastructure.

⚙️ IoT & Hardware Layer

The repository contains ESP32-oriented hardware code and sensor calibration definitions.

Environmental Intelligence
          │
          ▼
      Agent Decision
          │
          ▼
      MQTT Command
          │
          ▼
        ESP32
          │
          ▼
   Physical Controller
          │
          ▼
   Pollution Mitigation

The hardware layer is intentionally separated from the higher-level intelligence and governance components.

This makes it possible to develop and test software intelligence without tightly coupling the entire system to a specific physical device.

🔄 End-to-End Pipeline

The overall system can be summarized as:

┌──────────────────────┐
│ Environmental Sources│
│ WAQI / OWM / Sensors │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│      Ingestion       │
│ Data Collection      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│     Intelligence     │
│ ML / Forecasting     │
│ Weather Analysis     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│      Governance      │
│ AQI / P-GRAP Logic   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   Multi-Agent Layer  │
│ Reasoning / Routing  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Communication Layer  │
│ MQTT / State / APIs  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│      Mitigation      │
│ IoT / ESP32 / Device │
└──────────────────────┘
🏗️ Repository Architecture

The repository is organized into modular layers:

PROJECT_SAAS_BUGFIXED/
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
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── pyrightconfig.json
└── refresh_data.py
🧪 Testing & Reliability

The repository includes automated tests covering core system functionality.

Test modules include:

Agent behavior
Smoke tests
Fallback behavior
Rate limiting
Weather services
General system functionality

The project also contains a GitHub Actions workflow for automated CI execution.

The objective is to ensure that changes to individual modules can be validated before being integrated into the broader system.

🐳 Containerization

The project includes Docker configuration for reproducible environments.

Available infrastructure includes:

Dockerfile
docker-compose.yml
.dockerignore

Containerization provides a consistent environment for:

Application execution
Dependency management
Service orchestration
Deployment preparation
Team development
📊 Dashboard

The repository includes a web dashboard for visualizing system information.

The dashboard is designed to provide a human-readable interface over the underlying environmental intelligence and agent state.

The architecture allows the dashboard to evolve independently from the underlying intelligence and governance layers.

🔐 Configuration & Secrets

API credentials should never be committed to the repository.

Create a local .env file containing credentials such as:

WAQI_TOKEN=your_token
OPENWEATHER_API_KEY=your_key
GROQ_API_KEY=your_key

The .env file is intentionally excluded through .gitignore.

For collaborators, provide a .env.example template containing variable names but never real credentials.

📡 Data Sources
Data	Source	Purpose
AQI	WAQI	Air-quality intelligence
PM2.5	WAQI	Fine particulate monitoring
PM10	WAQI	Particulate monitoring
NO₂	WAQI	Pollutant monitoring
Wind	OpenWeatherMap	Atmospheric transport
Temperature	OpenWeatherMap	Environmental context
Humidity	OpenWeatherMap	Environmental context
Satellite / environmental inputs	Ingestion modules	Extended intelligence pipeline
🐛 Engineering & Bug-Fix History

The current repository represents a bug-fixed iteration of the S.A.A.S. platform.

Major fixes include:

Bug	Resolution
Empty JSON state causing json.load() failure	Safe state loading
Ward key corruption	Ward-key cleaning logic
Duplicate alerts	Cooldown / deduplication mechanism
Wind unit mismatch	Explicit m/s → km/h conversion
Unsafe state writes	Atomic file replacement
Incorrect pollutant field usage	Correct WAQI data handling
Single-pollutant assumptions	Multi-pollutant processing
Raw PM2.5 incorrectly treated as AQI	Piecewise AQI conversion

These fixes improve the robustness of the state-management, environmental-data, and agent communication layers.
...
🧠 Why S.A.A.S.?

Traditional air-quality systems often follow:

Measure → Display

S.A.A.S. aims toward:

Measure
   ↓
Understand
   ↓
Predict
   ↓
Reason
   ↓
Govern
   ↓
Coordinate
   ↓
Mitigate
   ↓
Monitor Again

The important architectural shift is from passive monitoring toward an integrated environmental intelligence and intervention loop.

🎯 Current Scope

The current implementation provides infrastructure across:

Environmental Intelligence
AQI ingestion
Weather ingestion
Pollutant processing
Temporal forecasting infrastructure
Wind-aware reasoning
Governance
P-GRAP evaluation
Ward-level decision logic
Policy-oriented actions
Agentic AI
Specialized agents
Agent orchestration
LLM integration points
Inter-agent communication
IoT
MQTT communication
ESP32 integration
Hardware control interfaces
Software Infrastructure
API layer
Database layer
State management
Dashboard
Docker
Automated tests
CI
🚀 Quick Start
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
4. Configure environment variables

Create:

.env

and add:

WAQI_TOKEN=your_token
OPENWEATHER_API_KEY=your_key
GROQ_API_KEY=your_key
5. Refresh environmental data
python refresh_data.py

For continuous refresh:

python refresh_data.py --loop
6. Start the dashboard
python -m http.server 8080

Then open:

http://localhost:8080/dashboard/
7. Run the agent layer
python _05_Agent/aura_agent.py
🛠️ Development Workflow

The repository is designed for collaborative development.

Recommended workflow:

main
 │
 ├── feature/ingestion
 ├── feature/intelligence
 ├── feature/governance
 ├── feature/agents
 ├── feature/hardware
 └── feature/dashboard

Developers should work on isolated branches and merge changes through pull requests.

Example:

git checkout -b feature/new-agent

Make changes:

git add .
git commit -m "Add new environmental agent"

Push:

git push -u origin feature/new-agent

Then open a pull request.

🧱 Technology Stack
Layer	Technology
Language	Python
API	FastAPI
ML	PyTorch
Forecasting	Temporal Fusion Transformer
Data Processing	NumPy / Pandas
Database	PostgreSQL-compatible architecture
Messaging	MQTT
Hardware	ESP32
Dashboard	HTML / JavaScript
Containers	Docker
CI	GitHub Actions
Testing	Pytest
Configuration	.env / JSON
Version Control	Git / GitHub
🔮 Future Development

The architecture provides a foundation for expanding toward:

More Delhi wards
Additional cities
Higher-resolution pollution forecasting
More advanced spatial modeling
Computer-vision-based pollution analysis
More sophisticated agent planning
Autonomous mitigation scheduling
Additional IoT devices
Distributed sensor networks
Historical analytics
Improved feedback loops
Advanced environmental simulation
Production cloud deployment
Scalable multi-city governance

The modular design allows these capabilities to be introduced incrementally without requiring a complete rewrite of the system.

📜 License

This project is licensed under the Apache License 2.0.

See the LICENSE file for the complete license text.

👨‍💻 Project

Project S.A.A.S.

Smart Atmospheric Analysis & Suppression

An experimental AI + IoT architecture for moving environmental monitoring from:

Observation → Intelligence → Governance → Action

Built as a modular research and engineering platform combining machine learning, multi-agent systems, environmental data, governance logic, and physical IoT intervention.


