import pytest


def _payload(name="生产故障通知", revision=None):
    payload = {
        "name": name,
        "description": "生产环境告警通知",
        "team": [1],
        "scope": "single_alert",
        "contents": [
            {
                "channel_type": "email",
                "subject_template": "【告警】{{ alert.title }}",
                "body_template": "<h2>{{ alert.title }}</h2><p>{{ alert.content }}</p>",
            },
            {
                "channel_type": "enterprise_wechat_bot",
                "subject_template": "",
                "body_template": "## {{ alert.title }}\n> {{ alert.content }}",
            },
        ],
    }
    if revision is not None:
        payload["revision"] = revision
    return payload


@pytest.fixture
def template_client(authenticated_user):
    from rest_framework.test import APIClient

    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    client = APIClient()
    client.force_authenticate(authenticated_user)
    client.cookies["current_team"] = "1"
    return client


@pytest.mark.django_db
def test_create_and_read_multichannel_template(template_client):
    response = template_client.post("/api/v1/alerts/api/notification_templates/", _payload(), format="json")

    assert response.status_code == 201, response.content
    assert response.data["revision"] == 1
    assert {item["channel_type"] for item in response.data["contents"]} == {"email", "enterprise_wechat_bot"}

    detail = template_client.get(f"/api/v1/alerts/api/notification_templates/{response.data['id']}/")
    assert detail.status_code == 200
    assert detail.data["contents"][0]["body_template"]


@pytest.mark.django_db
def test_team_scope_is_normalized_and_name_is_unique(template_client):
    payload = _payload()
    payload["team"] = [2, 1, 2]
    created = template_client.post("/api/v1/alerts/api/notification_templates/", payload, format="json")
    duplicate_payload = _payload()
    duplicate_payload["team"] = [1, 2]
    duplicate = template_client.post("/api/v1/alerts/api/notification_templates/", duplicate_payload, format="json")

    assert created.status_code == 201, created.content
    assert created.data["team"] == [1, 2]
    assert duplicate.status_code == 400
    assert "name" in duplicate.data


@pytest.mark.django_db
def test_update_requires_current_revision(template_client):
    created = template_client.post("/api/v1/alerts/api/notification_templates/", _payload(), format="json").data
    url = f"/api/v1/alerts/api/notification_templates/{created['id']}/"

    success = template_client.put(url, _payload(name="新名称", revision=1), format="json")
    conflict = template_client.put(url, _payload(name="过期覆盖", revision=1), format="json")

    assert success.status_code == 200
    assert success.data["revision"] == 2
    assert conflict.status_code == 409
    assert "revision" in conflict.data


@pytest.mark.django_db
def test_locked_queryset_keeps_distinct_out_of_select_for_update(template_client):
    from apps.alerts.models.notification_template import NotificationTemplate
    from apps.alerts.views.notification_template import NotificationTemplateViewSet

    template = NotificationTemplate.objects.create(name="待锁定模板", team=[1])
    view = NotificationTemplateViewSet()
    view.kwargs = {"pk": template.pk}
    view.get_queryset = lambda: NotificationTemplate.objects.filter(team=[1]).distinct()

    locked_queryset = view._locked_queryset()

    assert locked_queryset.query.select_for_update is True
    assert locked_queryset.query.distinct is False
    assert locked_queryset.get() == template


@pytest.mark.django_db
def test_partial_update_preserves_contents_and_checks_revision(template_client):
    created = template_client.post("/api/v1/alerts/api/notification_templates/", _payload(), format="json").data
    url = f"/api/v1/alerts/api/notification_templates/{created['id']}/"

    response = template_client.patch(url, {"description": "仅更新说明", "revision": 1}, format="json")

    assert response.status_code == 200, response.content
    assert response.data["description"] == "仅更新说明"
    assert len(response.data["contents"]) == 2
    assert response.data["revision"] == 2


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["patch", "put", "delete"])
@pytest.mark.parametrize("target", ["deleted", "other_team"])
def test_write_unavailable_template_returns_not_found(api_client, authenticated_user, method, target):
    from apps.alerts.models.notification_template import NotificationTemplate

    authenticated_user.permission = {"alarm": {"notification_templates-Edit", "notification_templates-Delete"}}
    api_client.cookies["current_team"] = "1"
    template = NotificationTemplate.objects.create(name="不可访问模板", team=[2] if target == "other_team" else [1])
    url = f"/api/v1/alerts/api/notification_templates/{template.pk}/"
    if target == "deleted":
        template.delete()

    response = getattr(api_client, method)(url, {"revision": 1, "name": "不应修改"}, format="json")

    assert response.status_code == 404
    if target == "other_team":
        template.refresh_from_db()
        assert template.name == "不可访问模板"
        assert template.revision == 1


