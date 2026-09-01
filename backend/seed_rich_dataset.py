"""
GridLite Rich Dataset Seeder
Generates deep time-series history, trains ML anomaly models, establishes baselines,
and creates realistic active industrial faults (Bearing Wear, Overheating, Low PF, Overload).
"""
import os
import sys
import time
import datetime
import random
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.database import Base, engine, SessionLocal, seed_machines
from app.models import Machine, SensorReading, Anomaly, BehaviorChange, DiagnosisEvent, MachineHealthEvent
from app.schemas import SensorReadingCreate
from app.pipeline.pipeline_service import PipelineService
from app.pipeline.auto_simulator import AUTO_MACHINES, AutoMachine
from app.ml.model_manager import ModelManager
from app.health.health_engine import HealthEngine

def seed_local_database(samples_per_machine=50):
    print(f"[*] Starting local database seeding ({samples_per_machine} samples per machine)...")
    Base.metadata.create_all(bind=engine)
    
    # 1. Pre-train baseline ML models
    print("[*] Training baseline ML models...")
    ModelManager.ensure_all_models_trained()
    
    db = SessionLocal()
    try:
        # 2. Seed machines
        seed_machines(db)
        
        # 3. Simulate realistic historical time series
        machines = [
            AutoMachine("MOTOR-01", "Motor 01", "Motor", "Production Line A"),
            AutoMachine("MOTOR-02", "Motor 02", "Motor", "Production Line A"),
            AutoMachine("PUMP-01", "Pump 01", "Pump", "Production Line B"),
            AutoMachine("PUMP-02", "Pump 02", "Pump", "Production Line B"),
            AutoMachine("COMPRESSOR-01", "Compressor 01", "Compressor", "Utility Room"),
            AutoMachine("CONVEYOR-01", "Conveyor 01", "Conveyor", "Assembly Line")
        ]
        
        now = datetime.datetime.utcnow()
        
        # Step through historical normal steps
        print(f"[*] Generating {samples_per_machine} historical baseline steps...")
        for i in range(samples_per_machine):
            time_offset = datetime.timedelta(seconds=(samples_per_machine - i) * 10)
            step_time = now - time_offset
            
            # Inject faults into MOTOR-02 and COMPRESSOR-01 during recent steps
            if i >= samples_per_machine - 20:
                machines[1].active_fault = "MECHANICAL_DEGRADATION" # MOTOR-02
                machines[1].fault_duration = i - (samples_per_machine - 20)
                machines[4].active_fault = "OVERHEATING"             # COMPRESSOR-01
                machines[4].fault_duration = i - (samples_per_machine - 20)
                machines[2].active_fault = "POWER_FACTOR_DROP"      # PUMP-01
                machines[2].fault_duration = i - (samples_per_machine - 20)
                
            for m in machines:
                m.step()
                raw = m.generate_reading()
                raw["timestamp"] = step_time
                reading_create = SensorReadingCreate(**raw)
                PipelineService.ingest_and_process(db, reading_create)
                
        # 4. Evaluate health factory overview
        overview = HealthEngine.get_factory_overview(db)
        print("\n[+] Database Seeding Complete!")
        print(f"    - Total Readings: {db.query(SensorReading).count()}")
        print(f"    - Total Anomalies Flagged: {db.query(Anomaly).count()}")
        print(f"    - Behavioral Drift Events: {db.query(BehaviorChange).count()}")
        print(f"    - Plant Health Overview: {overview.healthy_count} Healthy, {overview.watch_count} Watch, {overview.attention_count} Attention, {overview.critical_count} Critical")
        for m in overview.machines:
            print(f"      * {m.machine_id}: {m.health_status} (Priority {m.priority_score}) - {m.primary_reason}")
            
    finally:
        db.close()

def seed_cloud_backend(cloud_url="https://gridlite-backend.onrender.com/api/readings", samples=25):
    print(f"\n[*] Streaming {samples} rich simulated readings to Cloud Backend ({cloud_url})...")
    machines = [
        AutoMachine("MOTOR-01", "Motor 01", "Motor", "Production Line A"),
        AutoMachine("MOTOR-02", "Motor 02", "Motor", "Production Line A"),
        AutoMachine("PUMP-01", "Pump 01", "Pump", "Production Line B"),
        AutoMachine("PUMP-02", "Pump 02", "Pump", "Production Line B"),
        AutoMachine("COMPRESSOR-01", "Compressor 01", "Compressor", "Utility Room"),
        AutoMachine("CONVEYOR-01", "Conveyor 01", "Conveyor", "Assembly Line")
    ]
    
    # Inject faults
    machines[1].active_fault = "MECHANICAL_DEGRADATION" # MOTOR-02
    machines[1].fault_duration = 15
    machines[4].active_fault = "OVERHEATING"             # COMPRESSOR-01
    machines[4].fault_duration = 12
    machines[2].active_fault = "POWER_FACTOR_DROP"      # PUMP-01
    machines[2].fault_duration = 10
    
    for i in range(samples):
        for m in machines:
            m.step()
            raw = m.generate_reading()
            try:
                r = requests.post(cloud_url, json=raw, timeout=5.0)
                if r.status_code == 201:
                    print(f"  [✓] Streamed {m.machine_id} ({raw['operating_state']}) - Power: {raw['power']}kW, Vib: {raw['vibration']:.3f}, Temp: {raw['temperature']:.1f}°C")
                else:
                    print(f"  [!] HTTP {r.status_code} on {m.machine_id}")
            except Exception as e:
                print(f"  [X] Failed sending to cloud: {e}")
        time.sleep(0.5)
        
    print("\n[+] Cloud Seeding Complete! Refresh https://volthack-ideabuilders.vercel.app/ to see updated live data.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GridLite Rich Dataset Seeder")
    parser.add_argument("--cloud", action="store_true", help="Stream data directly to cloud backend on Render")
    parser.add_argument("--samples", type=int, default=30, help="Number of samples per machine to generate")
    args = parser.parse_args()
    
    if args.cloud:
        seed_cloud_backend(samples=args.samples)
    else:
        seed_local_database(samples_per_machine=args.samples)
