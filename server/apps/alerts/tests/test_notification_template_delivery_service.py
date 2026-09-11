from types import SimpleNamespace

import pytest


def _alert():
    alert = SimpleNamespace(
        alert_id="ALERT-100",
        title="CPU 使用率过高",
        content="当前值 95%",
        level="2",
        status="unassigned",
        source_name="Prometheus",
        resource_id="host-1",
        resource_name="生产主机",
        resource_type="host",
        item="cpu_usage",
        labels={"env": "prod"},
        dimensions={"instance": "10.0.0.8"},
        enrichment={"cmdb": {"owner": "张三"}},
        operator=["owner"],
        team=[1],
        created_at=None,
        first_event_time=None,
        last_event_time=None,
    )
    alert.format_created_at = lambda _timezone: "2026-09-08 10:00:00"
    return alert


@pytest.mark.django_db
def test_dispatcher_renders_per_channel_template_and_freezes_metadata():
    from apps.alerts.common.notify.dispatcher import build_channel_params
    from apps.alerts.models.notification_template import NotificationTemplate, NotificationTemplateContent

    template = NotificationTemplate.objects.create(name="邮件模板", team=[1])
    NotificationTemplateContent.objects.create(
        template=template,
        channel_type="email",
        subject_template="【自定义】{{ alert.title }}",
        body_template="<h2>{{ alert.title }}</h2><p>{{ enrichment.cmdb.owner }}</p>",
    )
    channels = [
        {
            "id": 3,
            "name": "生产邮件",
            "channel_type": "email",
            "notification_templates": {"default": template.id},
        }
    ]

    params = build_channel_params(["admin"], channels, [_alert()], "ALERT-100", scene="assignment")

    assert params[0]["title"] == "【自定义】CPU 使用率过高"
    assert params[0]["content"] == "<h2>CPU 使用率过高</h2><p>张三</p>"
    assert params[0]["append_receivers"] is False
    assert params[0]["template_snapshot"] == {"id": template.id, "revision": 1, "scene": "assignment"}


@pytest.mark.django_db
def test_dispatcher_exposes_mapped_alert_level_and_raw_level_id():
    from apps.alerts.common.notify.dispatcher import build_channel_params
    from apps.alerts.constants.constants import LevelType
    from apps.alerts.models.models import Level
    from apps.alerts.models.notification_template import NotificationTemplate, NotificationTemplateContent

    Level.objects.create(
        level_id=2,
        level_type=LevelType.ALERT,
        level_name="Warning",
        level_display_name="警告",
    )
    template = NotificationTemplate.objects.create(name="级别映射模板", team=[1])
    NotificationTemplateContent.objects.create(
        template=template,
        channel_type="email",
        subject_template="{{ alert.level }}｜{{ alert.title }}",
        body_template="<p>{{ alert.level }}（原始级别 {{ alert.level_id }}）</p>",
    )
    channels = [
        {
            "id": 3,
            "channel_type": "email",
            "notification_templates": {"default": template.id},
        }
    ]

    params = build_channel_params(["admin"], channels, [_alert()], "ALERT-100", scene="assignment")

    assert params[0]["title"] == "警告｜CPU 使用率过高"
    assert params[0]["content"] == "<p>警告（原始级别 2）</p>"


@pytest.mark.django_db
def test_dispatcher_falls_back_to_default_when_bound_template_is_missing():
    from apps.alerts.common.notify.dispatcher import build_channel_params

    channels = [
        {
            "id": 3,
            "name": "生产邮件",
            "channel_type": "email",
            "notification_templates": {"default": 99999},
        }
    ]

    params = build_channel_params(["admin"], channels, [_alert()], "ALERT-100", scene="assignment")

    assert "CPU 使用率过高" in params[0]["title"]
    assert params[0]["append_receivers"] is True
    assert params[0]["template_snapshot"]["fallback"] is True
