"""Host 采集端到端流水线测试。

模拟链路：
  Shell 脚本输出 → Stargazer 标准化 → push 到 VictoriaMetrics →
  CMDB 从 VM query → HostCollectMetrics 转换 → 准备写入 FalkorDB 的实例

每段之间做：
  1. JSON Schema 契约校验（格式漂移立即报警）
  2. 业务断言（关键字段值是否正确）

参考方案：
  - mock 数据驱动（不依赖真实采集环境）
  - 真实代码跑（CMDB 的 HostCollectMetrics 走真实 format_data + format_metrics）
  - 只把"网络边界"（VM HTTP、SSH 远程脚本）替换成 fixture
"""

import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


# ============================================================================
# 段 1: shell 输出 —— 校验 fixture 本身格式合规（防止 fixture 漂移）
# ============================================================================


def test_step1_shell_output_matches_schema(load_fixture, load_schema):
    shell_output = load_fixture("host/01_shell_output.json")
    schema = load_schema("host/01_shell_output.schema.json")
    jsonschema.validate(shell_output, schema)


# ============================================================================
# 段 2: Stargazer 标准化 —— 跑真实转换逻辑 + 校验输出形态
# ============================================================================


def test_step2_stargazer_normalize_produces_valid_payload(load_fixture, load_schema):
    shell_output = load_fixture("host/01_shell_output.json")

    # 真实跑标准化
    payload = pipeline.step1_stargazer_normalize(shell_output, model_id="host")

    # 契约校验
    schema = load_schema("host/02_stargazer_payload.schema.json")
    jsonschema.validate(payload, schema)

    # 业务断言
    assert payload["success"] is True
    assert len(payload["result"]["host"]) == 1
    assert payload["result"]["host"][0]["hostname"] == "web01.prod.example.com"
    # proc 字段从顶层 host 字典里被剥离，挪到 host_proc_usage
    assert "proc" not in payload["result"]["host"][0]
    assert len(payload["result"]["host_proc_usage"]) == 2
    # 进程都关联回了 host（self_device + ip_addr 双向回填）
    for proc in payload["result"]["host_proc_usage"]:
        assert proc["self_device"] == "web01.prod.example.com"
        assert proc["ip_addr"] == "10.0.0.11"


# ============================================================================
# 段 3: push 到 VictoriaMetrics —— 校验 PromQL vector 响应形态
# ============================================================================


def test_step3_vm_response_matches_schema(load_fixture, load_schema):
    shell_output = load_fixture("host/01_shell_output.json")
    payload = pipeline.step1_stargazer_normalize(shell_output, model_id="host")

    vm_response = pipeline.step2_push_to_vm(payload, task_id=1001)

    schema = load_schema("host/03_vm_metrics.schema.json")
    jsonschema.validate(vm_response, schema)

    # 业务断言：3 条指标 = 1 host_info + 2 host_proc_usage
    metrics = vm_response["data"]["result"]
    assert len(metrics) == 3
    metric_names = sorted({m["metric"]["__name__"] for m in metrics})
    assert metric_names == ["host_info_gauge", "host_proc_usage_info_gauge"]
    # instance_id 一致，对应同一个采集任务
    instance_ids = {m["metric"]["instance_id"] for m in metrics}
    assert instance_ids == {"cmdb_1001"}


# ============================================================================
# 段 4: CMDB 消费 —— 真实跑 HostCollectMetrics + 校验最终实例字典
# ============================================================================


@pytest.mark.django_db
def test_step4_cmdb_consume_produces_valid_instance(load_fixture, load_schema, monkeypatch):
    vm_response = load_fixture("host/03_vm_metrics_response.json")

    result = pipeline.step3_cmdb_consume(vm_response, task_id=1001, monkeypatch=monkeypatch)

    # 至少包含 host 模型实例
    assert "host" in result
    instances = result["host"]
    assert len(instances) >= 1

    inst = instances[0]
    schema = load_schema("host/04_cmdb_instance.schema.json")
    jsonschema.validate(inst, schema)

    # 关键业务断言
    assert inst["inst_name"] == "web01.prod.example.com"
    assert inst["ip_addr"] == "10.0.0.11"
    assert inst["os_type"] == "1"          # Linux → "1"（业务编码）
    assert inst["cpu_arch"] == "x64"       # x86_64 → x64（业务编码）
    assert inst["cpu_core"] == 8
    assert inst["memory"] == 16384
    assert inst["disk"] == 500


# ============================================================================
# 完整链路 e2e —— 一条样本走完 4 段
# ============================================================================


@pytest.mark.django_db
def test_host_pipeline_end_to_end(load_fixture, load_schema, monkeypatch):
    """从 shell 输出一路串到 CMDB 实例。"""
    shell_output = load_fixture("host/01_shell_output.json")
    expected = load_fixture("host/04_expected_cmdb_result.json")

    run = pipeline.run_full_pipeline(shell_output, monkeypatch=monkeypatch, task_id=1001)

    # 每段都过 schema
    schemas = {
        "shell":             load_schema("host/01_shell_output.schema.json"),
        "stargazer_payload": load_schema("host/02_stargazer_payload.schema.json"),
        "vm_response":       load_schema("host/03_vm_metrics.schema.json"),
    }
    jsonschema.validate(run["shell"],             schemas["shell"])
    jsonschema.validate(run["stargazer_payload"], schemas["stargazer_payload"])
    jsonschema.validate(run["vm_response"],       schemas["vm_response"])
    inst_schema = load_schema("host/04_cmdb_instance.schema.json")
    for inst in run["cmdb_result"][expected["model_id"]]:
        jsonschema.validate(inst, inst_schema)

    # 业务结果断言
    instances = run["cmdb_result"][expected["model_id"]]
    assert len(instances) >= expected["instance_count_min"]
    exp = expected["expected_instance"]
    actual = instances[0]
    for field, expected_value in exp.items():
        assert actual.get(field) == expected_value, \
            f"字段 {field} 不匹配：期望 {expected_value}，实际 {actual.get(field)}"


# ============================================================================
# 段间漂移检测 —— 故意改坏一段输入，下游必须立即报错（而不是默默吞掉）
# ============================================================================


def test_drift_detection_bad_shell_output_caught_by_schema(load_schema):
    """模拟 shell 脚本输出字段类型变了（cpu_cores 从 string 变 int），
    schema 校验立即报错——这就是契约的强制力。"""
    bad_shell_output = {
        "hostname": "h1", "os_type": "Linux", "os_name": "x", "os_version": "1",
        "os_bits": "64", "cpu_architecture": "x86_64",
        "cpu_cores": 8,  # ← 协议要求 string，这里传了 int
        "mac_address": "00:00:00:00:00:00",
    }
    schema = load_schema("host/01_shell_output.schema.json")
    with pytest.raises(jsonschema.ValidationError) as exc:
        jsonschema.validate(bad_shell_output, schema)
    assert "cpu_cores" in str(exc.value) or "8 is not of type 'string'" in str(exc.value)


def test_drift_detection_bad_vm_response_caught_by_schema(load_schema):
    """模拟 VM 响应 metric name 不再以 _info_gauge 结尾。"""
    bad_vm = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{
                "metric": {"__name__": "host_random_metric",  # ← 不符合命名规范
                           "instance_id": "cmdb_1"},
                "value": [1, "1"],
            }],
        },
    }
    schema = load_schema("host/03_vm_metrics.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_vm, schema)
