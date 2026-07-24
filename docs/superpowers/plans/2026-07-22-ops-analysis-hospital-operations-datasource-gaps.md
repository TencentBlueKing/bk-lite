# 医院运维大屏缺失数据源能力补齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐网络设备 CPU/内存/总流量 Top10 与按 `Alert.source_name` 全量聚合的告警来源分布，并注册为运营分析可选数据源。

**Architecture:** 网络设备排行沿用现有主机 Top10 的“纯归一化服务 + NATS 适配器”结构，在独立服务中完成指标查询、权限范围内实例过滤、新鲜度判断、聚合与排序。告警来源分布直接在告警 NATS 模块复用统一权限 QuerySet，通过数据库聚合生成饼图数据；两项能力最后仅注册到 `source_api.json`，不创建或配置任何大屏。

**Tech Stack:** Python 3.12、Django ORM、VictoriaMetrics/PromQL、项目 NATS RPC 注册器、pytest、JSON 数据源配置。

## Global Constraints

- 本次只补齐数据能力及运营分析数据源注册，不创建、配置或验收具体大屏。
- 不修改 `get_alert_trend_data`，不注册或修改 `get_active_alert_top`。
- 网络设备首期范围固定为 `Switch`、`Router`、`Firewall`、`Loadbalance`。
- 网络流量按每台设备所有接口的当前入方向流量与出方向流量之和排序，单位为 `byteps`。
- 网络指标仅保留不超过实例采集周期 2 倍的新鲜样本；无有效采集周期时使用 300 秒。
- 告警来源按 `Alert.source_name` 全量统计；空值归为“未知来源”，不接收时间范围和 limit 参数。
- 所有查询必须沿用现有监控实例权限或告警权限范围。
- 不新增前端组件，不引入新依赖。
- 不执行 `git add` 或 `git commit`；所有变更由用户自行提交。

---

## File Structure

- Create: `server/apps/monitor/services/network_device_resource_top.py`  
  负责网络设备指标类型校验、VM 查询结果解析、CPU/内存/流量聚合、新鲜度过滤和 TopN 行构造。
- Create: `server/apps/monitor/tests/test_network_device_resource_top.py`  
  覆盖纯服务及 VM 查询契约，不依赖数据库。
- Create: `server/apps/monitor/tests/test_network_device_resource_top_handler.py`  
  覆盖 NATS Handler 的权限过滤、设备类型范围、参数错误和 VM 异常。
- Modify: `server/apps/monitor/nats/monitor.py`  
  注册 `get_network_device_resource_top`，复用 `_get_authorized_monitor_instances` 并过滤首期四类设备。
- Modify: `server/apps/alerts/nats/nats.py`  
  注册 `get_alert_source_distribution`，复用 `_get_authorized_alert_queryset`，不接收时间和 limit 参数。
- Modify: `server/apps/alerts/tests/test_nats_handlers.py`  
  覆盖全量来源聚合、权限、未知来源和数量守恒。
- Modify: `server/apps/operation_analysis/support-files/source_api.json`  
  注册网络设备 Top10 与告警来源分布两个数据源。
- Create: `server/apps/operation_analysis/tests/test_hospital_operations_datasource_registry.py`  
  锁定两条配置的 API 名称、图表类型、默认参数和字段结构，并防止误改两个排除项。

---

### Task 1: 网络设备 Top10 的纯领域服务

**Files:**
- Create: `server/apps/monitor/services/network_device_resource_top.py`
- Create: `server/apps/monitor/tests/test_network_device_resource_top.py`

**Interfaces:**
- Consumes: `VictoriaMetricsAPI.query(query, lookback_delta=...)` 返回的 VictoriaMetrics instant-query 结构；授权实例对象提供 `id`、`name`、`ip`、`interval`、`monitor_object.name`。
- Produces: `validate_network_metric_type(metric_type: str) -> str`；`NetworkMetricSample`；`normalize_network_samples(...)`；`build_network_ranked_rows(...)`；`NetworkDeviceResourceTopService.run(metric_type, authorized_instances, limit=10) -> list[dict]`。

- [ ] **Step 1: 写指标校验、类型范围与行结构的失败测试**

在 `server/apps/monitor/tests/test_network_device_resource_top.py` 写入：