@pytest.mark.django_db
@pytest.mark.parametrize("body", ["<script>alert(1)</script>", "<a {{ alert.title }}>open</a>", '<img src="https://example.test/pixel">'])
def test_create_rejects_mismatched_channel_format(template_client, body):
    payload = _payload()
    payload["contents"][0]["body_template"] = body

    response = template_client.post("/api/v1/alerts/api/notification_templates/", payload, format="json")

    assert response.status_code == 400
    assert "contents" in response.data


@pytest.mark.django_db
def test_list_is_scoped_and_global_templates_are_visible(template_client):
    from apps.alerts.models.notification_template import NotificationTemplate

    NotificationTemplate.objects.create(name="team-1", team=[1])
    NotificationTemplate.objects.create(name="team-2", team=[2])
    NotificationTemplate.objects.create(name="global", team=[], is_global=True)

    response = template_client.get("/api/v1/alerts/api/notification_templates/")
    items = response.data.get("items", response.data) if isinstance(response.data, dict) else response.data

    assert response.status_code == 200
    assert {item["name"] for item in items} == {"team-1", "global", "告警操作通知"}


@pytest.mark.django_db
@pytest.mark.parametrize("existing", [False, True])
def test_unauthorized_team_list_does_not_create_or_upgrade_templates(api_client, authenticated_user, existing):
    from apps.alerts.models.notification_template import NotificationTemplate, NotificationTemplateContent
    from apps.alerts.notification_templates.operation import _legacy_default_content

    authenticated_user.permission = {"alarm": {"notification_templates-View"}}
    api_client.cookies["current_team"] = "2"
    if existing:
        template = NotificationTemplate.objects.create(name="告警操作通知", team=[2], scope="alert_operation", builtin_key="alert_operation:2")
        subject, body = _legacy_default_content("email")
        NotificationTemplateContent.objects.create(template=template, channel_type="email", subject_template=subject, body_template=body)
    before_templates = list(NotificationTemplate.objects.values())
    before_contents = list(NotificationTemplateContent.objects.values())

    response = api_client.get("/api/v1/alerts/api/notification_templates/")

    assert response.status_code == 403
    assert list(NotificationTemplate.objects.values()) == before_templates
    assert list(NotificationTemplateContent.objects.values()) == before_contents


@pytest.mark.django_db
def test_list_ensures_one_editable_alert_operation_template_for_current_team(template_client):
    from apps.alerts.models.notification_template import NotificationTemplate, NotificationTemplateContent
    from apps.system_mgmt.models.channel import Channel

    channel = Channel.objects.create(
        name="团队邮件",
        channel_type="email",
        config={},
        description="test",
        team=[1],
    )
    other = NotificationTemplate.objects.create(
        name="告警操作通知",
        team=[2],
        scope="alert_operation",
        builtin_key="alert_operation:2",
    )
    NotificationTemplateContent.objects.create(
        template=other,
        channel_type="email",
        subject_template="{{ alert.title }}",
        body_template="<p>{{ alert.content }}</p>",
    )

    first = template_client.get("/api/v1/alerts/api/notification_templates/")
    second = template_client.get("/api/v1/alerts/api/notification_templates/")
    first_items = first.data.get("items", first.data) if isinstance(first.data, dict) else first.data
    operation_items = [item for item in first_items if item["scope"] == "alert_operation"]

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(operation_items) == 1
    assert operation_items[0]["is_builtin"] is True
    assert operation_items[0]["channel_id"] == channel.id
    assert len(operation_items[0]["contents"]) == 1
    content = operation_items[0]["contents"][0]
    assert content["subject_template"] == "【{{ notification.scene_name }}】【待认领】【{{ alert.level }}】{{ alert.title }}"
    assert "{{ notification.action_summary }}" in content["body_template"]
    assert "操作信息" in content["body_template"]
    assert "请进入告警中心认领并处理该告警" in content["body_template"]


