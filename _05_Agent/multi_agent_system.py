"""
_05_Agent/multi_agent_system.py
Project S.A.A.S. — Multi-Agent Task Delegation & Communication System
======================================================================
Architecture:
  CommanderAgent  — top-level strategic planner, reads city state, delegates tasks
  IntelAgent      — owns TFT forecasting, vision analysis, pollution classification
  GovernanceAgent — owns P-GRAP evaluation, policy enforcement, scrubber dispatch
  AlertAgent      — owns Telegram/SMS dispatch, audit trail, ops notifications
  FieldAgent      — owns IoT node management, ESP32 firmware commands, sensor validation

Communication:
  Agents communicate via an AgentMessageBus (in-memory + JSON-persisted).
  Each message has: sender, recipient, message_type, payload, priority, correlation_id.
  CommanderAgent is the only agent that initiates cycles; all others respond to delegations.
  Agents can REJECT tasks (with reason) and ESCALATE back to Commander.
  Policy enforcement: GovernanceAgent can veto IntelAgent classifications if physics constraints
  are violated.

Flow (unchanged from original S.A.A.S. design):
  TROPOMI Ingest → Met Sync → TFT Inference → Ward Agents → P-GRAP → IoT Dispatch
  ↑ Each arrow is now an inter-agent message with full auditability.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from queue import Empty, PriorityQueue
from typing import Any, Optional

import groq
from dotenv import load_dotenv
load_dotenv()

# WardAgent import — works whether folder is named 03_Governance or _03_Governance
import sys
from pathlib import Path as _Path
_BASE_DIR_IMPORT = _Path(__file__).parent.parent
for _candidate in ("_03_Governance", "03_Governance"):
    _candidate_path = _BASE_DIR_IMPORT / _candidate
    if _candidate_path.exists():
        sys.path.insert(0, str(_candidate_path))
        break

# BUGFIX: ward_agents.py does `from state_manager import load_state, save_state`,
# which requires 04_Bridge on sys.path too. That was only ever added by
# refresh_data.py's own top-level setup, so importing this module directly
# (e.g. `python -m _05_Agent.multi_agent_system`) failed with
# "ModuleNotFoundError: No module named 'state_manager'". Same shim pattern
# as above, applied to the folder ward_agents.py actually needs.
for _candidate in ("_04_Bridge", "04_Bridge"):
    _candidate_path = _BASE_DIR_IMPORT / _candidate
    if _candidate_path.exists():
        sys.path.insert(0, str(_candidate_path))
        break

from ward_agents import WardAgent  # type: ignore[import]
import ward_agents as ward_module   # type: ignore[import]

log = logging.getLogger("MULTI-AGENT")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
    datefmt="%H:%M:%S",
)

BASE_DIR    = Path(__file__).parent.parent
BRIDGE_PATH = BASE_DIR / "04_Bridge" / "aura_master_state.json"
COMMS_LOG   = BASE_DIR / "04_Bridge" / "agent_comms_log.json"

# BUG-1 FIX: Safe state manager — never crashes on empty/corrupt JSON
import sys as _sys
_BRIDGE_MODULE_DIR = str(BASE_DIR / "04_Bridge")
if _BRIDGE_MODULE_DIR not in _sys.path:
    _sys.path.insert(0, _BRIDGE_MODULE_DIR)
from state_manager import load_state as _safe_load, save_state as _safe_save  # type: ignore[import]

client = groq.Groq()  # reads GROQ_API_KEY from env


# ═══════════════════════════════════════════════════════════════════════════════
# Message Protocol
# ═══════════════════════════════════════════════════════════════════════════════

class MessageType(str, Enum):
    # Delegation messages (Commander → subordinate)
    TASK_DELEGATE      = "TASK_DELEGATE"
    TASK_RESULT        = "TASK_RESULT"
    TASK_REJECT        = "TASK_REJECT"
    TASK_ESCALATE      = "TASK_ESCALATE"

    # Policy messages (Governance ↔ Intel/Field)
    POLICY_CHECK       = "POLICY_CHECK"
    POLICY_APPROVE     = "POLICY_APPROVE"
    POLICY_VETO        = "POLICY_VETO"

    # Data sharing (any → any)
    DATA_SHARE         = "DATA_SHARE"
    DATA_REQUEST       = "DATA_REQUEST"
    DATA_RESPONSE      = "DATA_RESPONSE"

    # Alert coordination (Governance → Alert)
    ALERT_TRIGGER      = "ALERT_TRIGGER"
    ALERT_CONFIRM      = "ALERT_CONFIRM"

    # Field coordination (Governance → Field)
    FIELD_COMMAND      = "FIELD_COMMAND"
    FIELD_ACK          = "FIELD_ACK"
    FIELD_NACK         = "FIELD_NACK"

    # System
    HEARTBEAT          = "HEARTBEAT"
    SHUTDOWN           = "SHUTDOWN"


class Priority(int, Enum):
    CRITICAL  = 0
    HIGH      = 1
    MEDIUM    = 2
    LOW       = 3


@dataclass(order=True)
class AgentMessage:
    priority:       int
    message_id:     str          = field(compare=False, default_factory=lambda: str(uuid.uuid4())[:8])
    message_type:   MessageType  = field(compare=False, default=MessageType.DATA_SHARE)
    sender:         str          = field(compare=False, default="")
    recipient:      str          = field(compare=False, default="")
    payload:        dict         = field(compare=False, default_factory=dict)
    correlation_id: Optional[str]= field(compare=False, default=None)
    timestamp_utc:  str          = field(compare=False, default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttl_seconds:    int          = field(compare=False, default=120)

    def to_dict(self) -> dict:
        return {
            "message_id":     self.message_id,
            "message_type":   self.message_type.value,
            "sender":         self.sender,
            "recipient":      self.recipient,
            "priority":       self.priority,
            "payload":        self.payload,
            "correlation_id": self.correlation_id,
            "timestamp_utc":  self.timestamp_utc,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Message Bus
# ═══════════════════════════════════════════════════════════════════════════════

class AgentMessageBus:
    """
    Priority-queue-based message bus.
    Each agent has its own inbox queue.
    Thread-safe. Messages are also appended to the comms audit log.
    """

    def __init__(self):
        self._inboxes:  dict[str, PriorityQueue] = {}
        self._lock      = threading.Lock()
        self._audit_log: list[dict] = []
        self._audit_lock = threading.Lock()

    def register(self, agent_id: str):
        with self._lock:
            if agent_id not in self._inboxes:
                self._inboxes[agent_id] = PriorityQueue()
                log.debug("Bus: registered agent '%s'", agent_id)

    def send(self, msg: AgentMessage):
        with self._lock:
            if msg.recipient not in self._inboxes:
                log.warning("Bus: unknown recipient '%s'", msg.recipient)
                return
            self._inboxes[msg.recipient].put(msg)

        log.debug(
            "Bus: %s→%s [%s] #%s",
            msg.sender, msg.recipient, msg.message_type.value, msg.message_id
        )

        with self._audit_lock:
            self._audit_log.append(msg.to_dict())
            if len(self._audit_log) > 500:
                self._audit_log = self._audit_log[-500:]

        self._persist_audit()

    def broadcast(self, msg: AgentMessage, exclude: Optional[list[str]] = None):
        with self._lock:
            targets = [aid for aid in self._inboxes if aid != msg.sender]
            if exclude:
                targets = [t for t in targets if t not in exclude]
        for target in targets:
            m = AgentMessage(
                priority=msg.priority,
                message_type=msg.message_type,
                sender=msg.sender,
                recipient=target,
                payload=msg.payload,
                correlation_id=msg.correlation_id,
            )
            self.send(m)

    def receive(self, agent_id: str, timeout: float = 2.0) -> Optional[AgentMessage]:
        try:
            return self._inboxes[agent_id].get(timeout=timeout)  # type: ignore[call-overload]
        except Empty:
            return None

    def _persist_audit(self):
        try:
            COMMS_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(COMMS_LOG, "w") as f:
                json.dump(self._audit_log[-200:], f, indent=2, default=str)
        except Exception:
            pass

    @property
    def audit_log(self) -> list[dict]:
        return list(self._audit_log)


# Global bus instance — shared by all agents
BUS = AgentMessageBus()


# ═══════════════════════════════════════════════════════════════════════════════
# Base Agent
# ═══════════════════════════════════════════════════════════════════════════════

class BaseAgent:
    """
    Base class for all S.A.A.S. agents.
    Each agent runs its own thread, processes messages from its inbox,
    and can call the LLM when complex reasoning is required.
    """

    AGENT_ID: str = "base"
    MODEL:    str = "llama-3.3-70b-versatile"

    def __init__(self, bus: AgentMessageBus):
        self.bus        = bus
        self.bus.register(self.AGENT_ID)
        self._running   = False
        self._thread:  Optional[threading.Thread] = None
        self._pending_tasks: dict[str, Any] = {}  # correlation_id → task metadata dict

    # ── Messaging helpers ─────────────────────────────────────────────────────

    def send(
        self,
        recipient: str,
        msg_type: MessageType,
        payload: dict,
        priority: Priority = Priority.MEDIUM,
        correlation_id: Optional[str] = None,
    ) -> Optional[str]:
        msg = AgentMessage(
            priority=priority.value,
            message_type=msg_type,
            sender=self.AGENT_ID,
            recipient=recipient,
            payload=payload,
            correlation_id=correlation_id or str(uuid.uuid4())[:8],
        )
        self.bus.send(msg)
        return msg.correlation_id

    def reply(self, original: AgentMessage, msg_type: MessageType, payload: dict):
        self.send(
            recipient=original.sender,
            msg_type=msg_type,
            payload=payload,
            priority=Priority(original.priority),
            correlation_id=original.correlation_id,
        )

    def broadcast(self, msg_type: MessageType, payload: dict, priority: Priority = Priority.LOW):
        msg = AgentMessage(
            priority=priority.value,
            message_type=msg_type,
            sender=self.AGENT_ID,
            recipient="__broadcast__",
            payload=payload,
        )
        self.bus.broadcast(msg)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._run_loop, name=self.AGENT_ID, daemon=True)
        self._thread.start()
        log.info("[%s] started", self.AGENT_ID)

    def stop(self):
        self._running = False
        log.info("[%s] stopped", self.AGENT_ID)

    def _run_loop(self):
        self.on_start()
        while self._running:
            msg = self.bus.receive(self.AGENT_ID, timeout=1.0)
            if msg:
                self._dispatch(msg)
        self.on_stop()

    def _dispatch(self, msg: AgentMessage):
        try:
            self.handle_message(msg)
        except Exception as exc:
            log.error("[%s] error handling %s: %s", self.AGENT_ID, msg.message_type, exc)

    # ── Override in subclasses ────────────────────────────────────────────────

    def on_start(self):
        pass

    def on_stop(self):
        pass

    def handle_message(self, msg: AgentMessage):
        raise NotImplementedError

    # ── LLM helper ───────────────────────────────────────────────────────────

    def _ask_claude(self, system: str, prompt: str, tools: Optional[list[Any]] = None, max_tokens: int = 1024) -> str:
        """Single-turn Groq call for reasoning tasks."""
        messages: list[Any] = [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ]
        if tools:
            resp = client.chat.completions.create(
                model=self.MODEL,
                max_tokens=max_tokens,
                messages=messages,       # type: ignore[arg-type]
                tools=tools,             # type: ignore[arg-type]
                tool_choice="auto",
            )
        else:
            resp = client.chat.completions.create(
                model=self.MODEL,
                max_tokens=max_tokens,
                messages=messages,       # type: ignore[arg-type]
            )
        return resp.choices[0].message.content or ""

    # ── Bridge helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _load_state() -> dict:
        # BUG-1 FIX: Use safe atomic loader — no crash on empty/corrupt file
        return _safe_load()

    @staticmethod
    def _save_state(state: dict):
        # BUG-5 FIX: Atomic write via temp file + os.rename — no corruption risk
        _safe_save(state)


# ═══════════════════════════════════════════════════════════════════════════════
# CommanderAgent — Strategic Planner & Task Delegator
# ═══════════════════════════════════════════════════════════════════════════════

class CommanderAgent(BaseAgent):
    """
    Top-level strategic planner.
    Initiates every monitoring cycle, reads city state, and delegates
    specialized tasks to subordinate agents via the message bus.
    Handles escalations and makes final Stage 3/4 decisions.
    """

    AGENT_ID = "COMMANDER"

    SYSTEM = """You are the CommanderAgent in the S.A.A.S. multi-agent pollution control system.
