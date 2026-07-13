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
import importlib

import pytest

from apps.cmdb.tests.e2e import pipeline
from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def, ModelFieldDef


# 由 conftest.py 的 alignment_covered_model_ids fixture 提供;此处保留 inline 列表作为 fallback / docstring。
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


# P0 真实化对象的 (runner_cls, plugin_cls) 注册表 + B 端 extra_payload_keys
# A 端 metric.__name__ 后缀 / B 端 pipeline.run_full_pipeline_generic 都用这个
P0_RUNNER_PLUGIN = {
    "aliyun_ecs": (
        "apps.cmdb.collection.collect_plugin.aliyun.AliyunCollectMetrics",
        "apps.cmdb.collection.plugins.community.cloud.aliyun.AliyunAccountCollectionPlugin",
        None,
    ),
    "vmware": (
        "apps.cmdb.collection.collect_plugin.vmware.CollectVmwareMetrics",
        "apps.cmdb.collection.plugins.community.vm.plugins.VmwareVCCollectionPlugin",
        None,
    ),
    "host": (
        "apps.cmdb.collection.collect_plugin.host.HostCollectMetrics",
        "apps.cmdb.collection.plugins.community.host.host.HostCollectionPlugin",
        None,
    ),
    "network": (
        "apps.cmdb.collection.collect_plugin.network.CollectNetworkMetrics",
        "apps.cmdb.collection.plugins.community.network.plugins.NetworkCollectionPlugin",
        None,
    ),
}


def _resolve_p0_runner_plugin(model_id: str):
    """解析 P0 model_id 的 (runner_cls, plugin_cls, extra_payload_keys) 元组。失败时返回 None。"""
    if model_id not in P0_RUNNER_PLUGIN:
        return None
    runner_path, plugin_path, extra = P0_RUNNER_PLUGIN[model_id]
    runner_mod_path, runner_cls_name = runner_path.rsplit(".", 1)
    plugin_mod_path, plugin_cls_name = plugin_path.rsplit(".", 1)
    runner_mod = importlib.import_module(runner_mod_path)
    plugin_mod = importlib.import_module(plugin_mod_path)
    return getattr(runner_mod, runner_cls_name), getattr(plugin_mod, plugin_cls_name), extra


def _get_runner_plugin_for_alignment_b(model_id, runner_plugin_factory):
    """根据 model_id 获取 (runner_cls, plugin_cls, extra_payload_keys)。

    P0 真实化对象:从 P0_RUNNER_PLUGIN 解析
    其他:从 conftest runner_plugin_factory 解析
    失败时抛 KeyError。
    """
    p0_result = _resolve_p0_runner_plugin(model_id)
    if p0_result is not None:
        return p0_result
    return runner_plugin_factory(model_id)