@pytest.mark.django_db
def test_alert_operation_template_is_editable_but_requires_exactly_one_scoped_channel(template_client):
    from apps.system_mgmt.models.channel import Channel

    email = Channel.objects.create(
        name="团队邮件",
        channel_type="email",
        config={},
        description="test",
        team=[1],
    )
    wecom = Channel.objects.create(
        name="团队企微",
        channel_type="enterprise_wechat_bot",
        config={},
        description="test",
        team=[1],
    )
    other_team = Channel.objects.create(
        name="其他团队邮件",
        channel_type="email",
        config={},
        description="test",
        team=[2],
    )
    template_client.get("/api/v1/alerts/api/notification_templates/")
    from apps.alerts.models.notification_template import NotificationTemplate

    template = NotificationTemplate.objects.get(scope="alert_operation", team=[1])
    payload = {
        "name": template.name,
        "description": template.description,
        "team": [1],
        "scope": "alert_operation",
        "channel_id": wecom.id,
        "revision": template.revision,
        "contents": [
            {
                "channel_type": "enterprise_wechat_bot",
                "subject_template": "",
                "body_template": "### {{ notification.scene_name }}\n{{ alert.title }}",
            }
        ],
    }

    success = template_client.put(
        f"/api/v1/alerts/api/notification_templates/{template.id}/",
        payload,
        format="json",
    )
    wrong_test_channel = template_client.post(
        f"/api/v1/alerts/api/notification_templates/{template.id}/test_send/",
        {"channel_id": email.id},
        format="json",
    )
    payload["revision"] = success.data.get("revision", 1)
    payload["channel_id"] = other_team.id
    other_team_response = template_client.put(
        f"/api/v1/alerts/api/notification_templates/{template.id}/",
        payload,
        format="json",
    )
    payload["channel_id"] = email.id
    payload["contents"].append(
        {
            "channel_type": "email",
            "subject_template": "{{ alert.title }}",
            "body_template": "<p>{{ alert.content }}</p>",
        }
    )
    multiple = template_client.put(
        f"/api/v1/alerts/api/notification_templates/{template.id}/",
        payload,
        format="json",
    )

    assert success.status_code == 200, success.content
    assert success.data["channel_id"] == wecom.id
    assert success.data["contents"][0]["channel_type"] == "enterprise_wechat_bot"
    assert wrong_test_channel.status_code == 400
    assert "channel_id" in wrong_test_channel.data
    assert other_team_response.status_code == 400
    assert "channel_id" in other_team_response.data
    assert multiple.status_code == 400
    assert "contents" in multiple.data

    deleted = template_client.delete(f"/api/v1/alerts/api/notification_templates/{template.id}/")
    assert deleted.status_code == 400


