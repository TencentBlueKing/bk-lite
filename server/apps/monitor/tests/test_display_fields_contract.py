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
                # 绑定带 plugin 时，指标须存在于本文件(plugin 留空=跨插件绑定，跳过校验)
                if plugin and not data.get("is_compound_object"):
                    assert metric in metric_names, f"{path}: 列 {col['name']} 指标 {metric} 不在本文件"
