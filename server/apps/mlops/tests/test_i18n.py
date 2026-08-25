from types import SimpleNamespace

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