```python
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from apps.monitor.services.network_device_resource_top import (
    NETWORK_DEVICE_TYPES,
    NetworkDeviceResourceTopService,
    NetworkMetricSample,
    build_network_ranked_rows,
    normalize_network_samples,
    validate_network_metric_type,
)

NOW = datetime(2026, 7, 22, 4, 0, tzinfo=timezone.utc)


def sample(instance_id, metric_name, value, *, sampled_at=NOW):
    return NetworkMetricSample(
        instance_id=instance_id,
        metric_name=metric_name,
        value=value,
        sampled_at=sampled_at,
    )


def test_contract_accepts_three_metrics_and_four_device_types():
    assert {validate_network_metric_type(x) for x in ("cpu", "memory", "traffic")} == {
        "cpu", "memory", "traffic"
    }
    assert NETWORK_DEVICE_TYPES == {"Switch", "Router", "Firewall", "Loadbalance"}
    with pytest.raises(ValueError):
        validate_network_metric_type("disk")


def test_rows_are_stable_top_ten_and_keep_common_schema():
    samples = [sample(f"dev-{i:02d}", "device_cpu_usage", 50) for i in range(12)]
    meta = {item.instance_id: {"name": item.instance_id, "device_type": "Switch"} for item in samples}
    rows = build_network_ranked_rows(samples, meta, metric_type="cpu", limit=10)
    assert [row["instance_id"] for row in rows] == [f"dev-{i:02d}" for i in range(10)]
    assert rows[0] == {
        "rank": 1,
        "display_name": "dev-00",
        "value": 50.0,
        "unit": "percent",
        "instance_id": "dev-00",
        "device_type": "Switch",
        "sampled_at": NOW.isoformat(),
    }
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run:

```powershell
cd server
uv run pytest -o addopts= apps/monitor/tests/test_network_device_resource_top.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: apps.monitor.services.network_device_resource_top`.

- [ ] **Step 3: 创建最小领域模型、校验器和排行输出**

在 `server/apps/monitor/services/network_device_resource_top.py` 定义以下稳定接口：

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any

NETWORK_DEVICE_TYPES = {"Switch", "Router", "Firewall", "Loadbalance"}
SUPPORTED_METRIC_TYPES = ("cpu", "memory", "traffic")
DEFAULT_INTERVAL_SECONDS = 300


@dataclass(frozen=True)
class NetworkMetricSample:
    instance_id: str
    metric_name: str
    value: Any
    sampled_at: datetime


def validate_network_metric_type(metric_type: str) -> str:
    normalized = str(metric_type or "").strip().lower()
    if normalized not in SUPPORTED_METRIC_TYPES:
        raise ValueError("metric_type 仅支持 cpu、memory、traffic")
    return normalized


def build_network_ranked_rows(samples, device_meta, *, metric_type, limit=10):
    unit = "byteps" if metric_type == "traffic" else "percent"
    ordered = sorted(
        samples,
        key=lambda item: (-float(item.value), device_meta[item.instance_id]["name"], item.instance_id),
    )[:limit]
    return [
        {
            "rank": rank,
            "display_name": device_meta[item.instance_id]["name"] or item.instance_id,
            "value": round(float(item.value), 2),
            "unit": unit,
            "instance_id": item.instance_id,
            "device_type": device_meta[item.instance_id]["device_type"],
            "sampled_at": item.sampled_at.isoformat(),
        }
        for rank, item in enumerate(ordered, start=1)
    ]
```

- [ ] **Step 4: 写新鲜度、CPU 聚合、内存回退和流量相加的失败测试**

继续追加：