@pytest.mark.django_db
def test_alert_operation_template_upgrades_only_untouched_legacy_content(template_client):
    from apps.alerts.models.notification_template import NotificationTemplate, NotificationTemplateContent
    from apps.system_mgmt.models.channel import Channel

    channel = Channel.objects.create(
        name="团队邮件",
        channel_type="email",
        config={},
        description="test",
        team=[1],
    )
    template = NotificationTemplate.objects.create(
        name="告警操作通知",
        team=[1],
        scope="alert_operation",
        builtin_key="alert_operation:1",
        channel_id=channel.id,
    )
    legacy_body = (
        "<h2>{{ notification.scene_name }}｜{{ alert.title }}</h2>\n"
        '<table style="width:100%;border-collapse:collapse">\n'
        "  <tr>\n    <td>告警级别</td>\n    <td><strong>{{ alert.level }}</strong></td>\n  </tr>\n"
        "  <tr>\n    <td>告警资源</td>\n    <td>{{ alert.resource_name }}（{{ alert.resource_type }}）</td>\n  </tr>\n"
        "  <tr>\n    <td>监控来源</td>\n    <td>{{ alert.source_name }} / {{ alert.item }}</td>\n  </tr>\n"
        "  <tr>\n    <td>发生时间</td>\n    <td>{{ alert.created_at }}</td>\n  </tr>\n"
        "  <tr>\n    <td>本次接收人</td>\n    <td>{{ notification.receiver_names }}</td>\n  </tr>\n"
        "</table>\n<p>\n  <strong>告警内容</strong><br>\n  {{ alert.content }}\n</p>\n"
        "<p>告警 ID：{{ alert.alert_id }}</p>"
    )
    content = NotificationTemplateContent.objects.create(
        template=template,
        channel_type="email",
        subject_template="【{{ notification.scene_name }}】【{{ alert.level }}】{{ alert.title }}",
        body_template=legacy_body,
    )

    response = template_client.get("/api/v1/alerts/api/notification_templates/")

    assert response.status_code == 200
    content.refresh_from_db()
    template.refresh_from_db()
    assert template.revision == 2
    assert content.subject_template == "【{{ notification.scene_name }}】【待认领】【{{ alert.level }}】{{ alert.title }}"
    assert "{{ notification.action_summary }}" in content.body_template

    content.subject_template = "用户自定义标题"
    content.body_template = "<p>用户自定义正文</p>"
    content.save(update_fields=["subject_template", "body_template"])
    template.revision = 3
    template.save(update_fields=["revision"])

    template_client.get("/api/v1/alerts/api/notification_templates/")

    content.refresh_from_db()
    template.refresh_from_db()
    assert template.revision == 3
    assert content.subject_template == "用户自定义标题"
    assert content.body_template == "<p>用户自定义正文</p>"


@pytest.mark.django_db
def test_assignment_template_options_exclude_alert_operation_template(template_client):
    template_client.get("/api/v1/alerts/api/notification_templates/")

    response = template_client.get("/api/v1/alerts/api/notification_templates/options/")

    assert response.status_code == 200
    assert all(item["scope"] != "alert_operation" for item in response.data)


@pytest.mark.django_db
def test_list_counts_distinct_assignment_references(template_client):
    from apps.alerts.models.notification_template import NotificationTemplateReference

    created = template_client.post("/api/v1/alerts/api/notification_templates/", _payload(), format="json").data
    NotificationTemplateReference.objects.bulk_create(
        [
            NotificationTemplateReference(
                template_id=created["id"],
                source_type="assignment",
                source_id="7",
                scene="default",
                channel_id=3,
                locator="notify_channels.0",
            ),
            NotificationTemplateReference(
                template_id=created["id"],
                source_type="assignment",
                source_id="7",
                scene="recovery",
                channel_id=3,
                locator="notify_channels.0",
            ),
            NotificationTemplateReference(
                template_id=created["id"],
                source_type="assignment",
                source_id="8",
                scene="default",
                channel_id=4,
                locator="notify_channels.1",
            ),
            NotificationTemplateReference(
                template_id=created["id"],
                source_type="escalation_task",
                source_id="ALERT-1",
                scene="escalation",
                channel_id=3,
                locator="layers.0.notify_channels.0",
                is_snapshot=True,
            ),
        ]
    )

    response = template_client.get("/api/v1/alerts/api/notification_templates/")
    items = response.data.get("items", response.data) if isinstance(response.data, dict) else response.data
    item = next(row for row in items if row["id"] == created["id"])

    assert response.status_code == 200
    assert item["assignment_count"] == 2


