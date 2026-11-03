"""系统 Token 双租户：通知渠道目录与投递 OpenAPI 契约。"""

import json
import uuid
from types import SimpleNamespace

import pytest
from jsonschema import Draft7Validator
from rest_framework.test import APIClient

from apps.core.openapi.testing import acting_headers, create_system_tenant
from apps.system_mgmt.models import Group, Menu, Role
from apps.system_mgmt.models import User as SystemUser
from apps.system_mgmt.models.channel import Channel, ChannelChoices

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

LIST_URL = "/openapi/v1/system-mgmt/notification-channels"
SEND_URL = "/openapi/v1/system-mgmt/notification-channels/send"
DOCS_URL = "/openapi/v1/_docs"
SCOPE = {"mode": "all"}
_SECRET = "secret-smtp-value"
_WEBHOOK = "https://hooks.example.com/secret-token"
_ITEM_FIELDS = {
    "id",
    "name",
    "channel_type",
    "description",
    "delivery_mode",
    "recipient_mode",
    "availability",
    "send_parameters",
    "tag",
}


def _tenant(user, team, token):
    return SimpleNamespace(
        user=user,
        team=team,
        token=token,
        system_user=SystemUser.objects.get(username=user.username, domain=user.domain),
    )


def _acting(tenant):
    return acting_headers(tenant.token, tenant.user, tenant.team.id)


def _grant(system_user, names):
    menu_ids = []
    for name in names:
        menu, _ = Menu.objects.get_or_create(
            name=name,
            app="system-manager",
            defaults={"display_name": name, "url": "", "menu_type": "button"},
        )
        menu_ids.append(menu.id)
    role, _ = Role.objects.update_or_create(
        name=f"openapi-channel-{system_user.username}",
        app="system-manager",
        defaults={"menu_list": menu_ids},
    )
    system_user.role_list = [role.id]
    system_user.save(update_fields=["role_list"])


def _channel(*, name, channel_type, team_id, config=None):
    return Channel.objects.create(
        name=name,
        channel_type=channel_type,
        config=config or {},
        description=f"{name} 说明",
        team=[team_id],
    )


@pytest.fixture
def tenants():
    team_a = Group.objects.create(name=f"ch-a-{uuid.uuid4().hex[:8]}")
    team_b = Group.objects.create(name=f"ch-b-{uuid.uuid4().hex[:8]}")
    user_a, token = create_system_tenant(
        team_a.id,
        username=f"ch-a-{uuid.uuid4().hex[:8]}",
        system_id="itsm",
        scope=SCOPE,
    )
    user_b, reused = create_system_tenant(
        team_b.id,
        username=f"ch-b-{uuid.uuid4().hex[:8]}",
        system_id="itsm",
        scope=SCOPE,
        plaintext_token=token,
    )
    assert reused == token
    a = _tenant(user_a, team_a, token)
    b = _tenant(user_b, team_b, token)
    _grant(a.system_user, ["channel_list-View", "channel_list-Edit"])
    _grant(b.system_user, ["channel_list-View", "channel_list-Edit"])
    a.email = _channel(
        name="邮箱A",
        channel_type=ChannelChoices.EMAIL,
        team_id=team_a.id,
        config={"smtp_pwd": _SECRET},
    )
    a.webhook = _channel(
        name="钩子A",
        channel_type=ChannelChoices.CUSTOM_WEBHOOK,
        team_id=team_a.id,
        config={"webhook_url": _WEBHOOK},
    )
    a.nats = _channel(name="内部A", channel_type=ChannelChoices.NATS, team_id=team_a.id, config={"method_name": "receive_alert_events"})
    b.email = _channel(name="邮箱B", channel_type=ChannelChoices.EMAIL, team_id=team_b.id, config={"smtp_pwd": _SECRET})
    return SimpleNamespace(a=a, b=b, token=token)


@pytest.fixture
def local_docs_catalog(monkeypatch):
    monkeypatch.setattr("apps.core.openapi.renderer.get_external_catalog", lambda: [])