```python
def test_normalization_filters_stale_unknown_and_invalid_percentage():
    raw = [
        sample("fresh", "device_cpu_usage", 80),
        sample("stale", "device_cpu_usage", 99, sampled_at=NOW - timedelta(seconds=601)),
        sample("unknown", "device_cpu_usage", 70),
        sample("bad", "device_cpu_usage", 101),
    ]
    normalized = normalize_network_samples(
        raw,
        {
            "fresh": {"interval": 300},
            "stale": {"interval": 300},
            "bad": {"interval": 300},
        },
        metric_type="cpu",
        now=NOW,
    )
    assert [(x.instance_id, x.value) for x in normalized] == [("fresh", 80.0)]


def test_cpu_averages_current_series_per_device():
    normalized = normalize_network_samples(
        [sample("sw-1", "device_cpu_usage", 40), sample("sw-1", "device_cpu_usage", 60)],
        {"sw-1": {"interval": 300}},
        metric_type="cpu",
        now=NOW,
    )
    assert normalized[0].value == 50.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ([sample("sw-1", "device_memory_usage", 72)], 72.0),
        ([sample("sw-1", "device_memory_used", 80), sample("sw-1", "device_memory_total", 100)], 80.0),
        ([sample("sw-1", "device_memory_free", 20), sample("sw-1", "device_memory_total", 100)], 80.0),
        ([sample("sw-1", "device_memory_used", 80), sample("sw-1", "device_memory_free", 20)], 80.0),
    ],
)
def test_memory_prefers_usage_then_uses_supported_fallbacks(raw, expected):
    normalized = normalize_network_samples(
        raw, {"sw-1": {"interval": 300}}, metric_type="memory", now=NOW
    )
    assert normalized[0].value == expected


def test_traffic_sums_all_current_incoming_and_outgoing_series():
    normalized = normalize_network_samples(
        [
            sample("sw-1", "device_total_incoming_traffic", 100),
            sample("sw-1", "device_total_incoming_traffic", 50),
            sample("sw-1", "device_total_outgoing_traffic", 25),
        ],
        {"sw-1": {"interval": 300}},
        metric_type="traffic",
        now=NOW,
    )
    assert normalized[0].value == 175.0
```

- [ ] **Step 5: 实现归一化规则**

实现时使用以下明确规则：

```python
METRIC_NAMES = {
    "cpu": {"device_cpu_usage"},
    "memory": {
        "device_memory_usage", "device_memory_used",
        "device_memory_free", "device_memory_total",
    },
    "traffic": {
        "device_total_incoming_traffic", "device_total_outgoing_traffic",
    },
}

# 每条样本先验证 instance_id、有限非负数值、授权元数据和 sampled_at；
# sampled_at 超过 2 * max(interval, 300 fallback) 时删除。
# CPU：同一设备所有新鲜 device_cpu_usage 取算术平均。
# Memory：usage 平均值优先；否则依次 used/total、(total-free)/total、used/(used+free)。
# Traffic：同一设备所有新鲜 incoming 与 outgoing 数值相加；任一方向存在即可计算。
# 百分比不在 0..100 或分母 <= 0 时，该设备不输出。
# 聚合后的 sampled_at 取参与计算样本中最早时间，保证整组数据都满足该时间点的新鲜度。
```

`normalize_network_samples` 返回每台设备一条 `NetworkMetricSample`，其 `metric_name` 分别固定为 `cpu`、`memory`、`traffic`。

- [ ] **Step 6: 写服务查询契约的失败测试**

```python
def test_service_queries_only_needed_metrics_and_authorized_devices():
    class FakeVM:
        def __init__(self):
            self.calls = []

        def query(self, query, **kwargs):
            self.calls.append((query, kwargs))
            return {
                "status": "success",
                "data": {"result": [
                    {"metric": {"__name__": "device_cpu_usage", "instance_id": "sw-1"},
                     "value": [NOW.timestamp(), "77"]},
                    {"metric": {"__name__": "device_cpu_usage", "instance_id": "hidden"},
                     "value": [NOW.timestamp(), "99"]},
                ]},
            }

    instance = SimpleNamespace(
        id="sw-1", name="core-sw", ip="10.0.0.1", interval=300,
        monitor_object=SimpleNamespace(name="Switch"),
    )
    vm = FakeVM()
    rows = NetworkDeviceResourceTopService(vm_api=vm, now=NOW).run("cpu", [instance])
    assert [row["instance_id"] for row in rows] == ["sw-1"]
    assert "device_cpu_usage" in vm.calls[0][0]
    assert vm.calls[0][1]["lookback_delta"] == "600s"


def test_service_rejects_failed_vm_response():
    class FailedVM:
        def query(self, query, **kwargs):
            return {"status": "error", "error": "unavailable"}

    instance = SimpleNamespace(
        id="sw-1", name="sw", ip=None, interval=300,
        monitor_object=SimpleNamespace(name="Switch"),
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        NetworkDeviceResourceTopService(vm_api=FailedVM(), now=NOW).run("traffic", [instance])
```

- [ ] **Step 7: 实现 VM 查询、解析和授权实例交集**

`NetworkDeviceResourceTopService` 应：