@pytest.mark.django_db
def test_preview_uses_server_renderer_without_sending(template_client):
    payload = {
        "scope": "single_alert",
        "channel_type": "email",
        "subject_template": "{{ alert.title }}",
        "body_template": "<b>{{ enrichment.cmdb.owner }}</b>",
        "sample": {
            "alert": {"title": "CPU 高"},
            "enrichment": {"cmdb": {"owner": "王五"}},
        },
    }

    response = template_client.post("/api/v1/alerts/api/notification_templates/preview/", payload, format="json")

    assert response.status_code == 200, response.content
    assert response.data["subject"] == "CPU 高"
    assert response.data["body"] == "<b>王五</b>"
    assert response.data["missing_fields"] == []


@pytest.mark.django_db
def test_preview_uses_level_display_name_and_keeps_raw_level_id(template_client):
    payload = {
        "scope": "single_alert",
        "channel_type": "email",
        "subject_template": "{{ alert.level }}",
        "body_template": "<p>{{ alert.level }}（{{ alert.level_id }}）</p>",
    }

    response = template_client.post("/api/v1/alerts/api/notification_templates/preview/", payload, format="json")

    assert response.status_code == 200, response.content
    assert response.data["subject"] == "警告"
    assert response.data["body"] == "<p>警告（2）</p>"