def _service_endpoints(auth):
    response = APIClient().get(DOCS_URL, **auth)
    assert response.status_code == 200, response.json()
    service = next(item for item in response.json()["data"]["services"] if item["name"] == "system-mgmt")
    return service["endpoints"]


def _endpoint(auth, method):
    path = "system-mgmt/notification-channels" if method == "GET" else "system-mgmt/notification-channels/send"
    return next(item for item in _service_endpoints(auth) if item["path"] == path and item["method"] == method)


def _capture_send(monkeypatch):
    calls = []

    def fake_send(*args, **kwargs):
        calls.append((args, kwargs))
        return {"result": True}

    monkeypatch.setattr("apps.system_mgmt.nats.channels.send_msg_with_channel", fake_send)
    return calls


def test_system_tenant_lists_own_external_channels_only(tenants, local_docs_catalog):
    response = APIClient().get(LIST_URL, **_acting(tenants.a))

    assert response.status_code == 200, response.json()
    body = response.json()
    Draft7Validator(_endpoint(_acting(tenants.a), "GET")["response_schema"]).validate(body)
    items = body["data"]["results"]
    assert [item["id"] for item in items] == [tenants.a.email.id, tenants.a.webhook.id]
    assert items[0]["channel_type"] == "email"
    assert items[0]["recipient_mode"] == "system_user"
    assert items[1]["channel_type"] == "custom_webhook"
    assert items[1]["recipient_mode"] == "free_text"
    email_parameters = {item["name"]: item for item in items[0]["send_parameters"]}
    webhook_parameters = {item["name"]: item for item in items[1]["send_parameters"]}
    assert list(email_parameters) == ["channel_id", "channel_type", "title", "content", "receivers"]
    assert email_parameters["channel_type"]["required"] is True
    assert email_parameters["channel_type"]["description"] == "固定填写 email。"
    assert email_parameters["channel_id"]["description"].startswith(f"固定填写 {tenants.a.email.id}")
    assert "用户 ID" in email_parameters["receivers"]["description"]
    assert "邮件主题" in email_parameters["title"]["description"]
    assert "渠道侧接收人名" in webhook_parameters["receivers"]["description"]
    assert "不使用标题" in webhook_parameters["title"]["description"]
    assert all(set(item) == _ITEM_FIELDS for item in items)
    assert items[0]["tag"] == []
    assert items[1]["tag"] == []
    rendered = json.dumps(body, ensure_ascii=False)
    assert _SECRET not in rendered
    assert _WEBHOOK not in rendered
    assert "config" not in rendered

    endpoints = _service_endpoints(_acting(tenants.a))
    notification_paths = sorted(item["path"] for item in endpoints if "notification" in item["path"])
    assert notification_paths == [
        "system-mgmt/notification-channels",
        "system-mgmt/notification-channels/send",
    ]
    catalog = _endpoint(_acting(tenants.a), "GET")
    item_properties = catalog["response_schema"]["properties"]["data"]["properties"]["results"]["items"]["properties"]
    channel_type = item_properties["channel_type"]
    assert channel_type["type"] == "string"
    assert "enum" not in channel_type
    assert item_properties["tag"]["type"] == "array"
    tag_query = catalog["request_schema"]["properties"]["tag"]
    assert tag_query["default"] == ""
    assert "examples" not in tag_query
    assert "实时返回" in catalog["summary"]


