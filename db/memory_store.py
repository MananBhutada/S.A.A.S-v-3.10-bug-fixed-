"""
db/memory_store.py — Persistent Agent Memory
=============================================
Ward agents now remember across cycles:
  - Last alert sent (prevents re-firing)
  - Current P-GRAP stage
  - Consecutive violation hours
  - Spread targets already alerted (with timestamps)
  - Alert count in last 24h
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from db.session import get_session
from db.models import AgentMemory

log = logging.getLogger("MEMORY-STORE")

class MemoryStore:
    """Persistent per-ward memory backed by SQLite/PostgreSQL."""

    def __init__(self, ward_id: str):
        self.ward_id = ward_id
        self._ensure_exists()

    def _ensure_exists(self):
        with get_session() as s:
            existing = s.query(AgentMemory).filter_by(ward_id=self.ward_id).first()
            if not existing:
                s.add(AgentMemory(ward_id=self.ward_id))
                log.info("Created memory record for ward: %s", self.ward_id)

    def get(self) -> dict:
        with get_session() as s:
            m = s.query(AgentMemory).filter_by(ward_id=self.ward_id).first()
            if not m:
                return {}
            return {
                "ward_id":                    m.ward_id,
                "last_alert_sent":            m.last_alert_sent,
                "last_alert_type":            m.last_alert_type,
                "current_pgrap_stage":        m.current_pgrap_stage or 0,
                "alert_count_24h":            m.alert_count_24h or 0,
                "consecutive_violation_hours":m.consecutive_violation_hours or 0.0,
                "last_known_aqi":             m.last_known_aqi,
                "last_scrubber_activation":   m.last_scrubber_activation,
                "spread_targets_alerted":     m.spread_targets_alerted or {},
                "updated_at":                 m.updated_at,
            }

    def update(self, **kwargs):
        with get_session() as s:
            m = s.query(AgentMemory).filter_by(ward_id=self.ward_id).first()
            if not m:
                m = AgentMemory(ward_id=self.ward_id)
                s.add(m)
            for k, v in kwargs.items():
                if hasattr(m, k):
                    setattr(m, k, v)
            m.updated_at = datetime.now(timezone.utc)

    def can_send_alert(self, alert_type: str, cooldown_minutes: int = 30) -> bool:
        """Check if alert cooldown has passed — prevents duplicate alerts (BUG-3 fix at DB level)."""
        mem = self.get()
        last = mem.get("last_alert_sent")
        if last is None:
            return True
        # Make timezone-aware if needed
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 60
        can = elapsed >= cooldown_minutes
        if not can:
            log.debug("[%s] Alert cooldown active: %.1f/%d min elapsed",
                      self.ward_id, elapsed, cooldown_minutes)
        return can

    def record_alert_sent(self, alert_type: str):
        self.update(
            last_alert_sent=datetime.now(timezone.utc),
            last_alert_type=alert_type,
        )
        # Increment 24h counter
        mem = self.get()
        self.update(alert_count_24h=(mem.get("alert_count_24h", 0) + 1))

    def update_pgrap_stage(self, new_stage: int, aqi: float):
        mem = self.get()
        old_stage = mem.get("current_pgrap_stage", 0)
        # Track consecutive violation hours
        hours = mem.get("consecutive_violation_hours", 0.0)
        if new_stage > 0:
            hours += 1.0  # each cycle = ~1h
        else:
            hours = 0.0
        self.update(
            current_pgrap_stage=new_stage,
            last_known_aqi=aqi,
            consecutive_violation_hours=hours,
        )
        if new_stage != old_stage:
            log.info("[%s] P-GRAP stage changed: %d → %d (AQI=%.0f, violations=%.0fh)",
                     self.ward_id, old_stage, new_stage, aqi, hours)
        return old_stage, new_stage

    def reset_24h_counters(self):
        """Call once daily to reset 24h alert counts."""
        self.update(alert_count_24h=0)
        log.info("[%s] 24h counters reset", self.ward_id)
