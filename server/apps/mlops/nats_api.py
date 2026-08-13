import os

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
from apps.mlops.utils.i18n import mlops_message_for_locale

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

MAX_PAGE_SIZE = int(os.getenv("MLOPS_NATS_MAX_PAGE_SIZE", "500"))

MODULE_NAMES = ("dataset", "train_job", "serving")

MODULE_DISPLAY_NAME_KEYS = {
    "dataset": "module.dataset",
    "train_job": "module.train_job",
    "serving": "module.serving",
}

CHILD_DISPLAY_NAME_KEYS = {
    "anomaly_detection_dataset": "module.anomaly_detection_dataset",
    "anomaly_detection_train_data": "module.anomaly_detection_train_data",
    "anomaly_detection_dataset_release": "module.anomaly_detection_dataset_release",
    "anomaly_detection_train_job": "module.anomaly_detection_train_job",
    "anomaly_detection_serving": "module.anomaly_detection_serving",
    "classification_dataset": "module.classification_dataset",
    "classification_train_data": "module.classification_train_data",
    "classification_dataset_release": "module.classification_dataset_release",
    "classification_train_job": "module.classification_train_job",
    "classification_serving": "module.classification_serving",
    "image_classification_dataset": "module.image_classification_dataset",
    "image_classification_train_data": "module.image_classification_train_data",
    "image_classification_dataset_release": "module.image_classification_dataset_release",
    "image_classification_train_job": "module.image_classification_train_job",
    "image_classification_serving": "module.image_classification_serving",
    "log_clustering_dataset": "module.log_clustering_dataset",
    "log_clustering_train_data": "module.log_clustering_train_data",
    "log_clustering_dataset_release": "module.log_clustering_dataset_release",
    "log_clustering_train_job": "module.log_clustering_train_job",
    "log_clustering_serving": "module.log_clustering_serving",
    "object_detection_dataset": "module.object_detection_dataset",
    "object_detection_train_data": "module.object_detection_train_data",
    "object_detection_dataset_release": "module.object_detection_dataset_release",
    "object_detection_train_job": "module.object_detection_train_job",
    "object_detection_serving": "module.object_detection_serving",
    "timeseries_predict_dataset": "module.timeseries_predict_dataset",
    "timeseries_predict_train_data": "module.timeseries_predict_train_data",
    "timeseries_predict_dataset_release": "module.timeseries_predict_dataset_release",
    "timeseries_predict_train_job": "module.timeseries_predict_train_job",
    "timeseries_predict_serving": "module.timeseries_predict_serving",
}


def _get_module_registry():
    registry = {}
    for module_name in MODULE_NAMES:
        merged = {}
        merged.update(ROOT_MODULE_MODEL_MAP.get(module_name, {}))
        merged.update(INHERITED_MODULE_MODEL_MAP.get(module_name, {}))
        registry[module_name] = merged
    return registry


def _resolve_nats_locale(locale=None, actor_context=None):
    if locale is not None:
        return locale
    if isinstance(actor_context, dict) and actor_context.get("locale") is not None:
        return actor_context.get("locale")
    return "zh-Hans"


def _nats_message(locale, key, **values):
    return mlops_message_for_locale(locale, key, **values)


def _module_display_name(module_name, locale):
    return _nats_message(locale, MODULE_DISPLAY_NAME_KEYS[module_name])


def _child_display_name(child_name, locale):
    key = CHILD_DISPLAY_NAME_KEYS.get(child_name)
    if not key:
        return child_name
    return _nats_message(locale, key)


def _normalize_actor_group_ids(actor_context):
    group_ids = set()
    for group in (actor_context or {}).get("group_list") or []:
        group_id = group.get("id") if isinstance(group, dict) else group
        try:
            group_ids.add(int(group_id))
        except (TypeError, ValueError):
            continue
    return group_ids


def _validate_actor_group(actor_context, group_id, locale="zh-Hans"):
    if not isinstance(actor_context, dict):
        return False, None, _nats_message(locale, "error.nats_missing_actor_context")

    try:
        group_id = int(group_id)
    except (TypeError, ValueError):
        return False, None, _nats_message(locale, "error.nats_invalid_group_id")

    if actor_context.get("is_superuser"):
        return True, group_id, ""

    if group_id not in _normalize_actor_group_ids(actor_context):
        return False, group_id, _nats_message(locale, "error.nats_group_access_denied")

    return True, group_id, ""


@nats_client.register
def get_mlops_module_list(locale=None, actor_context=None):
    locale = _resolve_nats_locale(locale=locale, actor_context=actor_context)
    registry = _get_module_registry()
    return [
        {
            "name": module_name,
            "display_name": _module_display_name(module_name, locale),
            "children": [
                {
                    "name": child_name,
                    "display_name": _child_display_name(child_name, locale),
                }
                for child_name in registry[module_name]
            ],
        }
        for module_name in MODULE_NAMES
    ]


@nats_client.register
def get_mlops_module_data(module, child_module, page, page_size, group_id, actor_context=None, locale=None):
    locale = _resolve_nats_locale(locale=locale, actor_context=actor_context)
    registry = _get_module_registry()

    module_map = registry.get(module)
    if module_map is None:
        return {
            "result": False,
            "message": _nats_message(locale, "error.nats_unknown_module", module=module),
        }

    entry = module_map.get(child_module)
    if entry is None:
        return {
            "result": False,
            "message": _nats_message(
                locale,
                "error.nats_unknown_child_module",
                module=module,
                child_module=child_module,
            ),
        }

    is_valid, group_id, message = _validate_actor_group(actor_context, group_id, locale=locale)
    if not is_valid:
        return {"result": False, "message": message}

    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))

    model, team_lookup = entry
    queryset = model.objects.filter(**{f"{team_lookup}__contains": group_id})

    total_count = queryset.count()
    start = (page - 1) * page_size
    end = page * page_size
    data_list = queryset.values("id", "name")[start:end]

    return {"result": True, "count": total_count, "items": list(data_list)}
