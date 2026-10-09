import pytest

from apps.system_mgmt.models import User
from apps.workflow_orchestration.services.business_options import materialize_business_options


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
