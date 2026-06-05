"""VMware 采集端到端流水线测试 —— vm 大类代表。

VMware 采集特点：
  - 单次采集 vc/esxi/vm/ds 多个 sub-model（按 VMWARE_COLLECT_MAP 拆分 metric → model_id）
  - 本测试只校验最简单的 vmware_vc 路径，证明 plugin model_field_mapping 正确加载
  - vmware_esxi/vm/ds 含关联关系（self_vc/self_esxi/assos），属业务规则范畴，单 fixture 校验不全
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


def test_step1_raw_matches_schema(load_fixture, load_schema):
    raw = load_fixture("vmware/01_raw_collector.json")
    schema = load_schema("vmware/01_raw_collector.schema.json")
    jsonschema.validate(raw, schema)


@pytest.mark.django_db
def test_vmware_vc_pipeline_end_to_end(load_fixture, load_schema, monkeypatch):
    from apps.cmdb.collection.collect_plugin.vmware import CollectVmwareMetrics
    from apps.cmdb.collection.plugins.community.vm.plugins import VmwareVCCollectionPlugin

    raw = load_fixture("vmware/01_raw_collector.json")
    expected = load_fixture("vmware/04_expected_cmdb_result.json")

    # 给 plugin 加一个最小 field_mapping，generic 驱动会用它
    monkeypatch.setattr(
        VmwareVCCollectionPlugin, "field_mapping",
        {"vc_version": "vc_version", "inst_name": CollectVmwareMetrics.set_vc_inst_name},
        raising=False,
    )

    run = pipeline.run_full_pipeline_generic(
        raw_items=raw,
        runner_cls=CollectVmwareMetrics,
        plugin_cls=VmwareVCCollectionPlugin,
        model_id="vmware_vc",
        task_id=6001,
        instances=[{"inst_name": "vc-prod-01"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["vmware_vc"]
    assert len(instances) >= expected["instance_count_min"]

    inst_schema = load_schema("vmware/04_cmdb_instance.schema.json")
    for inst in instances:
        jsonschema.validate(inst, inst_schema)

    actual = instances[0]
    for field, expected_value in expected["expected_instance_subset"].items():
        assert actual.get(field) == expected_value, \
            f"字段 {field}：期望 {expected_value!r}，实际 {actual.get(field)!r}"


def test_drift_detection(load_schema):
    bad = {"inst_name": "vc-01"}  # 缺 vc_version
    schema = load_schema("vmware/01_raw_collector.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
