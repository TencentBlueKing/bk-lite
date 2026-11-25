import json
from datetime import datetime, timedelta, timezone

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.log.models import SyslogSourceDevice
from apps.log.views.syslog_source_device import SyslogSourceDeviceViewSet
from apps.node_mgmt.models.cloud_region import CloudRegion

VIEW = SyslogSourceDeviceViewSet.as_view({"get": "list"})
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def _get(user, params=None, team="1"):
    request = APIRequestFactory().get("/api/v1/log/syslog_source_devices/", params or {})
    if team is not None:
        request.COOKIES["current_team"] = team
    force_authenticate(request, user=user)
    return VIEW(request)


def _body(response):
    return json.loads(response.content)


def _device(cloud_region_id, source_ip, hostname, last_seen, first_seen=None):
    return SyslogSourceDevice.objects.create(
        cloud_region_id=cloud_region_id,
        source_ip=source_ip,
        hostname=hostname,
        first_seen=first_seen or last_seen,
        last_seen=last_seen,
    )


def _freeze(monkeypatch):
    monkeypatch.setattr("apps.log.services.syslog_source_device.django_timezone.now", lambda: NOW)


@pytest.mark.django_db
def test_list_requires_current_team_and_source_device_view_permission(authenticated_user, monkeypatch):
    _freeze(monkeypatch)
    _device("1", "10.0.0.1", "edge", NOW)
    _device("2", "10.0.0.2", "other-team-label", NOW)

    missing_team = _get(authenticated_user, team=None)
    assert missing_team.status_code == 403
    assert _body(missing_team)["result"] is False

    for integration_only in ({"integration_list-View"}, {"integration_configure-View"}, {"receive-View"}):
        authenticated_user.permission = {"log": integration_only}
        denied = _get(authenticated_user)
        assert denied.status_code == 403

    authenticated_user.permission = {"log": {"source_device-View"}}
    allowed = _get(authenticated_user)
    assert allowed.status_code == 200
    payload = _body(allowed)["data"]
    assert payload["count"] == 2
    assert {item["hostname"] for item in payload["items"]} == {"edge", "other-team-label"}
    assert "organization" not in payload["items"][0]

    authenticated_user.permission = {"log": set()}
    authenticated_user.is_superuser = True
    superuser = _get(authenticated_user)
    assert superuser.status_code == 200
    assert _body(superuser)["data"]["count"] == 2


@pytest.mark.django_db
def test_status_boundary_search_query_and_filters(authenticated_user, monkeypatch):
    _freeze(monkeypatch)
    authenticated_user.permission = {"log": {"source_device-View"}}
    region = CloudRegion.objects.create(name="华东")
    boundary = NOW - timedelta(hours=24)
    silent_at = boundary - timedelta(microseconds=1)
    quoted_hostname = 'a"b\\c'
    active = _device(str(region.id), "10.1.2.3", quoted_hostname, boundary, first_seen=boundary - timedelta(hours=1))
    _device("missing", "10.9.9.9", "", silent_at)
    _device(str(region.id), "10.1.2.30", "other", boundary)

    active_response = _get(authenticated_user, {"status": "active"})
    assert active_response.status_code == 200
    active_items = _body(active_response)["data"]["items"]
    assert [item["hostname"] for item in active_items] == [quoted_hostname, "other"]
    quoted = next(item for item in active_items if item["hostname"] == quoted_hostname)
    assert quoted["cloud_region_name"] == "华东"
    assert quoted["status"] == "active"
    assert quoted["search_query"] == (
        'collect_type:"syslog" AND ' f'cloud_region_id:"{region.id}" AND ' 'source_ip:"10.1.2.3" AND ' 'hostname:"a\\"b\\\\c"'
    )
    assert quoted["search_start"] == int(active.first_seen.timestamp() * 1000)
    assert quoted["search_end"] == int(NOW.timestamp() * 1000)

    silent_response = _get(authenticated_user, {"status": "silent"})
    silent_items = _body(silent_response)["data"]["items"]
    assert len(silent_items) == 1
    assert silent_items[0]["hostname"] == ""
    assert silent_items[0]["status"] == "silent"
    assert silent_items[0]["cloud_region_name"] == ""
    assert 'hostname:""' in silent_items[0]["search_query"]

    filtered = _get(authenticated_user, {"cloud_region_id": str(region.id), "source_ip": "10.1.2.3", "hostname": "a"})
    filtered_items = _body(filtered)["data"]["items"]
    assert [item["source_ip"] for item in filtered_items] == ["10.1.2.3"]

    by_name = _get(authenticated_user, {"cloud_region_id": "华东"})
    assert {item["source_ip"] for item in _body(by_name)["data"]["items"]} == {"10.1.2.3", "10.1.2.30"}
    by_host = _get(authenticated_user, {"keyword": "other"})
    assert [item["hostname"] for item in _body(by_host)["data"]["items"]] == ["other"]
    by_ip = _get(authenticated_user, {"keyword": "10.9.9.9"})
    assert [item["source_ip"] for item in _body(by_ip)["data"]["items"]] == ["10.9.9.9"]


@pytest.mark.django_db
def test_cloud_region_name_uses_the_same_display_name_as_the_region_list(authenticated_user, monkeypatch):
    _freeze(monkeypatch)
    authenticated_user.permission = {"log": {"source_device-View"}}
    builtin = CloudRegion.objects.create(name="default")
    custom = CloudRegion.objects.create(name="华东")
    _device(str(builtin.id), "10.0.0.1", "edge", NOW)
    _device(str(custom.id), "10.0.0.2", "core", NOW)

    authenticated_user.locale = "zh-Hans"
    zh_items = _body(_get(authenticated_user))["data"]["items"]
    zh_names = {item["source_ip"]: item["cloud_region_name"] for item in zh_items}
    assert zh_names["10.0.0.1"] == "直连区域"
    assert zh_names["10.0.0.2"] == "华东"

    authenticated_user.locale = "en"
    en_items = _body(_get(authenticated_user))["data"]["items"]
    en_names = {item["source_ip"]: item["cloud_region_name"] for item in en_items}
    assert en_names["10.0.0.1"] == "Direct Connection Zone"
    assert en_names["10.0.0.2"] == "华东"


@pytest.mark.django_db
def test_list_paginates_and_rejects_invalid_query(authenticated_user, monkeypatch):
    _freeze(monkeypatch)
    authenticated_user.permission = {"log": {"source_device-View"}}
    for index in range(3):
        _device("1", f"10.0.0.{index}", f"host-{index}", NOW - timedelta(minutes=index))

    page = _get(authenticated_user, {"page": 2, "page_size": 2})
    payload = _body(page)["data"]
    assert payload["count"] == 3
    assert [item["hostname"] for item in payload["items"]] == ["host-2"]

    sentinel = "STATUS_SENTINEL"
    invalid = _get(authenticated_user, {"status": sentinel, "page_size": -1})
    assert invalid.status_code == 400
    assert _body(invalid)["message"] == "invalid query"
    assert sentinel not in invalid.content.decode()

    post = APIRequestFactory().post("/api/v1/log/syslog_source_devices/", {}, format="json")
    post.COOKIES["current_team"] = "1"
    force_authenticate(post, user=authenticated_user)
    assert VIEW(post).status_code == 405