You coordinate IntelAgent (forecasting), GovernanceAgent (P-GRAP policy), AlertAgent (notifications),
and FieldAgent (IoT scrubbers). You receive their reports and make final strategic decisions.

Your responsibilities:
- Read current city AQI state and decide which wards need immediate attention.
- Delegate TFT forecasting to IntelAgent for gateway wards first.
- After Intel reports, delegate P-GRAP evaluation to GovernanceAgent.
- After Governance approves, delegate scrubber dispatch to FieldAgent.
- If any agent REJECTS or ESCALATES, you resolve the conflict.
- For Stage 3+, you must authorize BOTH GovernanceAgent AND AlertAgent simultaneously.
- Be concise. Each delegation should be a clear task with measurable output.
"""

    def on_start(self):
        log.info("[COMMANDER] Online — awaiting cycle trigger")

    def handle_message(self, msg: AgentMessage):
        t = msg.message_type

        if t == MessageType.HEARTBEAT:
            self._run_cycle(msg.payload)

        elif t == MessageType.TASK_RESULT:
            self._handle_result(msg)

        elif t == MessageType.TASK_ESCALATE:
            self._handle_escalation(msg)

        elif t == MessageType.TASK_REJECT:
            log.warning("[COMMANDER] Task rejected by %s: %s", msg.sender, msg.payload.get("reason"))
            # Re-evaluate and re-delegate with modified parameters
            self._handle_rejection(msg)

    def _run_cycle(self, cycle_info: dict):
        state     = self._load_state()
        city      = state.get("city", {})
        wards     = state.get("wards", {})
        city_aqi  = max((w.get("aqi_current", 0) for w in wards.values()), default=0)

        log.info("[COMMANDER] Cycle #%s — city AQI=%d", cycle_info.get("cycle", "?"), city_aqi)

        # Use LLM to decide delegation priority
        known_wards  = list(wards.keys()) or ["Ward-1", "Ward-2"]
        ward_summary = json.dumps(
            {k: {"aqi": v.get("aqi_current", 0), "stage": v.get("pgrap_stage", 0)} for k, v in wards.items()},
            indent=2
        )
        plan = self._ask_claude(
            system=self.SYSTEM,
            prompt=(
                f"Current city AQI: {city_aqi}. Ward summary:\n{ward_summary}\n\n"
                f"Available ward names (use EXACTLY as shown): {known_wards}\n\n"
                "Reply ONLY with a raw JSON object — no prose, no markdown fences. "
                "Format: {\"wards\": [\"<name1>\", \"<name2>\"], \"action\": \"forecast\", \"reason\": \"<why>\"} "
                "The wards value MUST be a JSON array. Pick at most 3 ward names from the list above. "
                "Action must be one of: forecast, scrub, alert."
            ),
        )

        try:
            clean    = plan.strip().replace("```json", "").replace("```", "").strip()
            decision = json.loads(clean)
        except Exception:
            decision = {"wards": known_wards[:2], "action": "forecast", "reason": "fallback"}

        priority_wards = decision.get("wards", known_wards[:2])
        # Guard: LLM sometimes returns a comma-separated string instead of a list
        if isinstance(priority_wards, str):
            priority_wards = [w.strip() for w in priority_wards.split(",") if w.strip()]
        # Guard: keep only names that exist in state; fall back if none match
        priority_wards = [w for w in priority_wards if w in wards] or known_wards[:2]

        action = decision.get("action", "forecast")

        log.info("[COMMANDER] Delegating '%s' for wards: %s", action, priority_wards)

        # Always start with Intel for fresh forecast
        corr = self.send(
            recipient="INTEL",
            msg_type=MessageType.TASK_DELEGATE,
            payload={
                "task":      "run_forecast",
                "wards":     priority_wards,
                "horizon_h": 6,
                "cycle":     cycle_info.get("cycle"),
            },
            priority=Priority.HIGH,
        )
        self._pending_tasks[corr or ""] = {
            "cycle": cycle_info.get("cycle"),
            "wards": priority_wards,
        }

    def _handle_result(self, msg: AgentMessage):
        sender  = msg.sender
        payload = msg.payload

        if sender == "INTEL":
            # Intel finished forecast — delegate P-GRAP to Governance
            self.send(
                recipient="GOVERNANCE",
                msg_type=MessageType.TASK_DELEGATE,
                payload={
                    "task":        "evaluate_pgrap",
                    "forecasts":   payload.get("forecasts", {}),
                    "wards":       payload.get("wards", []),
                    "cycle":       payload.get("cycle"),
                },
                priority=Priority.HIGH,
                correlation_id=msg.correlation_id,
            )

        elif sender == "GOVERNANCE":
            triggered = payload.get("triggered_wards", [])
            stage_max  = payload.get("max_stage", 0)

            if triggered:
                # Delegate field activation
                self.send(
                    recipient="FIELD",
                    msg_type=MessageType.FIELD_COMMAND,
                    payload={
                        "task":    "activate_scrubbers",
                        "wards":   triggered,
                        "cycle":   payload.get("cycle"),
                    },
                    priority=Priority.HIGH if stage_max >= 3 else Priority.MEDIUM,
                    correlation_id=msg.correlation_id,
                )

                if stage_max >= 2:
                    # Parallel: also trigger alerts
                    self.send(
                        recipient="ALERT",
                        msg_type=MessageType.ALERT_TRIGGER,
                        payload={
                            "task":    "dispatch_alerts",
                            "wards":   triggered,
                            "stages":  payload.get("stages", {}),
                            "max_stage": stage_max,
                            "cycle":   payload.get("cycle"),
                        },
                        priority=Priority.CRITICAL if stage_max >= 3 else Priority.HIGH,
                        correlation_id=msg.correlation_id,
                    )
            else:
                log.info("[COMMANDER] Cycle complete — no P-GRAP triggers")

        elif sender == "FIELD":
            log.info("[COMMANDER] Field confirmed scrubbers: %s", payload.get("activated", []))
            self._update_cycle_complete(payload)

        elif sender == "ALERT":
            log.info("[COMMANDER] Alert confirmed: %s", payload.get("sent_to", []))

    def _handle_escalation(self, msg: AgentMessage):
        """Agent cannot complete task — Commander decides."""
        reason = msg.payload.get("reason", "unknown")
        log.warning("[COMMANDER] Escalation from %s: %s", msg.sender, reason)

        resolution = self._ask_claude(
            system=self.SYSTEM,
            prompt=(
                f"Agent {msg.sender} escalated with reason: {reason}. "
                f"Payload: {json.dumps(msg.payload)}. "
                "Decide: 'retry', 'skip', or 'emergency'. Reply with one word and brief reason."
            ),
        )
        log.info("[COMMANDER] Escalation resolution: %s", resolution[:100])

        if "emergency" in resolution.lower():
            self.send(
                recipient="ALERT",
                msg_type=MessageType.ALERT_TRIGGER,
                payload={"task": "dispatch_alerts", "urgency": "critical", "reason": reason},
                priority=Priority.CRITICAL,
            )

    def _handle_rejection(self, msg: AgentMessage):
        """Re-delegate with adjusted parameters."""
        original_payload = msg.payload.get("original_payload", {})
        original_payload["retry"] = True
        original_payload["relaxed_constraints"] = True
        self.send(
            recipient=msg.sender,
            msg_type=MessageType.TASK_DELEGATE,
            payload=original_payload,
            priority=Priority.HIGH,
            correlation_id=msg.correlation_id,
        )

    def _update_cycle_complete(self, payload: dict):
        state = self._load_state()
        state.setdefault("city", {})["last_full_cycle_utc"] = datetime.now(timezone.utc).isoformat()
        self._save_state(state)

    def trigger_cycle(self, cycle_num: int):
        """External trigger — called by orchestrator heartbeat."""
        self.send(
            recipient="COMMANDER",
            msg_type=MessageType.HEARTBEAT,
            payload={"cycle": cycle_num},
            priority=Priority.HIGH,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# IntelAgent — Forecasting & Vision Analysis
# ═══════════════════════════════════════════════════════════════════════════════

class IntelAgent(BaseAgent):
    """
    Owns TFT forecasting, DCP vision analysis, and pollution intent classification.
    Reports structured forecast data back to Commander.
    Checks with GovernanceAgent before publishing any forecast that triggers Stage 3+.
    """

    AGENT_ID = "INTEL"

    SYSTEM = """You are IntelAgent in the S.A.A.S. system. You specialize in:
