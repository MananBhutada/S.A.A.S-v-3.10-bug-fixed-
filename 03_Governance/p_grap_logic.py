"""
03_Governance/p_grap_logic.py
Project S.A.A.S. — P-GRAP Economic Threshold Engine (FIXED)
============================================================
P-GRAP = Predictive Graded Response Action Plan

Stages:
  0  Normal    — AQI P90 < 100    — No action
  1  Watch     — AQI P90 100–200  — Public advisory, school alerts
  2  Alert     — AQI P90 200–300  — Scrubbers ON, trucking restricted
  3  Emergency — AQI P90 300–400  — Scrubbers MAX, construction halt, Telegram
  4  Lockdown  — AQI P90 > 400    — Industrial halt, odd-even vehicles

Fixes:
  - Added intent-based AQI adjustment (combustion is more hazardous)
  - Added credit-ledger stage upgrade for high-economic-risk wards
  - Added gateway-ward early-trigger logic
  - Added full action description for each stage
  - Added batch evaluation for all wards
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

log = logging.getLogger("P-GRAP")

PollutionIntent = Literal["dust", "combustion", "mixed"]

# Stage thresholds (P90 AQI)
THRESHOLDS = [100, 200, 300, 400]  # stage 1/2/3/4 trigger points

# Per-stage action descriptions
STAGE_ACTIONS = {
    0: "All systems nominal. Continue monitoring.",
    1: "Issue public health advisory. Alert schools and hospitals.",
    2: (
        "Activate gateway scrubbers. Restrict heavy trucking entry via Singhu/Tikri. "
        "Notify DPCB and municipal commissioner."
    ),
    3: (
        "Emergency scrubbing at maximum capacity. Halt all construction within 5km radius. "
        "Suspend biomass burning permits. Telegram alert to ops team and DPCC."
    ),
    4: (
        "CITY LOCKDOWN PROTOCOL. Industrial activity suspended. "
        "Odd-even vehicle scheme activated. Schools closed. "
        "Emergency hotline open. Coordinate with SAFAR and IMD."
    ),
}

# Economic credit thresholds that force stage upgrade
# If credit_score >= this and computed stage <= upgrade_below, bump by 1
CREDIT_UPGRADE_TABLE = [
    {"min_credit": 0.90, "upgrade_below": 4},  # Always upgrade highest-risk wards
    {"min_credit": 0.75, "upgrade_below": 3},
]

# Combustion pollution is ~1.3× more hazardous than equivalent dust AQI
# because of VOCs, PAHs, and ultra-fine PM < 1μm (not captured in standard AQI)
COMBUSTION_HAZARD_MULTIPLIER = 1.30
MIXED_HAZARD_MULTIPLIER = 1.10


def evaluate_stage(
    p90_aqi: float,
    credit_score: float,
    intent: PollutionIntent,
    is_gateway: bool = False,
) -> tuple[int, str]:
    """
    Evaluate P-GRAP stage for a single ward.

    Parameters
    ----------
    p90_aqi      : TFT P90 forecast AQI
    credit_score : Economic risk weight (0–1)
    intent       : Classified pollution source
    is_gateway   : Gateway wards (Narela, Alipur) trigger one stage earlier

    Returns
    -------
    (stage, action_description)
    """
    # 1. Apply hazard multiplier based on pollution intent
    if intent == "combustion":
        effective_aqi = p90_aqi * COMBUSTION_HAZARD_MULTIPLIER
    elif intent == "mixed":
        effective_aqi = p90_aqi * MIXED_HAZARD_MULTIPLIER
    else:
        effective_aqi = p90_aqi

    # 2. Compute base stage from thresholds
    stage = 0
    for threshold in THRESHOLDS:
        if effective_aqi >= threshold:
            stage += 1

    # 3. Gateway early-trigger: if plume is at the border, escalate by 1
    if is_gateway and stage < 4:
        stage += 1
        log.debug("Gateway escalation applied")

    # 4. Credit-ledger upgrade
    for rule in CREDIT_UPGRADE_TABLE:
        if credit_score >= rule["min_credit"] and stage < rule["upgrade_below"]:
            stage = min(stage + 1, 4)
            log.debug("Credit-ledger upgrade: score=%.2f → stage %d", credit_score, stage)
            break

    stage = min(stage, 4)
    action = STAGE_ACTIONS[stage]
    log.info("P-GRAP evaluation: AQI_eff=%.0f, intent=%s, stage=%d", effective_aqi, intent, stage)
    return stage, action


def evaluate_all_wards(bridge_path: Path) -> list[dict]:
    """
    Batch-evaluate all wards from bridge state.
    Returns list of {ward, stage, action} dicts sorted by stage descending.
    """
    if not bridge_path.exists():
        log.warning("Bridge state not found at %s", bridge_path)
        return []

    with open(bridge_path) as f:
        state = json.load(f)

    results = []
    for ward_name, w in state.get("wards", {}).items():
        p90 = w.get("forecast_p90", w.get("aqi_current", 0))
        credit = w.get("credit_score", 0.5)
        intent = w.get("intent", "mixed")
        is_gw = ward_name in {"Narela", "Alipur"}

        stage, action = evaluate_stage(
            p90_aqi=p90,
            credit_score=credit,
            intent=intent,
            is_gateway=is_gw,
        )
        results.append(
            {
                "ward": ward_name,
                "stage": stage,
                "p90_aqi": p90,
                "intent": intent,
                "credit_score": credit,
                "action": action,
            }
        )

    results.sort(key=lambda x: (-x["stage"], -x["credit_score"]))
    return results


def pgrap_summary(bridge_path: Path) -> str:
    """Return a human-readable P-GRAP summary for ops dashboard."""
    results = evaluate_all_wards(bridge_path)
    if not results:
        return "No ward data available."

    lines = ["P-GRAP City Summary", "=" * 40]
    for r in results:
        lines.append(
            f"Stage {r['stage']}  {r['ward']:<20s}  AQI P90={r['p90_aqi']:.0f}  "
            f"intent={r['intent']:<12s}  {r['action'][:60]}"
        )
    return "\n".join(lines)
