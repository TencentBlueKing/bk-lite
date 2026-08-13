"""补丁周期评估设置 API 的行为测试。"""

import pytest
from rest_framework import status

from apps.patch_mgmt.models import ScanSetting


SCAN_SETTING_URL = "/api/v1/patch_mgmt/api/scan_setting/save/"
NOTIFICATION_CANDIDATES_URL = (
    "/api/v1/patch_mgmt/api/scan_setting/notification_candidates/"
)


@pytest.mark.django_db
def test_notification_candidates_only_returns_authorized_channels_and_users(
    su_client, mocker
):
    """配置页只通过补丁管理的授权候选接口读取渠道和用户。"""
    load_candidates = mocker.patch(
        "apps.patch_mgmt.views.scan_setting.load_notification_candidates",
        return_value={
            "channels": [
                {"id": 7, "name": "运维邮箱", "channel_type": "email"}
            ],
            "users": [
                {"id": 11, "username": "alice", "display_name": "Alice"}
            ],
            "team_id": 1,
        },
    )

    response = su_client.get(NOTIFICATION_CANDIDATES_URL)

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {
        "channels": [
            {"id": 7, "name": "运维邮箱", "channel_type": "email"}
        ],
        "users": [
            {"id": 11, "username": "alice", "display_name": "Alice"}
        ],
    }
    load_candidates.assert_called_once()


@pytest.mark.django_db
def test_save_notification_rules_returns_server_normalized_channel_snapshots(
    su_client, mocker
):
    """开启通知时，API 应用授权范围内的渠道和用户数据固化规则，
    不信任客户端传入的渠道名称或类型。
    """
    mocker.patch(
        "apps.patch_mgmt.serializers.scan_setting.load_notification_candidates",
        return_value={
            "channels": [
                {"id": 7, "name": "运维邮箱", "channel_type": "email"},
                {"id": 9, "name": "自动化工作流", "channel_type": "nats"},
            ],
            "users": [
                {"id": 11, "username": "alice", "display_name": "Alice"},
                {"id": 12, "username": "bob", "display_name": "Bob"},
            ],
            "team_id": 1,
        },
    )

    response = su_client.put(
        SCAN_SETTING_URL,
        {
            "frequency": "daily",
            "hour_interval": 1,
            "weekday": 1,
            "time": "03:30",
            "is_enabled": True,
            "notification_enabled": True,
            "notification_rules": [
                {
                    "channel_id": 7,
                    "channel_name": "伪造名称",
                    "channel_type": "nats",
                    "receivers": [11, 12],
                },
                {"channel_id": 9, "receivers": []},
            ],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["notification_enabled"] is True
    assert response.data["notification_rules"] == [
        {
            "channel_id": 7,
            "channel_name": "运维邮箱",
            "channel_type": "email",
            "receivers": [11, 12],
            "team_id": 1,
        },
        {
            "channel_id": 9,
            "channel_name": "自动化工作流",
            "channel_type": "nats",
            "receivers": [],
            "team_id": 1,
        },
    ]


@pytest.mark.django_db
def test_turning_notification_off_preserves_rules_without_loading_candidates(
    su_client, mocker
):
    """关闭通知只停用现有规则，不应依赖渠道服务，也不接受客户端篡改规则。"""
    setting = ScanSetting.get_singleton()
    existing_rules = [
        {
            "channel_id": 7,
            "channel_name": "运维邮箱",
            "channel_type": "email",
            "receivers": [11],
            "team_id": 1,
        }
    ]
    setting.notification_enabled = True
    setting.notification_rules = existing_rules
    setting.save()
    load_candidates = mocker.patch(
        "apps.patch_mgmt.serializers.scan_setting.load_notification_candidates"
    )

    response = su_client.put(
        SCAN_SETTING_URL,
        {
            "frequency": "daily",
            "hour_interval": 1,
            "weekday": 1,
            "time": "03:30",
            "is_enabled": True,
            "notification_enabled": False,
            "notification_rules": [
                {
                    "channel_id": 999,
                    "channel_name": "客户端伪造渠道",
                    "channel_type": "nats",
                    "receivers": [],
                }
            ],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["notification_enabled"] is False
    assert response.data["notification_rules"] == existing_rules
    load_candidates.assert_not_called()


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


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("payload", "error_field"),
    [
        (
            {
                "hour_interval": 1,
                "weekday": 1,
                "time": "03:30",
                "is_enabled": True,
            },
            "frequency",
        ),
        (
            {
                "frequency": "hourly",
                "weekday": 1,
                "time": "03:30",
                "is_enabled": True,
            },
            "hour_interval",
        ),
        (
            {
                "frequency": "daily",
                "hour_interval": 1,
                "weekday": 1,
                "is_enabled": True,
            },
            "time",
        ),
        (
            {
                "frequency": "weekly",
                "hour_interval": 1,
                "time": "03:30",
                "is_enabled": True,
            },
            "weekday",
        ),
    ],
)
def test_enabled_scan_setting_requires_applicable_schedule_fields(
    su_client, mocker, payload, error_field
):
    """启用周期评估的完整保存必须显式提交当前频率所需字段。"""
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


@pytest.mark.django_db
@pytest.mark.parametrize(
    "notification_rules",
    [
        [],
        [{"receivers": [11]}],
        [{"channel_id": 7, "receivers": []}],
        [
            {"channel_id": 7, "receivers": [11]},
            {"channel_id": 7, "receivers": [12]},
        ],
        [{"channel_id": 7, "receivers": [999]}],
    ],
)
def test_invalid_notification_rules_are_rejected_without_changing_scheduler(
    su_client, mocker, notification_rules
):
    """通知开启时，缺失渠道、接收人、重复渠道和越权接收人都不得入库。"""
    mocker.patch(
        "apps.patch_mgmt.serializers.scan_setting.load_notification_candidates",
        return_value={
            "channels": [{"id": 7, "name": "运维邮箱", "channel_type": "email"}],
            "users": [
                {"id": 11, "username": "alice", "display_name": "Alice"},
                {"id": 12, "username": "bob", "display_name": "Bob"},
            ],
            "team_id": 1,
        },
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
            "is_enabled": True,
            "notification_enabled": True,
            "notification_rules": notification_rules,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "notification_rules" in response.data
    schedule.assert_not_called()
