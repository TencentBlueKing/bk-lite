"""补丁周期评估设置 API 的行为测试。"""

import pytest
from rest_framework import status


SCAN_SETTING_URL = "/api/v1/patch_mgmt/api/scan_setting/save/"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("payload", "expected_crontab"),
    [
        (
            {
                "frequency": "hourly",
                "hour_interval": 6,
                "weekday": 1,
                "time": "03:30",
                "is_enabled": True,
            },
            "0 */6 * * *",
        ),
        (
            {
                "frequency": "daily",
                "hour_interval": 1,
                "weekday": 1,
                "time": "03:30",
                "is_enabled": True,
            },
            "30 03 * * *",
        ),
        (
            {
                "frequency": "weekly",
                "hour_interval": 1,
                "weekday": 7,
                "time": "04:15",
                "is_enabled": True,
            },
            "15 04 * * 0",
        ),
    ],
)
def test_save_enabled_scan_setting_registers_runnable_crontab(
    su_client, mocker, payload, expected_crontab
):
    """启用周期评估时，应按频率向平台调度器提交标准五段 crontab。"""
    schedule = mocker.patch(
        "apps.patch_mgmt.serializers.scan_setting.CeleryUtils.create_or_update_periodic_task"
    )

    response = su_client.put(SCAN_SETTING_URL, payload, format="json")

    assert response.status_code == status.HTTP_200_OK
    schedule.assert_called_once_with(
        name="patch_mgmt_periodic_compliance_scan",
        crontab=expected_crontab,
        task="apps.patch_mgmt.tasks.run_periodic_compliance_scan",
        enabled=True,
    )


@pytest.mark.django_db
def test_save_disabled_scan_setting_disables_registered_task(su_client, mocker):
    """关闭周期评估时，应停用已有调度且不再注册新调度。"""
    disable = mocker.patch(
        "apps.patch_mgmt.serializers.scan_setting.CeleryUtils.disable_periodic_task"
    )
    schedule = mocker.patch(
        "apps.patch_mgmt.serializers.scan_setting.CeleryUtils.create_or_update_periodic_task"
    )

    response = su_client.put(
        SCAN_SETTING_URL,
        {
            "frequency": "daily",
            "hour_interval": 1,
            "weekday": 1,
            "time": "03:30",
            "is_enabled": False,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    disable.assert_called_once_with("patch_mgmt_periodic_compliance_scan")
    schedule.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("payload", "error_field"),
    [
        (
            {
                "frequency": "hourly",
                "hour_interval": 0,
                "weekday": 1,
                "time": "03:30",
                "is_enabled": True,
            },
            "hour_interval",
        ),
        (
            {
                "frequency": "hourly",
                "hour_interval": 25,
                "weekday": 1,
                "time": "03:30",
                "is_enabled": True,
            },
            "hour_interval",
        ),
        (
            {
                "frequency": "weekly",
                "hour_interval": 1,
                "weekday": 8,
                "time": "03:30",
                "is_enabled": True,
            },
            "weekday",
        ),
        (
            {
                "frequency": "daily",
                "hour_interval": 1,
                "weekday": 1,
                "time": "24:00",
                "is_enabled": True,
            },
            "time",
        ),
        (
            {
                "frequency": "daily",
                "hour_interval": 1,
                "weekday": 1,
                "time": "invalid",
                "is_enabled": True,
            },
            "time",
        ),
    ],
)
def test_invalid_scan_setting_is_rejected_without_changing_scheduler(
    su_client, mocker, payload, error_field
):
    """非法调度配置应返回字段错误，且不得修改现有调度。"""
    schedule = mocker.patch(
        "apps.patch_mgmt.serializers.scan_setting.CeleryUtils.create_or_update_periodic_task"
    )
    disable = mocker.patch(
        "apps.patch_mgmt.serializers.scan_setting.CeleryUtils.disable_periodic_task"
    )

    response = su_client.put(SCAN_SETTING_URL, payload, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert error_field in response.data
    schedule.assert_not_called()
    disable.assert_not_called()
