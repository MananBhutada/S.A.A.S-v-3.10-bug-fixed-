# Architecture notes

S.A.A.S. separates environmental observation, prediction, governance, agent coordination, and presentation. The separation is intentional: a forecast is not a policy decision, a policy decision is not an agent message, and a software command is not proof of physical actuation.

## Data path

```text
Environmental providers / sensors
              |
              v
        Ingestion modules
              |
              v
    Bridge state (04_Bridge/)
       |        |        |
       v        v        v
   Forecast  Governance  Agent workflows
       |        |        |
       +--------+--------+
                |
                v
        FastAPI read layer
                |
          +-----+------+
          |            |
          v            v
      Dashboard    3D Digital Twin
```

The diagram is a logical overview, not a guarantee that every component runs in one process. The API reads the bridge state; ingestion and agent workers may be separate processes depending on the deployment.

## Sources of truth

- **Observed values:** ward readings and timestamps stored in bridge state.
- **Forecast values:** P10/P50/P90 fields produced by the forecasting engine, subject to model availability and its configured fallback.
- **Governance values:** P-GRAP stage, intent, and related fields written by governance workflows.
- **Agent activity:** messages and audit entries persisted by the agent/bridge components.
- **Geographic context:** ward polygons and map features used to orient the Digital Twin. Roads, buildings, parks, and waterways are presentation context, not AQI observations or model output.

## Boundaries to preserve

1. Keep observed AQI separate from forecast quantiles.
2. Do not synthesize live values when bridge data is missing.
3. Do not infer successful physical mitigation from a queued command, a UI animation, or a software-side state flag.
4. Keep geographic presentation geometry separate from environmental measurements.
5. Treat stale bridge timestamps as stale data, even if the API process is healthy.

These boundaries make the dashboard easier to interpret and keep demonstrations aligned with what the system has actually observed or executed.