```python
QUERY_METRICS = {
    "cpu": ("device_cpu_usage",),
    "memory": (
        "device_memory_usage", "device_memory_used",
        "device_memory_free", "device_memory_total",
    ),
    "traffic": (
        "device_total_incoming_traffic", "device_total_outgoing_traffic",
    ),
}

# 查询形式：{__name__=~"metric_a|metric_b"}
# lookback_delta = 授权实例中最大的 2 * 有效 interval，默认 interval=300。
# 解析 metric.__name__、metric.instance_id 和 value=[timestamp, value]。
# normalize 前只保留 authorized instance_id；不接受 VM 返回的额外设备。
# display_name = "name (ip)"（两者都有），否则 name、ip、instance_id 依次回退。
```

- [ ] **Step 8: 运行纯服务测试**

Run:

```powershell
cd server
uv run pytest -o addopts= apps/monitor/tests/test_network_device_resource_top.py -q
```

Expected: all tests PASS.

---

### Task 2: 网络设备 Top10 NATS Handler 与权限边界

**Files:**
- Modify: `server/apps/monitor/nats/monitor.py`
- Create: `server/apps/monitor/tests/test_network_device_resource_top_handler.py`

**Interfaces:**
- Consumes: Task 1 的 `NetworkDeviceResourceTopService`、`NETWORK_DEVICE_TYPES`、`validate_network_metric_type`；现有 `_get_authorized_monitor_instances(user_info)`。
- Produces: 注册后的 `monitor/get_network_device_resource_top(metric_type, limit=10, user_info=...)`。

- [ ] **Step 1: 写 Handler 失败测试**

```python
from types import SimpleNamespace

from apps.monitor.nats import monitor as nm


def instance(instance_id, object_name):
    return SimpleNamespace(
        id=instance_id, name=instance_id, ip=None, interval=300,
        monitor_object=SimpleNamespace(name=object_name),
    )


def test_handler_passes_only_supported_authorized_devices(monkeypatch):
    visible = {
        "sw-1": instance("sw-1", "Switch"),
        "router-1": instance("router-1", "Router"),
        "host-1": instance("host-1", "Host"),
        "wireless-1": instance("wireless-1", "Wireless"),
    }
    monkeypatch.setattr(nm, "_get_authorized_monitor_instances", lambda user_info: (visible, None))

    captured = {}
    class FakeService:
        def __init__(self, *, vm_api):
            pass
        def run(self, metric_type, authorized_instances, limit=10):
            captured["ids"] = [x.id for x in authorized_instances]
            captured["limit"] = limit
            return []

    monkeypatch.setattr(nm, "NetworkDeviceResourceTopService", FakeService)
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", object)
    out = nm.get_network_device_resource_top("traffic", limit=5, user_info={"user": "u", "team": 1})
    assert out == {"result": True, "data": [], "message": ""}
    assert captured == {"ids": ["sw-1", "router-1"], "limit": 5}


def test_handler_rejects_bad_metric_and_limit_before_vm(monkeypatch):
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", lambda: (_ for _ in ()).throw(AssertionError("no VM")))
    assert nm.get_network_device_resource_top("disk", user_info={})["result"] is False
    assert nm.get_network_device_resource_top("cpu", limit=0, user_info={})["result"] is False
    assert nm.get_network_device_resource_top("cpu", limit=101, user_info={})["result"] is False


def test_handler_returns_permission_error_unchanged(monkeypatch):
    error = {"result": False, "data": [], "message": "Insufficient permissions"}
    monkeypatch.setattr(nm, "_get_authorized_monitor_instances", lambda user_info: ({}, error))
    assert nm.get_network_device_resource_top("cpu", user_info={}) == error


def test_handler_converts_vm_failure_to_stable_error(monkeypatch):
    monkeypatch.setattr(
        nm, "_get_authorized_monitor_instances",
        lambda user_info: ({"sw-1": instance("sw-1", "Switch")}, None),
    )
    class FailedService:
        def __init__(self, *, vm_api):
            pass
        def run(self, metric_type, authorized_instances, limit=10):
            raise RuntimeError("VM down")
    monkeypatch.setattr(nm, "NetworkDeviceResourceTopService", FailedService)
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", object)
    out = nm.get_network_device_resource_top("cpu", user_info={"user": "u", "team": 1})
    assert out == {"result": False, "data": [], "message": "网络设备资源指标查询失败"}
```

- [ ] **Step 2: 运行测试并确认 Handler 尚不存在**

Run:

```powershell
cd server
uv run pytest -o addopts= apps/monitor/tests/test_network_device_resource_top_handler.py -q
```

Expected: FAIL with `AttributeError` for `get_network_device_resource_top`.

- [ ] **Step 3: 注册 Handler 并实现参数与设备类型过滤**

