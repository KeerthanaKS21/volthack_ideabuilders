import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Machine, SensorReading
from app.ml.baseline_manager import BaselineManager

# Create memory engine
engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

Base.metadata.create_all(bind=engine)

# Seed machines
m1 = Machine(machine_id="MOTOR-01", machine_name="Motor 1", machine_type="Motor", location="Line A")
db.add(m1)
db.commit()

# Seed baseline
import datetime
now = datetime.datetime.utcnow()
for i in range(110):
    timestamp = now - datetime.timedelta(minutes=5 * (110 - i))
    reading = SensorReading(
        machine_id="MOTOR-01",
        timestamp=timestamp,
        voltage=230.0,
        power=2.0,
        temperature=40.0,
        vibration=0.15,
        current=5.0,
        power_factor=0.9,
        operating_state="RUNNING"
    )
    db.add(reading)
db.commit()

# Calculate stats
stats = BaselineManager.calculate_baseline_statistics(db, "MOTOR-01", "Motor")
print("Stats for MOTOR-01:", stats)

readings = db.query(SensorReading).all()
print("Total readings count in DB:", len(readings))
