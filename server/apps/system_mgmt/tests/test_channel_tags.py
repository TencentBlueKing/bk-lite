import pytest
from django.core.management import call_command
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import ChannelChoices, NotificationTag
from apps.system_mgmt.viewset.channel_viewset import ChannelViewSet

pytestmark = pytest.mark.django_db


def _grant(user, permission):
    user.permission = {"system-manager": {permission}}
    user.group_list = [{"id": 1, "name": "team-a"}]
    user.is_superuser = False
    user.locale = "zh-Hans"
    return user


def _payload(tag):
    return {
        "name": "mail",
        "channel_type": ChannelChoices.EMAIL,
        "config": {
            "smtp_server": "smtp.example.com",
            "port": 25,
            "smtp_user": "sender",
            "smtp_pwd": "secret",
            "mail_sender": "sender@example.com",
        },
        "description": "mail channel",
        "team": [1],
        "tag": tag,
    }


def _create(user, tag):
    request = APIRequestFactory().post("/system_mgmt/channel/", _payload(tag), format="json")
    force_authenticate(request, user=user)
    return ChannelViewSet.as_view({"post": "create"})(request)


def test_create_channel_returns_selected_tags_on_later_read(authenticated_user):
    user = _grant(authenticated_user, "channel_list-Add")
    created = _create(user, ["用途:测试环境"])

    assert created.status_code == 201
    assert created.data["tag"] == ["用途:测试环境"]

    user.permission = {"system-manager": {"channel_list-View"}}
    request = APIRequestFactory().get(f"/system_mgmt/channel/{created.data['id']}/")
    force_authenticate(request, user=user)
    read = ChannelViewSet.as_view({"get": "retrieve"})(request, pk=created.data["id"])

    assert read.status_code == 200
    assert read.data["tag"] == ["用途:测试环境"]


def _put(user, channel_id, payload):
    request = APIRequestFactory().put(f"/system_mgmt/channel/{channel_id}/", payload, format="json")
    force_authenticate(request, user=user)
    return ChannelViewSet.as_view({"put": "update"})(request, pk=channel_id)


def test_update_replaces_tags_and_omitted_tag_keeps_selection(authenticated_user):
    user = _grant(authenticated_user, "channel_list-Add")
    created = _create(user, ["用途:测试环境"])
    channel_id = created.data["id"]

    user.permission = {"system-manager": {"channel_list-Edit"}}
    replaced = _put(user, channel_id, _payload(["用途:ITSM"]))
    assert replaced.status_code == 200
    assert replaced.data["tag"] == ["用途:ITSM"]

    kept_payload = _payload([])
    kept_payload.pop("tag")
    kept_payload["name"] = "改名"
    kept = _put(user, channel_id, kept_payload)
    assert kept.status_code == 200
    assert kept.data["name"] == "改名"
    assert kept.data["tag"] == ["用途:ITSM"]


def test_saving_one_channel_does_not_move_another_channels_tags(authenticated_user):
    user = _grant(authenticated_user, "channel_list-Add")
    tagged = _create(user, ["用途:ITSM", "用途:测试环境"])
    plain_payload = _payload([])
    plain_payload["name"] = "plain"
    request = APIRequestFactory().post("/system_mgmt/channel/", plain_payload, format="json")
    force_authenticate(request, user=user)
    plain = ChannelViewSet.as_view({"post": "create"})(request)
    assert plain.status_code == 201

    user.permission = {"system-manager": {"channel_list-Edit"}}
    saved = _put(user, plain.data["id"], {**plain_payload, "description": "saved"})
    assert saved.status_code == 200
    assert saved.data["tag"] == []

    user.permission = {"system-manager": {"channel_list-View"}}
    request = APIRequestFactory().get("/system_mgmt/channel/")
    force_authenticate(request, user=user)
    listed = ChannelViewSet.as_view({"get": "list"})(request)
    assert listed.status_code == 200
    rows = {item["id"]: item for item in listed.data}
    assert rows[tagged.data["id"]]["tag"] == ["用途:ITSM", "用途:测试环境"]
    assert rows[plain.data["id"]]["tag"] == []
    assert [item["id"] for item in listed.data] == sorted(item["id"] for item in listed.data)


def test_invalid_tag_is_rejected_and_empty_selection_is_saved(authenticated_user):
    user = _grant(authenticated_user, "channel_list-Add")
    for token in ("用途,测试", "用途:", ":ITSM", "用途:测 试", "用途:测试\n环境", "用 途:ITSM"):
        invalid = _create(user, [token])
        assert invalid.status_code == 400, token

    cleared = _create(user, [])
    assert cleared.status_code == 201
    assert cleared.data["tag"] == []


def test_tag_catalog_is_global_and_survives_channel_delete(authenticated_user):
    call_command("init_notification_tags")
    user = _grant(authenticated_user, "channel_list-Add")
    created = _create(user, ["用途:测试环境"])

    user.permission = {"system-manager": {"channel_list-Delete"}}
    request = APIRequestFactory().delete(f"/system_mgmt/channel/{created.data['id']}/")
    force_authenticate(request, user=user)
    deleted = ChannelViewSet.as_view({"delete": "destroy"})(request, pk=created.data["id"])
    assert deleted.status_code == 204

    user.permission = {"system-manager": {"channel_list-View"}}
    catalog_request = APIRequestFactory().get("/system_mgmt/channel/tag_catalog/")
    force_authenticate(catalog_request, user=user)
    catalog = ChannelViewSet.as_view({"get": "tag_catalog"})(catalog_request)
    assert catalog.status_code == 200
    assert {"key": "system", "value": "itsm"} in catalog.data["results"]
    assert {"key": "用途", "value": "测试环境"} in catalog.data["results"]

    user.permission = {"system-manager": {"channel_list-Add"}}
    NotificationTag.objects.filter(key="用途", value="ITSM").delete()
    reused = _create(user, ["用途:测试环境", "用途:ITSM"])
    assert reused.status_code == 201
    assert reused.data["tag"] == ["用途:测试环境", "用途:ITSM"]


def test_tag_catalog_pages_and_rejects_unbounded_size(authenticated_user):
    user = _grant(authenticated_user, "channel_list-View")
    NotificationTag.objects.create(key="pagekey", value="one")
    NotificationTag.objects.create(key="pagekey", value="two")

    def fetch(**params):
        request = APIRequestFactory().get("/system_mgmt/channel/tag_catalog/", params)
        force_authenticate(request, user=user)
        return ChannelViewSet.as_view({"get": "tag_catalog"})(request)

    first = fetch(page=1, page_size=1)
    assert first.status_code == 200
    assert first.data["page_size"] == 1
    assert len(first.data["results"]) == 1
    last = fetch(page=first.data["count"], page_size=1)
    assert last.data["results"] == [{"key": "pagekey", "value": "two"}]
    previous = fetch(page=first.data["count"] - 1, page_size=1)
    assert previous.data["results"] == [{"key": "pagekey", "value": "one"}]

    clamped = fetch(page_size=501)
    assert clamped.status_code == 200
    assert clamped.data["page_size"] == 500

    rejected = fetch(page_size=-1)
    assert rejected.status_code == 400
