from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate


def _template(channel_type="email", team=None):
    from apps.alerts.models.notification_template import NotificationTemplate, NotificationTemplateContent

    template = NotificationTemplate.objects.create(name=f"tpl-{channel_type}", team=team or [1])
    NotificationTemplateContent.objects.create(
        template=template,
        channel_type=channel_type,
        subject_template="{{ alert.title }}" if channel_type == "email" else "",
        body_template="<b>{{ alert.content }}</b>" if channel_type == "email" else "## {{ alert.title }}",
    )
    return template


def _assignment_payload(template_id, channel_type="email"):
    return {
        "name": "数据库告警分派",
        "match_type": "all",
        "match_rules": [],
        "personnel": ["testuser"],
        "notify_channels": [
            {
                "id": 5,
                "name": "邮件",
                "channel_type": channel_type,
                "notification_templates": {"default": template_id, "reminder": None},
            }
        ],
        "notification_scenario": ["alert"],
        "config": {},
        "notification_frequency": {},
        "is_active": True,
    }


def _channel(channel_type="email", team=None):
    from apps.system_mgmt.models.channel import Channel

    return Channel.objects.create(
        id=5,
        name="通知渠道",
        channel_type=channel_type,
        config={},
        description="test",
        team=team or [1],
    )


@pytest.mark.django_db
def test_assignment_rejects_template_without_matching_channel(authenticated_user):
    from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer
    from apps.system_mgmt.models import User

    authenticated_user.is_superuser = True
    User.objects.create(username="testuser", display_name="Test", email="test@example.com", password="x", group_list=[1])
    template = _template("email")
    _channel("email")
    request = APIRequestFactory().post("/")
    force_authenticate(request, authenticated_user)
    request.user = authenticated_user
    request.COOKIES["current_team"] = "1"

    serializer = AlertAssignmentModelSerializer(data=_assignment_payload(template.id, "enterprise_wechat_bot"), context={"request": request})

    assert not serializer.is_valid()
    assert "notify_channels" in serializer.errors


@pytest.mark.django_db
def test_assignment_save_builds_reference_index(authenticated_user):
    from apps.alerts.models.notification_template import NotificationTemplateReference
    from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer
    from apps.system_mgmt.models import User

    authenticated_user.is_superuser = True
    User.objects.create(username="testuser", display_name="Test", email="test@example.com", password="x", group_list=[1])
    template = _template("email")
    _channel("email")
    request = APIRequestFactory().post("/")
    force_authenticate(request, authenticated_user)
    request.user = authenticated_user
    request.COOKIES["current_team"] = "1"
    serializer = AlertAssignmentModelSerializer(data=_assignment_payload(template.id), context={"request": request})

    assert serializer.is_valid(), serializer.errors
    assignment = serializer.save()
    reference = NotificationTemplateReference.objects.get(source_type="assignment", source_id=str(assignment.id))
    assert reference.template_id == template.id
    assert reference.scene == "default"
    assert reference.channel_id == 5


@pytest.mark.django_db
def test_assignment_rejects_forged_channel_type(authenticated_user):
    from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer
    from apps.system_mgmt.models import User

    authenticated_user.is_superuser = True
    User.objects.create(username="testuser", display_name="Test", email="test@example.com", password="x", group_list=[1])
    template = _template("enterprise_wechat_bot")
    _channel("email")
    request = APIRequestFactory().post("/")
    force_authenticate(request, authenticated_user)
    request.user = authenticated_user
    request.COOKIES["current_team"] = "1"

    serializer = AlertAssignmentModelSerializer(data=_assignment_payload(template.id, "enterprise_wechat_bot"), context={"request": request})

    assert not serializer.is_valid()
    assert "类型与系统配置不一致" in str(serializer.errors["notify_channels"])


@pytest.mark.django_db
def test_assignment_rejects_alert_operation_builtin_template(authenticated_user):
    from apps.alerts.models.notification_template import NotificationTemplate, NotificationTemplateContent
    from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer
    from apps.system_mgmt.models import User

    authenticated_user.is_superuser = True
    User.objects.create(username="testuser", display_name="Test", email="test@example.com", password="x", group_list=[1])
    channel = _channel("email")
    template = NotificationTemplate.objects.create(
        name="告警操作通知",
        team=[1],
        scope="alert_operation",
        builtin_key="alert_operation:1",
        channel_id=channel.id,
    )
    NotificationTemplateContent.objects.create(
        template=template,
        channel_type="email",
        subject_template="{{ alert.title }}",
        body_template="<p>{{ alert.content }}</p>",
    )
    request = APIRequestFactory().post("/")
    force_authenticate(request, authenticated_user)
    request.user = authenticated_user
    request.COOKIES["current_team"] = "1"

    serializer = AlertAssignmentModelSerializer(
        data=_assignment_payload(template.id),
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "告警操作内置模板不能绑定" in str(serializer.errors["notify_channels"])


@pytest.mark.django_db
def test_channel_scene_binding_prefers_scene_then_default():
    from apps.alerts.notification_templates.binding import select_template_id

    channel = {"notification_templates": {"default": 10, "reminder": 11, "recovery": None}}

    assert select_template_id(channel, "reminder") == 11
    assert select_template_id(channel, "escalation") == 10
    assert select_template_id(channel, "recovery") is None


@pytest.mark.django_db
def test_runtime_rejects_template_from_other_alert_team():
    from apps.alerts.notification_templates.binding import TemplateBindingError, render_bound_template

    template = _template("email", team=[2])
    alert = SimpleNamespace(
        alert_id="ALERT-1",
        title="CPU 高",
        content="95%",
        level="2",
        status="unassigned",
        source_name="Prometheus",
        resource_id="host-1",
        resource_name="host-1",
        resource_type="host",
        item="cpu",
        labels={},
        dimensions={},
        enrichment={},
        operator=[],
        team=[1],
        created_at=None,
        first_event_time=None,
        last_event_time=None,
    )

    with pytest.raises(TemplateBindingError):
        render_bound_template(template.id, "email", alert, ["admin"], "assignment")
