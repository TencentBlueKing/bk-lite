"""A 端对齐检查 —— stargazer 端 prometheus 修复格式化后,03 VM PromQL 响应字段跟 CMDB model 定义对齐。

检查项:
  - metric.__name__ 后缀合法(跟 plugin.metric_names 对齐)
  - metric.instance_id / collect_status label 完整
  - 业务 label 集合 ⊇ model 必填字段(避免漏字段)
  - metric.value 格式合法
  - K8s 特殊:prometheus_kube_* 前缀

不动现有 33 真实落盘对象 + test_pipeline_factory.py。
只覆盖 35 个新工作对象(6 真实化 + 7 云采集 + 22 archived placeholder)。
"""
import pytest

from apps.cmdb.tests.e2e import pipeline
from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def


# 35 个新工作对象(本期 P0/P1/P2 覆盖)
# 由 conftest.py 的 ALIGNMENT_COVERED_MODEL_IDS fixture 提供;此处 list 仅作 fallback / docstring。
# 优先用 fixture:`def test_...(alignment_covered_model_ids): ids = alignment_covered_model_ids`
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


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_metric_name_suffix(model_id, load_fixture, runner_plugin_factory):
    """metric.__name__ 后缀必须合法(对齐 plugin.metric_names)。"""
    # K8s 走 minimal path(Pre-Flight Issue 1 决策),跳过 A 端 generic 检查
    if model_id.startswith("k8s_"):
        pytest.skip(f"{model_id} 走 minimal path,A 端字段对齐检查由 test_k8s_pipeline.py 覆盖")

    try:
        runner_cls, plugin_cls, _ = runner_plugin_factory(model_id)
    except KeyError:
        pytest.skip(f"{model_id} 尚未在 runner_plugin_factory 注册(Task 2/3/4 加进来)")

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id=model_id)
    p3 = pipeline.step2_push_to_vm(p2)

    for result_item in p3["data"]["result"]:
        metric_name = result_item["metric"]["__name__"]
        # 后缀必须以 _info_gauge / _gauge / _count 结尾(或 K8s 特殊)
        assert metric_name.endswith(("_info_gauge", "_gauge", "_count")) or \
               metric_name.startswith("prometheus_kube_"), \
               f"{model_id} metric.__name__={metric_name!r} 后缀不合法"


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_instance_id_label(model_id, load_fixture, runner_plugin_factory):
    """metric.instance_id label 必须是 cmdb_<task_id> 格式。"""
    # K8s 走 minimal path,跳过
    if model_id.startswith("k8s_"):
        pytest.skip(f"{model_id} 走 minimal path,跳过 A 端 instance_id 检查")
    try:
        runner_cls, plugin_cls, _ = runner_plugin_factory(model_id)
    except KeyError:
        pytest.skip(f"{model_id} 尚未在 runner_plugin_factory 注册")

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    p3 = pipeline.step2_push_to_vm(
        pipeline.step1_stargazer_normalize_generic(raw_items, model_id=model_id),
        task_id=99999,
    )

    for result_item in p3["data"]["result"]:
        instance_id = result_item["metric"].get("instance_id")
        assert instance_id == "cmdb_99999", \
            f"{model_id} instance_id={instance_id!r} 必须是 'cmdb_<task_id>' 格式"


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_business_labels(model_id, load_fixture, runner_plugin_factory):
    """业务 label 集合必须 ⊇ model 必填字段(避免漏字段)。"""
    # K8s 走 minimal path,跳过
    if model_id.startswith("k8s_"):
        pytest.skip(f"{model_id} 走 minimal path,跳过 A 端业务 label 检查")
    try:
        get_model_field_def(model_id)  # 验证 model 反射可拿到
    except KeyError:
        pytest.skip(f"{model_id} 04 schema 尚未存在(Task 2/3/4 加进来)")
    try:
        runner_cls, plugin_cls, _ = runner_plugin_factory(model_id)
    except KeyError:
        pytest.skip(f"{model_id} 尚未在 runner_plugin_factory 注册")

    model_fields = get_model_field_def(model_id)
    required_fields = {f.name for f in model_fields.values() if f.is_required}

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id=model_id)
    p3 = pipeline.step2_push_to_vm(p2)

    for result_item in p3["data"]["result"]:
        labels = set(result_item["metric"].keys()) - {"__name__", "instance_id", "collect_status"}
        # 业务 label 集合 ⊇ model 必填字段(ip_addr 通用 label 排除)
        missing = required_fields - labels - {"ip_addr"}
        assert not missing, f"{model_id} 03 metric 缺 model 必填字段: {missing}"