def test_list_returns_selected_tags_and_filters_by_any_match(tenants):
    from apps.system_mgmt.models import NotificationTag

    itsm, _ = NotificationTag.objects.get_or_create(key="用途", value="ITSM")
    staging = NotificationTag.objects.create(key="用途", value="测试环境")
    tenants.a.email.tags.add(itsm)
    tenants.a.webhook.tags.add(staging)
    tenants.b.email.tags.add(itsm)
    untagged = _channel(name="无标签A", channel_type=ChannelChoices.EMAIL, team_id=tenants.a.team.id)

    listed = APIClient().get(LIST_URL, **_acting(tenants.a))
    assert listed.status_code == 200, listed.json()
    by_id = {item["id"]: item for item in listed.json()["data"]["results"]}
    assert by_id[tenants.a.email.id]["tag"] == ["用途:ITSM"]
    assert by_id[tenants.a.webhook.id]["tag"] == ["用途:测试环境"]
    assert by_id[untagged.id]["tag"] == []
    assert tenants.b.email.id not in by_id

    matched = APIClient().get(LIST_URL, {"tag": "用途:ITSM,用途:不存在"}, **_acting(tenants.a))
    assert matched.status_code == 200, matched.json()
    assert [item["id"] for item in matched.json()["data"]["results"]] == [tenants.a.email.id]

    either = APIClient().get(LIST_URL, {"tag": "用途:ITSM,用途:测试环境"}, **_acting(tenants.a))
    assert [item["id"] for item in either.json()["data"]["results"]] == [tenants.a.email.id, tenants.a.webhook.id]

    rejected = APIClient().get(LIST_URL, {"tag": "用途,测试"}, **_acting(tenants.a))
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "SCHEMA_INVALID"

    send = APIClient().post(
        SEND_URL,
        {
            "channel_id": tenants.a.email.id,
            "channel_type": "email",
            "content": "仍按渠道",
            "receivers": [str(tenants.a.system_user.id)],
            "tag": ["用途:ITSM"],
        },
        format="json",
        **_acting(tenants.a),
    )
    assert send.status_code == 400
    assert send.json()["code"] == "SCHEMA_INVALID"


def _im_channel(*, name, team_id, instance, status="ready", enabled=True, channel_id=None):
    from apps.system_mgmt.models import IMNotificationChannel

    return IMNotificationChannel.objects.create(
        id=channel_id,
        name=name,
        integration_instance=instance,
        enabled=enabled,
        status=status,
        description=f"{name} 说明",
        platform_match_field="email",
        external_match_field="email",
        external_receive_field="user_id",
        team=[team_id],
    )


def _im_instance(name):
    from apps.system_mgmt.models import IntegrationInstance

    return IntegrationInstance.objects.create(
        name=name,
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"im_notification": "ready"},
        config={"app_id": "cli_xxx", "app_secret": "plain-im-secret"},
    )


