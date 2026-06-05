"""端到端流水线驱动 —— 通用化版本，所有采集对象共用。

流水线 4 段：
  [1] Stargazer 采集脚本/SDK 原始输出      (fixture)
        ↓ step1_stargazer_normalize
  [2] Stargazer 标准化 payload             (fixture)
        ↓ step2_push_to_vm
  [3] VictoriaMetrics PromQL 响应          (fixture)
        ↓ step3_cmdb_consume_generic
  [4] CMDB 实例字典（落库前）              (fixture)

每个采集对象只需：
  - 4 个边界处的 fixture
  - 4 个 JSON Schema
  - 调用 step3_cmdb_consume_generic 时指定 runner_cls / plugin_cls / model_id

不需要：
  - mock 真实业务函数（runner.format_data + format_metrics 真实跑）
  - mock bind_collection_mapping（自动绑定 plugin 方法到 runner）
"""
from typing import Any, Optional


# ============================================================================
# Step 1: Stargazer 标准化（通用版本：包装单/多对象）
# ============================================================================


def step1_stargazer_normalize_generic(
    raw_items: Any,
    model_id: str = "host",
    proc_items: Optional[list] = None,
) -> dict:
    """通用包装：raw_items → {success: True, result: {model_id: [...], ...optional extras}}。

    raw_items 是 dict 时自动包装为 [dict]；list 时直接使用。
    proc_items 非空时挂到 result["host_proc_usage"]（host 专用扩展点）。
    """
    if isinstance(raw_items, dict):
        items = [dict(raw_items)]
    else:
        items = list(raw_items)

    # 兼容 host：原 dict 里可能含 proc，剥离到 host_proc_usage
    auto_procs = []
    for item in items:
        procs = item.pop("proc", None)
        if isinstance(procs, list):
            host_inst_name = item.get("hostname") or item.get("ip_addr") or ""
            ip_addr = item.get("ip_addr") or ""
            for p in procs:
                if isinstance(p, dict):
                    pp = dict(p)
                    pp["self_device"] = host_inst_name
                    pp["ip_addr"] = ip_addr
                    auto_procs.append(pp)

    result = {model_id: items}
    procs = (proc_items or []) + auto_procs
    if procs:
        result["host_proc_usage"] = procs
    return {"success": True, "result": result}


# ============================================================================
# Step 2: Stargazer push 到 VictoriaMetrics → query 响应
# ============================================================================


def step2_push_to_vm(
    stargazer_payload: dict,
    task_id: int = 1001,
    metric_name_suffix: str = "_info_gauge",
    extra_payload_keys: Optional[dict] = None,
) -> dict:
    """通用 VM PromQL 响应构造：把 stargazer payload 的每个 item 变成一条 metric。

    - 一级 key (model_id) → 对应 metric_name = "{key}{suffix}"
    - 每个 item 的字段 → metric labels
    - extra_payload_keys: {"result_json_field": "real_payload_field"} 注入到 metric.result
      （兼容 middleware/db/protocol：runner 会从 metric.result 解码业务字段）

    输入：stargazer payload
    输出：VictoriaMetrics /api/v1/query 响应
    """
    import json

    result_data = stargazer_payload.get("result", {})
    instance_id = f"cmdb_{task_id}"
    vector_results = []

    for raw_metric_key, items in result_data.items():
        # host_proc_usage 这种"附加流"对应 metric 名带 _info_gauge
        # 其他 model_id（如 nginx/redis/mysql）也是 {model_id}_info_gauge
        metric_name = f"{raw_metric_key}{metric_name_suffix}"

        for item_dict in items:
            base_labels = {
                "__name__": metric_name,
                "instance_id": instance_id,
                "collect_status": "success",
            }
            if extra_payload_keys is not None:
                # 走 middleware/db/protocol 模式：业务字段 JSON 编码到 metric.result
                payload_obj = {k: v for k, v in item_dict.items() if k != "ip_addr"}
                base_labels["result"] = json.dumps(payload_obj)
                base_labels["ip_addr"] = str(item_dict.get("ip_addr", ""))
            else:
                # host 模式：业务字段直接平铺到 labels
                base_labels.update({k: str(v) for k, v in item_dict.items()})
            vector_results.append({"metric": base_labels, "value": [9999999999, "1"]})

    return {
        "status": "success",
        "data": {"resultType": "vector", "result": vector_results},
    }


# ============================================================================
# Step 3: CMDB 消费 —— 通用驱动
# ============================================================================


def step3_cmdb_consume_generic(
    vm_response: dict,
    runner_cls,
    plugin_cls,
    model_id: str,
    task_id: int = 1001,
    instances: Optional[list] = None,
    plugin_type=None,
    monkeypatch=None,
) -> dict:
    """通用 CMDB 消费驱动 —— runner.format_data + format_metrics 真实跑。

    参数：
      vm_response: VM PromQL 响应（fixture）
      runner_cls:  CollectBase 子类，比如 MiddlewareCollectMetrics
      plugin_cls:  采集插件类（含 metric_names + field_mapping），比如 NginxCollectionPlugin
      model_id:    具体对象 id，如 "nginx" / "redis" / "mysql"
      instances:   FakeTask.instances，None 时用默认空 list
      plugin_type: CollectPluginTypes 枚举值，用于 mock get_collection_plugin

    返回：runner.result = {model_id: [instance_dict, ...]}
    """

    # ---- Mock DB / VM 边界 ----
    from types import SimpleNamespace

    fake_task = SimpleNamespace(
        id=task_id,
        params={},
        instances=list(instances or []),
    )
    monkeypatch.setattr(runner_cls, "get_collect_inst", lambda self: fake_task)
    monkeypatch.setattr(runner_cls, "model_id", property(lambda self: model_id))
    monkeypatch.setattr(
        "apps.cmdb.collection.query_vm.Collection.query",
        lambda self, sql, timeout=60: vm_response,
    )

    # ---- Mock plugin 注册表 ----
    # 不同 runner 取 plugin 时调的是不同的 plugin_type；统一拦截 get_collection_plugin
    import apps.cmdb.collection.plugins as plugins_module

    # 找到 runner 模块里 import 的 get_collection_plugin 函数所在模块
    runner_module = runner_cls.__module__
    monkeypatch.setattr(
        f"{runner_module}.get_collection_plugin",
        lambda plug_type, mid: plugin_cls,
    )

    # ---- 构造 runner 并运行 ----
    inst_name = instances[0]["inst_name"] if instances else f"{model_id}_inst_1"
    runner = runner_cls(inst_name=inst_name, inst_id=10001, task_id=task_id)
    runner.run()
    return runner.result