在 `server/apps/monitor/nats/monitor.py` 导入 Task 1 接口并增加：

```python
@nats_client.register
def get_network_device_resource_top(metric_type: str, limit: int = 10, *args, **kwargs):
    try:
        metric_type = validate_network_metric_type(metric_type)
        limit = int(limit)
        if not 1 <= limit <= 100:
            raise ValueError("limit 必须在 1 到 100 之间")
    except (TypeError, ValueError) as exc:
        return {"result": False, "data": [], "message": str(exc)}

    authorized_instances, error = _get_authorized_monitor_instances(kwargs.get("user_info") or {})
    if error:
        return error
    devices = [
        item for item in authorized_instances.values()
        if item.monitor_object and item.monitor_object.name in NETWORK_DEVICE_TYPES
    ]
    if not devices:
        return {"result": True, "data": [], "message": ""}

    try:
        rows = NetworkDeviceResourceTopService(vm_api=VictoriaMetricsAPI()).run(
            metric_type, devices, limit=limit
        )
    except Exception:
        logger.exception("network device resource top query failed metric_type=%s", metric_type)
        return {"result": False, "data": [], "message": "网络设备资源指标查询失败"}
    return {"result": True, "data": rows, "message": ""}
```

- [ ] **Step 4: 运行 Handler 与主机 Top10 回归测试**

Run:

```powershell
cd server
uv run pytest -o addopts= `
  apps/monitor/tests/test_network_device_resource_top_handler.py `
  apps/monitor/tests/test_host_resource_top.py `
  apps/monitor/tests/test_host_resource_top_handler.py -q
```

Expected: all tests PASS，现有主机 Top10 行为不变。

---

### Task 3: 按 Alert.source_name 聚合告警来源分布

**Files:**
- Modify: `server/apps/alerts/nats/nats.py`
- Modify: `server/apps/alerts/tests/test_nats_handlers.py`

**Interfaces:**
- Consumes: `_get_authorized_alert_queryset(user_info)`、`_resolve_target_timezone(...)`、`_parse_client_datetime(...)`、`Alert.created_at`、`Alert.source_name`。
- Produces: 注册后的 `alert/get_alert_source_distribution(user_info=...)`，返回 `{"result": True, "data": [{"name": str, "value": int}], "message": ""}`。

- [ ] **Step 1: 写基础聚合、未知来源和时间范围失败测试**

在 `server/apps/alerts/tests/test_nats_handlers.py` 追加：

```python
@pytest.mark.django_db
def test_get_alert_source_distribution_groups_alert_source_name(user_info):
    now = timezone.now()
    rows = [
        ("A1", "Zabbix"), ("A2", "Zabbix"), ("A3", "Prometheus"),
        ("A4", None), ("A5", ""), ("A6", "   "),
    ]
    for alert_id, source_name in rows:
        alert = Alert.objects.create(
            alert_id=alert_id, level="0", title="t", content="c",
            fingerprint=f"fp-{alert_id}", team=[1], source_name=source_name,
        )
        Alert.objects.filter(pk=alert.pk).update(created_at=now)

    result = N.get_alert_source_distribution(user_info=user_info)
    assert result["result"] is True
    assert result["data"] == [
        {"name": "Zabbix", "value": 2},
        {"name": "Prometheus", "value": 1},
        {"name": "未知来源", "value": 3},
    ]


@pytest.mark.django_db
def test_get_alert_source_distribution_reads_all_alerts(user_info):
    now = timezone.now()
    recent = Alert.objects.create(
        alert_id="recent", level="0", title="t", content="c",
        fingerprint="recent", team=[1], source_name="recent-source",
    )
    old = Alert.objects.create(
        alert_id="old", level="0", title="t", content="c",
        fingerprint="old", team=[1], source_name="old-source",
    )
    Alert.objects.filter(pk=recent.pk).update(created_at=now - datetime.timedelta(days=6))
    Alert.objects.filter(pk=old.pk).update(created_at=now - datetime.timedelta(days=8))
    result = N.get_alert_source_distribution(user_info=user_info)
    assert result["data"] == [{"name": "old-source", "value": 1}, {"name": "recent-source", "value": 1}]
