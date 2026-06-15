"""HostCollectMetrics.set_cpu_arch 的纯映射测试。

回归 bug：host 模型把 cpu_architecture="x86_64" 错误映射成 "x86"。
根因——set_cpu_arch 遍历的是展示用的 cup_arch_list（含 "x86" 条目），
"x86" 是 "x86_64" 的子串且排在前面，子串匹配短路返回 "x86"，
永远到不了 "x64"。正确应遍历 server_cpuarch_list（原始 uname -m → 业务编码）。
"""
import pytest

from apps.cmdb.collection.collect_plugin.host import HostCollectMetrics


@pytest.fixture
def host_runner(monkeypatch):
    # model_id 属性会触发 DB 查询，测纯映射时直接打桩成 "host"
    monkeypatch.setattr(HostCollectMetrics, "model_id", property(lambda self: "host"))
    return HostCollectMetrics("web01.prod.example.com", "cmdb_1", 1)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("x86_64", "x64"),     # 最常见：之前会错成 "x86"
        ("aarch64", "arm64"),
        ("arm64", "arm64"),
        ("armv7l", "arm"),
        ("armv8l", "arm64"),
        ("i386", "x86"),
        ("i686", "x86"),
        ("", "other"),
        ("totally-unknown-arch", "other"),
    ],
)
def test_set_cpu_arch_maps_raw_uname_to_business_code(host_runner, raw, expected):
    assert host_runner.set_cpu_arch({"cpu_architecture": raw}) == expected