# ============================================================================
# 4 段拼接 —— 通用 e2e
# ============================================================================


def run_full_pipeline_generic(
    raw_items,
    runner_cls,
    plugin_cls,
    model_id: str,
    task_id: int = 1001,
    instances=None,
    proc_items=None,
    extra_payload_keys=None,
    monkeypatch=None,
) -> dict:
    """跑完 4 段，返回每段中间结果。"""
    p1 = raw_items
    p2 = step1_stargazer_normalize_generic(raw_items, model_id=model_id, proc_items=proc_items)
    p3 = step2_push_to_vm(p2, task_id=task_id, extra_payload_keys=extra_payload_keys)
    p4 = step3_cmdb_consume_generic(
        p3, runner_cls=runner_cls, plugin_cls=plugin_cls, model_id=model_id,
        task_id=task_id, instances=instances, monkeypatch=monkeypatch,
    )
    return {"raw": p1, "stargazer_payload": p2, "vm_response": p3, "cmdb_result": p4}


# ============================================================================
# Host 专用流水线（向后兼容已有 test_host_pipeline.py）
# ============================================================================


def step1_stargazer_normalize_host(shell_output: dict, model_id: str = "host") -> dict:
    """Host 专用，直接调通用函数。"""
    return step1_stargazer_normalize_generic(shell_output, model_id=model_id)


def step3_cmdb_consume_host(vm_response: dict, task_id: int = 1001, model_id: str = "host", monkeypatch=None) -> dict:
    """Host 专用 —— 用简化 mapping 而非真实 HostCollectionPlugin。

    设计理由：真实 HostCollectionPlugin 的 set_ip_addr / set_display_inst_name 需要 host
    label 或完整 instance_id 上下文，与本测试 fixture 关注的"格式契约"无关。
    本流水线只验证 host_info_gauge / host_proc_usage_info_gauge 两个 metric 的 labels
    → CMDB 实例字段的映射规则。如需测真实 plugin，请用 step3_cmdb_consume_generic。
    """
    from apps.cmdb.collection.collect_plugin.host import HostCollectMetrics

    fake_task = type("FakeTask", (), {
        "id": task_id,
        "instances": [{"inst_name": "web01.prod.example.com", "ip_addr": "10.0.0.11"}],
    })()

    monkeypatch.setattr(HostCollectMetrics, "get_collect_inst", lambda self: fake_task)
    monkeypatch.setattr(HostCollectMetrics, "model_id", property(lambda self: model_id))
    monkeypatch.setattr(
        "apps.cmdb.collection.query_vm.Collection.query",
        lambda self, sql, timeout=60: vm_response,
    )

    runner = HostCollectMetrics(
        inst_name="web01.prod.example.com", inst_id=10001, task_id=task_id,
    )

    mapping_for_host = {
        "inst_name":   "hostname",
        "ip_addr":     "ip_addr",
        "os_name":     "os_name",
        "os_version":  "os_version",
        "mac_address": lambda data, model_id=None: HostCollectMetrics.format_mac(data.get("mac_address", "")),
        "os_type":     lambda data, model_id=None: runner.set_os_type(data),
        "cpu_arch":    lambda data, model_id=None: runner.set_cpu_arch(data),
        "cpu_core":    (int, "cpu_cores"),
        "memory":      (lambda v: int(float(v)), "mem_total_mb"),
        "disk":        (lambda v: int(float(v)), "disk_total_gb"),
    }
    monkeypatch.setattr(
        HostCollectMetrics, "model_field_mapping",
        property(lambda self: {model_id: mapping_for_host}),
    )
    monkeypatch.setattr(
        HostCollectMetrics, "_metrics",
        property(lambda self: ["host_info_gauge", "host_proc_usage_info_gauge"]),
    )
    runner.collection_metrics_dict = {m: [] for m in runner._metrics}
    runner.run()
    return runner.result


def run_full_pipeline(shell_output: dict, monkeypatch, task_id: int = 1001) -> dict:
    """Host 专用，沿用旧名兼容老测试。"""
    p1 = shell_output
    p2 = step1_stargazer_normalize_host(p1)
    p3 = step2_push_to_vm(p2, task_id=task_id)
    p4 = step3_cmdb_consume_host(p3, task_id=task_id, monkeypatch=monkeypatch)
    return {"shell": p1, "stargazer_payload": p2, "vm_response": p3, "cmdb_result": p4}


# 旧测试兼容（避免改 test_host_pipeline.py 里的 import）
step1_stargazer_normalize = step1_stargazer_normalize_host
step3_cmdb_consume = step3_cmdb_consume_host