```

- [ ] **Step 2: 写 Top10、其他、总量守恒和权限复用失败测试**

```python
@pytest.mark.django_db
def test_get_alert_source_distribution_keeps_unknown_outside_top_and_merges_rest(user_info):
    now = timezone.now()
    expected_total = 0
    for index in range(12):
        count = 20 - index
        expected_total += count
        for item in range(count):
            Alert.objects.create(
                alert_id=f"S{index}-{item}", level="0", title="t", content="c",
                fingerprint=f"fp-{index}-{item}", team=[1], source_name=f"source-{index:02d}",
            )
    Alert.objects.create(
        alert_id="unknown", level="0", title="t", content="c",
        fingerprint="unknown", team=[1], source_name=None,
    )
    expected_total += 1

    result = N.get_alert_source_distribution(limit=10, user_info=user_info)
    assert len([x for x in result["data"] if x["name"].startswith("source-")]) == 10
    assert next(x["value"] for x in result["data"] if x["name"] == "其他") == 19
    assert next(x["value"] for x in result["data"] if x["name"] == "未知来源") == 1
    assert sum(x["value"] for x in result["data"]) == expected_total


def test_get_alert_source_distribution_returns_permission_error(monkeypatch):
    error = {"result": False, "data": [], "message": "Insufficient permissions"}
    monkeypatch.setattr(N, "_get_authorized_alert_queryset", lambda user_info: (None, error))
    assert N.get_alert_source_distribution(user_info={}) == error


@pytest.mark.parametrize("limit", [0, -1, 101, "bad"])
def test_get_alert_source_distribution_rejects_invalid_limit(limit, user_info):
    result = N.get_alert_source_distribution(limit=limit, user_info=user_info)
    assert result["result"] is False
```

- [ ] **Step 3: 运行新增测试并确认 Handler 尚不存在**

Run:

```powershell
cd server
uv run pytest -o addopts= apps/alerts/tests/test_nats_handlers.py -k "alert_source_distribution" -q
```

Expected: FAIL with `AttributeError: module ... has no attribute 'get_alert_source_distribution'`.

- [ ] **Step 4: 实现来源标准化与聚合 Handler**

在 `server/apps/alerts/nats/nats.py` 增加 `Case`、`When`、`Value`、`CharField`、`Trim` 所需导入，并实现：

```python
@nats_client.register
def get_alert_source_distribution(*args, **kwargs) -> Dict[str, Any]:
    user_info = kwargs.pop("user_info", {})
    queryset, error = _get_authorized_alert_queryset(user_info)
    if error:
        return error

    try:
        limit = int(kwargs.pop("limit", 10))
        if not 1 <= limit <= 100:
            raise ValueError("limit 必须在 1 到 100 之间")
    except (TypeError, ValueError) as exc:
        return {"result": False, "data": [], "message": str(exc)}

    target_tz = _resolve_target_timezone(
        (user_info or {}).get("timezone") or kwargs.pop("timezone", None)
    )
    time_range = kwargs.pop("time", None)
    if time_range:
        if not isinstance(time_range, (list, tuple)) or len(time_range) != 2:
            return {"result": False, "data": [], "message": "time 必须包含开始和结束时间"}
        start = _parse_client_datetime(time_range[0], target_tz)
        end = _parse_client_datetime(time_range[1], target_tz)
    else:
        end = timezone.now()
        start = end - datetime.timedelta(days=7)
    if start >= end:
        return {"result": False, "data": [], "message": "开始时间必须早于结束时间"}

    scoped = queryset.filter(created_at__gte=start, created_at__lt=end).annotate(
        trimmed_source=Trim(Coalesce("source_name", Value(""))),
    ).annotate(
        normalized_source=Case(
            When(trimmed_source="", then=Value("未知来源")),
            default="trimmed_source",
            output_field=CharField(),
        )
    )
    grouped = list(
        scoped.values("normalized_source")
        .annotate(value=Count("id"))
        .order_by("-value", "normalized_source")
    )
    unknown = next((x["value"] for x in grouped if x["normalized_source"] == "未知来源"), 0)
    known = [x for x in grouped if x["normalized_source"] != "未知来源"]
    data = [{"name": x["normalized_source"], "value": x["value"]} for x in known[:limit]]
    if len(known) > limit:
        data.append({"name": "其他", "value": sum(x["value"] for x in known[limit:])})
    if unknown:
        data.append({"name": "未知来源", "value": unknown})
    return {"result": True, "data": data, "message": ""}