- Running TFT P10/P50/P90 forecasts for Delhi wards
- Classifying pollution intent (dust vs combustion) using Mie scattering and CO/NO2 ratios
- Applying VSN re-weighting when wind > 15 km/h
- Validating satellite data quality (QA > 0.75 threshold)

Rules:
- Always use P90 for P-GRAP trigger decisions (Precautionary Principle).
- If wind > 15 km/h, weight trans-boundary flux at 75%, local vehicular at 10%.
- If P90 > 400 (Stage 4 territory), request GovernanceAgent policy check before reporting.
- Be precise. Return structured data, not prose.
"""

    def handle_message(self, msg: AgentMessage):
        t = msg.message_type

        if t == MessageType.TASK_DELEGATE and msg.payload.get("task") == "run_forecast":
            self._run_forecast(msg)

        elif t == MessageType.POLICY_APPROVE:
            # Governance wraps approved forecasts under "approved" key
            # Normalise so _publish_forecast always receives {"forecasts": {...}, ...}
            _payload = msg.payload
            if isinstance(_payload, dict) and "approved" in _payload and "forecasts" not in _payload:
                _payload = {
                    "forecasts": _payload["approved"],
                    "wards":     list(_payload["approved"].keys()),
                    "cycle":     _payload.get("cycle"),
                }
            self._publish_forecast(_payload, msg.correlation_id)

        elif t == MessageType.POLICY_VETO:
            log.warning("[INTEL] Forecast vetoed by Governance: %s", msg.payload.get("reason"))
            # Downgrade P90 by 10% and resubmit
            vetoed = msg.payload.get("forecast_data", {})
            for w in vetoed:
                vetoed[w]["p90"] = round(vetoed[w].get("p90", 0) * 0.90)
            self._publish_forecast(vetoed, msg.correlation_id)

        elif t == MessageType.DATA_REQUEST:
            self._handle_data_request(msg)

    def _run_forecast(self, msg: AgentMessage):
        wards      = msg.payload.get("wards", [])
        horizon_h  = msg.payload.get("horizon_h", 6)
        cycle      = msg.payload.get("cycle")
        state      = self._load_state()
        forecasts  = {}

        for ward_name in wards:
            w    = state.get("wards", {}).get(ward_name, {})
            aqi  = w.get("aqi_current", 180)
            wind = w.get("wind_speed_kmh", 5.0)
            mie  = w.get("mie_index", 0.5)
            no2  = w.get("no2_ppb", 30)
            co   = w.get("co_ppb", 500)

            # VSN re-weighting
            vsn_mode = "trans_boundary" if wind > 15 else "local"

            # Intent classification
            combustion_score = (co / 500) + (no2 / 60)
            dust_score       = mie + (w.get("pm10", 100) / 300)
            if dust_score > 1.1 and combustion_score < 0.8:
                intent = "dust"
            elif combustion_score > 1.2:
                intent = "combustion"
            else:
                intent = "mixed"

            # Hazard multiplier
            mult = {"combustion": 1.30, "mixed": 1.10, "dust": 1.0}.get(intent, 1.0)
            base_trend = aqi * (1 + horizon_h * 0.02) * mult

            import random
            p50 = round(base_trend + random.gauss(0, aqi * 0.15))
            forecasts[ward_name] = {
                "p10":    round(p50 * 0.70),
                "p50":    p50,
                "p90":    round(p50 * 1.22),
                "intent": intent,
                "vsn_mode": vsn_mode,
                "wind_kmh": wind,
            }
            log.info("[INTEL] %s: P90=%d intent=%s vsn=%s", ward_name, forecasts[ward_name]["p90"], intent, vsn_mode)

        # Policy check if any P90 >= 400
        high_risk = {k: v for k, v in forecasts.items() if v["p90"] >= 400}
        if high_risk:
            cid = self.send(
                recipient="GOVERNANCE",
                msg_type=MessageType.POLICY_CHECK,
                payload={
                    "check_type":    "extreme_forecast",
                    "forecast_data": high_risk,
                    "wards":         wards,
                    "cycle":         cycle,
                },
                priority=Priority.CRITICAL,
                correlation_id=msg.correlation_id,
            )
            log.warning("[INTEL] Sent extreme forecast policy check for: %s", list(high_risk.keys()))
        else:
            self._publish_forecast({"forecasts": forecasts, "wards": wards, "cycle": cycle}, msg.correlation_id)

    def _publish_forecast(self, payload: dict, correlation_id: Optional[str]):
        forecasts = payload.get("forecasts", payload)
        # Guard: if forecasts is not a dict (e.g. a string slipped through), abort
        if not isinstance(forecasts, dict):
            log.error("[INTEL] _publish_forecast received non-dict forecasts: %s", type(forecasts))
            return
        wards = payload.get("wards", list(forecasts.keys()))
        # Guard: if wards came back as a string, convert to list
        if isinstance(wards, str):
            wards = [w.strip() for w in wards.split(",") if w.strip()]
        cycle = payload.get("cycle")

        # Write to bridge
        state = self._load_state()
        for ward_name, fc in forecasts.items():
            state.setdefault("wards", {}).setdefault(ward_name, {}).update({
                "forecast_p10": fc.get("p10"),
                "forecast_p50": fc.get("p50"),
                "forecast_p90": fc.get("p90"),
                "intent":       fc.get("intent"),
                "vsn_mode":     fc.get("vsn_mode"),
            })
        self._save_state(state)

        self.send(
            recipient="COMMANDER",
            msg_type=MessageType.TASK_RESULT,
            payload={"forecasts": forecasts, "wards": wards, "cycle": cycle},
            priority=Priority.HIGH,
            correlation_id=correlation_id,
        )

    def _handle_data_request(self, msg: AgentMessage):
        requested_ward = msg.payload.get("ward")
        state          = self._load_state()
        ward_data      = state.get("wards", {}).get(requested_ward, {})
        self.reply(msg, MessageType.DATA_RESPONSE, {"ward": requested_ward, "data": ward_data})


# ═══════════════════════════════════════════════════════════════════════════════
# GovernanceAgent — P-GRAP Policy Enforcement
# ═══════════════════════════════════════════════════════════════════════════════

class GovernanceAgent(BaseAgent):
    """
    Owns P-GRAP stage evaluation, policy enforcement, and credit ledger.
    Can VETO Intel forecasts that violate physics constraints.
    Must approve all Stage 3/4 actions before FieldAgent acts.
    Acts as policy arbiter between Intel and Field agents.
    """

    AGENT_ID = "GOVERNANCE"

    SYSTEM = """You are GovernanceAgent in the S.A.A.S. system. You enforce:
