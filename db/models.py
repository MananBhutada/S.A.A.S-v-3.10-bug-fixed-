"""
db/models.py — SQLAlchemy ORM Models for Project S.A.A.S.
"""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, Text, JSON, Index
from sqlalchemy.orm import DeclarativeBase

def _now(): return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class WardReading(Base):
    __tablename__ = "ward_readings"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    timestamp        = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    ward_id          = Column(String(64), nullable=False, index=True)
    station_name     = Column(String(128))
    aqi              = Column(Float)
    aqi_category     = Column(String(32))
    effective_aqi    = Column(Float)
    pm25             = Column(Float)
    pm25_min         = Column(Float)
    pm25_max         = Column(Float)
    pm10             = Column(Float)
    pm10_min         = Column(Float)
    pm10_max         = Column(Float)
    no2              = Column(Float)
    so2              = Column(Float)
    co               = Column(Float)
    ozone            = Column(Float)
    naaqs_pm25_exceeded = Column(Boolean, default=False)
    naaqs_pm10_exceeded = Column(Boolean, default=False)
    wind_speed_kmh   = Column(Float)
    wind_bearing_deg = Column(Float)
    temperature_c    = Column(Float)
    humidity_pct     = Column(Float)
    pgrap_stage      = Column(Integer, default=0)
    intent           = Column(String(16))
    vsn_mode         = Column(String(32))
    scrubber_active  = Column(Boolean, default=False)
    droplet_um       = Column(Float)
    credit_score     = Column(Float)
    forecast_p10     = Column(Float)
    forecast_p50     = Column(Float)
    forecast_p90     = Column(Float)
    data_complete    = Column(Boolean, default=False)
    data_source      = Column(String(32), default="OWM")
    __table_args__ = (Index("ix_ward_ts", "ward_id", "timestamp"),)

class Alert(Base):
    __tablename__ = "alerts"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    timestamp      = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    ward_id        = Column(String(64), nullable=False, index=True)
    alert_type     = Column(String(64))
    severity       = Column(String(16))
    triggering_aqi = Column(Float)
    pgrap_stage    = Column(Integer)
    source_ward    = Column(String(64))
    target_ward    = Column(String(64))
    message        = Column(Text)
    channel        = Column(String(32))
    llm_generated  = Column(Boolean, default=False)
    suppressed     = Column(Boolean, default=False)
    __table_args__ = (Index("ix_alerts_ward_ts", "ward_id", "timestamp"),)

class PGRAPAction(Base):
    __tablename__ = "pgrap_actions"
    id                 = Column(Integer, primary_key=True, autoincrement=True)
    timestamp          = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    ward_id            = Column(String(64), nullable=False, index=True)
    pgrap_stage        = Column(Integer)
    stage_name         = Column(String(32))
    action_desc        = Column(Text)
    aqi_at_entry       = Column(Float)
    aqi_at_exit        = Column(Float)
    duration_hours     = Column(Float)
    scrubbers_deployed = Column(Boolean, default=False)
    droplet_um         = Column(Float)
    credit_score       = Column(Float)
    policy_vetoed      = Column(Boolean, default=False)
    veto_reason        = Column(Text)
    cycle_number       = Column(Integer)

class AgentDecision(Base):
    __tablename__ = "agent_decisions"
    id                  = Column(Integer, primary_key=True, autoincrement=True)
    timestamp           = Column(DateTime(timezone=True), default=_now, nullable=False)
    ward_id             = Column(String(64), index=True)
    agent_name          = Column(String(64))
    decision_type       = Column(String(64))
    triggering_aqi      = Column(Float)
    pgrap_stage         = Column(Integer)
    matched_rule        = Column(String(128))
    llm_prompt_hash     = Column(String(64))
    llm_response        = Column(Text)
    recommended_actions = Column(JSON)
    confidence_score    = Column(Float)
    cycle_number        = Column(Integer)

class AgentMemory(Base):
    __tablename__ = "agent_memory"
    id                          = Column(Integer, primary_key=True, autoincrement=True)
    ward_id                     = Column(String(64), unique=True, nullable=False, index=True)
    last_alert_sent             = Column(DateTime(timezone=True))
    last_alert_type             = Column(String(64))
    current_pgrap_stage         = Column(Integer, default=0)
    alert_count_24h             = Column(Integer, default=0)
    consecutive_violation_hours = Column(Float, default=0.0)
    last_known_aqi              = Column(Float)
    last_scrubber_activation    = Column(DateTime(timezone=True))
    spread_targets_alerted      = Column(JSON, default=list)
    updated_at                  = Column(DateTime(timezone=True), default=_now, onupdate=_now)

class WeatherSnapshot(Base):
    __tablename__ = "weather_snapshots"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    timestamp        = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    ward_id          = Column(String(64), nullable=False, index=True)
    city_name        = Column(String(64))
    temperature_c    = Column(Float)
    humidity_pct     = Column(Float)
    wind_speed_ms    = Column(Float)
    wind_speed_kmh   = Column(Float)
    wind_bearing_deg = Column(Float)
    pressure_hpa     = Column(Float)
    description      = Column(String(128))
    rain_1h_mm       = Column(Float)
    flood_risk       = Column(String(16))
    mosquito_risk    = Column(String(16))
    heat_alert       = Column(Boolean, default=False)
