"""MinIO 采集端到端流水线测试（middleware 大类，脚本采集）。

middleware 模式：业务字段经 metric.result JSON 传递，runner.format_data 解码后映射。
验证 stargazer 脚本输出 → VM → CMDB 实例 全链路字段映射。
"""
import pytest

from apps.cmdb.tests.e2e import pipeline


@pytest.mark.django_db
def test_minio_pipeline_end_to_end(monkeypatch):
    from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
    from apps.cmdb.collection.plugins.community.middleware.minio import MinioCollectionPlugin

    # 模拟 stargazer minio_default_discover.sh 的单实例输出
    raw = {
        "ip_addr": "10.0.0.50",
        "port": "9000",
        "console_port": "9001",
        "version": "RELEASE.2024-01-18T22-51-28Z",
        "bin_path": "/usr/local/bin/minio",
        "data_path": "/data1,/data2,/data3,/data4",
        "conf_path": "/etc/default/minio",
        "deploy_mode": "erasure",
        "region": "cn-north-1",
        "start_args": "minio server --address :9000 --console-address :9001 /data{1...4}",
    }

    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=MiddlewareCollectMetrics,
        plugin_cls=MinioCollectionPlugin,
        model_id="minio",
        task_id=9001,
        instances=[{"inst_name": "10.0.0.50-minio-9000", "ip_addr": "10.0.0.50"}],
        extra_payload_keys={},  # middleware：业务字段走 metric.result
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["minio"]
    assert len(instances) == 1
    inst = instances[0]

    expected = {
        "ip_addr": "10.0.0.50",
        "port": "9000",
        "console_port": "9001",
        "version": "RELEASE.2024-01-18T22-51-28Z",
        "bin_path": "/usr/local/bin/minio",
        "data_path": "/data1,/data2,/data3,/data4",
        "conf_path": "/etc/default/minio",
        "deploy_mode": "erasure",
        "region": "cn-north-1",
    }
    for field, value in expected.items():
        assert inst.get(field) == value, \
            f"字段 {field}：期望 {value!r}，实际 {inst.get(field)!r}"

    # inst_name 由 ip+port 生成，应非空
    assert inst.get("inst_name")


@pytest.mark.django_db
def test_minio_pipeline_field_aliases(monkeypatch):
    """脚本若用别名字段（minio_path/volumes/config_path），仍能正确映射。"""
    from apps.cmdb.collection.collect_plugin.middleware import MiddlewareCollectMetrics
    from apps.cmdb.collection.plugins.community.middleware.minio import MinioCollectionPlugin

    raw = {
        "ip_addr": "10.0.0.51",
        "port": "9000",
        "version": "RELEASE.2024-01-18T22-51-28Z",
        "minio_path": "/opt/minio/minio",
        "volumes": "/srv/minio",
        "config_path": "/etc/minio/minio.conf",
        "deploy_mode": "standalone",
    }
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=MiddlewareCollectMetrics,
        plugin_cls=MinioCollectionPlugin,
        model_id="minio",
        task_id=9002,
        instances=[{"inst_name": "10.0.0.51-minio-9000", "ip_addr": "10.0.0.51"}],
        extra_payload_keys={},
        monkeypatch=monkeypatch,
    )
    inst = run["cmdb_result"]["minio"][0]
    assert inst.get("bin_path") == "/opt/minio/minio"
    assert inst.get("data_path") == "/srv/minio"
    assert inst.get("conf_path") == "/etc/minio/minio.conf"
