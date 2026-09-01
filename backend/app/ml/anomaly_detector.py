import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from app.ml.preprocessing import FEATURE_NAMES

class AnomalyDetector:
    def __init__(self, contamination=0.05, random_state=42):
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            contamination=contamination, 
            random_state=random_state,
            n_estimators=100
        )
        self.feature_means = {}

    def train(self, X_train):
        """
        Train the preprocessor and the Isolation Forest model on normal historical readings.
        X_train: 2D numpy array of shape (n_samples, n_features)
        """
        # 1. Fit and transform the features using StandardScaler
        X_scaled = self.scaler.fit_transform(X_train)
        
        # 2. Fit the Isolation Forest model
        self.model.fit(X_scaled)
        
        # 3. Calculate baseline average values for deviation calculations
        means = np.mean(X_train, axis=0)
        for i, name in enumerate(FEATURE_NAMES):
            self.feature_means[name] = float(means[i])

    def predict_single(self, x):
        """
        Predict whether a single 1D feature vector is an anomaly using a hybrid model:
        1. Isolation Forest output.
        2. Statistical deviation threshold check.
        """
        # 1. Isolation Forest prediction
        x_reshaped = np.array(x).reshape(1, -1)
        x_scaled = self.scaler.transform(x_reshaped)
        prediction = self.model.predict(x_scaled)[0]
        if prediction == -1:
            return True
            
        # 2. Statistical deviation backup checks
        for i, name in enumerate(FEATURE_NAMES):
            mean_val = self.feature_means.get(name, 0.0)
            val = float(x[i])
            if mean_val != 0.0:
                deviation = abs((val - mean_val) / mean_val)
                if name in ["vibration", "temperature", "current", "power"] and deviation > 0.20:
                    return True
                if name == "voltage" and deviation > 0.10:
                    return True
                if name == "power_factor" and deviation > 0.15:
                    return True
        return False

    def get_anomaly_score(self, x):
        """
        Compute the normalized anomaly score for a single feature vector.
        Standardizes score so that 0.5 is the anomaly threshold boundary.
        Returns score: float in range [0.0, 1.0]
        """
        x_reshaped = np.array(x).reshape(1, -1)
        x_scaled = self.scaler.transform(x_reshaped)
        
        # decision_function yields positive for normal, negative for anomalous (bounds approx [-0.5, 0.5])
        decision_val = self.model.decision_function(x_scaled)[0]
        score_if = float(0.5 - decision_val)
        
        # Calculate maximum absolute deviation to adjust score if flagged
        max_dev = 0.0
        is_stat_anomaly = False
        for i, name in enumerate(FEATURE_NAMES):
            mean_val = self.feature_means.get(name, 0.0)
            val = float(x[i])
            if mean_val != 0.0:
                deviation = abs((val - mean_val) / mean_val)
                max_dev = max(max_dev, deviation)
                if name in ["vibration", "temperature", "current", "power"] and deviation > 0.20:
                    is_stat_anomaly = True
                if name == "voltage" and deviation > 0.10:
                    is_stat_anomaly = True
                if name == "power_factor" and deviation > 0.15:
                    is_stat_anomaly = True
                    
        if is_stat_anomaly:
            # deviation of 1.0 (100% change) maps to 0.5 + 0.3 = 0.8 score (HIGH severity)
            score_dev = 0.5 + min(0.45, max_dev * 0.3)
            score = max(score_if, score_dev)
        else:
            score = score_if
            
        return float(max(0.0, min(score, 1.0)))

    def calculate_deviations(self, x):
        """
        Calculate the percentage deviation of the current features from the normal baseline profile.
        Returns: dict of parameter name -> string percentage (e.g. "+42%")
        """
        deviations = {}
        for i, name in enumerate(FEATURE_NAMES):
            mean_val = self.feature_means.get(name, 0.0)
            current_val = float(x[i])
            
            if mean_val != 0.0:
                diff_pct = ((current_val - mean_val) / mean_val) * 100.0
                # Represent signed integer deviations
                sign = "+" if diff_pct >= 0 else ""
                deviations[name] = f"{sign}{int(round(diff_pct))}%"
            else:
                deviations[name] = "0%"
                
        return deviations