```

同时从 `django.db.models.functions` 导入 `Coalesce` 与 `Trim`；这一实现不依赖数据库正则能力，`null`、空字符串和纯空白字符串都会稳定进入“未知来源”。

- [ ] **Step 5: 增加非法时间与稳定排序测试**

```python
@pytest.mark.parametrize("time_range", [["2026-01-01"], ["2026-01-02", "2026-01-01"]])
def test_get_alert_source_distribution_rejects_invalid_time(time_range, user_info):
    result = N.get_alert_source_distribution(time=time_range, user_info=user_info)
    assert result["result"] is False


@pytest.mark.django_db
def test_get_alert_source_distribution_breaks_count_ties_by_name(user_info):
    for alert_id, source_name in [("b", "B"), ("a", "A")]:
        Alert.objects.create(
            alert_id=alert_id, level="0", title="t", content="c",
            fingerprint=alert_id, team=[1], source_name=source_name,
        )
    result = N.get_alert_source_distribution(user_info=user_info)
    assert [x["name"] for x in result["data"]] == ["A", "B"]
```

- [ ] **Step 6: 运行告警 NATS 聚焦测试及既有来源统计回归**

Run:

```powershell
cd server
uv run pytest -o addopts= apps/alerts/tests/test_nats_handlers.py `
  -k "alert_source_distribution or alert_source_event_top or alert_source_statistics" -q
```

Expected: all selected tests PASS；现有事件来源 Top 和告警源配置统计行为不变。

---

### Task 4: 运营分析数据源注册契约

**Files:**
- Modify: `server/apps/operation_analysis/support-files/source_api.json`
- Create: `server/apps/operation_analysis/tests/test_hospital_operations_datasource_registry.py`

**Interfaces:**
- Consumes: Task 2 的 `monitor/get_network_device_resource_top` 和 Task 3 的 `alert/get_alert_source_distribution`。
- Produces: 运营分析可导入的两条 JSON 数据源定义。

- [ ] **Step 1: 写配置失败测试**

创建 `server/apps/operation_analysis/tests/test_hospital_operations_datasource_registry.py`：

```python
import json
from pathlib import Path


SOURCE_FILE = Path(__file__).parents[1] / "support-files" / "source_api.json"


def sources_by_api():
    rows = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    return {row["rest_api"]: row for row in rows}


def test_network_device_resource_top_registry_contract():
    source = sources_by_api()["monitor/get_network_device_resource_top"]
    assert source["chart_type"] == ["topN", "table"]
    assert [(x["name"], x["value"]) for x in source["params"]] == [
        ("metric_type", "cpu"), ("limit", 10)
    ]
    metric = source["params"][0]
    assert metric["inputConfig"]["componentSwitch"] is True
    assert [x["value"] for x in metric["inputConfig"]["optionsSource"]["staticItems"]] == [
        "cpu", "memory", "traffic"
    ]
    assert [x["key"] for x in source["field_schema"]] == [
        "rank", "display_name", "value", "unit", "instance_id",
        "device_type", "sampled_at",
    ]


def test_alert_source_distribution_registry_contract():
    source = sources_by_api()["alert/get_alert_source_distribution"]
    assert source["chart_type"] == ["pie"]
    assert source["params"] == []


def test_excluded_alert_datasources_are_unchanged():
    sources = sources_by_api()
    assert sources["alert/get_alert_trend_data"]["chart_type"] == ["single"]
    assert "alert/get_active_alert_top" not in sources
```

- [ ] **Step 2: 运行测试并确认缺少两条配置**

Run:

```powershell
cd server
uv run pytest -o addopts= apps/operation_analysis/tests/test_hospital_operations_datasource_registry.py -q
```

Expected: FAIL with `KeyError: monitor/get_network_device_resource_top` or `KeyError: alert/get_alert_source_distribution`.

- [ ] **Step 3: 在 source_api.json 注册网络设备 Top10**

新增对象，字段必须为：

