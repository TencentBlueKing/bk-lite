from types import SimpleNamespace

import pytest

from apps.mlops.utils.i18n import mlops_exception_message, mlops_message, mlops_message_for_locale
from apps.mlops.utils.webhook_client import WebhookConnectionError, WebhookError, WebhookTimeoutError


def _request(locale: str):
    return SimpleNamespace(user=SimpleNamespace(locale=locale))


def test_mlops_message_uses_request_user_locale():
    assert (
        mlops_message(
            _request("en"),
            "error.algorithm_config_not_found",
            algorithm="anomaly_detection/ECOD",
        )
        == "Algorithm configuration was not found: anomaly_detection/ECOD"
    )


def test_mlops_message_uses_default_for_zh_cn_locale():
    assert (
        mlops_message(
            _request("zh-CN"),
            "error.algorithm_config_not_found",
            algorithm="anomaly_detection/ECOD",
        )
        == "未找到算法配置：anomaly_detection/ECOD"
    )


def test_mlops_message_for_locale_supports_nats_keys():
    assert mlops_message_for_locale("en", "module.dataset") == "Dataset"
    assert mlops_message_for_locale("zh-Hans", "module.dataset") == "数据集"
    assert mlops_message_for_locale("en", "error.nats_unknown_module", module="x") == "Unknown module: x"


def test_mlops_exception_message_localizes_webhook_timeout_to_english():
    message = mlops_exception_message(_request("en"), WebhookTimeoutError("请求 webhookd 服务超时，请检查服务是否正常运行"))
    assert message == "Request to the webhookd service timed out. Please check whether the service is running"
    assert "请求" not in message


def test_mlops_exception_message_localizes_webhook_connection_to_english():
    message = mlops_exception_message(_request("en"), WebhookConnectionError("无法连接到 webhookd 服务: refused"))
    assert message == "Unable to connect to the webhookd service"
    assert "无法连接" not in message


def test_mlops_exception_message_maps_generic_webhook_error_without_leaking_source():
    message = mlops_exception_message(_request("en"), WebhookError("boom: gateway down"))
    assert message == "Request to the webhookd service failed"
    assert "boom" not in message
    assert "gateway" not in message


def test_mlops_exception_message_localizes_error_keys():
    assert (
        mlops_exception_message(_request("en"), ValueError("error.serving_port_not_configured"))
        == "Service port is not configured. Please confirm the service has started"
    )
    assert (
        mlops_exception_message(_request("zh-Hans"), ValueError("error.mlflow_tracker_url_not_configured"))
        == "环境变量 MLFLOW_TRACKER_URL 未配置"
    )


def test_remaining_user_facing_keys_have_english_copy():
    assert mlops_message(_request("en"), "error.prediction_failed") == "Prediction failed"
    assert (
        mlops_message(_request("en"), "error.serving_prediction_timeout_exceeded", seconds=80)
        == "Prediction request timed out (exceeded 80 seconds)"
    )
    assert mlops_message(_request("zh-Hans"), "error.serving_prediction_timeout_exceeded", seconds=80) == "预测请求超时（超过 80 秒）"
    assert mlops_message(_request("en"), "message.container_already_exists") == "Container already exists"
    assert (
        mlops_message(_request("en"), "message.config_rolled_back_old_service_delete_unknown")
        == "Configuration was rolled back, but the result of deleting the old service is unknown"
    )
    assert (
        mlops_message(_request("en"), "error.train_job_dataset_version_access_denied")
        == "The associated dataset version of this training task cannot be accessed"
    )


@pytest.mark.parametrize(
    ("key", "values", "zh_text", "en_text"),
    [
        (
            "error.train_job_config_pointer_update_failed",
            {"pk": 7},
            "训练配置数据库指针更新失败: TrainJob 7 不存在",
            "Training config DB pointer update failed: TrainJob 7 does not exist",
        ),
        (
            "error.train_job_config_minio_sync_failed",
            {"detail": "storage offline"},
            "训练配置同步到 MinIO 失败，数据库变更已回滚: storage offline",
            "Failed to sync training config to MinIO; DB changes rolled back: storage offline",
        ),
        (
            "error.train_meta_must_be_nonempty_dict",
            {},
            "train_meta必须是非空字典",
            "train_meta must be a non-empty dict",
        ),
        (
            "error.train_meta_classes_must_be_nonempty_list",
            {},
            "train_meta.classes必须是非空列表",
            "train_meta.classes must be a non-empty list",
        ),
        (
            "error.val_meta_must_be_nonempty_dict",
            {},
            "val_meta必须是非空字典",
            "val_meta must be a non-empty dict",
        ),
        (
            "error.val_meta_classes_must_be_nonempty_list",
            {},
            "val_meta.classes必须是非空列表",
            "val_meta.classes must be a non-empty list",
        ),
        (
            "error.test_meta_must_be_dict",
            {},
            "test_meta必须是字典",
            "test_meta must be a dict",
        ),
        (
            "error.test_meta_classes_must_be_list",
            {},
            "test_meta.classes必须是列表",
            "test_meta.classes must be a list",
        ),
        (
            "error.dataset_classes_all_empty",
            {},
            "所有数据集的 classes 都为空",
            "classes are empty in all datasets",
        ),
        (
            "error.dataset_class_name_conflict",
            {"detail": "class_id=1: expected='dog', actual='bird'"},
            "类别名称冲突，无法发布数据集版本: class_id=1: expected='dog', actual='bird'",
            "Class name conflict; cannot publish dataset version: class_id=1: expected='dog', actual='bird'",
        ),
    ],
)
def test_review_ab_error_keys_match_catalog(key, values, zh_text, en_text):
    assert mlops_message_for_locale("zh-Hans", key, **values) == zh_text
    assert mlops_message_for_locale("zh-CN", key, **values) == zh_text
    assert mlops_message_for_locale(None, key, **values) == zh_text
    assert mlops_message_for_locale("en", key, **values) == en_text
    assert zh_text != en_text
    assert key not in zh_text
    assert key not in en_text
