from dataclasses import dataclass

import pytest


@dataclass
class AlertStub:
    alert_id: str = "ALERT-001"
    title: str = "数据库连接数过高"
    content: str = "连接数达到 95% <script>alert(1)</script>"
    level: str = "2"
    status: str = "unassigned"
    source_name: str = "Prometheus"
    resource_id: str = "mysql-01"
    resource_name: str = "生产数据库"
    resource_type: str = "mysql"
    item: str = "connections"
    labels: dict = None
    dimensions: dict = None
    enrichment: dict = None
    operator: list = None
    team: list = None
    created_at: object = None
    first_event_time: object = None
    last_event_time: object = None

    def __post_init__(self):
        self.labels = self.labels or {"env": "prod"}
        self.dimensions = self.dimensions or {"instance": "10.0.0.8"}
        self.enrichment = self.enrichment or {"cmdb": {"owner": "张三"}}
        self.operator = self.operator or ["owner"]
        self.team = self.team or [1]


def test_email_html_keeps_layout_and_escapes_variable_values():
    from apps.alerts.notification_templates.renderer import build_alert_context, render_source

    context = build_alert_context(AlertStub(), ["zhangsan"], "assignment")
    result = render_source(
        '<table><tr><td style="color: red">{{ alert.title }}</td></tr>' "<tr><td>{{ alert.content }}</td></tr></table>",
        context,
        channel_type="email",
    )

    assert '<table><tr><td style="color: red">数据库连接数过高</td></tr>' in result.value
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result.value
    assert result.missing_fields == []


def test_receiver_names_are_human_readable_without_changing_raw_receiver_list():
    from apps.alerts.notification_templates.renderer import build_alert_context

    context = build_alert_context(AlertStub(), ["zhangsan", "lisi"], "assignment")

    assert context["notification"]["receiver_names"] == "zhangsan、lisi"
    assert context["notification"]["receivers"] == ["zhangsan", "lisi"]


def test_alert_operation_context_exposes_only_explicit_operation_fields():
    from apps.alerts.notification_templates.renderer import build_alert_context, render_source

    context = build_alert_context(
        AlertStub(),
        ["zhangsan"],
        "reassignment",
        notification_context={
            "action_summary": "该告警已由 admin 从 lisi 转派给 zhangsan，请新的处理人及时认领并处理。",
            "actor_name": "admin",
            "previous_receiver_names": "lisi",
            "action_time": "2026-09-10 11:30:00",
            "ignored": "不应进入模板上下文",
        },
    )

    result = render_source(
        "{{ notification.action_summary }}｜{{ notification.actor_name }}｜"
        "{{ notification.previous_receiver_names }}｜{{ notification.action_time }}",
        context,
        channel_type="custom_webhook",
        scope="alert_operation",
    )

    assert result.value == ("该告警已由 admin 从 lisi 转派给 zhangsan，请新的处理人及时认领并处理。｜" "admin｜lisi｜2026-09-10 11:30:00")
    assert "ignored" not in context["notification"]


def test_alert_operation_fields_are_rejected_by_ordinary_templates():
    from apps.alerts.notification_templates.renderer import TemplateValidationError, render_source

    with pytest.raises(TemplateValidationError, match="告警操作变量只能用于告警操作通知模板"):
        render_source(
            "{{ notification.action_summary }}",
            {"notification": {"action_summary": "人工分派"}},
            channel_type="custom_webhook",
            scope="single_alert",
        )


def test_markdown_escapes_dynamic_markup_but_keeps_template_markdown():
    from apps.alerts.notification_templates.renderer import build_alert_context, render_source

    alert = AlertStub(title="故障 **伪造标题**", content="@all `危险内容`")
    context = build_alert_context(alert, ["zhangsan"], "reminder")
    result = render_source(
        "## 告警提醒\n> **标题**：{{ alert.title }}\n\n{{ alert.content }}",
        context,
        channel_type="enterprise_wechat_bot",
    )

    assert result.value.startswith("## 告警提醒\n> **标题**：")
    assert r"故障 \*\*伪造标题\*\*" in result.value
    assert r"@\u200ball" not in result.value
    assert "@\u200ball" in result.value
    assert r"\`危险内容\`" in result.value


def test_optional_dynamic_path_uses_placeholder_and_reports_diagnostic():
    from apps.alerts.notification_templates.renderer import build_alert_context, render_source

    context = build_alert_context(AlertStub(), [], "recovery")
    result = render_source("负责人：{{ enrichment.cmdb.backup_owner }}", context, channel_type="enterprise_wechat_bot")

    assert result.value == "负责人：—"
    assert result.missing_fields == ["enrichment.cmdb.backup_owner"]


@pytest.mark.parametrize(
    "source",
    [
        "{{ alert.__class__ }}",
        "{{ alert.title.upper() }}",
        "{{ alert.title | safe }}",
        "{% for item in alerts %}{{ item }}{% endfor %}",
    ],
)
def test_executable_or_private_syntax_is_rejected(source):
    from apps.alerts.notification_templates.renderer import TemplateValidationError, validate_source

    with pytest.raises(TemplateValidationError):
        validate_source(source, channel_type="email")


@pytest.mark.parametrize(
    "source",
    [
        "<script>alert(1)</script>",
        '<img src="x" onerror="alert(1)">',
        '<a href="javascript:alert(1)">x</a>',
        '<div style="background:url(https://example.test/x)">x</div>',
        '<div class="{{ alert.title }}">x</div>',
    ],
)
def test_dangerous_email_html_is_rejected(source):
    from apps.alerts.notification_templates.renderer import TemplateValidationError, validate_source

    with pytest.raises(TemplateValidationError):
        validate_source(source, channel_type="email")


def test_subject_rejects_header_injection_and_unknown_root():
    from apps.alerts.notification_templates.renderer import TemplateValidationError, validate_source

    with pytest.raises(TemplateValidationError):
        validate_source("告警\r\nBcc: attacker@example.com", channel_type="email", is_subject=True)
    with pytest.raises(TemplateValidationError):
        validate_source("{{ secrets.token }}", channel_type="email", is_subject=True)


def test_variable_values_are_not_rendered_twice():
    from apps.alerts.notification_templates.renderer import build_alert_context, render_source

    context = build_alert_context(AlertStub(title="{{ alert.content }}"), [], "assignment")
    result = render_source("{{ alert.title }}", context, channel_type="email")

    assert result.value == "{{ alert.content }}"


def test_subject_rejects_newline_from_dynamic_value():
    from apps.alerts.notification_templates.renderer import TemplateValidationError, build_alert_context, render_source

    context = build_alert_context(AlertStub(title="合法标题\r\nBcc: attacker@example.com"), [], "assignment")

    with pytest.raises(TemplateValidationError, match="变量值不能包含换行"):
        render_source("{{ alert.title }}", context, channel_type="email", is_subject=True)


def test_large_collection_is_rejected_before_output_expansion():
    from apps.alerts.notification_templates.renderer import TemplateValidationError, build_alert_context, render_source

    alert = AlertStub(enrichment={"cmdb": {"owners": list(range(101))}})
    context = build_alert_context(alert, [], "assignment")

    with pytest.raises(TemplateValidationError, match="不能超过 100 项"):
        render_source("{{ enrichment.cmdb.owners }}", context, channel_type="enterprise_wechat_bot")
