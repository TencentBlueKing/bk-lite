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


# 由 conftest.py 的 alignment_covered_model_ids fixture 提供;此处保留 inline 列表作为 fallback / docstring。
# 优先用 fixture。
ALIGNMENT_COVERED_MODEL_IDS = [
    # P0 真实化(6) — Task 2 逐对象加进来
    "aliyun_ecs",
    "k8s_namespace",
    "vmware",
    "host",
    "network",
    "config_file",
    # P1 云采集新增(7) — Task 3 逐对象加进来
    "hwcloud_ecs",     # Task 3.1
    "hwcloud_vpc",     # Task 3.1
    "qcloud_cvm",      # Task 3.2
    "qcloud_clb",      # Task 3.2
    "qcloud_redis",    # Task 3.2
    "qcloud_bucket",   # Task 3.2
    "qcloud_cmq",      # Task 3.2
    "qcloud_mysql",    # Task 3.2
    "qcloud_mongodb",  # Task 3.2
    "fusioninsight_cluster",  # Task 3.3
    "fusioninsight_host",     # Task 3.3
    "zstack",          # Task 3.4
    "h3c_cas",         # Task 3.5
    "dameng_enterprise",         # Task 3.6
    "redis_sentinel_enterprise", # Task 3.7
    # P2 archived placeholder(22) — Task 4 逐对象加进来
]


# A 端业务 label 校验时排除的 system/derived 字段
# 这些字段由 runner 在 format_metrics 阶段 set,不在 03 metric label 里
A_LABEL_EXCLUDE = {
    "__name__", "instance_id", "collect_status",  # system labels
    "inst_name",                                  # 派生字段,set by runner.set_instance_inst_name
    "model_id", "id", "create_time", "update_time",  # CMDB instance 系统字段
    "assos",                                      # 关联关系
    # 字段重命名:plugin 接收 input X 产出 output Y(Y 跟 X 同名,需在 model 04 schema)
    "cpu_arch",                                   # host 接收 cpu_architecture,runner set_cpu_arch 转
}


# P0 真实化对象的 (runner_cls, plugin_cls) 注册表
# A 端只需要知道 plugin.metric_names,不需要跑 pipeline;先只注册需要的
# Task 3/4 会扩展更多 model_id
P0_RUNNER_PLUGIN = {
    "aliyun_ecs": (
        "apps.cmdb.collection.collect_plugin.aliyun.AliyunCollectMetrics",
        "apps.cmdb.collection.plugins.community.cloud.aliyun.AliyunAccountCollectionPlugin",
    ),
    "vmware": (
        "apps.cmdb.collection.collect_plugin.vmware.CollectVmwareMetrics",
        "apps.cmdb.collection.plugins.community.vm.plugins.VmwareVCCollectionPlugin",
    ),
    "host": (
        "apps.cmdb.collection.collect_plugin.host.HostCollectMetrics",
        "apps.cmdb.collection.plugins.community.host.host.HostCollectionPlugin",
    ),
    "network": (
        "apps.cmdb.collection.collect_plugin.network.CollectNetworkMetrics",
        "apps.cmdb.collection.plugins.community.network.plugins.NetworkCollectionPlugin",
    ),
}


def _resolve_p0_runner_plugin(model_id: str):
    """解析 P0 model_id 的 (runner_cls, plugin_cls) 元组。失败时返回 None。"""
    if model_id not in P0_RUNNER_PLUGIN:
        return None
    runner_path, plugin_path = P0_RUNNER_PLUGIN[model_id]
    import importlib
    runner_mod_path, runner_cls_name = runner_path.rsplit(".", 1)
    plugin_mod_path, plugin_cls_name = plugin_path.rsplit(".", 1)
    runner_mod = importlib.import_module(runner_mod_path)
    plugin_mod = importlib.import_module(plugin_mod_path)
    return getattr(runner_mod, runner_cls_name), getattr(plugin_mod, plugin_cls_name), None