def test_list_returns_im_channels_by_default_and_send_uses_channel_type(tenants, monkeypatch):
    from apps.system_mgmt.models import NotificationTag

    instance = _im_instance("feishu-a")
    ready = _im_channel(name="飞书A", team_id=tenants.a.team.id, instance=instance, channel_id=tenants.a.email.id)
    pending = _im_channel(
        name="飞书未同步",
        team_id=tenants.a.team.id,
        instance=instance,
        status="pending_sync",
    )
    other = _im_channel(name="飞书B", team_id=tenants.b.team.id, instance=_im_instance("feishu-b"))
    itsm, _ = NotificationTag.objects.get_or_create(key="用途", value="ITSM")
    ready.tags.add(itsm)

    listed = APIClient().get(LIST_URL, **_acting(tenants.a))
    assert listed.status_code == 200, listed.json()
    rendered = json.dumps(listed.json(), ensure_ascii=False)
    assert "plain-im-secret" not in rendered
    rows = [(item["id"], item["channel_type"], item["availability"]) for item in listed.json()["data"]["results"]]
    assert rows == sorted(rows, key=lambda row: (row[0], row[1]))
    assert set(rows) == {
        (tenants.a.email.id, "email", "available"),
        (ready.id, "im_notification", "available"),
        (tenants.a.webhook.id, "custom_webhook", "available"),
        (pending.id, "im_notification", "unavailable"),
    }
    im_item = next(item for item in listed.json()["data"]["results"] if item["id"] == ready.id and item["channel_type"] == "im_notification")
    assert im_item["recipient_mode"] == "system_user"
    assert im_item["tag"] == ["用途:ITSM"]
    assert [parameter["name"] for parameter in im_item["send_parameters"]] == [
        "channel_id",
        "channel_type",
        "title",
        "content",
        "receivers",
    ]
    assert other.id not in {item["id"] for item in listed.json()["data"]["results"] if item["channel_type"] == "im_notification"}

    filtered = APIClient().get(LIST_URL, {"tag": "用途:ITSM"}, **_acting(tenants.a))
    assert [(item["id"], item["channel_type"]) for item in filtered.json()["data"]["results"]] == [
        (ready.id, "im_notification"),
    ]

    im_calls = []

    def fake_im(channel_id, title, content, receivers):
        im_calls.append((channel_id, title, content, receivers))
        return {"result": True, "message": "sent"}

    monkeypatch.setattr("apps.system_mgmt.openapi_api.send_im_notification", fake_im)
    channel_calls = _capture_send(monkeypatch)
    sent = APIClient().post(
        SEND_URL,
        {
            "channel_id": ready.id,
            "channel_type": "im_notification",
            "title": "工单",
            "content": "请处理",
            "receivers": [str(tenants.a.system_user.id)],
        },
        format="json",
        **_acting(tenants.a),
    )
    assert sent.status_code == 200, sent.json()
    assert sent.json()["data"] == {
        "channel_id": ready.id,
        "channel_type": "im_notification",
        "delivery_code": "delivered",
    }
    assert im_calls == [(ready.id, "工单", "请处理", [str(tenants.a.system_user.id)])]
    assert channel_calls == []

    omitted = APIClient().post(
        SEND_URL,
        {
            "channel_id": tenants.a.email.id,
            "content": "漏了类型",
            "receivers": [str(tenants.a.system_user.id)],
        },
        format="json",
        **_acting(tenants.a),
    )
    assert omitted.status_code == 400
    assert omitted.json()["code"] == "SCHEMA_INVALID"
    assert im_calls == [(ready.id, "工单", "请处理", [str(tenants.a.system_user.id)])]
    assert channel_calls == []

    plain = APIClient().post(
        SEND_URL,
        {
            "channel_id": tenants.a.email.id,
            "channel_type": "email",
            "content": "仍走原渠道",
            "receivers": [str(tenants.a.system_user.id)],
        },
        format="json",
        **_acting(tenants.a),
    )
    assert plain.status_code == 200, plain.json()
    assert plain.json()["data"]["channel_type"] == "email"
    assert im_calls == [(ready.id, "工单", "请处理", [str(tenants.a.system_user.id)])]
    assert channel_calls[0][0][0] == tenants.a.email.id

    foreign = APIClient().post(
        SEND_URL,
        {
            "channel_id": other.id,
            "channel_type": "im_notification",
            "content": "越权",
            "receivers": [str(tenants.a.system_user.id)],
        },
        format="json",
        **_acting(tenants.a),
    )
    assert foreign.status_code == 403
    assert foreign.json()["code"] == "TEAM_OUT_OF_SCOPE"


def test_other_org_channels_are_not_listed(tenants):
    response = APIClient().get(LIST_URL, **_acting(tenants.b))

    assert response.status_code == 200, response.json()
    assert [item["id"] for item in response.json()["data"]["results"]] == [tenants.b.email.id]


def test_forged_acting_team_is_rejected(tenants):
    response = APIClient().get(LIST_URL, **acting_headers(tenants.token, tenants.a.user, tenants.b.team.id))

    assert response.status_code == 403
    assert response.json()["code"] == "TEAM_OUT_OF_SCOPE"


def test_list_without_channel_permission_is_denied(tenants):
    team = Group.objects.create(name=f"ch-none-{uuid.uuid4().hex[:8]}")
    user, _ = create_system_tenant(
        team.id,
        username=f"ch-none-{uuid.uuid4().hex[:8]}",
        system_id="itsm",
        scope=SCOPE,
        plaintext_token=tenants.token,
    )
    response = APIClient().get(LIST_URL, **acting_headers(tenants.token, user, team.id))

    assert response.status_code == 403
    assert response.json()["code"] == "PERM_MISSING"