```json
{
  "name": "网络设备资源使用排行",
  "desc": "查询当前组织权限范围内交换机、路由器、防火墙和负载均衡设备的CPU、内存或当前双向总流量排行",
  "rest_api": "monitor/get_network_device_resource_top",
  "tag": ["monitor"],
  "chart_type": ["topN", "table"],
  "params": [
    {
      "name": "metric_type",
      "type": "string",
      "value": "cpu",
      "alias_name": "指标类型",
      "filterType": "params",
      "required": true,
      "inputConfig": {
        "control": "select",
        "componentSwitch": true,
        "optionsSource": {
          "type": "static",
          "staticItems": [
            {"label": "CPU使用率", "value": "cpu"},
            {"label": "内存使用率", "value": "memory"},
            {"label": "总流量", "value": "traffic"}
          ]
        }
      }
    },
    {"name": "limit", "type": "number", "value": 10, "alias_name": "返回条数", "filterType": "fixed"}
  ],
  "field_schema": [
    {"key": "rank", "title": "排名", "value_type": "number"},
    {"key": "display_name", "title": "网络设备", "value_type": "string"},
    {"key": "value", "title": "指标值", "value_type": "number"},
    {"key": "unit", "title": "单位", "value_type": "string"},
    {"key": "instance_id", "title": "实例ID", "value_type": "string"},
    {"key": "device_type", "title": "设备类型", "value_type": "string"},
    {"key": "sampled_at", "title": "采样时间", "value_type": "datetime"}
  ]
}
```

- [ ] **Step 4: 在 source_api.json 注册告警来源分布**

新增对象：

```json
{
  "name": "告警来源分布",
  "desc": "按告警的source_name统计来源分布，空来源归为未知来源",
  "rest_api": "alert/get_alert_source_distribution",
  "tag": ["alerts"],
  "chart_type": ["pie"],
  "params": []
}
```

- [ ] **Step 5: 验证 JSON 和注册契约**

Run:

```powershell
cd server
uv run python -m json.tool apps/operation_analysis/support-files/source_api.json *> $null
uv run pytest -o addopts= apps/operation_analysis/tests/test_hospital_operations_datasource_registry.py -q
```

Expected: JSON command exit code 0；all registry tests PASS。

---

### Task 5: 全范围回归与交付检查

**Files:**
- Verify only: all files changed in Tasks 1–4

**Interfaces:**
- Consumes: 两个 NATS Handler、两条运营分析注册配置及所有聚焦测试。
- Produces: 可由用户自行提交、可通过运营分析配置使用的缺失数据能力。

- [ ] **Step 1: 运行全部相关后端测试**

Run:

```powershell
cd server
uv run pytest -o addopts= `
  apps/monitor/tests/test_network_device_resource_top.py `
  apps/monitor/tests/test_network_device_resource_top_handler.py `
  apps/monitor/tests/test_host_resource_top.py `
  apps/monitor/tests/test_host_resource_top_handler.py `
  apps/alerts/tests/test_nats_handlers.py `
  apps/operation_analysis/tests/test_hospital_operations_datasource_registry.py -q
```

Expected: all selected tests PASS。若仓库环境仍在 pytest 启动阶段阻塞，分别执行下一步的静态验证并在交付说明中如实记录，不能声称 pytest 已通过。

- [ ] **Step 2: 执行语法、JSON 和差异检查**

Run:

```powershell
uv run python -m py_compile `
  apps/monitor/services/network_device_resource_top.py `
  apps/monitor/nats/monitor.py `
  apps/alerts/nats/nats.py `
  apps/monitor/tests/test_network_device_resource_top.py `
  apps/monitor/tests/test_network_device_resource_top_handler.py `
  apps/alerts/tests/test_nats_handlers.py `
  apps/operation_analysis/tests/test_hospital_operations_datasource_registry.py
uv run python -m json.tool apps/operation_analysis/support-files/source_api.json *> $null
cd ..
git diff --check
```

Expected: all commands exit code 0。

- [ ] **Step 3: 检查严格范围**

Run:

```powershell
git diff --name-only
git diff -- server/apps/alerts/nats/nats.py server/apps/operation_analysis/support-files/source_api.json
```

Expected:

- 生产代码只涉及两个新能力和两条数据源注册。
- `get_alert_trend_data` 函数体没有变化。
- `get_active_alert_top` 函数体和 `source_api.json` 注册状态没有变化。
- 没有大屏页面、组件布局或样式文件变更。
- `server/apps/monitor/management/commands/seed_host_resource_mock.py` 的既有未跟踪内容未被改动。

- [ ] **Step 4: 生成用户自行提交所需的变更摘要**

最终交付说明必须列出：

```text
新增能力：
1. monitor/get_network_device_resource_top（cpu、memory、traffic；topN/table）
2. alert/get_alert_source_distribution（Alert.source_name；pie）

明确未处理：
1. get_alert_trend_data
2. get_active_alert_top
3. 大屏创建、布局和视觉配置

验证结果：逐条列出实际执行的测试命令及 PASS/未执行原因。
Git 状态：未暂存、未提交，由用户自行 commit。
```

不得执行任何暂存或提交命令。
