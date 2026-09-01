from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Machine(Base):
    __tablename__ = "machines"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(String, unique=True, index=True, nullable=False)
    machine_name = Column(String, nullable=False)
    machine_type = Column(String, nullable=False)
    location = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Establish relationship with readings (cascade deletes if appropriate)
    readings = relationship("SensorReading", back_populates="machine", cascade="all, delete-orphan")
    anomalies = relationship("Anomaly", back_populates="machine", cascade="all, delete-orphan")
    behavior_changes = relationship("BehaviorChange", back_populates="machine", cascade="all, delete-orphan")
    energy_events = relationship("EnergyEvent", back_populates="machine", cascade="all, delete-orphan")
    diagnosis_events = relationship("DiagnosisEvent", back_populates="machine", cascade="all, delete-orphan")
    health_events = relationship("MachineHealthEvent", back_populates="machine", cascade="all, delete-orphan")
    unified_events = relationship("UnifiedEvent", back_populates="machine", cascade="all, delete-orphan")


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(String, ForeignKey("machines.machine_id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime, index=True, nullable=False)
    voltage = Column(Float, nullable=False)
    current = Column(Float, nullable=False)
    power = Column(Float, nullable=False)
    temperature = Column(Float, nullable=False)
    vibration = Column(Float, nullable=False)
    power_factor = Column(Float, nullable=False)
    operating_state = Column(String, nullable=False)

    # Establish relationship with machine and anomaly
    machine = relationship("Machine", back_populates="readings")
    anomaly = relationship("Anomaly", back_populates="reading", uselist=False, cascade="all, delete-orphan")


class Anomaly(Base):
    __tablename__ = "anomalies"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(String, ForeignKey("machines.machine_id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime, index=True, default=datetime.utcnow, nullable=False)
    anomaly_score = Column(Float, nullable=False)
    severity = Column(String, nullable=False)  # NORMAL, LOW, MEDIUM, HIGH
    affected_parameters = Column(String, nullable=False)  # JSON-serialized deviations dict
    reading_id = Column(Integer, ForeignKey("sensor_readings.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)

    # Establish relationships
    machine = relationship("Machine", back_populates="anomalies")
    reading = relationship("SensorReading", back_populates="anomaly")


class BehaviorChange(Base):
    __tablename__ = "machine_behavior_changes"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(String, ForeignKey("machines.machine_id", ondelete="CASCADE"), index=True, nullable=False)
    detected_at = Column(DateTime, index=True, default=datetime.utcnow, nullable=False)
    parameter = Column(String, nullable=False)  # power, temperature, vibration, current, power_factor
    baseline_value = Column(Float, nullable=False)
    recent_value = Column(Float, nullable=False)
    percentage_change = Column(Float, nullable=False)
    change_type = Column(String, nullable=False)  # SHIFTED_LEVEL, INCREASING, DECREASING, INCREASED_VARIABILITY, DECREASED_VARIABILITY
    change_score = Column(Float, nullable=False)
    persistence_count = Column(Integer, default=1, nullable=False)
    status = Column(String, default="ACTIVE", nullable=False)  # ACTIVE, RESOLVED

    # Establish relationships
    machine = relationship("Machine", back_populates="behavior_changes")


class EnergyEvent(Base):
    __tablename__ = "energy_events"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(String, ForeignKey("machines.machine_id", ondelete="CASCADE"), index=True, nullable=False)
    detected_at = Column(DateTime, index=True, default=datetime.utcnow, nullable=False)
    expected_power = Column(Float, nullable=False)
    actual_power = Column(Float, nullable=False)
    excess_power = Column(Float, nullable=False)
    excess_energy_kwh = Column(Float, nullable=False)
    estimated_cost = Column(Float, nullable=False)
    status = Column(String, default="ACTIVE", nullable=False)  # ACTIVE, RESOLVED

    # Establish relationships
    machine = relationship("Machine", back_populates="energy_events")


class DiagnosisEvent(Base):
    __tablename__ = "diagnosis_events"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(String, ForeignKey("machines.machine_id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime, index=True, default=datetime.utcnow, nullable=False)
    primary_possible_cause = Column(String, nullable=False)  # MECHANICAL_DEGRADATION, OVERLOAD, OVERHEATING, ELECTRICAL_ANOMALY, UNKNOWN
    evidence_score = Column(Float, nullable=False)
    evidence_json = Column(String, nullable=False)  # JSON-serialized list of EvidenceItem dicts
    possible_causes_json = Column(String, nullable=False)  # JSON-serialized list of PossibleCause dicts
    explanation = Column(String, nullable=False)  # AI or rule-based generated natural language explanation
    suggested_inspections_json = Column(String, nullable=False)  # JSON-serialized list of inspection strings
    human_review_status = Column(String, default="UNDER_REVIEW", nullable=False)  # UNDER_REVIEW, CONFIRMED, REJECTED
    status = Column(String, default="ACTIVE", nullable=False)  # ACTIVE, RESOLVED

    # Establish relationships
    machine = relationship("Machine", back_populates="diagnosis_events")


class MachineHealthEvent(Base):
    __tablename__ = "machine_health_events"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(String, ForeignKey("machines.machine_id", ondelete="CASCADE"), index=True, nullable=False)
    timestamp = Column(DateTime, index=True, default=datetime.utcnow, nullable=False)
    health_status = Column(String, nullable=False)  # HEALTHY, WATCH, ATTENTION, CRITICAL
    priority_score = Column(Integer, nullable=False)  # 0 - 100
    primary_reason = Column(String, nullable=False)  # Concise summary of main issue
    contributing_factors_json = Column(String, nullable=False)  # JSON-serialized list of string descriptions
    signal_scores_json = Column(String, nullable=False)  # JSON-serialized dict of individual signal scores
    operator_status = Column(String, default="INVESTIGATE", nullable=False)  # INVESTIGATE, UNDER_REVIEW, RESOLVED
    status = Column(String, default="ACTIVE", nullable=False)  # ACTIVE, RESOLVED

    # Establish relationships
    machine = relationship("Machine", back_populates="health_events")


class UnifiedEvent(Base):
    __tablename__ = "unified_events"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(String, ForeignKey("machines.machine_id", ondelete="CASCADE"), index=True, nullable=False)
    event_type = Column(String, index=True, nullable=False)  # MACHINE_STATE_CHANGED, ANOMALY_DETECTED, BEHAVIOR_CHANGE, ENERGY_INEFFICIENCY, DIAGNOSIS_AVAILABLE, HEALTH_CHANGED, PRIORITY_CHANGED
    severity = Column(String, index=True, default="INFO", nullable=False)  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    timestamp = Column(DateTime, index=True, default=datetime.utcnow, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    evidence_json = Column(String, default="{}", nullable=False)  # JSON-serialized key-value evidence dict
    status = Column(String, index=True, default="ACTIVE", nullable=False)  # ACTIVE, ACKNOWLEDGED, RESOLVED
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    # Establish relationships
    machine = relationship("Machine", back_populates="unified_events")