def test_system_tenant_sends_through_own_channel(tenants, monkeypatch, local_docs_catalog):
    calls = _capture_send(monkeypatch)
    payload = {
        "channel_id": tenants.a.email.id,
        "channel_type": "email",
        "title": "工单提醒",
        "content": "请处理",
        "receivers": [str(tenants.a.system_user.id)],
    }

    response = APIClient().post(SEND_URL, payload, format="json", **_acting(tenants.a))

    assert response.status_code == 200, response.json()
    body = response.json()
    Draft7Validator(_endpoint(_acting(tenants.a), "POST")["response_schema"]).validate(body)
    assert body["data"] == {
        "channel_id": tenants.a.email.id,
        "channel_type": "email",
        "delivery_code": "delivered",
    }
    assert len(calls) == 1
    assert calls[0][0][0] == tenants.a.email.id
    request_schema = _endpoint(_acting(tenants.a), "POST")["request_schema"]
    assert set(request_schema["properties"]) == {
        "channel_id",
        "channel_type",
        "title",
        "content",
        "receivers",
        "group_id",
        "include_children",
    }
    assert "channel_type" in request_schema["required"]


def test_send_other_org_channel_is_forbidden(tenants, monkeypatch):
    calls = _capture_send(monkeypatch)
    response = APIClient().post(
        SEND_URL,
        {"channel_id": tenants.b.email.id, "channel_type": "email", "content": "越权", "receivers": [str(tenants.a.system_user.id)]},
        format="json",
        **_acting(tenants.a),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "TEAM_OUT_OF_SCOPE"
    assert calls == []


def test_send_internal_nats_channel_is_rejected(tenants, monkeypatch):
    calls = _capture_send(monkeypatch)
    response = APIClient().post(
        SEND_URL,
        {"channel_id": tenants.a.nats.id, "channel_type": "nats", "content": "内部", "receivers": ["ops"]},
        format="json",
        **_acting(tenants.a),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "BUSINESS_REJECTED"
    assert response.json()["message"] == "该通知渠道不支持外部投递。"
    assert calls == []


def test_send_recipient_outside_org_is_rejected(tenants, monkeypatch):
    calls = _capture_send(monkeypatch)
    response = APIClient().post(
        SEND_URL,
        {
            "channel_id": tenants.a.email.id,
            "channel_type": "email",
            "content": "越权接收人",
            "receivers": [str(tenants.b.system_user.id)],
        },
        format="json",
        **_acting(tenants.a),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "通知接收人不在授权组织内。"
    assert calls == []


def test_send_without_edit_permission_is_denied(tenants):
    _grant(tenants.a.system_user, ["channel_list-View"])
    response = APIClient().post(
        SEND_URL,
        {"channel_id": tenants.a.email.id, "channel_type": "email", "content": "只读", "receivers": [str(tenants.a.system_user.id)]},
        format="json",
        **_acting(tenants.a),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PERM_MISSING"


def test_send_outside_token_scope_is_denied(tenants):
    user, token = create_system_tenant(
        tenants.a.team.id,
        username=f"ch-scope-{uuid.uuid4().hex[:8]}",
        system_id="itsm-scope",
        scope={"mode": "allowlist", "endpoints": ["GET system-mgmt/notification-channels"]},
    )
    system_user = SystemUser.objects.get(username=user.username, domain=user.domain)
    _grant(system_user, ["channel_list-View", "channel_list-Edit"])
    auth = acting_headers(token, user, tenants.a.team.id)

    listed = APIClient().get(LIST_URL, **auth)
    denied = APIClient().post(
        SEND_URL,
        {"channel_id": tenants.a.email.id, "channel_type": "email", "content": "无 Scope", "receivers": [str(system_user.id)]},
        format="json",
        **auth,
    )

    assert listed.status_code == 200, listed.json()
    assert denied.status_code == 403
    assert denied.json()["code"] == "SCOPE_DENIED"


def test_unknown_send_field_is_rejected(tenants):
    response = APIClient().post(
        SEND_URL,
        {
            "channel_id": tenants.a.email.id,
            "channel_type": "email",
            "content": "字段",
            "receivers": [str(tenants.a.system_user.id)],
            "config": {"smtp_pwd": _SECRET},
        },
        format="json",
        **_acting(tenants.a),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"
