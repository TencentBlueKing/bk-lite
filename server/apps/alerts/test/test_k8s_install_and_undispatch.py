"""K8s 安装服务与未分派通知服务覆盖测试。

对照 spec/prd/告警中心·集成：K8s 接入渲染参数校验；未分派告警按系统配置通知。
"""

import pytest

from apps.alerts.service.k8s_install import K8sInstallService
from apps.alerts.service.un_dispatch import UnDispatchService
from apps.core.exceptions.base_app_exception import BaseAppException


# --------------------------------------------------------------------------
# K8sInstallService normalize helpers
# --------------------------------------------------------------------------


def test_normalize_base_url_ok():
    assert K8sInstallService.normalize_base_url("https://host:8000/") == "https://host:8000"


def test_normalize_base_url_empty_raises():
    with pytest.raises(BaseAppException):
        K8sInstallService.normalize_base_url("")


def test_normalize_base_url_bad_scheme_raises():
    with pytest.raises(BaseAppException):
        K8sInstallService.normalize_base_url("ftp://host")


def test_normalize_cluster_name_ok():
    assert K8sInstallService.normalize_cluster_name("  prod ") == "prod"


def test_normalize_cluster_name_empty_raises():
    with pytest.raises(BaseAppException):
        K8sInstallService.normalize_cluster_name("  ")


def test_normalize_push_source_id_default():
    assert K8sInstallService.normalize_push_source_id(None) == "k8s"
    assert K8sInstallService.normalize_push_source_id("custom") == "custom"


def test_build_render_payload():
    payload = K8sInstallService.build_render_payload(
        source_id="k8s",
        source_secret="sec",
        receiver_path="/api/v1/alerts/api/receiver_data/",
        server_url="https://host:8000",
        cluster_name="prod",
        push_source_id="k8s-prod",
    )
    assert payload["server_url"] == "https://host:8000"
    assert payload["cluster_name"] == "prod"
    assert payload["push_source_id"] == "k8s-prod"
    assert payload["receiver_url"].startswith("https://host:8000/")
    assert payload["secret"] == "sec"


def test_validate_token_required():
    with pytest.raises(BaseAppException):
        K8sInstallService.validate_and_get_token_data("")


def test_build_install_command():
    cmd = K8sInstallService.build_install_command("https://host:8000", "tok-123")
    assert "tok-123" in cmd
    assert "kubectl apply" in cmd


# --------------------------------------------------------------------------
# UnDispatchService
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_un_dispatch_config_none():
    assert UnDispatchService.get_un_dispatch_config() is None


@pytest.mark.django_db
def test_search_no_operator_alerts():
    from apps.alerts.constants.constants import AlertStatus
    from apps.alerts.models.models import Alert

    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", status=AlertStatus.UNASSIGNED)
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp2", status=AlertStatus.PENDING)
    result = UnDispatchService.search_no_operator_alerts()
    assert len(result) == 1


@pytest.mark.django_db
def test_notify_un_dispatched_no_config_returns_empty():
    assert UnDispatchService.notify_un_dispatched_alert_params_format(alerts=[]) == []


@pytest.mark.django_db
def test_notify_un_dispatched_config_missing_people_returns_empty():
    from apps.alerts.models.sys_setting import SystemSetting

    # 配置存在但缺少 notify_people → 返回空
    SystemSetting.objects.create(
        key="no_dispatch_alert_notice",
        value={"notify_people": [], "notify_channel": []},
    )
    assert UnDispatchService.notify_un_dispatched_alert_params_format(alerts=[]) == []
