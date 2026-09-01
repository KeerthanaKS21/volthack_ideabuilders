from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

import os
import asyncio
from app.database import Base, engine, SessionLocal, seed_machines
from app.routes import machines, readings, anomaly, change_detection, energy_routes, diagnosis_routes, health_routes, assistant_routes, event_routes
from app.ml.config import MODEL_DIR
from app.ml.model_manager import ModelManager
from app.pipeline.auto_simulator import start_simulator_daemon

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database and tables
    Base.metadata.create_all(bind=engine)
    
    # Ensure local model weights directory exists & pre-train baseline ML models
    os.makedirs(MODEL_DIR, exist_ok=True)
    ModelManager.ensure_all_models_trained()
    
    # Seed the default 6 virtual machines & initial telemetry
    db = SessionLocal()
    try:
        seed_machines(db)
    finally:
        db.close()
        
    # Start 24/7 autonomous cloud telemetry simulator in background daemon thread
    start_simulator_daemon()
    
    yield

app = FastAPI(
    title="GridLite Backend", 
    version="1.0.0", 
    lifespan=lifespan
)

# Enable CORS for local dev and all production cloud/Vercel origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.pipeline.auto_simulator import start_simulator_daemon, get_demo_status, reset_demo_scenario

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
    demo_info = get_demo_status()
    return {
        "status": "ok",
        "database": "connected",
        "pipeline": "running",
        "demo_mode": demo_info["demo_mode"],
        "simulation_running": demo_info["simulation_running"],
        "current_phase": demo_info["current_phase"],
        "cycle_step": demo_info["cycle_step"],
        "service": "GridLite Backend"
    }

@app.get("/api/demo/status")
def get_demo_simulation_status():
    """Retrieve current automated demo scenario state, phase, and target machine."""
    return get_demo_status()

@app.post("/api/demo/reset")
def reset_demo_simulation():
    """Reset the automated demo scenario back to Phase 1 (Normal Operation)."""
    reset_demo_scenario()
    return {
        "status": "ok",
        "message": "Demo scenario reset to Phase 1 (Normal Operation)",
        "demo_status": get_demo_status()
    }