@pytest.mark.django_db
def test_alert_operation_default_email_content_can_be_previewed(template_client):
    from apps.system_mgmt.models.channel import Channel

    Channel.objects.create(
        name="团队邮件",
        channel_type="email",
        config={},
        description="test",
        team=[1],
    )
    listed = template_client.get("/api/v1/alerts/api/notification_templates/")
    items = listed.data.get("items", listed.data) if isinstance(listed.data, dict) else listed.data
    operation = next(item for item in items if item["scope"] == "alert_operation")
    content = operation["contents"][0]
    response = template_client.post(
        "/api/v1/alerts/api/notification_templates/preview/",
        {
            "scope": "alert_operation",
            "channel_type": "email",
            "subject_template": content["subject_template"],
            "body_template": content["body_template"],
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.data["subject"] == "【测试发送】【待认领】【警告】CPU 使用率过高"
    assert "该告警已由 admin 分派给 zhangsan，请及时认领并处理。" in response.data["body"]
    assert "<strong>待响应</strong>" in response.data["body"]
    assert response.data["missing_fields"] == []


@pytest.mark.django_db
def test_preview_rejects_alert_operation_fields_in_ordinary_template(template_client):
    response = template_client.post(
        "/api/v1/alerts/api/notification_templates/preview/",
        {
            "scope": "single_alert",
            "channel_type": "custom_webhook",
            "subject_template": "",
            "body_template": "{{ notification.actor_name }}",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "告警操作变量只能用于告警操作通知模板" in str(response.data)


@pytest.mark.django_db
def test_referenced_template_cannot_be_deleted(template_client):
    from apps.alerts.models.notification_template import NotificationTemplateReference

    created = template_client.post("/api/v1/alerts/api/notification_templates/", _payload(), format="json").data
    NotificationTemplateReference.objects.create(
        template_id=created["id"], source_type="assignment", source_id="7", scene="default", channel_id=3, locator="notify_channels.0"
    )

    response = template_client.delete(f"/api/v1/alerts/api/notification_templates/{created['id']}/")

    assert response.status_code == 409
    assert response.data["references"][0]["source_type"] == "assignment"


@pytest.mark.django_db
@pytest.mark.parametrize("delete_target", ["assignment", "alert", "task", "rollback"])
def test_deleted_escalation_releases_only_its_template_references(template_client, delete_target):
    from django.utils import timezone

    from apps.alerts.models import Alert, AlertAssignment
    from apps.alerts.models.alert_operator import AlertEscalationTask
    from apps.alerts.notification_templates.binding import sync_escalation_template_references

    templates, tasks = [], []
    for index in range(2):
        created = template_client.post("/api/v1/alerts/api/notification_templates/", _payload(name=f"升级模板-{index}"), format="json")
        assert created.status_code == 201
        templates.append(created.data)
        assignment = AlertAssignment.objects.create(name=f"升级策略-{index}", match_type="all")
        alert = Alert.objects.create(alert_id=f"escalation-{index}", title="升级告警", fingerprint=f"escalation-{index}", team=[1])
        task = AlertEscalationTask.objects.create(
            alert=alert,
            assignment=assignment,
            mode="append",
            layer_started_at=timezone.now(),
            layers=[{"notify_channels": [{"id": 1, "channel_type": "email", "notification_templates": {"default": created.data["id"]}}]}],
        )
        sync_escalation_template_references(task)
        tasks.append(task)

    if delete_target == "assignment":
        response = template_client.delete(f"/api/v1/alerts/api/assignment/{tasks[0].assignment_id}/")
        assert response.status_code == 200
    elif delete_target == "alert":
        tasks[0].alert.delete()
    elif delete_target == "rollback":
        from django.db import transaction

        with pytest.raises(RuntimeError, match="删除事务回滚"):
            with transaction.atomic():
                tasks[0].assignment.delete()
                raise RuntimeError("删除事务回滚")
        assert AlertEscalationTask.objects.filter(pk=tasks[0].pk).exists()
        assert template_client.delete(f"/api/v1/alerts/api/notification_templates/{templates[0]['id']}/").status_code == 409
        tasks[0].delete()
    else:
        AlertEscalationTask.objects.filter(pk=tasks[0].pk).delete()

    deleted = template_client.delete(f"/api/v1/alerts/api/notification_templates/{templates[0]['id']}/")
    protected = template_client.delete(f"/api/v1/alerts/api/notification_templates/{templates[1]['id']}/")

    assert deleted.status_code == 200, deleted.data
    assert template_client.get(f"/api/v1/alerts/api/notification_templates/{templates[0]['id']}/").status_code == 404
    assert protected.status_code == 409
    assert AlertEscalationTask.objects.filter(pk=tasks[1].pk).exists()


@pytest.mark.django_db
def test_test_send_uses_selected_channel_and_disables_receiver_suffix(template_client, monkeypatch):
    from apps.alerts.models.models import Alert
    from apps.system_mgmt.models.channel import Channel, ChannelChoices

    created = template_client.post("/api/v1/alerts/api/notification_templates/", _payload(), format="json").data
    channel = Channel.objects.create(
        name="生产邮件",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="test",
        team=[1],
    )
    alert = Alert.objects.create(
        alert_id="ALERT-REAL-001",
        level="2",
        title="真实数据库连接数过高",
        content="真实连接数已达到 95%",
        fingerprint="test-send-real-alert",
        resource_id="mysql-01",
        resource_name="生产数据库 01",
        resource_type="mysql",
        source_name="Prometheus",
        item="connections",
        team=[1],
    )
    captured = {}

    def fake_notify(self):
        captured.update(
            channel_id=self.channel_id,
            title=self.title,
            content=self.content,
            append_receivers=self.append_receivers,
        )
        return {"result": True}

    monkeypatch.setattr(
        "apps.alerts.common.notify.notify.Notify.get_user_list",
        lambda _self, users: [{"id": index, "username": username} for index, username in enumerate(users, 1)],
    )
    monkeypatch.setattr("apps.alerts.common.notify.notify.Notify.notify", fake_notify)

    response = template_client.post(
        f"/api/v1/alerts/api/notification_templates/{created['id']}/test_send/",
        {"channel_id": channel.id, "alert_id": alert.id},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert captured["channel_id"] == channel.id
    assert captured["append_receivers"] is False
    assert "真实数据库连接数过高" in captured["title"]
    assert "真实连接数已达到 95%" in captured["content"]


@pytest.mark.django_db
def test_draft_test_send_uses_current_source_and_selected_real_alert(template_client, monkeypatch):
    from apps.alerts.models.models import Alert
    from apps.system_mgmt.models.channel import Channel, ChannelChoices

    channel = Channel.objects.create(
        name="生产邮件",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="test",
        team=[1],
    )
    alert = Alert.objects.create(
        alert_id="ALERT-DRAFT-001",
        level="2",
        title="真实 CPU 使用率过高",
        content="真实 CPU 使用率已达到 96%",
        fingerprint="draft-test-send-alert",
        resource_name="生产主机 02",
        team=[1],
    )
    captured = {}

    def fake_notify(self):
        captured.update(
            title=self.title,
            content=self.content,
            receivers=[user["username"] for user in self.user_list],
        )
        return {"result": True}

    monkeypatch.setattr(
        "apps.alerts.common.notify.notify.Notify.get_user_list",
        lambda _self, users: [{"id": index, "username": username} for index, username in enumerate(users, 1)],
    )
    monkeypatch.setattr("apps.alerts.common.notify.notify.Notify.notify", fake_notify)

    response = template_client.post(
        "/api/v1/alerts/api/notification_templates/test_send/",
        {
            "scope": "single_alert",
            "channel_type": "email",
            "channel_id": channel.id,
            "alert_id": alert.id,
            "receivers": ["alice", "bob", "alice"],
            "subject_template": "草稿｜{{ alert.title }}",
            "body_template": "<p>草稿正文：{{ alert.content }}｜{{ notification.receiver_names }}</p>",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    assert captured["title"] == "草稿｜真实 CPU 使用率过高"
    assert captured["content"] == "<p>草稿正文：真实 CPU 使用率已达到 96%｜alice、bob</p>"
    assert captured["receivers"] == ["alice", "bob"]


@pytest.mark.django_db
def test_draft_test_send_rejects_unknown_receiver(template_client, monkeypatch):
    from apps.alerts.models.models import Alert
    from apps.system_mgmt.models.channel import Channel, ChannelChoices

    channel = Channel.objects.create(
        name="生产邮件",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="test",
        team=[1],
    )
    alert = Alert.objects.create(
        alert_id="ALERT-UNKNOWN-RECEIVER",
        level="2",
        title="接收人校验",
        content="接收人不存在时不可试发",
        fingerprint="unknown-receiver-test-send-alert",
        team=[1],
    )
    monkeypatch.setattr("apps.alerts.common.notify.notify.Notify.get_user_list", lambda _self, _users: [])

    response = template_client.post(
        "/api/v1/alerts/api/notification_templates/test_send/",
        {
            "scope": "single_alert",
            "channel_type": "email",
            "channel_id": channel.id,
            "alert_id": alert.id,
            "receivers": ["missing-user"],
            "subject_template": "{{ alert.title }}",
            "body_template": "<p>{{ alert.content }}</p>",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["receivers"] == "接收人不存在：missing-user"


@pytest.mark.django_db
def test_draft_test_send_rejects_alert_outside_current_team(template_client, monkeypatch):
    from apps.alerts.models.models import Alert
    from apps.system_mgmt.models.channel import Channel, ChannelChoices

    channel = Channel.objects.create(
        name="生产邮件",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="test",
        team=[1],
    )
    alert = Alert.objects.create(
        alert_id="ALERT-OTHER-TEAM",
        level="2",
        title="其他团队告警",
        content="不可用于当前团队试发",
        fingerprint="other-team-test-send-alert",
        team=[2],
    )
    monkeypatch.setattr("apps.alerts.common.notify.notify.Notify.notify", lambda _self: {"result": True})

    response = template_client.post(
        "/api/v1/alerts/api/notification_templates/test_send/",
        {
            "scope": "single_alert",
            "channel_type": "email",
            "channel_id": channel.id,
            "alert_id": alert.id,
            "receivers": ["admin"],
            "subject_template": "{{ alert.title }}",
            "body_template": "<p>{{ alert.content }}</p>",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "alert_id" in response.data


@pytest.mark.django_db
def test_test_send_rejects_oversized_sample(template_client):
    created = template_client.post("/api/v1/alerts/api/notification_templates/", _payload(), format="json").data

    response = template_client.post(
        f"/api/v1/alerts/api/notification_templates/{created['id']}/test_send/",
        {"channel_id": 1, "sample": {"alert": {"content": "x" * (65 * 1024)}}},
        format="json",
    )

    assert response.status_code == 400
    assert "sample" in response.data