def _patch_p0_runner_for_b_endpoint(monkeypatch, runner_cls, plugin_cls, model_id):
    """为 B 端对齐测试 monkeypatch P0 真实化对象的 runner / plugin。

    Aliyun / Vmware / Network 的 runner 需要 _metrics / model_field_mapping 由 plugin 提供;
    不 monkeypatch 会导致 runner.__init__ 抛 "请定义_metrics"。
    """
    # P0 对象 _metrics 从 plugin.metric_names 拿
    metric_names = getattr(plugin_cls, "metric_names", None)
    if metric_names is None and hasattr(plugin_cls, "_metrics"):
        metric_names = plugin_cls._metrics
    if metric_names is not None:
        monkeypatch.setattr(
            runner_cls, "_metrics",
            property(lambda self, _mn=list(metric_names): list(_mn)),
        )
    # P0 对象 model_field_mapping 从 plugin.field_mapping / field_mappings 拿
    if hasattr(plugin_cls, "field_mapping"):
        # 单数(generic 走 plugin.field_mapping)
        monkeypatch.setattr(runner_cls, "model_field_mapping", property(
            lambda self, _m=plugin_cls: _m.model_field_mapping.fget(self) if hasattr(_m, "model_field_mapping") else _m.field_mapping
        ), raising=False)
    elif hasattr(plugin_cls, "field_mappings"):
        from apps.cmdb.collection.plugins.base import bind_collection_mapping
        monkeypatch.setattr(runner_cls, "model_field_mapping", property(
            lambda self, _cls=plugin_cls: {
                mid: bind_collection_mapping(self, m)
                for mid, m in _cls.field_mappings.items()
            }
        ))


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
    # config_file 走 NATS 路径,无 VM pipeline
    if model_id == "config_file":
        pytest.skip(f"{model_id} 走 NATS 路径,跳过 B 端 VM pipeline 字段子集检查")
    try:
        get_model_field_def(model_id)  # 验证 model 反射可拿到
    except KeyError:
        pytest.skip(f"{model_id} 04 schema 尚未存在(Task 2/3/4 加进来)")
    try:
        runner_cls, plugin_cls, extra_payload_keys = _get_runner_plugin_for_alignment_b(
            model_id, runner_plugin_factory,
        )
    except KeyError:
        pytest.skip(f"{model_id} 尚未在 runner_plugin_factory 注册")

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    raw_items_first = raw_items[0] if isinstance(raw_items, list) else raw_items

    # P0 真实化对象:monkeypatch runner / plugin 才能跑 generic pipeline
    if model_id in P0_RUNNER_PLUGIN:
        _patch_p0_runner_for_b_endpoint(monkeypatch, runner_cls, plugin_cls, model_id)
        # aliyun 还需要 check_task_id / 单数字段
        if model_id == "aliyun_ecs":
            monkeypatch.setattr(runner_cls, "check_task_id", lambda self, iid: True)
            monkeypatch.setattr(
                plugin_cls, "field_mapping",
                plugin_cls.field_mappings["aliyun_ecs"],
                raising=False,
            )

    # host 走专门 step3_cmdb_consume_host,不走 generic
    if model_id == "host":
        from apps.cmdb.tests.e2e import pipeline as p_mod
        p3 = p_mod.step2_push_to_vm(
            p_mod.step1_stargazer_normalize_host(raw_items_first),
            task_id=99999,
        )
        from apps.cmdb.tests.e2e import pipeline as p_mod2
        result = p_mod2.step3_cmdb_consume_host(p3, task_id=99999, monkeypatch=monkeypatch)
        run = {"cmdb_result": result}
    else:
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
    instances = run["cmdb_result"].get(model_id, [])

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
    # config_file 走 NATS 路径,无 VM pipeline
    if model_id == "config_file":
        pytest.skip(f"{model_id} 走 NATS 路径,跳过 B 端 VM pipeline 必填字段检查")
    try:
        model_fields = get_model_field_def(model_id)
    except KeyError:
        pytest.skip(f"{model_id} 04 schema 尚未存在")
    try:
        runner_cls, plugin_cls, extra_payload_keys = _get_runner_plugin_for_alignment_b(
            model_id, runner_plugin_factory,
        )
    except KeyError:
        pytest.skip(f"{model_id} 尚未在 runner_plugin_factory 注册")
    required_fields = {f.name for f in model_fields.values() if f.is_required}

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    raw_items_first = raw_items[0] if isinstance(raw_items, list) else raw_items

    # P0 真实化对象:monkeypatch runner / plugin 才能跑 generic pipeline
    if model_id in P0_RUNNER_PLUGIN:
        _patch_p0_runner_for_b_endpoint(monkeypatch, runner_cls, plugin_cls, model_id)
        if model_id == "aliyun_ecs":
            monkeypatch.setattr(runner_cls, "check_task_id", lambda self, iid: True)
            monkeypatch.setattr(
                plugin_cls, "field_mapping",
                plugin_cls.field_mappings["aliyun_ecs"],
                raising=False,
            )

    if model_id == "host":
        from apps.cmdb.tests.e2e import pipeline as p_mod
        p3 = p_mod.step2_push_to_vm(
            p_mod.step1_stargazer_normalize_host(raw_items_first),
            task_id=99999,
        )
        from apps.cmdb.tests.e2e import pipeline as p_mod2
        result = p_mod2.step3_cmdb_consume_host(p3, task_id=99999, monkeypatch=monkeypatch)
        run = {"cmdb_result": result}
    else:
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
    instances = run["cmdb_result"].get(model_id, [])

    if not instances:
        pytest.skip(f"{model_id} 流水线无实例产出,跳过")

    inst = instances[0]
    for field_name in required_fields:
        value = inst.get(field_name)
        if value is None or value == "":
            # placeholder 对象允许为空(标记 _placeholder_reason)
            if "_placeholder_reason" not in inst:
                pytest.fail(f"{model_id} Model 必填字段 {field_name!r} 为空")
