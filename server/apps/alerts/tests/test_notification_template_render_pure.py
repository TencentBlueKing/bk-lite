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
    owners: list = None
    team: list = None
    created_at: object = None
    first_event_time: object = None
    last_event_time: object = None

    def __post_init__(self):
        self.labels = self.labels or {"env": "prod"}
        self.dimensions = self.dimensions or {"instance": "10.0.0.8"}
        self.enrichment = self.enrichment or {"cmdb": {"owner": "张三"}}
        self.operator = self.operator or ["owner"]
        self.owners = self.owners or []
        self.team = self.team or [1]


def test_email_html_keeps_layout_and_escapes_variable_values():
    from apps.alerts.notification_templates.renderer import build_alert_context, render_source

    context = build_alert_context(AlertStub(owners=["alice", "bob"]), ["zhangsan"], "assignment")
    rendered_owners = render_source("责任人 {{ alert.owners }}", context, channel_type="email")
    assert "alice" in rendered_owners.value
    assert "bob" in rendered_owners.value
    result = render_source(
        '<table><tr><td style="color: red">{{ alert.title }}</td></tr>' "<tr><td>{{ alert.content }}</td></tr></table>",
        context,
        channel_type="email",
    )

    assert '<table><tr><td style="color: red">数据库连接数过高</td></tr>' in result.value
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result.value
    assert result.missing_fields == []


@pytest.mark.parametrize(
    ("time_zone", "expected_times", "expected_cell"),
    [
        ("UTC", "2026-10-16 03:24:01｜2026-10-16 03:24:01｜2026-10-16 03:30:00", "2026-10-16 03:24:01"),
        ("Asia/Shanghai", "2026-10-16 11:24:01｜2026-10-16 11:24:01｜2026-10-16 11:30:00", "2026-10-16 11:24:01"),
        ("Europe/Berlin", "2026-10-16 05:24:01｜2026-10-16 05:24:01｜2026-10-16 05:30:00", "2026-10-16 05:24:01"),
    ],
)
def test_time_variables_follow_display_timezone(time_zone, expected_times, expected_cell):
    from datetime import datetime, timezone

    from apps.alerts.notification_templates.events import cell_text
    from apps.alerts.notification_templates.renderer import build_alert_context, render_source

    created_at = datetime(2026, 10, 16, 3, 24, 1, 123456, tzinfo=timezone.utc)
    context = build_alert_context(
        AlertStub(created_at=created_at, first_event_time=created_at),
        [],
        "assignment",
        generated_at=datetime(2026, 10, 16, 3, 30, tzinfo=timezone.utc),
        display_timezone=time_zone,
    )
    result = render_source(
        "{{ alert.created_at }}｜{{ alert.first_event_time }}｜{{ notification.generated_at }}",
        context,
        channel_type="custom_webhook",
    )

    assert result.value == expected_times
    assert cell_text(created_at, time_zone) == expected_cell


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


@pytest.mark.parametrize(
    "source",
    [
        "<a {{ alert.title }}>open</a>",
        "<{{ alert.title }}>hello",
        "<a data-{{ alert.title }}='x'>hello</a>",
        "</{{ alert.title }}>",
        "<a {{ alert.title }}>open</a>&#98;klitetemplatevariable0end",
        "<!-- {{ alert.title }} -->",
        "<?{{ alert.title }}?>",
        "<!DOCTYPE {{ alert.title }}>",
        "<a title={{ alert.title }}",
        '<img src="https://example.test/pixel">',
        '<img srcset="https://example.test/pixel 1x">',
        '<table background="//example.test/pixel"><tr><td>x</td></tr></table>',
        '<a href="https://example.test" ping="https://example.test/track">open</a>',
        '<video poster="https://example.test/pixel"></video>',
        '<div style="background:u\\72l(https://example.test/pixel)">x</div>',
        "<div style='background-image:image-set(\"https://example.test/pixel\" 1x)'>x</div>",
        "<div style='background-image:-webkit-image-set(\"https://example.test/pixel\" 1x)'>x</div>",
    ],
)
def test_email_rejects_nontext_placeholders_and_resource_loading(source):
    from apps.alerts.notification_templates.renderer import TemplateValidationError, render_source

    with pytest.raises(TemplateValidationError):
        render_source(source, {"alert": {"title": "onclick=alert(1)"}}, channel_type="email")


def test_email_allows_static_links_and_repeated_escaped_text():
    from apps.alerts.notification_templates.renderer import render_source

    result = render_source(
        '<a href="https://example.test/alerts">{{ alert.title }}</a><p>{{ alert.title }}</p>',
        {"alert": {"title": '<img src="https://example.test/pixel">'}},
        channel_type="email",
    )
    escaped = '&lt;img src="https://example.test/pixel"&gt;'
    assert result.value == f'<a href="https://example.test/alerts">{escaped}</a><p>{escaped}</p>'


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


@pytest.mark.parametrize(
    ("level", "token"),
    [("0", "warning"), ("1", "warning"), ("2", "comment"), ("3", "info"), ("提醒", "info")],
)
def test_wecom_color_follows_alert_level_id(level, token):
    from apps.alerts.notification_templates.renderer import build_alert_context, render_source

    context = build_alert_context(AlertStub(level=level), [], "assignment", level_display_name="级别")
    result = render_source(
        '<font color="{{ alert.wecom_color }}">{{ alert.level }}</font>',
        context,
        channel_type="enterprise_wechat_bot",
    )

    assert result.value == f'<font color="{token}">级别</font>'


@pytest.mark.parametrize(
    ("level", "token"),
    [("0", "red"), ("1", "orange"), ("2", "yellow"), ("3", "green"), ("提醒", "green")],
)
def test_feishu_color_follows_alert_level_id(level, token):
    from apps.alerts.notification_templates.renderer import build_alert_context, render_source

    context = build_alert_context(AlertStub(level=level), [], "assignment", level_display_name="级别")
    result = render_source(
        "<font color='{{ alert.feishu_color }}'>{{ alert.level }}</font>",
        context,
        channel_type="feishu_bot",
    )

    assert result.value == f"<font color='{token}'>级别</font>"


def test_feishu_operation_template_colors_level_only():
    from apps.alerts.notification_templates.operation import _operation_base_content

    _subject, feishu = _operation_base_content("feishu_bot")
    _subject, dingtalk = _operation_base_content("dingtalk_bot")

    assert "<font color='{{ alert.feishu_color }}'>{{ alert.level }}</font>" in feishu
    assert "{{ alert.title }}" in feishu
    assert "{{ notification.action_summary }}" in feishu
    assert "<font" not in dingtalk
    assert "｜{{ alert.level }}" in dingtalk


def test_email_style_accepts_only_level_color_variable():
    from apps.alerts.notification_templates.renderer import TemplateValidationError, build_alert_context, render_source

    context = build_alert_context(AlertStub(), [], "assignment", level_display_name="警告", level_color="#11aa22")
    result = render_source(
        '<strong style="color:{{ alert.level_color }};">{{ alert.level }}</strong>',
        context,
        channel_type="email",
    )

    assert result.value == '<strong style="color:#11AA22;">警告</strong>'
    unsafe = build_alert_context(AlertStub(), [], "assignment", level_color='red;background:url("https://example.test/x")')
    fallback = render_source('<p style="color:{{ alert.level_color }};">x</p>', unsafe, channel_type="email")
    assert fallback.value == '<p style="color:#FFAD42;">x</p>'
    with pytest.raises(TemplateValidationError, match="变量只能放在 HTML 文本节点中"):
        render_source('<strong style="color:{{ alert.title }};">{{ alert.level }}</strong>', context, channel_type="email")