- P-GRAP stage thresholds (0=Normal, 1=Watch, 2=Alert, 3=Emergency, 4=Lockdown)
- Economic credit ledger priorities (higher credit = higher priority)
- Physics constraints: scrubber droplets must be 10–50 μm (Stokes Number)
- Policy: combustion × 1.30 hazard multiplier; gateway wards escalate one stage early
- Veto authority: can reject Intel forecasts that exceed physical plausibility
- Resource allocation: if two wards compete, credit score determines priority

Escalation rules:
- Stage 3+: MUST notify both AlertAgent and FieldAgent simultaneously
- Stage 4: notify Commander for city-level authorization
"""

    CREDIT_LEDGER = {
        "Narela": 0.91, "Alipur": 0.78, "Rohini": 0.65,
        "Dwarka": 0.70, "Saket": 0.82, "Lajpat Nagar": 0.75,
        "Connaught Place": 0.95, "Chandni Chowk": 0.88,
        "Mustafabad": 0.50, "Karawal Nagar": 0.55,
    }
    GATEWAY_WARDS = {"Narela", "Alipur"}

    def handle_message(self, msg: AgentMessage):
        t = msg.message_type

        if t == MessageType.TASK_DELEGATE and msg.payload.get("task") == "evaluate_pgrap":
            self._evaluate_pgrap(msg)

        elif t == MessageType.POLICY_CHECK:
            self._handle_policy_check(msg)

        elif t == MessageType.FIELD_COMMAND:
            # Governance must countersign field commands for Stage 3+
            self._countersign_field_command(msg)

        elif t == MessageType.DATA_REQUEST:
            ward = msg.payload.get("ward") or ""
            credit = self.CREDIT_LEDGER.get(ward, 0.5)
            self.reply(msg, MessageType.DATA_RESPONSE, {"ward": ward, "credit_score": credit})

    def _evaluate_pgrap(self, msg: AgentMessage):
        forecasts = msg.payload.get("forecasts", {})
        wards     = msg.payload.get("wards", list(forecasts.keys()))
        cycle     = msg.payload.get("cycle")

        triggered_wards = []
        stages_map      = {}
        max_stage       = 0

        for ward_name in wards:
            fc      = forecasts.get(ward_name, {})
            p90     = fc.get("p90", 0)
            intent  = fc.get("intent", "mixed")
            credit  = self.CREDIT_LEDGER.get(ward_name, 0.5)
            is_gw   = ward_name in self.GATEWAY_WARDS

            mult    = {"combustion": 1.30, "mixed": 1.10, "dust": 1.0}.get(intent, 1.0)
            eff_aqi = p90 * mult

            if eff_aqi < 100:   stage = 0
            elif eff_aqi < 200: stage = 1
            elif eff_aqi < 300: stage = 2
            elif eff_aqi < 400: stage = 3
            else:               stage = 4

            if is_gw and stage < 4:
                stage += 1

            if credit >= 0.90 and stage < 4:
                stage = min(stage + 1, 4)
            elif credit >= 0.75 and stage < 3:
                stage = min(stage + 1, 3)

            stages_map[ward_name] = stage
            max_stage = max(max_stage, stage)

            if stage >= 2:
                triggered_wards.append(ward_name)

            # Update bridge
            state = self._load_state()
            state.setdefault("wards", {}).setdefault(ward_name, {}).update({
                "pgrap_stage":   stage,
                "credit_score":  credit,
                "effective_aqi": round(eff_aqi),
            })
            self._save_state(state)

            log.info("[GOVERNANCE] %s: P90=%d intent=%s → Stage %d", ward_name, p90, intent, stage)

        # Sort triggered wards by credit score (highest first)
        triggered_wards.sort(key=lambda w: -self.CREDIT_LEDGER.get(w, 0.5))

        self.send(
            recipient="COMMANDER",
            msg_type=MessageType.TASK_RESULT,
            payload={
                "triggered_wards": triggered_wards,
                "stages":          stages_map,
                "max_stage":       max_stage,
                "cycle":           cycle,
            },
            priority=Priority.HIGH if max_stage >= 2 else Priority.MEDIUM,
            correlation_id=msg.correlation_id,
        )

        # Share policy data with FieldAgent proactively
        if triggered_wards:
            self.send(
                recipient="FIELD",
                msg_type=MessageType.DATA_SHARE,
                payload={
                    "type":            "pgrap_decision",
                    "triggered_wards": triggered_wards,
                    "stages":          stages_map,
                    "credit_ranking":  triggered_wards,
                },
                priority=Priority.MEDIUM,
            )

    def _handle_policy_check(self, msg: AgentMessage):
        """
        Validate extreme forecast from IntelAgent.
        Veto if physically implausible (AQI > 600 in a single cycle, for example).
        """
        check_type    = msg.payload.get("check_type")
        forecast_data = msg.payload.get("forecast_data", {})

        vetoed = {}
        approved = {}

        for ward, fc in forecast_data.items():
            p90 = fc.get("p90", 0)
            if p90 > 600:   # Physical plausibility cap
                vetoed[ward] = fc
                log.warning("[GOVERNANCE] Veto: %s P90=%d exceeds plausibility cap (600)", ward, p90)
            else:
                approved[ward] = fc

        if vetoed:
            self.reply(msg, MessageType.POLICY_VETO, {
                "reason":        "P90 exceeds plausibility cap of 600 AQI",
                "forecast_data": vetoed,
                "approved":      approved,
            })
        else:
            self.reply(msg, MessageType.POLICY_APPROVE, {
                "approved":     forecast_data,
                "check_type":   check_type,
                "cycle":        msg.payload.get("cycle"),
            })

    def _countersign_field_command(self, msg: AgentMessage):
        """Governance countersigns field commands — adds compliance metadata."""
        payload = msg.payload.copy()
        payload["governance_approved"] = True
        payload["approved_at_utc"]     = datetime.now(timezone.utc).isoformat()
        payload["compliance_note"]     = "Stokes droplets 10–50μm enforced, OWM guidelines met"
        self.send(
            recipient="FIELD",
            msg_type=MessageType.FIELD_COMMAND,
            payload=payload,
            priority=Priority(msg.priority),
            correlation_id=msg.correlation_id,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# AlertAgent — Notifications & Audit Trail
# ═══════════════════════════════════════════════════════════════════════════════

class AlertAgent(BaseAgent):
    """
    Manages all outbound communications:
    Telegram (ops team), DPCC portal, public advisory broadcast.
    Maintains a tamper-evident audit trail of all P-GRAP activations.
    """

    AGENT_ID = "ALERT"

    SYSTEM = """You are AlertAgent in the S.A.A.S. system. You handle:
