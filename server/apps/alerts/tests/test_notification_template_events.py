import pytest

BLOCK = "{{@ events limit=2 order=-start_time " "columns=level as 事件级别, resource_name as 资源, tags.alert as 规则, value @}}"


def _events_context():
    rows = [
        {
            "level": "提醒",
            "resource_name": "prod-mysql-02",
            "value": 1200,
            "start_time": "2026-09-22 10:00:00+08:00",
            "tags": {"alert": "Slow"},
            "labels": {},
            "enrichment": {"cmdb": {"owner": "李娜"}},
        },
        {
            "level": "严重",
            "resource_name": "prod-mysql-01",
            "value": "<script>alert(1)</script>",
            "start_time": "2026-09-22 10:05:00+08:00",
            "tags": {"alert": "Conn>1500"},
            "labels": {},
            "enrichment": {"cmdb": {"owner": "张伟"}},
        },
        {
            "level": "警告",
            "resource_name": "prod-mysql-03",
            "value": 900,
            "start_time": "2026-09-22 09:00:00+08:00",
            "tags": {"alert": "@all"},
            "labels": {},
            "enrichment": {},
        },
    ]
    return {"count": 47, "latest": rows[1], "first": rows[2], "rows": rows}


def test_event_block_renders_html_table_without_escaping_structure():
    from apps.alerts.notification_templates.renderer import render_source

    result = render_source(
        f"<h2>{{{{ alert.title }}}}</h2>{BLOCK}",
        {"alert": {"title": "连接数过高"}, "events": _events_context()},
        channel_type="email",
    )

    assert "<table" in result.value
    assert "&lt;table" not in result.value
    assert "Conn&gt;1500" in result.value
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result.value
    assert "共 47 条，已展示前 2 条" in result.value
    assert "prod-mysql-03" not in result.value


def test_markdown_channel_lists_rows_and_escapes_mentions():
    from apps.alerts.notification_templates.renderer import render_source

    result = render_source(
        "{{@ events limit=1 order=start_time columns=tags.alert @}}",
        {"events": _events_context()},
        channel_type="enterprise_wechat_bot",
    )

    assert "<table" not in result.value
    assert result.value.startswith("- tags\\_alert: ")
    assert "@\u200ball" in result.value
    assert "@all" not in result.value
    assert "共 47 条，已展示前 1 条" in result.value


def test_nested_json_path_uses_last_segment_as_default_header():
    from apps.alerts.notification_templates.events import parse_event_block

    spec = parse_event_block("events columns=enrichment.cmdb.owner, level as 事件级别")

    assert spec.columns[0].path == "enrichment.cmdb.owner"
    assert spec.columns[0].label == "enrichment_cmdb_owner"
    assert spec.columns[1].label == "事件级别"


def test_rejected_event_fields_and_bad_limits():
    from apps.alerts.notification_templates.renderer import TemplateValidationError, validate_source

    for source in (
        "{{@ events columns=raw_data @}}",
        "{{@ events columns=assignee @}}",
        "{{@ events columns=ingest_key @}}",
        "{{ events.latest.raw_data.token }}",
        "{{@ events limit=101 columns=level @}}",
        "{{@ events limit=all columns=level @}}{{@ events columns=title @}}" * 5,
        "标题 {{@ events columns=level @}}",
    ):
        with pytest.raises(TemplateValidationError):
            validate_source(source, channel_type="email", is_subject=source.startswith("标题"), scope="single_alert")


def test_summary_scope_rejects_event_variables():
    from apps.alerts.notification_templates.renderer import TemplateValidationError, validate_source

    with pytest.raises(TemplateValidationError, match="汇总模板不能使用事件变量"):
        validate_source("{{ events.count }}", channel_type="email", scope="unassigned_summary")
    with pytest.raises(TemplateValidationError, match="汇总模板不能使用事件变量"):
        validate_source("{{@ events columns=level @}}", channel_type="email", scope="unassigned_summary")


def test_email_rejects_event_block_outside_text_node():
    from apps.alerts.notification_templates.renderer import TemplateValidationError, validate_source

    with pytest.raises(TemplateValidationError):
        validate_source(
            '<div class="{{@ events columns=level @}}">x</div>',
            channel_type="email",
        )


def test_byte_budget_drops_rows_and_reports_the_shown_count():
    from apps.alerts.notification_templates.events import parse_event_block, render_event_block

    rows = [{"level": "严重", "value": "x" * 80, "start_time": f"2026-09-22 10:{index:02d}:00+08:00"} for index in range(12)]
    spec = parse_event_block("events limit=10 columns=level, value")
    text = render_event_block(
        spec,
        {"count": 40, "rows": rows},
        family="text",
        escape=lambda value: value,
        max_bytes=600,
    )

    assert "已展示前 10 条" not in text
    assert "已展示前" in text
    assert text.count("严重") < 10


def test_single_event_paths_resolve_latest_value():
    from apps.alerts.notification_templates.renderer import render_source

    result = render_source(
        "{{ events.count }} {{ events.latest.tags.alert }} {{ events.latest.enrichment.cmdb.owner }}",
        {"events": _events_context()},
        channel_type="custom_webhook",
    )

    assert result.value == "47 Conn>1500 张伟"
