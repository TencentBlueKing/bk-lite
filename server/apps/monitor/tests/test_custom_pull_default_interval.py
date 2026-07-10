"""锁定 custom_pull_plugin.DEFAULT_PULL_UI_TEMPLATE.interval.default_value = 60 的回归测试。

业务规则：监控采集频率统一为 60s（见 PR #4044 commit 5be4782774）。
custom_pull_plugin.DEFAULT_PULL_UI_TEMPLATE 是自定义拉取监控实例的 UI
表单模板，新建实例时 interval 字段默认值必须为 60s，防止后续误改回 10s。
"""
from apps.monitor.services.custom_pull_plugin import DEFAULT_PULL_UI_TEMPLATE

EXPECTED_DEFAULT_INTERVAL_SECONDS = 60


def _find_interval_field(template):
    """从 form_fields 中定位 name == 'interval' 的字段。

    DEFAULT_PULL_UI_TEMPLATE 的 interval 位于 form_fields 列表内
    （不是模板顶层 key），所以需要遍历一次。
    """
    form_fields = template.get("form_fields") or []
    for field in form_fields:
        if field.get("name") == "interval":
            return field
    return None


def test_default_pull_ui_template_interval_default_value_is_60_seconds():
    """custom_pull_plugin DEFAULT_PULL_UI_TEMPLATE 中 interval 字段默认值必须 = 60s。"""
    interval_field = _find_interval_field(DEFAULT_PULL_UI_TEMPLATE)
    assert interval_field is not None, (
        "DEFAULT_PULL_UI_TEMPLATE.form_fields 中未找到 name == 'interval' 的字段"
    )
    actual = interval_field.get("default_value")
    assert actual == EXPECTED_DEFAULT_INTERVAL_SECONDS, (
        f"DEFAULT_PULL_UI_TEMPLATE.interval.default_value 应为 "
        f"{EXPECTED_DEFAULT_INTERVAL_SECONDS}, 实际为 {actual!r}"
    )
