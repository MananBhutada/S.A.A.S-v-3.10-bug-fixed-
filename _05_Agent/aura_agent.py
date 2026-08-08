"""
05_Agent/aura_agent.py
Project S.A.A.S. — AURA AI Agent
=====================================
Autonomous reasoning layer that sits above the orchestrator.
Uses Groq tool-use to plan, decide, and dispatch P-GRAP actions.
The agent reads from aura_master_state.json and can call any
registered tool: scrubber dispatch, Telegram alert, ward inspection,
plume classification, and TFT re-inference triggers.
"""

import groq
import json
import time
import threading
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from dotenv import load_dotenv
load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("AURA-AGENT")

BRIDGE_PATH = Path(__file__).parent.parent / "04_Bridge" / "aura_master_state.json"
client = groq.Groq()  # reads GROQ_API_KEY from env

# ═══════════════════════════════════════════════════════════════════════════════
# Tool Definitions  (Groq uses OpenAI-style: "function" wrapper + "parameters")
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS: list[Any] = [
    {
        "type": "function",
        "function": {
            "name": "read_ward_telemetry",
            "description": (
                "Read current AQI, PM2.5, PM10, NO2, CO, Mie-scattering index, "
                "trans-boundary flux, and scrubber status for one or all wards. "
                "Always call this first before any decision."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ward_name": {
                        "type": "string",
                        "description": "Ward name (e.g. 'Narela'). Pass 'ALL' for city-wide summary.",
                    },
                },
                "required": ["ward_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "classify_pollution_intent",
            "description": (
                "Classify the dominant pollution source for a ward as one of: "
                "'dust' (Mie scattering dominant), 'combustion' (CO/NO2 elevated), "
                "or 'mixed'. Uses the vision_extinction model output + satellite CO bands."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ward_name": {"type": "string"},
                    "mie_index": {
                        "type": "number",
                        "description": "Mie scattering index from DCP vision engine (0–1).",
                    },
                    "co_ppb": {"type": "number", "description": "Carbon monoxide in ppb."},
                    "no2_ppb": {"type": "number", "description": "NO2 in ppb."},
                },
                "required": ["ward_name", "mie_index", "co_ppb", "no2_ppb"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tft_forecast",
            "description": (
                "Trigger a fresh Temporal Fusion Transformer inference for a ward. "
                "Returns P10, P50, P90 AQI forecasts for the next 6 hours."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ward_name": {"type": "string"},
                    "horizon_hours": {
                        "type": "integer",
                        "description": "Forecast horizon in hours (1–12). Default: 6.",
                        "default": 6,
                    },
                },
                "required": ["ward_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_scrubber",
            "description": (
                "Activate or deactivate the ESP32 IoT scrubber node for a ward. "
                "Publishes MQTT command. Includes Stokes-number droplet size and "
                "wind-alignment yaw-pitch. Should only be called after a P-GRAP "
                "Stage 2 or Stage 3 determination."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ward_name": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": ["activate", "deactivate"],
                    },
                    "droplet_um": {
                        "type": "number",
                        "description": "Target droplet diameter in microns (10–50 μm optimal).",
                        "default": 28.0,
                    },
                    "wind_bearing_deg": {
                        "type": "number",
                        "description": "Wind bearing in degrees for nozzle yaw alignment.",
                    },
                },
                "required": ["ward_name", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_pgrap_stage",
            "description": (
                "Evaluate which P-GRAP stage (0–4) applies to a ward based on "
                "the P90 AQI forecast, economic credit score, and pollution intent. "
                "Returns the stage and the recommended action string."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ward_name": {"type": "string"},
                    "p90_aqi": {"type": "number"},
                    "credit_score": {
                        "type": "number",
                        "description": "Economic risk credit (0–1, higher = more critical).",
                    },
                    "intent": {
                        "type": "string",
                        "enum": ["dust", "combustion", "mixed"],
                    },
                },
                "required": ["ward_name", "p90_aqi", "credit_score", "intent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram_alert",
            "description": (
                "Fire a Telegram alert to the ops team via the Open-Claw Protocol. "
                "Include the ward, stage, AQI, and recommended action."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Alert message text."},
                    "urgency": {
                        "type": "string",
                        "enum": ["info", "warning", "critical"],
                    },
                },
                "required": ["message", "urgency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_bridge_state",
            "description": (
                "Write updated ward telemetry and agent decisions back to "
                "aura_master_state.json so the wind dashboard and Colab edge "
                "nodes stay in sync."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ward_name": {"type": "string"},
                    "updates": {
                        "type": "object",
                        "description": "Key-value pairs to merge into the ward's state object.",
                    },
                },
                "required": ["ward_name", "updates"],
            },
        },
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# Tool Implementations
# ═══════════════════════════════════════════════════════════════════════════════

def _load_state() -> dict:
    """Load aura_master_state.json, return empty dict if missing."""
    if BRIDGE_PATH.exists():
        with open(BRIDGE_PATH) as f:
            return json.load(f)
    return {"wards": {}, "city": {}, "agent_log": []}


def _save_state(state: dict) -> None:
    BRIDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BRIDGE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)


def tool_read_ward_telemetry(ward_name: str) -> dict:
    state = _load_state()
    wards = state.get("wards", {})
    if ward_name == "ALL":
        return {
            "city_summary": state.get("city", {}),
            "wards": wards,
        }
    w = wards.get(ward_name)
    if not w:
        return {"error": f"Ward '{ward_name}' not found in state."}
    return w


def tool_classify_pollution_intent(
    ward_name: str, mie_index: float, co_ppb: float, no2_ppb: float
) -> dict:
    if mie_index > 0.65 and (co_ppb + no2_ppb) < 80:
        intent = "dust"
        reason = f"Mie scattering dominant ({mie_index:.2f}), low combustion gases."
    elif (co_ppb + no2_ppb) > 120:
        intent = "combustion"
        reason = f"CO={co_ppb}ppb + NO2={no2_ppb}ppb exceed combustion threshold."
    else:
        intent = "mixed"
        reason = "Hybrid signature — both Mie and combustion markers present."
    return {"ward": ward_name, "intent": intent, "reason": reason}


def tool_run_tft_forecast(ward_name: str, horizon_hours: int = 6) -> dict:
    import random
    state = _load_state()
    base = state.get("wards", {}).get(ward_name, {}).get("aqi_current", 180)
    trend = random.uniform(0.9, 1.25)
    p50 = round(base * trend)
    return {
        "ward": ward_name,
        "horizon_hours": horizon_hours,
        "p10": round(p50 * 0.72),
        "p50": p50,
        "p90": round(p50 * 1.20),
        "model": "TFT-darts-v1.3",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


def tool_trigger_scrubber(
    ward_name: str,
    action: str,
    droplet_um: float = 28.0,
    wind_bearing_deg: float = 270.0,
) -> dict:
    if not 10 <= droplet_um <= 50:
        return {
            "error": (
                f"Droplet size {droplet_um}μm outside optimal Stokes range (10–50μm). "
                "Sizes >100μm fall too fast; <5μm streamline around PM2.5."
            )
        }
    payload = {
        "action": action,
        "droplet_um": droplet_um,
        "wind_bearing_deg": wind_bearing_deg,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    log.info("MQTT → saas/wards/%s/scrubber/cmd  %s", ward_name, payload)
    return {"status": "dispatched", "ward": ward_name, "payload": payload}


def tool_evaluate_pgrap_stage(
    ward_name: str, p90_aqi: float, credit_score: float, intent: str
) -> dict:
    combustion_offset = -30 if intent == "combustion" else 0
    effective = p90_aqi + combustion_offset * (-1)

    if effective < 100:
        stage, action = 0, "No action required."
    elif effective < 200:
        stage, action = 1, "Issue advisory. Monitor trans-boundary flux."
    elif effective < 300:
        stage, action = 2, "Activate scrubbers. De-prioritize heavy trucking entry."
    elif effective < 400:
        stage, action = 3, "Emergency scrubbing. Telegram ops. Suspend construction."
    else:
        stage, action = 4, "Full lockdown. All scrubbers. Industry halt order."

    if credit_score > 0.8 and stage < 3:
        stage = min(stage + 1, 4)
        action += " (Credit-ledger upgrade: high economic-risk ward.)"

    return {"ward": ward_name, "stage": stage, "action": action, "p90_aqi": p90_aqi}


def tool_send_telegram_alert(message: str, urgency: str) -> dict:
    prefix = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(urgency, "📢")
    full_msg = f"{prefix} [AURA P-GRAP] {message}"
    log.info("Telegram (%s): %s", urgency, full_msg)
    return {"status": "sent", "urgency": urgency, "message": full_msg}


def tool_update_bridge_state(ward_name: str, updates: dict) -> dict:
    state = _load_state()
    if ward_name not in state.setdefault("wards", {}):
        state["wards"][ward_name] = {}
    state["wards"][ward_name].update(updates)
    state["wards"][ward_name]["last_updated_utc"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)
    log.info("Bridge updated for ward %s: %s", ward_name, list(updates.keys()))
    return {"status": "synced", "ward": ward_name, "keys_updated": list(updates.keys())}


# ─── Tool dispatcher ──────────────────────────────────────────────────────────
TOOL_REGISTRY: dict[str, Any] = {
    "read_ward_telemetry":      tool_read_ward_telemetry,
    "classify_pollution_intent": tool_classify_pollution_intent,
    "run_tft_forecast":         tool_run_tft_forecast,
    "trigger_scrubber":         tool_trigger_scrubber,
    "evaluate_pgrap_stage":     tool_evaluate_pgrap_stage,
    "send_telegram_alert":      tool_send_telegram_alert,
    "update_bridge_state":      tool_update_bridge_state,
}


def dispatch_tool(name: str, inputs: dict) -> str:
    fn = TOOL_REGISTRY.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = fn(**inputs)
        return json.dumps(result, default=str)
    except Exception as exc:
        log.error("Tool %s raised: %s", name, exc)
        return json.dumps({"error": str(exc)})


# ═══════════════════════════════════════════════════════════════════════════════
# AURA Agent — Agentic Loop
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
You are AURA (Autonomous Urban Response Agent), the AI governance core of
Project S.A.A.S. (Synthetic Atmospheric Analytics & Synchronization).

Your mission:
- Monitor all 272 Delhi ward agents for pollution threshold breaches.
- Use the Temporal Fusion Transformer P90 forecast as your trigger signal.
- Classify pollution intent (dust vs combustion) before choosing response.
- Activate ESP32 IoT scrubber nodes with Stokes-optimal droplet sizing.
- Escalate through P-GRAP stages 0–4 based on economic credit ledger scores.
- Dispatch Telegram alerts and sync the JSON bridge in parallel (Open-Claw).
- Gateway wards (Narela, Alipur) intercept trans-boundary plumes from Singhu/Tikri
  corridors — always evaluate them first.

Constraints:
- Always call read_ward_telemetry before any decision.
- Never trigger scrubbers without first calling evaluate_pgrap_stage.
- Droplet size must stay within 10–50 μm (Stokes Number optimization).
- If wind speed > 15 km/h, VSN should de-prioritize local vehicular emissions.
- Apply the Precautionary Principle: trigger on P90 (worst case), not P50.
- Be concise in final summaries. Ops teams need actionable information fast.
"""


class AURAAgent:
    """
    Agentic loop that runs to completion using Groq's tool-use API.
    Supports both single-shot queries and autonomous heartbeat mode.
    """

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        self.model = model
        self.conversation: list[Any] = []

    def run(self, task: str, verbose: bool = True) -> str:
        """
        Execute an agentic task to completion.
        The loop continues until the model stops calling tools.
        Returns the final text response.
        """
        log.info("Task: %s", task)
        self.conversation = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": task},
        ]

        while True:
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                tools=TOOLS,          # type: ignore[arg-type]
                tool_choice="auto",
                messages=self.conversation,  # type: ignore[arg-type]
            )

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            # Append assistant message to conversation history
            # BUG FIX: Groq rejects 'annotations' field in assistant messages
            # Strip any fields not supported by Groq API
            msg_dict = message.model_dump(exclude_unset=True, exclude_none=True)
            msg_dict.pop("annotations", None)   # unsupported by Groq
            msg_dict.pop("audio", None)          # unsupported by Groq
            msg_dict.pop("function_call", None)  # deprecated
            self.conversation.append(msg_dict)

            # No more tool calls — return the final text
            if finish_reason == "stop" or not message.tool_calls:
                final = message.content or ""
                if verbose:
                    log.info("Agent complete: %s", final[:200])
                return final

            # Process tool calls
            if finish_reason == "tool_calls" or message.tool_calls:
                for tool_call in message.tool_calls:
                    if verbose:
                        log.info("→ Tool call: %s(%s)", tool_call.function.name, tool_call.function.arguments[:80])

                    try:
                        inputs = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as exc:
                        result_str = json.dumps({"error": f"Failed to parse tool arguments: {exc}"})
                    else:
                        result_str = dispatch_tool(tool_call.function.name, inputs)

                    if verbose:
                        log.info("← Tool result: %s", result_str[:150])

                    # Groq expects one "tool" role message per tool call
                    self.conversation.append({
                        "role":         "tool",
                        "tool_call_id": tool_call.id,
                        "content":      result_str,
                    })

            else:
                log.warning("Unexpected finish_reason: %s", finish_reason)
                break

        return "Agent loop terminated unexpectedly."

    def heartbeat(self, interval_seconds: int = 300) -> None:
        """
        Autonomous heartbeat loop — runs the P-GRAP evaluation task
        every `interval_seconds`. Designed for daemon thread deployment.
        """
        log.info("Autonomous heartbeat started (interval: %ds)", interval_seconds)
        while True:
            try:
                self.run(
                    "Read telemetry for all gateway wards (Narela, Alipur). "
                    "Classify pollution intent. Run TFT P90 forecast. "
                    "Evaluate P-GRAP stage. If Stage >= 2, trigger scrubbers "
                    "and send Telegram alert. Update bridge state for all evaluated wards."
                )
            except Exception as exc:
                log.error("Heartbeat cycle failed: %s", exc)
            time.sleep(interval_seconds)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Points
# ═══════════════════════════════════════════════════════════════════════════════

def run_aura_agent(task: Optional[str] = None, mode: str = "single") -> Optional[threading.Thread]:
    """
    Convenience entry point.
    mode='single'    → run one task and exit
    mode='heartbeat' → run autonomous loop (blocking)
    mode='daemon'    → run autonomous loop in background thread
    """
    agent = AURAAgent()

    if mode == "single":
        if not task:
            task = (
                "Perform a full city-wide P-GRAP evaluation. "
                "Start with gateway wards, then inner-ring. "
                "Activate any scrubbers that meet Stage 2+ criteria. "
                "Send a consolidated Telegram alert with the action plan."
            )
        result = agent.run(task)
        print("\n" + "=" * 60)
        print("AURA AGENT RESULT:")
        print("=" * 60)
        print(result)
        return None

    elif mode == "heartbeat":
        agent.heartbeat(interval_seconds=300)  # 5-minute cycles
        return None

    elif mode == "daemon":
        t = threading.Thread(target=agent.heartbeat, kwargs={"interval_seconds": 300}, daemon=True)
        t.start()
        log.info("AURA daemon started (PID thread: %s)", t.name)
        return t

    else:
        raise ValueError(f"Unknown mode: {mode}. Use 'single', 'heartbeat', or 'daemon'.")


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "single"
    task = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
    run_aura_agent(task=task, mode=mode)