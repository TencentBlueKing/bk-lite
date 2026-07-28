import json

from rest_framework.test import APIClient

EXECUTE_AGUI_URL = "/api/v1/opspilot/model_provider_mgmt/llm/execute_agui/"


def test_execute_agui_accepts_event_stream_before_authentication():
    response = APIClient().post(
        EXECUTE_AGUI_URL,
        {},
        format="json",
        HTTP_ACCEPT="text/event-stream",
    )

    assert response.status_code == 403
    assert response["Content-Type"].startswith("text/event-stream")

    payload = json.loads(response.content.removeprefix(b"data: ").strip())
    assert payload["result"] is False
    assert payload["code"] == "40300"


def test_execute_agui_keeps_json_renderer_for_wildcard_accept():
    response = APIClient().post(
        EXECUTE_AGUI_URL,
        {},
        format="json",
        HTTP_ACCEPT="*/*",
    )

    assert response.status_code == 403
    assert response["Content-Type"].startswith("application/json")

    payload = response.json()
    assert payload["result"] is False
    assert payload["code"] == "40300"
