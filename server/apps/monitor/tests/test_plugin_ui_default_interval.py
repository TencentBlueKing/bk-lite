"""锁定监控插件 UI.json 的 interval.default_value 必须 = 60s 的回归测试。

业务规则:任何「采集频率/采集间隔」类默认值,不足 60s 一律改为 60s
(见 .projectmem/summary.md Decisions)。

该测试扫描所有 Telegraf / JVM-JMX / Kafka-Exporter / Oracle-Exporter 等
插件的 UI.json 配置文件,确保 form 表单渲染时 interval 输入框默认 = 60,
防止后续误改回 10s 或新插件引入 10s 默认。
"""
import json
from pathlib import Path

# server/ 是 pytest 的 cwd
PLUGINS_ROOT = Path("apps/monitor/support-files/plugins")
DEFAULT_INTERVAL_SECONDS = 60


def test_all_plugin_ui_interval_default_is_60_seconds():
    """所有插件 UI.json 的 interval 字段 default_value 必须 = 60。"""
    if not PLUGINS_ROOT.exists():
        # 测试在非 server/ 目录跑时直接跳过,避免误报
        import pytest
        pytest.skip(f"plugins 目录不存在: {PLUGINS_ROOT}")

    violations: list[tuple[str, int]] = []
    scanned = 0

    for ui_json in sorted(PLUGINS_ROOT.rglob("UI.json")):
        try:
            with open(ui_json, encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, OSError):
            continue

        form_fields = data.get("form_fields") or []
        for field in form_fields:
            if field.get("name") != "interval":
                continue
            scanned += 1
            dv = field.get("default_value")
            if dv != DEFAULT_INTERVAL_SECONDS:
                violations.append((str(ui_json), dv))
            break  # 一个文件只取第一个 interval 字段

    assert not violations, (
        f"扫描 {scanned} 个插件 UI.json,发现 {len(violations)} 个 "
        f"interval.default_value 不为 {DEFAULT_INTERVAL_SECONDS}s:\n"
        + "\n".join(f"  {p}: default_value={dv}" for p, dv in violations[:20])
        + ("\n  ..." if len(violations) > 20 else "")
    )