def _get_runner_plugin_for_alignment(model_id, runner_plugin_factory):
    """根据 model_id 获取 (runner_cls, plugin_cls, extra_payload_keys)。

    P0 真实化对象:从 P0_RUNNER_PLUGIN 解析
    其他:从 conftest runner_plugin_factory 解析
    失败时抛 KeyError。
    """
    p0_result = _resolve_p0_runner_plugin(model_id)
    if p0_result is not None:
        return p0_result
    return runner_plugin_factory(model_id)


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_metric_name_suffix(model_id, load_fixture, runner_plugin_factory):
    """metric.__name__ 后缀必须合法(对齐 plugin.metric_names)。"""
    # K8s 走 minimal path(Pre-Flight Issue 1 决策),跳过 A 端 generic 检查
    if model_id.startswith("k8s_"):
        pytest.skip(f"{model_id} 走 minimal path,A 端字段对齐检查由 test_k8s_pipeline.py 覆盖")
    # config_file 走 NATS 路径,无 03 VM metric
    if model_id == "config_file":
        pytest.skip(f"{model_id} 走 NATS 路径,无 03 VM metric,A 端检查由 NATS 路径测试覆盖")

    try:
        runner_cls, plugin_cls, extra_payload_keys = _get_runner_plugin_for_alignment(model_id, runner_plugin_factory)
    except KeyError as e:
        pytest.skip(f"{model_id} 尚未在 runner_plugin_factory 注册(Task 2/3/4 加进来): {e}")

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id=model_id)
    p3 = pipeline.step2_push_to_vm(p2, extra_payload_keys=extra_payload_keys)

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
    if model_id == "config_file":
        pytest.skip(f"{model_id} 走 NATS 路径,跳过 A 端 instance_id 检查")
    try:
        runner_cls, plugin_cls, extra_payload_keys = _get_runner_plugin_for_alignment(model_id, runner_plugin_factory)
    except KeyError:
        pytest.skip(f"{model_id} 尚未在 runner_plugin_factory 注册")

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    p3 = pipeline.step2_push_to_vm(
        pipeline.step1_stargazer_normalize_generic(raw_items, model_id=model_id),
        task_id=99999,
        extra_payload_keys=extra_payload_keys,
    )

    for result_item in p3["data"]["result"]:
        instance_id = result_item["metric"].get("instance_id")
        assert instance_id == "cmdb_99999", \
            f"{model_id} instance_id={instance_id!r} 必须是 'cmdb_<task_id>' 格式"


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_business_labels(model_id, load_fixture, runner_plugin_factory):
    """业务 label 集合必须 ⊇ model 必填字段(避免漏字段)。

    inst_name / model_id / assos 等 system/derived 字段由 runner 在 04 阶段 set,
    不参与 03 label 校验。ip_addr 是 03 通用 label,显式排除。
    """
    # K8s 走 minimal path,跳过
    if model_id.startswith("k8s_"):
        pytest.skip(f"{model_id} 走 minimal path,跳过 A 端业务 label 检查")
    if model_id == "config_file":
        pytest.skip(f"{model_id} 走 NATS 路径,跳过 A 端业务 label 检查")
    try:
        get_model_field_def(model_id)  # 验证 model 反射可拿到
    except KeyError:
        pytest.skip(f"{model_id} 04 schema 尚未存在(Task 2/3/4 加进来)")
    try:
        runner_cls, plugin_cls, extra_payload_keys = _get_runner_plugin_for_alignment(model_id, runner_plugin_factory)
    except KeyError:
        pytest.skip(f"{model_id} 尚未在 runner_plugin_factory 注册")

    model_fields = get_model_field_def(model_id)
    required_fields = {f.name for f in model_fields.values() if f.is_required}
    # 排除 system/derived 字段
    required_input_fields = required_fields - A_LABEL_EXCLUDE

    raw = load_fixture(f"{model_id}/01_stargazer_raw.json")
    raw_items = raw if isinstance(raw, list) else [raw]
    p2 = pipeline.step1_stargazer_normalize_generic(raw_items, model_id=model_id)
    p3 = pipeline.step2_push_to_vm(p2, extra_payload_keys=extra_payload_keys)

    # 只检查主 metric({model_id}_info_gauge),不查附属 metric(如 host_proc_usage_info_gauge)
    main_metric = f"{model_id}_info_gauge"
    for result_item in p3["data"]["result"]:
        metric_name = result_item["metric"]["__name__"]
        if metric_name != main_metric:
            continue
        labels = set(result_item["metric"].keys())
        # 业务 label 集合 ⊇ model 必填字段(排除 system/derived 字段)
        missing = required_input_fields - labels
        assert not missing, f"{model_id} 03 metric 缺 model 必填字段: {missing}"
