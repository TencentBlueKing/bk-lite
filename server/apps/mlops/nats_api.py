import nats_client

from apps.mlops.models.anomaly_detection import (
    AnomalyDetectionDataset,
    AnomalyDetectionDatasetRelease,
    AnomalyDetectionServing,
    AnomalyDetectionTrainData,
    AnomalyDetectionTrainJob,
)
from apps.mlops.models.classification import (
    ClassificationDataset,
    ClassificationDatasetRelease,
    ClassificationServing,
    ClassificationTrainData,
    ClassificationTrainJob,
)
from apps.mlops.models.image_classification import (
    ImageClassificationDataset,
    ImageClassificationDatasetRelease,
    ImageClassificationServing,
    ImageClassificationTrainData,
    ImageClassificationTrainJob,
)
from apps.mlops.models.log_clustering import (
    LogClusteringDataset,
    LogClusteringDatasetRelease,
    LogClusteringServing,
    LogClusteringTrainData,
    LogClusteringTrainJob,
)
from apps.mlops.models.object_detection import (
    ObjectDetectionDataset,
    ObjectDetectionDatasetRelease,
    ObjectDetectionServing,
    ObjectDetectionTrainData,
    ObjectDetectionTrainJob,
)
from apps.mlops.models.timeseries_predict import (
    TimeSeriesPredictDataset,
    TimeSeriesPredictDatasetRelease,
    TimeSeriesPredictServing,
    TimeSeriesPredictTrainData,
    TimeSeriesPredictTrainJob,
)


ROOT_MODULE_MODEL_MAP = {
    "dataset": {
        "anomaly_detection_dataset": (AnomalyDetectionDataset, "team"),
        "classification_dataset": (ClassificationDataset, "team"),
        "image_classification_dataset": (ImageClassificationDataset, "team"),
        "log_clustering_dataset": (LogClusteringDataset, "team"),
        "object_detection_dataset": (ObjectDetectionDataset, "team"),
        "timeseries_predict_dataset": (TimeSeriesPredictDataset, "team"),
    },
    "train_job": {
        "anomaly_detection_train_job": (AnomalyDetectionTrainJob, "team"),
        "classification_train_job": (ClassificationTrainJob, "team"),
        "image_classification_train_job": (ImageClassificationTrainJob, "team"),
        "log_clustering_train_job": (LogClusteringTrainJob, "team"),
        "object_detection_train_job": (ObjectDetectionTrainJob, "team"),
        "timeseries_predict_train_job": (TimeSeriesPredictTrainJob, "team"),
    },
    "serving": {
        "anomaly_detection_serving": (AnomalyDetectionServing, "team"),
        "classification_serving": (ClassificationServing, "team"),
        "image_classification_serving": (ImageClassificationServing, "team"),
        "log_clustering_serving": (LogClusteringServing, "team"),
        "object_detection_serving": (ObjectDetectionServing, "team"),
        "timeseries_predict_serving": (TimeSeriesPredictServing, "team"),
    },
}

INHERITED_MODULE_MODEL_MAP = {
    "dataset": {
        "anomaly_detection_train_data": (AnomalyDetectionTrainData, "dataset__team"),
        "anomaly_detection_dataset_release": (
            AnomalyDetectionDatasetRelease,
            "dataset__team",
        ),
        "classification_train_data": (ClassificationTrainData, "dataset__team"),
        "classification_dataset_release": (
            ClassificationDatasetRelease,
            "dataset__team",
        ),
        "image_classification_train_data": (
            ImageClassificationTrainData,
            "dataset__team",
        ),
        "image_classification_dataset_release": (
            ImageClassificationDatasetRelease,
            "dataset__team",
        ),
        "log_clustering_train_data": (LogClusteringTrainData, "dataset__team"),
        "log_clustering_dataset_release": (
            LogClusteringDatasetRelease,
            "dataset__team",
        ),
        "object_detection_train_data": (ObjectDetectionTrainData, "dataset__team"),
        "object_detection_dataset_release": (
            ObjectDetectionDatasetRelease,
            "dataset__team",
        ),
        "timeseries_predict_train_data": (
            TimeSeriesPredictTrainData,
            "dataset__team",
        ),
        "timeseries_predict_dataset_release": (
            TimeSeriesPredictDatasetRelease,
            "dataset__team",
        ),
    },
    "train_job": {},
}

MODULE_DISPLAY_NAMES = {
    "dataset": "数据集",
    "train_job": "训练任务",
    "serving": "能力发布",
}

CHILD_DISPLAY_NAMES = {
    "anomaly_detection_dataset": "异常检测数据集",
    "anomaly_detection_train_data": "异常检测训练数据",
    "anomaly_detection_dataset_release": "异常检测数据集发布版本",
    "anomaly_detection_train_job": "异常检测训练任务",
    "anomaly_detection_serving": "异常检测能力发布",
    "classification_dataset": "分类任务数据集",
    "classification_train_data": "分类任务训练数据",
    "classification_dataset_release": "分类任务数据集发布版本",
    "classification_train_job": "分类任务训练任务",
    "classification_serving": "分类任务能力发布",
    "image_classification_dataset": "图片分类数据集",
    "image_classification_train_data": "图片分类训练数据",
    "image_classification_dataset_release": "图片分类数据集发布版本",
    "image_classification_train_job": "图片分类训练任务",
    "image_classification_serving": "图片分类能力发布",
    "log_clustering_dataset": "日志聚类数据集",
    "log_clustering_train_data": "日志聚类训练数据",
    "log_clustering_dataset_release": "日志聚类数据集发布版本",
    "log_clustering_train_job": "日志聚类训练任务",
    "log_clustering_serving": "日志聚类能力发布",
    "object_detection_dataset": "目标检测数据集",
    "object_detection_train_data": "目标检测训练数据",
    "object_detection_dataset_release": "目标检测数据集发布版本",
    "object_detection_train_job": "目标检测训练任务",
    "object_detection_serving": "目标检测能力发布",
    "timeseries_predict_dataset": "时间序列预测数据集",
    "timeseries_predict_train_data": "时间序列预测训练数据",
    "timeseries_predict_dataset_release": "时间序列预测数据集发布版本",
    "timeseries_predict_train_job": "时间序列预测训练任务",
    "timeseries_predict_serving": "时间序列预测能力发布",
}


def _get_module_registry():
    registry = {}
    for module_name in MODULE_DISPLAY_NAMES:
        merged = {}
        merged.update(ROOT_MODULE_MODEL_MAP.get(module_name, {}))
        merged.update(INHERITED_MODULE_MODEL_MAP.get(module_name, {}))
        registry[module_name] = merged
    return registry


@nats_client.register
def get_mlops_module_list():
    registry = _get_module_registry()
    return [
        {
            "name": module_name,
            "display_name": MODULE_DISPLAY_NAMES[module_name],
            "children": [
                {
                    "name": child_name,
                    "display_name": CHILD_DISPLAY_NAMES.get(child_name, child_name),
                }
                for child_name in registry[module_name]
            ],
        }
        for module_name in MODULE_DISPLAY_NAMES
    ]


@nats_client.register
def get_mlops_module_data(module, child_module, page, page_size, group_id):
    registry = _get_module_registry()
    model, team_lookup = registry[module][child_module]
    queryset = model.objects.filter(**{f"{team_lookup}__contains": int(group_id)})

    total_count = queryset.count()
    start = (page - 1) * page_size
    end = page * page_size
    data_list = queryset.values("id", "name")[start:end]

    return {"count": total_count, "items": list(data_list)}
