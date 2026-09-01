from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

import os
from app.database import Base, engine, SessionLocal, seed_machines
from app.routes import machines, readings, anomaly, change_detection, energy_routes, diagnosis_routes, health_routes, assistant_routes, event_routes
from app.ml.config import MODEL_DIR

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database and tables
    Base.metadata.create_all(bind=engine)
    
    # Ensure local model weights directory exists
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    # Seed the default 6 virtual machines
    db = SessionLocal()
    try:
        seed_machines(db)
    finally:
        db.close()
    yield

app = FastAPI(
    title="GridLite Backend", 
    version="1.0.0", 
    lifespan=lifespan
)

# Enable CORS for React frontend running at http://localhost:5173
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(machines.router)
app.include_router(readings.router)
app.include_router(readings.history_router)
app.include_router(anomaly.router)
app.include_router(change_detection.router)
app.include_router(energy_routes.router)
app.include_router(diagnosis_routes.router)
app.include_router(health_routes.router)
app.include_router(assistant_routes.router)
app.include_router(event_routes.router)

@app.get("/api/health")
def read_health():
    return {
        "status": "ok",
        "database": "connected",
        "pipeline": "running",
        "service": "GridLite Backend"
    }
