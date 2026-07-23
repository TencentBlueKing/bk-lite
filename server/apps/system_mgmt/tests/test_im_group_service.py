from unittest.mock import MagicMock, patch

import pytest

from apps.system_mgmt.models import IMNotificationChannel, IntegrationInstance, User
from apps.system_mgmt.services.im_channel_access import can_access_im_channel, filter_accessible_im_channels
from apps.system_mgmt.services.im_group_service import IMGroupChannelError, IMGroupRuntimeService

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def user(db):
    return User.objects.create(username="im-group-user", display_name="IM Group User", email="im-group-user@example.com", domain="domain.com",)


@pytest.fixture
def ready_instance(db):
    return IntegrationInstance.objects.create(
        name="feishu-im-group",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"im_notification": "ready", "im_group": "ready"},
        config={"app_id": "cli_xxx", "app_secret": "plain-secret"},
    )


@pytest.fixture
def channel(ready_instance):
    return IMNotificationChannel.objects.create(
        name="feishu-im-group",
        integration_instance=ready_instance,
        enabled=True,
        status="ready",
        platform_match_field="email",
        external_match_field="email",
        external_receive_field="user_id",
        team=[1],
    )


@pytest.mark.django_db
def test_ready_channels_require_team_mapping_and_both_capabilities(user, channel):
    user.group_list = [{"id": channel.team[0]}]

    assert list(IMGroupRuntimeService.list_ready_channels(user)) == [channel]


@pytest.mark.django_db
def test_channel_with_mapping_ready_but_group_unverified_is_hidden(user, channel):
    user.group_list = [{"id": channel.team[0]}]
    channel.integration_instance.capability_status = {"im_notification": "ready"}
    channel.integration_instance.save(update_fields=["capability_status"])

    assert list(IMGroupRuntimeService.list_ready_channels(user)) == []


@pytest.mark.django_db
def test_common_access_rules_cover_regular_unassigned_cross_team_and_superusers(user, channel):
    user.group_list = [{"id": 1}]
    assert can_access_im_channel(user, channel) is True
    assert list(filter_accessible_im_channels(IMNotificationChannel.objects.all(), user)) == [channel]

    user.group_list = []
    assert can_access_im_channel(user, channel) is False
    assert list(filter_accessible_im_channels(IMNotificationChannel.objects.all(), user)) == []

    user.group_list = [{"id": 2}]
    assert can_access_im_channel(user, channel) is False
    assert list(filter_accessible_im_channels(IMNotificationChannel.objects.all(), user)) == []

    user.is_superuser = True
    assert can_access_im_channel(user, channel) is True
    assert list(filter_accessible_im_channels(IMNotificationChannel.objects.all(), user)) == [channel]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda channel: setattr(channel, "enabled", False), "im_group.channel_unavailable"),
        (lambda channel: setattr(channel, "status", "needs_resync"), "im_group.channel_not_ready"),
        (lambda channel: setattr(channel.integration_instance, "provider_key", "wechat"), "im_group.provider_unsupported",),
        (lambda channel: setattr(channel.integration_instance, "enabled", False), "im_group.instance_not_ready"),
        (lambda channel: setattr(channel.integration_instance, "status", "verification_failed"), "im_group.instance_not_ready"),
        (lambda channel: setattr(channel.integration_instance, "capability_status", {"im_notification": "ready"}), "im_group.capability_not_ready"),
    ],
)
def test_require_ready_channel_rejects_each_unready_state(user, channel, mutate, expected_code):
    user.group_list = [{"id": 1}]
    mutate(channel)
    channel.integration_instance.save()
    channel.save()

    with pytest.raises(IMGroupChannelError) as error:
        IMGroupRuntimeService.require_ready_channel(user, channel.id)

    assert error.value.code == expected_code


@pytest.mark.django_db
def test_require_ready_channel_rejects_cross_team_user(user, channel):
    user.group_list = [{"id": 2}]

    with pytest.raises(IMGroupChannelError) as error:
        IMGroupRuntimeService.require_ready_channel(user, channel.id)

    assert error.value.code == "im_group.channel_access_denied"


@pytest.mark.django_db
def test_require_ready_channel_allows_superuser_without_team_mapping(user, channel):
    user.is_superuser = True

    assert IMGroupRuntimeService.require_ready_channel(user, channel.id) == channel


@pytest.mark.django_db
def test_execute_dispatches_im_group_capability(channel):
    expected = MagicMock()
    with patch("apps.system_mgmt.services.im_group_service.RuntimeApplicationService") as runtime_class:
        runtime_class.return_value.execute.return_value = expected

        result = IMGroupRuntimeService.execute(channel, "create_group", group_name="incident")

    assert result is expected
    runtime_class.return_value.execute.assert_called_once_with(
        provider_key="feishu",
        capability_key="im_group",
        operation="create_group",
        config=channel.integration_instance.get_runtime_config(),
        channel=channel,
        group_name="incident",
    )
