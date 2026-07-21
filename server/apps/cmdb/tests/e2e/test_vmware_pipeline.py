"""VMware 采集端到端流水线测试 —— vm 大类代表。

VMware 采集特点：
  - 单次采集 vc/esxi/vm/ds 多个 sub-model（按 VMWARE_COLLECT_MAP 拆分 metric → model_id）
  - 本测试只校验最简单的 vmware_vc 路径，证明 plugin model_field_mapping 正确加载
  - vmware_esxi/vm/ds 含关联关系（self_vc/self_esxi/assos），属业务规则范畴，单 fixture 校验不全
  - Task 2.3 新增 test_vmware_vc_a_b_alignment:真实形态 01 fixture + A/B 端覆盖
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


def test_step1_raw_matches_schema(load_fixture, load_schema):
    raw = load_fixture("vmware/01_raw_collector.json")
    schema = load_schema("vmware/01_raw_collector.schema.json")
    jsonschema.validate(raw, schema)


def test_step1_stargazer_raw_matches_schema(load_fixture, load_schema):
    """Task 2.3 新增:验证真实形态 01_stargazer_raw.json 符合 schema。"""
    raw = load_fixture("vmware/01_stargazer_raw.json")
    schema = load_schema("vmware/01_stargazer_raw.schema.json")
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


# ============================================================================
# Task 2.3: vmware_vc A 端 + B 端对齐全覆盖测试
# ============================================================================


@pytest.mark.django_db
def test_vmware_vc_a_b_alignment(load_fixture, load_schema, monkeypatch):
    """vmware_vc A 端 + B 端对齐全覆盖测试。

    vmware model_id 在 alignment test 里使用,实际 pipeline 走 vmware_vc sub-model
    (因为 VMWARE_COLLECT_MAP 把 vmware_vc_info_gauge 映射到 vmware_vc)。
    """
    from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def
    from apps.cmdb.collection.collect_plugin.vmware import CollectVmwareMetrics
    from apps.cmdb.collection.plugins.community.vm.plugins import VmwareVCCollectionPlugin

    raw = load_fixture("vmware/01_stargazer_raw.json")
    expected = load_fixture("vmware/04_expected_cmdb_result.json")

    # A 端:02 → 03(pipeline 用 vmware_vc)
    raw_items = [raw] if isinstance(raw, dict) else raw
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id="vmware_vc")
    p3 = pipeline.step2_push_to_vm(p2, task_id=66666)

    for result_item in p3["data"]["result"]:
        assert result_item["metric"]["__name__"].endswith("_info_gauge")
        # instance_id 来自 step2_push_to_vm 的 cmdb_<task_id> 格式(01 fixture 无 instance_id 字段)
        assert result_item["metric"]["instance_id"] == "cmdb_66666"
        # 业务 label 集合 ⊇ model 必填字段
        model_fields = get_model_field_def("vmware")
        required = {f.name for f in model_fields.values() if f.is_required}
        labels = set(result_item["metric"].keys())
        exclude = {"__name__", "instance_id", "collect_status", "inst_name",
                   "model_id", "id", "create_time", "update_time", "assos"}
        missing = required - labels - exclude
        assert not missing, f"A 端 03 metric 缺 model 必填字段: {missing}"

    # B 端:03 → 04
    monkeypatch.setattr(
        VmwareVCCollectionPlugin, "field_mapping",
        {"vc_version": "vc_version", "inst_name": CollectVmwareMetrics.set_vc_inst_name},
        raising=False,
    )
    from apps.cmdb.collection.plugins.base import bind_collection_mapping
    monkeypatch.setattr(
        CollectVmwareMetrics, "_metrics",
        property(lambda self: [
            "vmware_vc_info_gauge", "vmware_ds_info_gauge",
            "vmware_esxi_info_gauge", "vmware_vm_info_gauge",
        ]),
    )
    monkeypatch.setattr(
        CollectVmwareMetrics, "model_field_mapping",
        property(lambda self: {
            mid: bind_collection_mapping(self, m)
            for mid, m in VMWARE_MODEL_FIELD_MAPPING.items()
        }),
    )

    raw_items = raw if isinstance(raw, list) else raw
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=CollectVmwareMetrics,
        plugin_cls=VmwareVCCollectionPlugin,
        model_id="vmware_vc",
        task_id=66666,
        instances=[{"inst_name": "vc-prod-01"}],
        extra_payload_keys=None,
        monkeypatch=monkeypatch,
    )

    instances = run["cmdb_result"]["vmware_vc"]
    assert len(instances) >= expected["instance_count_min"]

    inst = instances[0]
    # B 端:实例字段 ⊆ model 字段定义
    model_fields = get_model_field_def("vmware")
    system_fields = {
        "inst_name", "model_id", "id", "create_time", "update_time",
        "_placeholder_reason", "license_status", "assos",
    }
    model_field_names = set(model_fields.keys()) - system_fields
    inst_fields = set(inst.keys())
    missing = model_field_names - inst_fields
    assert not missing, f"B 端 04 实例缺 model 字段: {missing}"

    # B 端:vc_version 是 string
    assert inst.get("vc_version") == "8.0.2.00100", \
        f"vc_version 应该是 8.0.2.00100,实际 {inst.get('vc_version')}"


# 导入 VMWARE_MODEL_FIELD_MAPPING 用于 test_vmware_vc_a_b_alignment
from apps.cmdb.collection.plugins.community.vm.plugins import VMWARE_MODEL_FIELD_MAPPING
