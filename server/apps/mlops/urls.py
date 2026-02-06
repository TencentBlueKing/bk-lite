from rest_framework import routers

from apps.mlops.views.algorithm_config import AlgorithmConfigViewSet
from apps.mlops.views.anomaly_detection import (
    AnomalyDetectionDatasetReleaseViewSet,
    AnomalyDetectionDatasetViewSet,
    AnomalyDetectionServingViewSet,
    AnomalyDetectionTrainDataViewSet,
    AnomalyDetectionTrainJobViewSet,
)
from apps.mlops.views.classification import (
    ClassificationDatasetReleaseViewSet,
    ClassificationDatasetViewSet,
    ClassificationServingViewSet,
    ClassificationTrainDataViewSet,
    ClassificationTrainJobViewSet,
)
from apps.mlops.views.image_classification import (
    ImageClassificationDatasetReleaseViewSet,
    ImageClassificationDatasetViewSet,
    ImageClassificationServingViewSet,
    ImageClassificationTrainDataViewSet,
    ImageClassificationTrainJobViewSet,
)
from apps.mlops.views.log_clustering import (
    LogClusteringDatasetReleaseViewSet,
    LogClusteringDatasetViewSet,
    LogClusteringServingViewSet,
    LogClusteringTrainDataViewSet,
    LogClusteringTrainJobViewSet,
)
from apps.mlops.views.object_detection import (
    ObjectDetectionDatasetReleaseViewSet,
    ObjectDetectionDatasetViewSet,
    ObjectDetectionServingViewSet,
    ObjectDetectionTrainDataViewSet,
    ObjectDetectionTrainJobViewSet,
)
from apps.mlops.views.timeseries_predict import (
    TimeSeriesPredictDatasetReleaseViewSet,
    TimeSeriesPredictDatasetViewSet,
    TimeSeriesPredictServingViewSet,
    TimeSeriesPredictTrainDataViewSet,
    TimeSeriesPredictTrainJobViewSet,
)

router = routers.DefaultRouter()

# 算法配置
router.register(
    r"algorithm_configs",
    AlgorithmConfigViewSet,
    basename="algorithm_configs",
)

# 异常检测
router.register(
    r"anomaly_detection_datasets",
    AnomalyDetectionDatasetViewSet,
    basename="anomaly_detection_datasets",
)
router.register(
    r"anomaly_detection_train_data",
    AnomalyDetectionTrainDataViewSet,
    basename="anomaly_detection_train_data",
)
router.register(
    r"anomaly_detection_train_jobs",
    AnomalyDetectionTrainJobViewSet,
    basename="anomaly_detection_train_jobs",
)
router.register(
    r"anomaly_detection_dataset_releases",
    AnomalyDetectionDatasetReleaseViewSet,
    basename="anomaly_detection_dataset_releases",
)
router.register(
    r"anomaly_detection_servings",
    AnomalyDetectionServingViewSet,
    basename="anomaly_detection_servings",
)

# 时间序列预测
router.register(
    r"timeseries_predict_datasets",
    TimeSeriesPredictDatasetViewSet,
    basename="timeseries_predict_datasets",
)
router.register(
    r"timeseries_predict_train_data",
    TimeSeriesPredictTrainDataViewSet,
    basename="timeseries_predict_train_data",
)
router.register(
    r"timeseries_predict_train_jobs",
    TimeSeriesPredictTrainJobViewSet,
    basename="timeseries_predict_train_jobs",
)
router.register(
    r"timeseries_predict_servings",
    TimeSeriesPredictServingViewSet,
    basename="timeseries_predict_servings",
)
router.register(
    r"timeseries_predict_dataset_releases",
    TimeSeriesPredictDatasetReleaseViewSet,
    basename="timeseries_predict_dataset_releases",
)

# 分类任务
router.register(
    r"classification_datasets",
    ClassificationDatasetViewSet,
    basename="classification_datasets",
)
router.register(
    r"classification_train_data",
    ClassificationTrainDataViewSet,
    basename="classification_train_data",
)
router.register(
    r"classification_train_jobs",
    ClassificationTrainJobViewSet,
    basename="classification_train_jobs",
)
router.register(
    r"classification_dataset_releases",
    ClassificationDatasetReleaseViewSet,
    basename="classification_dataset_releases",
)
router.register(
    r"classification_servings",
    ClassificationServingViewSet,
    basename="classification_servings",
)

# 图片分类任务
router.register(
    r"image_classification_datasets",
    ImageClassificationDatasetViewSet,
    basename="image_classification_datasets",
)
router.register(
    r"image_classification_train_data",
    ImageClassificationTrainDataViewSet,
    basename="image_classification_train_data",
)
router.register(
    r"image_classification_dataset_releases",
    ImageClassificationDatasetReleaseViewSet,
    basename="image_classification_dataset_releases",
)
router.register(
    r"image_classification_train_jobs",
    ImageClassificationTrainJobViewSet,
    basename="image_classification_train_jobs",
)
router.register(
    r"image_classification_servings",
    ImageClassificationServingViewSet,
    basename="image_classification_servings",
)

# 目标检测
router.register(
    r"object_detection_datasets",
    ObjectDetectionDatasetViewSet,
    basename="object_detection_datasets",
)
router.register(
    r"object_detection_train_data",
    ObjectDetectionTrainDataViewSet,
    basename="object_detection_train_data",
)
router.register(
    r"object_detection_dataset_releases",
    ObjectDetectionDatasetReleaseViewSet,
    basename="object_detection_dataset_releases",
)
router.register(
    r"object_detection_train_jobs",
    ObjectDetectionTrainJobViewSet,
    basename="object_detection_train_jobs",
)
router.register(
    r"object_detection_servings",
    ObjectDetectionServingViewSet,
    basename="object_detection_servings",
)

# 日志聚类
router.register(
    r"log_clustering_datasets",
    LogClusteringDatasetViewSet,
    basename="log_clustering_datasets",
)
router.register(
    r"log_clustering_train_data",
    LogClusteringTrainDataViewSet,
    basename="log_clustering_train_data",
)
router.register(
    r"log_clustering_train_jobs",
    LogClusteringTrainJobViewSet,
    basename="log_clustering_train_jobs",
)
router.register(
    r"log_clustering_dataset_releases",
    LogClusteringDatasetReleaseViewSet,
    basename="log_clustering_dataset_releases",
)
router.register(
    r"log_clustering_servings",
    LogClusteringServingViewSet,
    basename="log_clustering_servings",
)

urlpatterns = router.urls
