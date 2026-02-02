"""
MLOps Celery 任务模块
"""

from .timeseries import (
    publish_dataset_release_async as timeseries_publish_dataset_release_async,
)
from .anomaly_detection import (
    publish_dataset_release_async as anomaly_publish_dataset_release_async,
)
from .log_clustering import (
    publish_dataset_release_async as log_clustering_publish_dataset_release_async,
)
from .classification import (
    publish_dataset_release_async as classification_publish_dataset_release_async,
)
from .image_classification import (
    publish_dataset_release_async as image_classification_publish_dataset_release_async,
)
from .object_detection import (
    publish_dataset_release_async as object_detection_publish_dataset_release_async,
)

__all__ = [
    "timeseries_publish_dataset_release_async",
    "anomaly_publish_dataset_release_async",
    "log_clustering_publish_dataset_release_async",
    "classification_publish_dataset_release_async",
    "image_classification_publish_dataset_release_async",
    "object_detection_publish_dataset_release_async",
]
