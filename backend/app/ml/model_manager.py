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
