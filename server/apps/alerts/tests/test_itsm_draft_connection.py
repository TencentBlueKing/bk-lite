from unittest.mock import patch

import pytest

from apps.alerts.tests.test_itsm_client import response
from apps.alerts.tests.test_itsm_views import configured_api_client, superuser_client  # noqa: F401

BASE = "/api/v1/alerts/api/itsm_integration/"


def draft(**changes):
    return {"name": "Draft", "url": "https://itsm.example/api", "token": "DRAFT-SENTINEL", "enabled": False, **changes}


@pytest.mark.django_db
def test_unsaved_form_is_tested_without_persisting_credentials(itsm_api_client):
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch(
        "requests.Session.request", return_value=response({"result": True, "code": "20000", "data": {"results": [], "count": 0}})
    ) as http:
        result = itsm_api_client.post(BASE + "test_connection/", draft(), format="json")
    assert result.status_code == 200
    assert http.call_args.args == ("GET", "https://itsm.example/api/ticket_list/?page=1&page_size=1")
    assert http.call_args.kwargs["headers"]["Authorization"] == "Bearer DRAFT-SENTINEL"
    assert http.call_args.kwargs["verify"] is True
    assert "DRAFT-SENTINEL" not in str(result.data)
    assert itsm_api_client.get(BASE).json()["data"] is None


@pytest.mark.django_db
def test_failed_probe_blocks_enable_but_allows_disabled_draft(itsm_api_client):
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch(
        "requests.Session.request", return_value=response({}, 404)
    ) as http:
        result = itsm_api_client.put(BASE + "configure/", draft(enabled=True), format="json")
        assert result.status_code == 400
        assert "404" in str(result.data)
        assert http.call_count == 1
        assert itsm_api_client.get(BASE).json()["data"] is None
        assert itsm_api_client.put(BASE + "configure/", draft(), format="json").status_code == 200
        assert http.call_count == 1


@pytest.mark.django_db
def test_draft_reuses_saved_token_only_for_same_target(itsm_api_client):
    assert itsm_api_client.put(BASE + "configure/", draft(), format="json").status_code == 200
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch(
        "requests.Session.request", return_value=response({"result": True, "code": "20000", "data": {"results": [], "count": 0}})
    ) as http:
        assert itsm_api_client.post(BASE + "test_connection/", draft(token=""), format="json").status_code == 200
        assert http.call_args.kwargs["headers"]["Authorization"] == "Bearer DRAFT-SENTINEL"
        denied = itsm_api_client.post(BASE + "test_connection/", draft(token="", url="https://other.example/api"), format="json")
        assert denied.status_code == 400
        assert http.call_count == 1
        values = draft(token="NEW-SENTINEL", url="https://other.example/api")
        assert itsm_api_client.post(BASE + "test_connection/", values, format="json").status_code == 200
        assert http.call_args.kwargs["headers"]["Authorization"] == "Bearer NEW-SENTINEL"
    assert itsm_api_client.get(BASE).json()["data"]["url"] == draft()["url"]


@pytest.mark.django_db
def test_failed_update_preserves_enabled_connection_and_disable_needs_no_network(itsm_api_client):
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch(
        "requests.Session.request", return_value=response({"result": True, "code": "20000", "data": {"results": [], "count": 0}})
    ):
        assert itsm_api_client.put(BASE + "configure/", draft(enabled=True), format="json").status_code == 200
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch(
        "requests.Session.request", return_value=response({}, 401)
    ) as http:
        result = itsm_api_client.put(BASE + "configure/", draft(enabled=True, token="INVALID-SENTINEL"), format="json")
        assert result.status_code == 400
        assert itsm_api_client.get(BASE).json()["data"]["enabled"] is True
        assert itsm_api_client.put(BASE + "configure/", draft(token=""), format="json").status_code == 200
        assert http.call_count == 1
    from apps.alerts.itsm.integration import resolve_token
    from apps.alerts.models.itsm import AlertItsmIntegration

    row = AlertItsmIntegration.objects.get(team_id=1)
    assert resolve_token(row.pk, allow_disabled=True) == "DRAFT-SENTINEL"


@pytest.mark.django_db
def test_configuration_changed_during_probe_cannot_be_overwritten(itsm_api_client):
    assert itsm_api_client.put(BASE + "configure/", draft(), format="json").status_code == 200

    def remote(*args, **kwargs):
        changed = draft(token="CONCURRENT-SENTINEL", name="Other admin")
        assert itsm_api_client.put(BASE + "configure/", changed, format="json").status_code == 200
        return response({"result": True, "code": "20000", "data": {"results": [], "count": 0}})

    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), patch("requests.Session.request", side_effect=remote):
        result = itsm_api_client.put(BASE + "configure/", draft(enabled=True, token=""), format="json")
    assert result.status_code == 400
    assert "配置在测试期间已变更" in str(result.data)
    current = itsm_api_client.get(BASE).json()["data"]
    assert current["name"] == "Other admin" and current["enabled"] is False
