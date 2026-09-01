import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Construct absolute path to backend/gridlite.db to ensure consistency
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'gridlite.db')}"

# SQLite requires check_same_thread=False for multi-threaded FastAPI usage
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def seed_machines(db: Session):
    """Seed the database with the initial set of 6 virtual machines if they do not exist."""
    from app.models import Machine

    initial_machines = [
        {
            "machine_id": "MOTOR-01",
            "machine_name": "Motor 01",
            "machine_type": "Motor",
            "location": "Production Line A"
        },
        {
            "machine_id": "MOTOR-02",
            "machine_name": "Motor 02",
            "machine_type": "Motor",
            "location": "Production Line A"
        },
        {
            "machine_id": "PUMP-01",
            "machine_name": "Pump 01",
            "machine_type": "Pump",
            "location": "Production Line B"
        },
        {
            "machine_id": "PUMP-02",
            "machine_name": "Pump 02",
            "machine_type": "Pump",
            "location": "Production Line B"
        },
        {
            "machine_id": "COMPRESSOR-01",
            "machine_name": "Compressor 01",
            "machine_type": "Compressor",
            "location": "Utility Area"
        },
        {
            "machine_id": "CONVEYOR-01",
            "machine_name": "Conveyor 01",
            "machine_type": "Conveyor",
            "location": "Production Line A"
        }
    ]

    for m_data in initial_machines:
        # Check if machine already exists
        exists = db.query(Machine).filter(Machine.machine_id == m_data["machine_id"]).first()
        if not exists:
            db_machine = Machine(
                machine_id=m_data["machine_id"],
                machine_name=m_data["machine_name"],
                machine_type=m_data["machine_type"],
                location=m_data["location"]
            )
            db.add(db_machine)
    db.commit()
    seed_initial_telemetry(db)

def seed_initial_telemetry(db: Session):
    """Seed initial baseline history and demonstration faults if database is empty."""
    from app.models import SensorReading
    from app.schemas import SensorReadingCreate
    from app.pipeline.pipeline_service import PipelineService
    from app.pipeline.auto_simulator import AUTO_MACHINES
    
    if db.query(SensorReading).count() < 30:
        # Step through 15 cycles to establish baseline and trigger active anomalies
        for step_idx in range(15):
            for machine in AUTO_MACHINES:
                machine.step()
                raw = machine.generate_reading()
                reading_data = SensorReadingCreate(**raw)
                PipelineService.ingest_and_process(db, reading_data)


