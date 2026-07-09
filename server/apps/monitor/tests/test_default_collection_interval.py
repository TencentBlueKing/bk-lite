"""监控实例采集间隔默认值锁定为 60s 的回归测试。

业务规则:任何「采集频率/采集间隔」类默认值,不足 60s 一律改为 60s。
该测试防止后续误改回 10s。
"""
from apps.monitor.models import MonitorInstance


def test_monitor_instance_default_interval_is_60_seconds():
    field = MonitorInstance._meta.get_field("interval")
    assert field.default == 60, (
        f"MonitorInstance.interval 默认值应为 60s,实际为 {field.default}"
    )