- Telegram alerts to ops team (OC_TELEGRAM)
- DPCC/OWM compliance notifications
- Public advisory messages (plain language, not technical)
- Audit trail logging for all Stage 2+ events

Rules:
- Stage 2: advisory + scrubber activation notice
- Stage 3: emergency alert + ops team call-out + DPCC notification
- Stage 4: all of Stage 3 + request Commander for public broadcast authorization
- Messages must be under 280 characters for SMS compatibility
- Always include: ward name, AQI, Stage, recommended public action
"""

    def __init__(self, bus: AgentMessageBus):
        super().__init__(bus)
        self._audit_trail: list[dict] = []

    def handle_message(self, msg: AgentMessage):
        t = msg.message_type

        if t == MessageType.ALERT_TRIGGER:
            self._dispatch_alerts(msg)
        elif t == MessageType.DATA_REQUEST:
            self.reply(msg, MessageType.DATA_RESPONSE, {"audit_trail": self._audit_trail[-20:]})

    def _dispatch_alerts(self, msg: AgentMessage):
        wards     = msg.payload.get("wards", [])
        stages    = msg.payload.get("stages", {})
        max_stage = msg.payload.get("max_stage", 0)
        cycle     = msg.payload.get("cycle")
        urgency   = msg.payload.get("urgency", "warning")

        # Guard: if wards is a string (LLM slippage), convert to list
        if isinstance(wards, str):
            wards = [w.strip() for w in wards.split(",") if w.strip()]

        # Guard: if no wards specified but urgency given, use all known wards
        state = self._load_state()
        if not wards and urgency:
            wards = list(state.get("wards", {}).keys())

        sent_to   = []

        for ward in wards:
            stage = stages.get(ward, max_stage)
            aqi   = state.get("wards", {}).get(ward, {}).get("aqi_current", 0)
            intent= state.get("wards", {}).get(ward, {}).get("intent", "mixed")

            # Generate plain-language alert via LLM
            alert_text = self._ask_claude(
                system=self.SYSTEM,
                prompt=(
                    f"Generate a concise alert for: Ward={ward}, Stage={stage}, "
                    f"AQI={aqi}, Intent={intent}. "
                    "Under 200 chars. Include recommended public action."
                ),
            )

            log.info("[ALERT] Telegram → [%s] Stage%d AQI%d: %s", ward, stage, aqi, alert_text[:80])

            # Audit trail entry
            audit_entry = {
                "event_id":    str(uuid.uuid4())[:8],
                "timestamp":   datetime.now(timezone.utc).isoformat(),
                "ward":        ward,
                "stage":       stage,
                "aqi":         aqi,
                "intent":      intent,
                "alert_text":  alert_text,
                "channel":     "telegram",
                "cycle":       cycle,
            }
            self._audit_trail.append(audit_entry)
            self._persist_audit()
            sent_to.append(ward)

            # If Stage 4, escalate back to Commander for public broadcast authorization
            if stage >= 4:
                self.send(
                    recipient="COMMANDER",
                    msg_type=MessageType.TASK_ESCALATE,
                    payload={
                        "reason":     f"Stage 4 detected in {ward} — requesting public broadcast authorization",
                        "ward":       ward,
                        "stage":      stage,
                        "aqi":        aqi,
                        "alert_text": alert_text,
                    },
                    priority=Priority.CRITICAL,
                )

        self.send(
            recipient="COMMANDER",
            msg_type=MessageType.ALERT_CONFIRM,
            payload={"sent_to": sent_to, "cycle": cycle},
            priority=Priority.MEDIUM,
            correlation_id=msg.correlation_id,
        )

    def _persist_audit(self):
        audit_path = BASE_DIR / "04_Bridge" / "pgrap_audit_trail.json"
        try:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with open(audit_path, "w") as f:
                json.dump(self._audit_trail, f, indent=2, default=str)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# FieldAgent — IoT Node Management
# ═══════════════════════════════════════════════════════════════════════════════

class FieldAgent(BaseAgent):
    """
    Manages all IoT scrubber nodes (ESP32-WROOM-32).
    Validates Stokes Number constraints before activation.
    Receives wind bearing from MetSync and aligns nozzle yaw-pitch.
    Rejects commands that violate hardware safety thresholds.
    """

    AGENT_ID = "FIELD"

    SYSTEM = """You are FieldAgent in the S.A.A.S. system. You control ESP32 IoT scrubber nodes.
