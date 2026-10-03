"""
S.A.A.S cloud worker.

Single long-running process for EC2:
  1. Refresh live environmental data from configured providers.
  2. Run the real ward-agent / multi-agent evaluation against that refreshed state.
  3. Repeat on a fixed cadence.

Important:
- Never generates synthetic AQI/weather values.
- Never runs 03_Governance/orchestrator.py because that legacy heartbeat contains
  a random-data simulator.
- Forecast values must come from the configured forecasting model; unavailable
  forecasts stay unavailable rather than being fabricated.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from refresh_data import fetch_all_wards
from _05_Agent.multi_agent_system import MultiAgentSystem

log = logging.getLogger("CLOUD-WORKER")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

INTERVAL_SECONDS = max(60, int(os.getenv("SAAS_CYCLE_INTERVAL_SECONDS", "300")))
STARTUP_DELAY_SECONDS = max(0, int(os.getenv("SAAS_STARTUP_DELAY_SECONDS", "10")))

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    log.info("Shutdown signal received: %s", signum)
    _shutdown = True


def _run_cycle(mas: MultiAgentSystem, cycle: int) -> None:
    started = datetime.now(timezone.utc)
    log.info("=== Cloud cycle %d starting ===", cycle)

    success, failed = fetch_all_wards()
    if success == 0:
        raise RuntimeError("Live data refresh returned zero successful wards")

    log.info(
        "Live refresh complete: %d wards updated, %d failed",
        success,
        failed,
    )

    # Run the existing real agent stack against the refreshed bridge state.
    # It may call the configured AQI providers and forecasting model as part of
    # WardAgent evaluation; it does not generate random sensor data here.
    mas.trigger_cycle(cycle)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    log.info("=== Cloud cycle %d complete in %.1fs ===", cycle, elapsed)


def main() -> None:
    global _shutdown

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if STARTUP_DELAY_SECONDS:
        log.info("Waiting %ds for container startup...", STARTUP_DELAY_SECONDS)
        time.sleep(STARTUP_DELAY_SECONDS)

    mas = MultiAgentSystem()
    mas.start()

    cycle = 0
    try:
        while not _shutdown:
            cycle += 1
            try:
                _run_cycle(mas, cycle)
            except Exception:
                log.exception("Cloud cycle %d failed; preserving service uptime", cycle)

            if _shutdown:
                break

            log.info("Next cloud cycle in %ds", INTERVAL_SECONDS)
            end = time.monotonic() + INTERVAL_SECONDS
            while not _shutdown and time.monotonic() < end:
                time.sleep(min(5, max(0.1, end - time.monotonic())))
    finally:
        mas.stop()
        log.info("Cloud worker stopped cleanly")


if __name__ == "__main__":
    main()
