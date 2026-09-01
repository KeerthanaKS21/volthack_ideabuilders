import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from app.database import Base, engine, SessionLocal, seed_machines
from app.models import Machine, SensorReading, Anomaly, BehaviorChange, DiagnosisEvent, MachineHealthEvent
from app.schemas import SensorReadingCreate
from app.pipeline.pipeline_service import PipelineService
from app.pipeline.auto_simulator import AUTO_MACHINES
from app.health.health_engine import HealthEngine

from app.ml.model_manager import ModelManager

Base.metadata.create_all(bind=engine)
ModelManager.ensure_all_models_trained()
db = SessionLocal()
seed_machines(db)

print("--- Machine count ---", db.query(Machine).count())

# Inject mechanical degradation on MOTOR-02
m2 = next(m for m in AUTO_MACHINES if m.machine_id == 'MOTOR-02')
m2.active_fault = 'MECHANICAL_DEGRADATION'
m2.fault_duration = 15

print("Generating 10 readings for MOTOR-02 under fault...")
for i in range(10):
    m2.step()
    raw = m2.generate_reading()
    res, anomaly = PipelineService.ingest_and_process(db, SensorReadingCreate(**raw))
    print(f"Step {i}: Vib={raw['vibration']:.4f}, Temp={raw['temperature']:.1f}, Power={raw['power']:.2f}, Anomaly={anomaly}")

print("\n--- Anomalies in DB (Total: %d) ---" % db.query(Anomaly).count())
for a in db.query(Anomaly).all()[-5:]:
    print(f"Anomaly: {a.machine_id} | Severity: {a.severity} | Score: {a.anomaly_score} | Params: {a.affected_parameters}")

print("\n--- Behavior changes in DB (Total: %d) ---" % db.query(BehaviorChange).count())
for b in db.query(BehaviorChange).all()[-5:]:
    print(f"Behavior: {b.machine_id} | Param: {b.parameter} | Shift: {b.percentage_change}% | Status: {b.status}")

print("\n--- Health Evaluation ---")
h = HealthEngine.evaluate_machine(db, 'MOTOR-02')
print(f"MOTOR-02 Health: {h.health_status} | Score: {h.priority_score} | Reason: {h.primary_reason}")

overview = HealthEngine.get_factory_overview(db)
print(f"Overview: {overview.healthy_count} healthy, {overview.watch_count} watch, {overview.attention_count} attention, {overview.critical_count} critical")
for rm in overview.machines:
    print(f"Ranked: {rm.machine_id} -> {rm.health_status} (Priority: {rm.priority_score}) | Reason: {rm.primary_reason}")

db.close()
