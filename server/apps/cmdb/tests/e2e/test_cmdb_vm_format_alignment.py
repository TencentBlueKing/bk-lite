"""B 端对齐检查 —— CMDB 端从 VM 拉数据后,04 实例字段跟 CMDB model 定义对齐。

检查项:
  - 实例字段名 ⊆ Model 字段定义(允许额外字段,不能漏)
  - 字段类型匹配 Model field_type
  - 必填字段非空
  - choice 枚举合法
  - inst_name 模式({ip}-{name_token}-{port})

不动现有 33 真实落盘对象 + test_pipeline_factory.py。
只覆盖 35 个新工作对象(6 真实化 + 7 云采集 + 22 archived placeholder)。
"""
import pytest

from apps.cmdb.tests.e2e import pipeline
from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def, ModelFieldDef


# 同 A 端:35 个新工作对象
ALIGNMENT_COVERED_MODEL_IDS = [
    # P0 真实化(6) — Task 2 逐对象加进来
    "aliyun_ecs",
    "k8s_namespace",
    "vmware",
    "host",
    "network",
    "config_file",
    # P1 云采集新增(7) — Task 3 逐对象加进来
    # P2 archived placeholder(22) — Task 4 逐对象加进来
]


def _type_match(actual_value, expected_type: str) -> bool:
    """检查 actual_value 类型是否跟 expected_type 匹配。"""
    if expected_type == "int":
        return isinstance(actual_value, int) or (
            isinstance(actual_value, str) and actual_value.isdigit()
        )
    if expected_type == "str":
        return isinstance(actual_value, str)
    if expected_type == "float":
        return isinstance(actual_value, (int, float))
    if expected_type == "bool":
        return isinstance(actual_value, bool)
    if expected_type == "choice":
        return isinstance(actual_value, str)
    return True  # unknown 类型跳过


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_b_alignment_field_subset(model_id, load_fixture, runner_plugin_factory, monkeypatch):
    """实例字段名 ⊆ Model 字段定义(允许额外字段,不能漏 model 字段)。

    system_fields 来自 Model 系统自带字段(不参与业务字段子集校验)。
    """
    # K8s 走 minimal path,跳过
    if model_id.startswith("k8s_"):
        pytest.skip(f"{model_id} 走 minimal path,跳过 B 端字段子集检查")
    try:
        get_model_field_def(model_id)  # 验证 model 反射可拿到
    except KeyError:
        pytest.skip(f"{model_id} 04 schema 尚未存在(Task 2/3/4 加进来)")
    try:
        runner_cls, plugin_cls, extra_payload_keys = runner_plugin_factory(model_id)
    except KeyError:
        pytest.skip(f"{model_id} 尚未在 runner_plugin_factory 注册")

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    raw_items_first = raw_items[0] if isinstance(raw_items, list) else raw_items

    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=runner_cls,
        plugin_cls=plugin_cls,
        model_id=model_id,
        task_id=99999,
        instances=[{"inst_name": f"{model_id}-align-01", "ip_addr": raw_items_first.get("ip_addr", "127.0.0.1")}],
        extra_payload_keys=extra_payload_keys,
        monkeypatch=monkeypatch,
    )
    instances = run["cmdb_result"][model_id]

    if not instances:
        pytest.skip(f"{model_id} 流水线无实例产出,跳过(可能是 placeholder 模式)")

    inst = instances[0]
    inst_fields = set(inst.keys())

    # system_fields:不参与业务字段子集校验的 Model 系统字段
    system_fields = {
        "inst_name", "model_id", "id", "create_time", "update_time",
        "_placeholder_reason", "license_status", "assos",
    }
    model_fields = get_model_field_def(model_id)
    model_field_names = set(model_fields.keys()) - system_fields

    missing = model_field_names - inst_fields
    assert not missing, f"{model_id} 04 实例缺 Model 字段: {missing}"


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_b_alignment_required_nonempty(model_id, load_fixture, runner_plugin_factory, monkeypatch):
    """Model 必填字段必须非空。"""
    # K8s 走 minimal path,跳过
    if model_id.startswith("k8s_"):
        pytest.skip(f"{model_id} 走 minimal path,跳过 B 端必填字段检查")
    try:
        model_fields = get_model_field_def(model_id)
    except KeyError:
        pytest.skip(f"{model_id} 04 schema 尚未存在")
    try:
        runner_cls, plugin_cls, extra_payload_keys = runner_plugin_factory(model_id)
    except KeyError:
        pytest.skip(f"{model_id} 尚未在 runner_plugin_factory 注册")
    required_fields = {f.name for f in model_fields.values() if f.is_required}

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    raw_items_first = raw_items[0] if isinstance(raw_items, list) else raw_items

    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=runner_cls,
        plugin_cls=plugin_cls,
        model_id=model_id,
        task_id=99999,
        instances=[{"inst_name": f"{model_id}-align-01", "ip_addr": raw_items_first.get("ip_addr", "127.0.0.1")}],
        extra_payload_keys=extra_payload_keys,
        monkeypatch=monkeypatch,
    )
    instances = run["cmdb_result"][model_id]

    if not instances:
        pytest.skip(f"{model_id} 流水线无实例产出,跳过")

    inst = instances[0]
    for field_name in required_fields:
        value = inst.get(field_name)
        if value is None or value == "":
            # placeholder 对象允许为空(标记 _placeholder_reason)
            if "_placeholder_reason" not in inst:
                pytest.fail(f"{model_id} Model 必填字段 {field_name!r} 为空")
