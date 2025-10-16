from neco.mlops.anomaly_detection.base_anomaly_detection import BaseAnomalyDetection
from sklearn.ensemble import RandomForestClassifier


class RandomForestAnomalyDetector(BaseAnomalyDetection):
    def build_model(self, train_params):
        model = RandomForestClassifier(**train_params)
        return model
