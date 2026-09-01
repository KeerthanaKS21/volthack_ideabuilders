import os
import pickle
import datetime
from app.ml.config import MODEL_DIR
from app.ml.anomaly_detector import AnomalyDetector

class ModelManager:
    @staticmethod
    def _get_model_path(machine_id):
        return os.path.join(MODEL_DIR, f"{machine_id.upper()}.pkl")

    @classmethod
    def save_model(cls, machine_id, detector, training_samples):
        """Serialize and save the trained AnomalyDetector wrapper to disk."""
        # Ensure the models directory exists
        os.makedirs(MODEL_DIR, exist_ok=True)
        
        model_path = cls._get_model_path(machine_id)
        
        # Structure model data with metadata included
        model_data = {
            "detector": detector,
            "metadata": {
                "machine_id": machine_id.upper(),
                "trained_at": datetime.datetime.now().isoformat(),
                "training_samples": training_samples
            }
        }
        
        with open(model_path, "wb") as f:
            pickle.dump(model_data, f)
            
        return model_path

    @classmethod
    def load_model(cls, machine_id):
        """Load and deserialize model data from disk."""
        model_path = cls._get_model_path(machine_id)
        if not os.path.exists(model_path):
            return None
            
        with open(model_path, "rb") as f:
            model_data = pickle.load(f)
            
        return model_data

    @classmethod
    def model_exists(cls, machine_id):
        """Check whether a model file exists on disk for the machine ID."""
        model_path = cls._get_model_path(machine_id)
        return os.path.exists(model_path)

    @classmethod
    def get_model_info(cls, machine_id):
        """Retrieve model training info metadata if it exists."""
        model_data = cls.load_model(machine_id)
        if not model_data:
            return None
        return model_data.get("metadata")

    @classmethod
    def ensure_all_models_trained(cls):
        """Train default baseline Isolation Forest models for all virtual machines if missing."""
        import numpy as np
        from app.ml.config import PROFILES
        
        machine_types = {
            "MOTOR-01": "Motor",
            "MOTOR-02": "Motor",
            "PUMP-01": "Pump",
            "PUMP-02": "Pump",
            "COMPRESSOR-01": "Compressor",
            "CONVEYOR-01": "Conveyor"
        }
        
        for m_id, m_type in machine_types.items():
            if not cls.model_exists(m_id):
                profile = PROFILES.get(m_type, PROFILES["Motor"])
                np.random.seed(42)
                v_nom = profile["voltage"]["nominal"]
                p_nom = profile["power"]["nominal"]
                t_nom = profile["temperature"]["nominal"]
                vib_nom = profile["vibration"]["nominal"]
                pf_nom = profile["power_factor"]["nominal"]
                
                n_samples = 150
                v = np.random.normal(v_nom, v_nom * 0.015, n_samples)
                p = np.random.normal(p_nom, p_nom * 0.02, n_samples)
                pf = np.random.normal(pf_nom, 0.01, n_samples)
                curr = (p * 1000.0) / (np.sqrt(3) * v * pf)
                t = np.random.normal(t_nom, 1.0, n_samples)
                vib = np.random.normal(vib_nom, 0.01, n_samples)
                
                X = np.column_stack([v, curr, p, t, vib, pf])
                detector = AnomalyDetector()
                detector.train(X)
                cls.save_model(m_id, detector, n_samples)

