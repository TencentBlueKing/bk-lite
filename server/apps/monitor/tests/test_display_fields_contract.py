import glob
import json
import os

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "support-files", "plugins")
ENT = os.path.join(os.path.dirname(__file__), "..", "enterprise", "support-files", "plugins")

# 默认列里禁止出现的"存活/运行时间"类指标(列表已自带上报状态列)
FORBIDDEN_METRICS = {
    "snmp_uptime", "mysql_uptime", "redis_uptime", "mongodb_uptime_ns",
    "oracledb_uptime_seconds_gauge", "rabbitmq_node_uptime", "system_uptime",
    "oceanbase_uptime", "apache_ServerUptimeSeconds", "sqlserver_server_properties_uptime",
    "minio_node_process_uptime_seconds_gauge",
}


def _iter_metrics_files():
    files = glob.glob(os.path.join(ROOT, "**", "metrics.json"), recursive=True)
    files += glob.glob(os.path.join(ENT, "**", "metrics.json"), recursive=True)
    return sorted(files)


def _objects(data):
    return data.get("objects") if data.get("is_compound_object") else [data]


@pytest.mark.parametrize("path", _iter_metrics_files())
def test_display_fields_contract(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for obj in _objects(data):
        dfs = obj.get("display_fields")
        if not dfs:
            continue  # 缺默认列的对象由各自任务补齐，这里不强制
        # 列数 3~5
        assert 3 <= len(dfs) <= 5, f"{path}: 列数={len(dfs)} 不在 [3,5]"
        metric_names = {m["name"] for m in obj.get("metrics", [])}
        for col in dfs:
            assert col.get("name"), f"{path}: 列缺 name"
            binds = col.get("metrics") or []
            assert binds, f"{path}: 列 {col['name']} 无绑定"
            for b in binds:
                plugin = b.get("plugin", "")
                metric = b.get("metric")
                assert metric, f"{path}: 空 metric"
                # 禁止存活/uptime 类进默认列
                assert metric not in FORBIDDEN_METRICS, f"{path}: 列 {col['name']} 含禁用指标 {metric}"
                # 仅校验"本插件"绑定的指标存在于本文件；跨插件绑定(Host 多绑定的外插件)与
                # plugin 留空(SNMP 跨品牌)绑定均跳过——它们的指标不在本文件理所应当。
                if plugin and plugin == data.get("plugin") and not data.get("is_compound_object"):
                    assert metric in metric_names, f"{path}: 列 {col['name']} 指标 {metric} 不在本文件"


def test_host_three_plugins_share_same_block():
    base = os.path.join(os.path.dirname(__file__), "..", "support-files", "plugins", "Telegraf")
    paths = [f"{base}/host/os/metrics.json", f"{base}/http/windows_wmi/metrics.json", f"{base}/http/host/metrics.json"]
    blocks = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            blocks.append(json.load(f)["display_fields"])
    assert [c["name"] for c in blocks[0]] == [c["name"] for c in blocks[1]] == [c["name"] for c in blocks[2]]
    cpu = blocks[0][0]
    plugins = {b["plugin"] for b in cpu["metrics"]}
    assert plugins == {"Host", "Windows WMI", "Host Remote"}, plugins
