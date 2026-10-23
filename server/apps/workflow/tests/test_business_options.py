import pytest

from apps.system_mgmt.models import User
from apps.workflow.services.business_options import materialize_business_options


@pytest.mark.django_db
def test_materialize_business_options_filters_users_by_team_membership(mocker):
    User.objects.create(
        username="in-team",
        password="x",
        display_name="In Team",
        email="in@example.com",
        group_list=[7],
        disabled=False,
    )
    User.objects.create(
        username="out-team",
        password="x",
        display_name="Out Team",
        email="out@example.com",
        group_list=[8],
        disabled=False,
    )
    catalog = {
        "bklite_notification": {
            "input_schema": {
                "properties": {
                    "recipients": {"type": "array", "items": {"type": "string"}},
                }
            }
        }
    }
    filter_spy = mocker.spy(User.objects, "filter")

    materialize_business_options(catalog, team=7)

    recipients = catalog["bklite_notification"]["input_schema"]["properties"]["recipients"]["items"]
    assert recipients["x-enum-usernames"]
    assert "in-team" in recipients["x-enum-usernames"].values()
    assert "out-team" not in recipients["x-enum-usernames"].values()
    assert any(call.kwargs.get("disabled") is False for call in filter_spy.call_args_list)


@pytest.mark.django_db
def test_notification_channels_keep_name_and_record_type():
    from apps.system_mgmt.models import Channel

    email = Channel.objects.create(name="邮件服务器", channel_type="email", description="", team=[7])
    nats = Channel.objects.create(name="告警中心", channel_type="nats", description="", team=[7])
    Channel.objects.create(name="其他组织邮箱", channel_type="email", description="", team=[8])
    catalog = {
        "bklite_notification": {
            "input_schema": {
                "properties": {
                    "channel_id": {"type": "integer"},
                }
            }
        }
    }

    materialize_business_options(catalog, team=7)

    channel_schema = catalog["bklite_notification"]["input_schema"]["properties"]["channel_id"]
    assert set(channel_schema["enum"]) == {email.id, nats.id}
    assert channel_schema["x-enum-labels"] == {str(email.id): "邮件服务器", str(nats.id): "告警中心"}
    assert channel_schema["x-enum-channel-types"] == {str(email.id): "email", str(nats.id): "nats"}
