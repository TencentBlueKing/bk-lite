from types import SimpleNamespace

from apps.mlops.utils.i18n import mlops_message, mlops_message_for_locale


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
