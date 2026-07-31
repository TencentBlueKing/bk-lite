import datetime

import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_旧时间范围_patch_通过统计接口生效(api_client, authenticated_user, mocker):
    api_client.force_login(authenticated_user)
    start_time = datetime.datetime(2026, 1, 1)
    end_time = datetime.datetime(2026, 1, 2)
    get_time_range = mocker.patch(
        "apps.opspilot.views.set_time_range",
        return_value=(end_time, start_time),
    )

    response = api_client.get(
        "/api/v1/opspilot/bot_mgmt/get_token_consumption_overview/",
        {"start_time": "2026-01-01T00:00:00.000Z", "end_time": "2026-01-02T00:00:00.000Z"},
    )

    assert response.status_code == 200
    get_time_range.assert_called_once_with("2026-01-02T00:00:00.000Z", "2026-01-01T00:00:00.000Z")
    assert [item["date"] for item in response.json()["data"]["items"]] == ["2026-01-01", "2026-01-02"]
