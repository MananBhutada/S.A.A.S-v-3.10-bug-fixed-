# Runtime and operations notes

## API process

The container entrypoint starts the FastAPI application with Uvicorn:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
```

This serves the web UI and API routes. It should not be assumed to launch the ingestion loop or the multi-agent worker automatically. Configure those workers as separate services/processes in the target runtime.

## Bridge state and freshness

The API reads JSON state under `04_Bridge/`. In particular:

- `aura_master_state.json` contains the current shared state used by ward and dashboard endpoints.
- `agent_comms_log.json` backs the communication view.
- `pgrap_audit_trail.json` backs the governance audit/alert view.

A successful HTTP response only confirms that the API returned a response. Check the bridge timestamps and the `/health` payload before describing the environmental data as current.

The `POST /api/refresh` endpoint reloads the state visible to the API from disk. It does not call external environmental providers or trigger a complete agent cycle.

## Health checks

Useful checks during a deployment:

1. Open `/health` and inspect `status`, `last_cycle_utc`, `data_age_seconds`, `wards_loaded`, and dependency status.
2. Open `/api/wards` and verify that the ward count and timestamps match the expected bridge snapshot.
3. Open `/api/comms` and `/api/audit` when checking persisted agent and governance activity.
4. Check worker logs separately; API health alone does not establish that background workers are running.

## Secrets

Supply provider credentials through environment variables or the deployment platform's secret manager. Keep `.env`, tokens, and private credentials out of commits and container images.