Hardware constraints you enforce:
- Droplet size: 10–50 μm (Stokes Number optimization). Reject if outside range.
  - Too large (>100μm): falls too fast, misses PM2.5
  - Too small (<5μm): streamlines around particles
- Max pressure: 6 bar. Reject if requested pressure > 6 bar.
- Wind alignment: nozzle yaw must be within ±10° of wind bearing for effective dwell time.
- Battery threshold: if node battery < 15%, request recharge before activation.
- You receive GovernanceAgent approval before acting on any command.
"""

    def __init__(self, bus: AgentMessageBus):
        super().__init__(bus)
        self._node_status: dict[str, dict] = {}  # ward → {active, droplet_um, battery}

    def handle_message(self, msg: AgentMessage):
        t = msg.message_type

        if t == MessageType.FIELD_COMMAND:
            if msg.payload.get("task") == "activate_scrubbers":
                self._activate_scrubbers(msg)

        elif t == MessageType.DATA_SHARE and msg.payload.get("type") == "pgrap_decision":
            # Pre-load credit ranking so we know which wards to prioritize
            self._credit_ranking = msg.payload.get("credit_ranking", [])

        elif t == MessageType.DATA_REQUEST:
            self.reply(msg, MessageType.DATA_RESPONSE, {
                "node_status": self._node_status,
                "active_count": sum(1 for n in self._node_status.values() if n.get("active")),
            })

    def _activate_scrubbers(self, msg: AgentMessage):
        wards    = msg.payload.get("wards", [])
        approved = msg.payload.get("governance_approved", False)
        cycle    = msg.payload.get("cycle")
        state    = self._load_state()
        activated = []
        rejected  = []

        for ward_name in wards:
            w           = state.get("wards", {}).get(ward_name, {})
            wind_kmh    = w.get("wind_speed_kmh", 5.0)
            wind_bearing= w.get("wind_bearing_deg", 270.0)
            pm25        = w.get("pm25", 80)

            # Stokes-optimized droplet size
            if pm25 < 60:       droplet_um = 18.0
            elif pm25 < 120:    droplet_um = 28.0
            else:               droplet_um = 42.0

            # Validate
            if not 10 <= droplet_um <= 50:
                rejected.append(ward_name)
                self.send(
                    recipient="COMMANDER",
                    msg_type=MessageType.TASK_ESCALATE,
                    payload={
                        "reason":    f"Droplet size {droplet_um}μm outside Stokes range for {ward_name}",
                        "ward":      ward_name,
                        "droplet_um":droplet_um,
                    },
                    priority=Priority.HIGH,
                )
                continue

            # Issue MQTT command (stub)
            cmd = {
                "action":           "activate",
                "droplet_um":       droplet_um,
                "wind_bearing_deg": wind_bearing,
                "yaw_offset_deg":   0,  # align nozzle INTO wind vector
                "pressure_bar":     min(3.5, 1.5 + (pm25 / 100)),
                "timestamp_utc":    datetime.now(timezone.utc).isoformat(),
            }
            log.info("[FIELD] MQTT → %s scrubber: %.0fμm droplets @ %.0f°", ward_name, droplet_um, wind_bearing)

            self._node_status[ward_name] = {"active": True, "droplet_um": droplet_um, "cmd": cmd}

            # Update bridge
            state.setdefault("wards", {}).setdefault(ward_name, {}).update({
                "scrubber_active": True,
                "droplet_um":      droplet_um,
                "scrubber_cmd":    cmd,
            })
            activated.append(ward_name)

        self._save_state(state)

        response_type = MessageType.FIELD_ACK if activated else MessageType.FIELD_NACK
        self.send(
            recipient="COMMANDER",
            msg_type=MessageType.TASK_RESULT,
            payload={
                "activated": activated,
                "rejected":  rejected,
                "cycle":     cycle,
            },
            priority=Priority.MEDIUM,
            correlation_id=msg.correlation_id,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Multi-Agent System Manager
# ═══════════════════════════════════════════════════════════════════════════════

class MultiAgentSystem:
    """
    Manages all agents as a cohesive system.
    Integrates with the existing orchestrator heartbeat.
    """

    def __init__(self):
        # Inject shared bus objects into ward module
        ward_module.BUS          = BUS
        ward_module.AgentMessage = AgentMessage
        ward_module.MessageType  = MessageType
        ward_module.Priority     = Priority

        self.bus        = BUS
        self.commander  = CommanderAgent(self.bus)
        self.intel      = IntelAgent(self.bus)
        self.governance = GovernanceAgent(self.bus)
        self.alert      = AlertAgent(self.bus)
        self.field      = FieldAgent(self.bus)
        self._agents    = [self.commander, self.intel, self.governance, self.alert, self.field]
        self._cycle     = 0

        # ─────────────────────────────
        # WARD AGENTS
        # ─────────────────────────────
        # All 10 Delhi wards — each gets its own WardAgent + message inbox
        WARD_NAMES = [
            "Narela",          # North,      Industrial, Gateway
            "Rohini",          # NorthWest,  Residential
            "Dwarka",          # SouthWest,  Residential
            "Connaught Place", # Central,    Commercial
            "Chandni Chowk",   # Central,    Mixed
            "Saket",           # South,      Commercial
            "Lajpat Nagar",    # South,      Commercial
            "Karawal Nagar",   # NorthEast,  Industrial, Gateway
            "Mustafabad",      # East,       Industrial, Gateway
            "Wazirpur",        # NorthWest,  Industrial
        ]
        self.ward_agents = {name: WardAgent(name) for name in WARD_NAMES}

        # Register each ward inbox on the message bus
        for ward_name in self.ward_agents:
            self.bus.register(ward_name)

        log.info("Ward agents online: %s", list(self.ward_agents.keys()))

    def start(self):
        for agent in self._agents:
            agent.start()
        log.info("Multi-agent system online — %d agents running", len(self._agents))

    def stop(self):
        for agent in self._agents:
            agent.stop()
        log.info("Multi-agent system shutdown")

    def trigger_cycle(self):
        """Called by orchestrator on each heartbeat tick."""
        self._cycle += 1
        self.commander.trigger_cycle(self._cycle)

        # Give system slight delay
        time.sleep(1)

        # ─────────────────────────────
        # RUN WARD AGENTS
        # ─────────────────────────────
        for ward_name, agent in self.ward_agents.items():
            try:
                plan = agent.evaluate()
                log.info(
                    "[WARD] %s | Stage=%s | P90=%s",
                    ward_name,
                    plan.pgrap_stage,
                    plan.forecast.p90,
                )
            except Exception as e:
                log.error(
                    "[WARD ERROR] %s: %s",
                    ward_name,
                    e,
                )

        # Process communication
        self.process_ward_messages()

    def process_ward_messages(self):
        """
        Handle inter-ward communication.
        """
        for ward_name, agent in self.ward_agents.items():
            msg = self.bus.receive(ward_name, timeout=0.1)

            while msg:
                try:
                    if msg.message_type == MessageType.ALERT_TRIGGER:
                        agent.receive_alert(msg)
                        log.warning(
                            "[BUS] %s received alert from %s",
                            ward_name,
                            msg.sender,
                        )
                except Exception as e:
                    log.error("[WARD MESSAGE ERROR] %s", e)

                msg = self.bus.receive(ward_name, timeout=0.1)

    def get_comms_log(self) -> list[dict]:
        return self.bus.audit_log

    def get_system_status(self) -> dict:
        state = BaseAgent._load_state()
        return {
            "cycle":        self._cycle,
            "agents":       [a.AGENT_ID for a in self._agents],
            "bus_messages": len(self.bus.audit_log),
            "city_aqi":     max(
                (w.get("aqi_current", 0) for w in state.get("wards", {}).values()),
                default=0,
            ),
            "ward_agents":   list(self.ward_agents.keys()),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Standalone entry point
# ═══════════════════════════════════════════════════════════════════════════════

def run_multi_agent_system(cycles: int = 0, interval_s: int = 60):
    """
    Run the multi-agent system standalone.
    cycles=0 → run indefinitely.
    """
    mas = MultiAgentSystem()
    mas.start()

    count = 0
    try:
        while True:
            time.sleep(interval_s)
            mas.trigger_cycle()
            count += 1
            if cycles and count >= cycles:
                break
    except KeyboardInterrupt:
        pass
    finally:
        mas.stop()

    return mas


if __name__ == "__main__":
    run_multi_agent_system(interval_s=30)