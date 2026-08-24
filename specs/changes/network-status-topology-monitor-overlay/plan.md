# 网络状态拓扑叠色改为监控中心活跃告警 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 运营分析网络状态拓扑只返回 CMDB 结构；前端用两个内置 NATS 数据源按 `monitor_id` 叠监控中心活跃告警，未知与正常分开，角标弹框看该设备最新列表。

**Architecture:** 场景接口去掉告警中心。新增 CMDB NATS `get_monitor_ids_by_inst_uuids`。改造已有 `query_latest_active_alerts` 返回真实 `count`、`max_level`、`instance_summaries`。保存/导出/分享/报表按组件类型把这两个 `rest_api` 纳入依赖。前端纯函数合并叠色，组件自己解析数据源并编排两次取数。

**Tech Stack:** Django NATS、运营分析数据源、React/X6 网络状态拓扑组件、Vitest/pytest。

产品契约：[`spec.md`](./spec.md)（本变更唯一需求真源）。冲突以 Spec 为准。

**Commit 约定：** 本仓库默认不主动 commit。各 Task 的 Commit 步骤仅在用户明确要求提交时执行。

---

## 0. 文件与常量

写死的两个 `rest_api`（组件、内置 YAML、后端收集器共用同一字符串）：

```python
NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS = (
    "cmdb/get_monitor_ids_by_inst_uuids",
    "monitor/query_latest_active_alerts",
)
```

内置数据源 key（YAML `refs.datasource_keys` 与 `source_api.json` 对齐）：

- `CMDB 实例监控ID映射::cmdb/get_monitor_ids_by_inst_uuids`
- `监控活跃告警::monitor/query_latest_active_alerts`

NATS 函数名（`rest_api` 在 `datasource_view` 里按第一个 `/` 拆成 path）：

- `get_monitor_ids_by_inst_uuids`
- `query_latest_active_alerts`（已有）

取数信封：HTTP `{ data, warnings }`；NATS `{ result, data, message }`。CMDB 映射的 `data` 为 `{ items: [...] }`。监控 `data` 为 `{ count, max_level, items, instance_summaries }`。

| 文件 | 职责 |
|---|---|
| `server/apps/monitor/nats/monitor.py` | 改造活跃告警信封 |
| `server/apps/cmdb/nats/nats.py` | 新增 UUID→monitor_id |
| `server/apps/rpc/cmdb.py` | RPC 转发 |
| `server/apps/operation_analysis/support-files/source_api.json` | 登记映射源、补 `instance_ids` |
| `server/apps/operation_analysis/services/network_status_topology.py` | 只返回结构 |
| `server/apps/operation_analysis/services/network_status_topology_overlay.py` | **新建**：按 rest_api 解析 overlay 数据源 id |
| `web/.../networkStatusTopology/overlayModel.ts` | **新建**：合并规则纯函数 |
| `web/.../networkStatusTopology/index.tsx` | 编排取数、弹框、角标点击 |
| `support-files/builtin_network_topology_screen.yaml` | 引用两个数据源 |

不要：新开监控汇总 NATS、回退告警中心、改 CMDB 拓扑编辑页、修内置 YAML 的 `instId: '220'`、OpenAPI 暴露。

---

### Task 1: 监控 NATS `count` / `max_level` / `instance_summaries`

**Files:**
- Modify: `server/apps/monitor/nats/monitor.py`（`query_latest_active_alerts` 及其上方辅助函数）
- Test: `server/apps/monitor/tests/test_monitor_inherited_data_scope.py`（在现有 latest-alerts 测试后追加）

- [ ] **Step 1: Write the failing tests**

在 `test_nats_latest_alerts_also_inherit_policy_root` 之后追加。复用文件里的 `_policy`、`_patch_nats_alert_permissions`。不要改现有「count == 1」断言——有 1 条告警时新契约仍然成立。

```python
def test_nats_latest_alerts_count_is_untruncated_and_exposes_summaries(mocker):
    from datetime import datetime, timezone

    policy = _policy("latest-summary-policy", [1])
    quiet = MonitorInstance.objects.create(
        id="latest-quiet-instance",
        name="latest-quiet-instance",
        monitor_object=policy.monitor_object,
        is_active=True,
    )
    noisy = MonitorInstance.objects.create(
        id="latest-noisy-instance",
        name="latest-noisy-instance",
        monitor_object=policy.monitor_object,
        is_active=True,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance=quiet, organization=1)
    MonitorInstanceOrganization.objects.create(monitor_instance=noisy, organization=1)
    older = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id=noisy.id,
        status="new",
        level="warning",
        start_event_time=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
    )
    newer_critical = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id=noisy.id,
        status="new",
        level="critical",
        start_event_time=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
    )
    MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id=noisy.id,
        status="closed",
        level="error",
        start_event_time=datetime(2026, 1, 1, 13, tzinfo=timezone.utc),
    )
    user_info = _patch_nats_alert_permissions(mocker)

    response = monitor_nats.query_latest_active_alerts(
        {
            "instance_ids": [quiet.id, noisy.id],
            "limit": 1,
        },
        user_info=user_info,
    )

    assert response["result"] is True
    assert response["data"]["count"] == 2
    assert response["data"]["max_level"] == "critical"
    assert [item["id"] for item in response["data"]["items"]] == [newer_critical.id]
    summaries = {row["instance_id"]: row for row in response["data"]["instance_summaries"]}
    assert summaries[quiet.id] == {"instance_id": quiet.id, "count": 0, "max_level": None}
    assert summaries[noisy.id] == {"instance_id": noisy.id, "count": 2, "max_level": "critical"}


def test_nats_latest_alerts_omits_unauthorized_instance_from_summaries(mocker):
    policy = _policy("latest-partial-policy", [1])
    allowed = MonitorInstance.objects.create(
        id="latest-allowed-instance",
        name="latest-allowed-instance",
        monitor_object=policy.monitor_object,
        is_active=True,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance=allowed, organization=1)
    MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id=allowed.id,
        status="new",
        level="error",
    )
    user_info = _patch_nats_alert_permissions(mocker)

    response = monitor_nats.query_latest_active_alerts(
        {"instance_ids": [allowed.id, "someone-elses-instance"]},
        user_info=user_info,
    )

    assert response["result"] is True
    assert [row["instance_id"] for row in response["data"]["instance_summaries"]] == [allowed.id]
    assert response["data"]["max_level"] == "error"


def test_nats_latest_alerts_all_requested_instances_unauthorized_still_fails(mocker):
    user_info = _patch_nats_alert_permissions(mocker)

    response = monitor_nats.query_latest_active_alerts(
        {"instance_ids": ["no-access-a", "no-access-b"]},
        user_info=user_info,
    )

    assert response["result"] is False
    assert response["message"] == "没有权限访问指定的实例"


def test_nats_latest_alerts_without_instance_ids_does_not_emit_summaries(mocker):
    policy = _policy("latest-global-summary-policy", [1])
    instance = MonitorInstance.objects.create(
        id="latest-global-summary-instance",
        name="latest-global-summary-instance",
        monitor_object=policy.monitor_object,
        is_active=True,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=1)
    MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id=instance.id,
        status="new",
        level="warning",
    )
    user_info = _patch_nats_alert_permissions(mocker)

    response = monitor_nats.query_latest_active_alerts({}, user_info=user_info)

    assert response["result"] is True
    assert response["data"]["count"] == 1
    assert response["data"]["max_level"] == "warning"
    assert response["data"]["instance_summaries"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd server && python -m pytest apps/monitor/tests/test_monitor_inherited_data_scope.py::test_nats_latest_alerts_count_is_untruncated_and_exposes_summaries apps/monitor/tests/test_monitor_inherited_data_scope.py::test_nats_latest_alerts_omits_unauthorized_instance_from_summaries apps/monitor/tests/test_monitor_inherited_data_scope.py::test_nats_latest_alerts_all_requested_instances_unauthorized_still_fails apps/monitor/tests/test_monitor_inherited_data_scope.py::test_nats_latest_alerts_without_instance_ids_does_not_emit_summaries -q
```

Expected: FAIL（`instance_summaries` / `max_level` KeyError，或 `count == 1` 而期望 2）。

- [ ] **Step 3: Write minimal implementation**

在 `query_latest_active_alerts` 上方增加级别比较（只服务本函数，不要新建 NATS）：

```python
_MONITOR_ALERT_LEVEL_RANK = {
    "critical": 3,
    "error": 2,
    "warning": 1,
}


def _monitor_alert_level_rank(level) -> int:
    if level in (None, ""):
        return 0
    return _MONITOR_ALERT_LEVEL_RANK.get(str(level).strip().lower(), 1)


def _max_monitor_alert_level(levels) -> str | None:
    best_level = None
    best_rank = 0
    for level in levels:
        rank = _monitor_alert_level_rank(level)
        if rank > best_rank:
            best_rank = rank
            best_level = str(level).strip().lower()
    return best_level
```

替换 `query_latest_active_alerts` 里构建 `items` 之后的 return。在 `queryset` 过滤完成后：

1. `total_count = queryset.count()`
2. `max_level = _max_monitor_alert_level(queryset.values_list("level", flat=True))`（无行则为 `None`）
3. `items` 仍 `order_by("-start_event_time", "-created_at")[:limit]`，逻辑不变
4. `instance_summaries`：仅当请求合并后的 `instance_ids` 非空。对 `authorized_instance_ids`（已按权限收窄后的请求 ID）逐个汇总。用 `queryset.values("monitor_instance_id", "level")` 在 Python 里按实例聚合 `count` 与 `max_level`。没有告警的授权 ID 也要出现，`count=0`、`max_level=None`。未授权 ID 不出现。请求未带任何 instance id 时 `instance_summaries=[]`
5. 无授权实例的早期成功返回补上 `"max_level": None, "instance_summaries": []`
6. 「指定了 instance_ids 且过滤后一个都没有」的失败分支保持现有 `result=False` / `message="没有权限访问指定的实例"`，不要改成成功全 0

成功信封：

```python
return {
    "result": True,
    "data": {
        "count": total_count,
        "max_level": max_level,
        "items": items,
        "instance_summaries": instance_summaries,
    },
    "message": "",
}
```

`instance_ids` 与 `instance_id` 的合并、limit 校验、`status="new"`、策略权限交叉，全部沿用现有代码。

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd server && python -m pytest apps/monitor/tests/test_monitor_inherited_data_scope.py -q --tb=short
```

Expected: PASS。现有 latest-alerts 权限测试继续绿。

- [ ] **Step 5: Commit**（仅当用户要求提交）

```bash
git add server/apps/monitor/nats/monitor.py server/apps/monitor/tests/test_monitor_inherited_data_scope.py
git commit -m "$(cat <<'EOF'
fix: 监控活跃告警 NATS 返回未截断总数与按实例汇总

拓扑叠色需要真实 count 和全量最高级别，不能再用 len(items)。
EOF
)"
```

---

### Task 2: CMDB NATS 批量 monitor_id + RPC + 内置数据源

**Files:**
- Create: `server/apps/cmdb/tests/test_get_monitor_ids_by_inst_uuids_nats.py`
- Modify: `server/apps/cmdb/nats/nats.py`（在 `get_room_list` 附近新增）
- Modify: `server/apps/rpc/cmdb.py`
- Modify: `server/apps/rpc/tests/test_misc_forwarding.py`
- Modify: `server/apps/operation_analysis/support-files/source_api.json`

- [ ] **Step 1: Write the failing NATS tests**

```python
import pytest

from apps.cmdb.constants.constants import NETWORK_TOPO_NODE_LIMIT
from apps.cmdb.nats import nats as N

USER_INFO = {"user": "alice", "domain": "domain.com", "team": 1, "include_children": False}


def test_get_monitor_ids_rejects_more_than_node_limit():
    result = N.get_monitor_ids_by_inst_uuids(
        inst_uuids=[f"00000000-0000-4000-8000-{i:012d}" for i in range(NETWORK_TOPO_NODE_LIMIT + 1)],
        user_info=USER_INFO,
    )
    assert result["result"] is False
    assert result["data"] == {"items": []}


def test_get_monitor_ids_returns_empty_monitor_id_and_omits_missing(monkeypatch):
    visible = [
        {"inst_uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "model_id": "switch", "monitor_id": "mon-1"},
        {"inst_uuid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "model_id": "router", "monitor_id": ""},
    ]
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {1: {}})
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuids", lambda uuids: visible)
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: True),
    )

    result = N.get_monitor_ids_by_inst_uuids(
        inst_uuids=[
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        ],
        user_info=USER_INFO,
    )

    assert result == {
        "result": True,
        "message": "",
        "data": {
            "items": [
                {
                    "inst_uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    "model_id": "switch",
                    "monitor_id": "mon-1",
                },
                {
                    "inst_uuid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                    "model_id": "router",
                    "monitor_id": "",
                },
            ]
        },
    }


def test_get_monitor_ids_omits_unauthorized_instances(monkeypatch):
    entities = [
        {"inst_uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "model_id": "switch", "monitor_id": "mon-1"},
        {"inst_uuid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "model_id": "host", "monitor_id": "mon-2"},
    ]
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {1: {}})
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuids", lambda uuids: entities)
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: instance["model_id"] == "switch"),
    )

    result = N.get_monitor_ids_by_inst_uuids(
        inst_uuids=[
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        ],
        user_info=USER_INFO,
    )

    assert [item["inst_uuid"] for item in result["data"]["items"]] == [
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    ]


def test_get_monitor_ids_dedupes_and_does_not_pass_duplicates_to_query(monkeypatch):
    seen = {}

    def fake_query(uuids):
        seen["uuids"] = list(uuids)
        return [
            {"inst_uuid": uuids[0], "model_id": "switch", "monitor_id": "mon-1"},
        ]

    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {1: {}})
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuids", fake_query)
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: True),
    )

    uuid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    result = N.get_monitor_ids_by_inst_uuids(inst_uuids=[uuid, uuid], user_info=USER_INFO)

    assert seen["uuids"] == [uuid]
    assert len(result["data"]["items"]) == 1
```

RPC 测试加到 `test_misc_forwarding.py` 的 CMDB 段：

```python
def test_cmdb_get_monitor_ids_by_inst_uuids(cmdb):
    payload = {"inst_uuids": ["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"], "user_info": {"team": 1}}
    cmdb.get_monitor_ids_by_inst_uuids(**payload)
    assert _last(cmdb.client) == ("run", "get_monitor_ids_by_inst_uuids", (), payload)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd server && python -m pytest apps/cmdb/tests/test_get_monitor_ids_by_inst_uuids_nats.py apps/rpc/tests/test_misc_forwarding.py::test_cmdb_get_monitor_ids_by_inst_uuids -q
```

Expected: FAIL（函数未定义）。

- [ ] **Step 3: Implement NATS + RPC + source_api.json**

`nats.py`，风格对齐 `get_room_list` / `get_change_trend`。`query_entity_by_uuids` 会因输入重复抛错，必须先去重。不收 `model_id`。跨模型。`user` 用 `_normalize_permission_user(user_info.get("user"), domain=user_info.get("domain"))`。

```python
@nats_client.register
def get_monitor_ids_by_inst_uuids(inst_uuids=None, user_info=None, **kwargs):
    from apps.cmdb.constants.constants import NETWORK_TOPO_NODE_LIMIT
    from apps.cmdb.services.instance_identity import normalize_inst_uuid

    raw = inst_uuids if inst_uuids is not None else kwargs.get("inst_uuids")
    if raw in (None, ""):
        raw = []
    if not isinstance(raw, list):
        return {"result": False, "data": {"items": []}, "message": "inst_uuids 必须是列表"}

    unique = []
    seen = set()
    for value in raw:
        if value in (None, ""):
            continue
        normalized = normalize_inst_uuid(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)

    if len(unique) > NETWORK_TOPO_NODE_LIMIT:
        return {
            "result": False,
            "data": {"items": []},
            "message": f"inst_uuids 不能超过 {NETWORK_TOPO_NODE_LIMIT}",
        }

    if not unique:
        return {"result": True, "data": {"items": []}, "message": ""}

    permission_map = _build_nats_permission_map(user_info) or {}
    user = _normalize_permission_user((user_info or {}).get("user"), domain=(user_info or {}).get("domain"))
    entities = InstanceManage.query_entity_by_uuids(unique)
    items = []
    for entity in entities:
        if not InstanceManage._has_topology_view_permission(entity, permission_map, user=user):
            continue
        monitor_id = entity.get("monitor_id")
        items.append(
            {
                "inst_uuid": entity.get("inst_uuid"),
                "model_id": entity.get("model_id"),
                "monitor_id": "" if monitor_id in (None, "") else str(monitor_id),
            }
        )
    return {"result": True, "data": {"items": items}, "message": ""}
```

`rpc/cmdb.py` 在 `model_inst_count` 附近：

```python
def get_monitor_ids_by_inst_uuids(self, **kwargs):
    return self.client.run("get_monitor_ids_by_inst_uuids", **kwargs)
```

不要走 `_run_params_handler`。运营分析 `GetNatsData` 把 `inst_uuids` / `user_info` 当顶层 kwargs。

`source_api.json`：

1. 在「监控活跃告警」的 `params` 里，`instance_id` 后面加：

```json
{
    "name": "instance_ids",
    "type": "string",
    "value": "",
    "alias_name": "实例ID列表",
    "filterType": "params"
}
```

2. 新增一条（`chart_type` 空，对齐机房列表选项源）：

```json
{
    "key": "CMDB 实例监控ID映射::cmdb/get_monitor_ids_by_inst_uuids",
    "name": "CMDB 实例监控ID映射",
    "desc": "按实例 UUID 批量返回关联的监控实例 ID，供网络状态拓扑叠色使用，本身不直接出图",
    "rest_api": "cmdb/get_monitor_ids_by_inst_uuids",
    "tag": ["cmdb"],
    "chart_type": [],
    "params": [
        {
            "name": "inst_uuids",
            "type": "string",
            "value": "",
            "alias_name": "实例UUID列表",
            "filterType": "params"
        }
    ],
    "field_schema": [
        {"key": "inst_uuid", "title": "实例UUID", "value_type": "string", "description": "CMDB 实例 UUID"},
        {"key": "model_id", "title": "模型ID", "value_type": "string", "description": "CMDB 模型 ID"},
        {"key": "monitor_id", "title": "监控实例ID", "value_type": "string", "description": "未关联时为空字符串"}
    ]
}
```

不要加 `@openapi_expose`。

- [ ] **Step 4: Run tests**

```bash
cd server && python -m pytest apps/cmdb/tests/test_get_monitor_ids_by_inst_uuids_nats.py apps/rpc/tests/test_misc_forwarding.py::test_cmdb_get_monitor_ids_by_inst_uuids apps/operation_analysis/tests/test_init_builtin_canvases.py::test_all_builtin_canvas_datasource_references_resolve_after_merge -q
```

Expected: NATS/RPC PASS。内置引用测试此时仍 PASS（YAML 还没改 refs）。`source_api.json` 必须仍是合法 JSON。

- [ ] **Step 5: Commit**（仅当用户要求提交）

---

### Task 3: 场景接口只返回结构

**Files:**
- Modify: `server/apps/operation_analysis/services/network_status_topology.py`
- Modify: `server/apps/operation_analysis/tests/test_network_status_topology.py`

- [ ] **Step 1: Rewrite the failing/updated tests first**

删掉 `test_map_alert_level_to_node_status`。把 `test_build_merges_topology_structure_with_alert_status` 改成结构断言。当前测试还在用 `inst_id=`，与 `build(..., inst_uuid=...)` 不一致，一并改掉。

```python
def test_build_returns_topology_structure_without_alert_fields(monkeypatch, authenticated_user):
    topology = {
        "center": {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "model_id": "switch", "name": "core-switch", "hop": 0},
        "nodes": [
            {"id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "model_id": "switch", "name": "core-switch", "hop": 0},
            {"id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "model_id": "host", "name": "biz-host", "hop": 1},
        ],
        "links": [{"relationship_id": "rel-1", "source_device": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "target_device": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}],
        "truncated": False,
    }
    monkeypatch.setattr(
        NetworkStatusTopologyService,
        "_get_cmdb_topology",
        staticmethod(lambda request, model_id, inst_uuid, depth: topology),
    )

    result = NetworkStatusTopologyService.build(
        request=SimpleNamespace(user=authenticated_user),
        model_id="switch",
        inst_uuid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        depth=2,
    )

    assert result["center_id"] == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert result["center_model_id"] == "switch"
    assert result["links"] == topology["links"]
    assert result["truncated"] is False
    for node in result["nodes"]:
        assert "status" not in node
        assert "alert_count" not in node
        assert "pulse" not in node
        assert "severity" not in node
        assert "color" not in node
```

文件里其它引用 `_get_active_alert_summary` / `map_alert_level_to_node_status` / `inst_id=` 的 build 测试同样改成只测结构。若有「告警中心权限/状态合并」测试，删除或改成「不再查询告警」。

- [ ] **Step 2: Run to verify fail**

```bash
cd server && python -m pytest apps/operation_analysis/tests/test_network_status_topology.py -q
```

Expected: FAIL（节点仍带 `alert_count` / `status`）。

- [ ] **Step 3: Strip alert merge**

`NetworkStatusTopologyService.build` 只调用 `_get_cmdb_topology`，原样返回 nodes/links。删除 `_get_active_alert_summary`、`map_alert_level_to_node_status`、`ALERT_LEVEL_PRIORITY`。不要 import 告警中心模型。

```python
@classmethod
def build(cls, request, model_id: str, inst_uuid: str, depth: int) -> dict[str, Any]:
    topology = cls._get_cmdb_topology(request, model_id, inst_uuid, depth)
    center = topology.get("center") or {}
    return {
        "center_id": str(center.get("id") or inst_uuid),
        "center_model_id": str(center.get("model_id") or model_id),
        "nodes": topology.get("nodes", []),
        "links": topology.get("links", []),
        "truncated": bool(topology.get("truncated", False)),
        "node_limit": NETWORK_TOPO_NODE_LIMIT,
    }
```

- [ ] **Step 4: Run tests**

```bash
cd server && python -m pytest apps/operation_analysis/tests/test_network_status_topology.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**（仅当用户要求提交）

---

### Task 4: 按组件类型收集两个 overlay 数据源

这是分享/导出/报表能取数的接缝。对齐 `named_option_datasources._resolve_unique_rest_api_ids`：全表恰好一条，或恰好一条内置。

**Files:**
- Create: `server/apps/operation_analysis/services/network_status_topology_overlay.py`
- Create: `server/apps/operation_analysis/tests/test_network_status_topology_overlay.py`
- Modify: `server/apps/operation_analysis/services/import_export/export_service.py`
- Modify: `server/apps/operation_analysis/services/canvas_report/{dashboard,screen,report}.py`
- Modify: `server/apps/operation_analysis/views/share_view.py`（`_canvas_data_source_ids`）
- Modify: `server/apps/operation_analysis/services/share_service.py`（`allowed_share_query_keys`）
- Modify: `server/apps/operation_analysis/tests/test_export_and_viewsets.py`
- Modify: `server/apps/operation_analysis/tests/test_canvas_report_adapter.py`（或 screen adapter 测试）
- Modify: `server/apps/operation_analysis/tests/test_share_service.py`
- Modify: `server/apps/operation_analysis/tests/test_dashboard_report_render_token.py`（允许 overlay 数据源取数，仍拒绝无关 id）

- [ ] **Step 1: Write collector tests**

```python
import pytest

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.services.network_status_topology_overlay import (
    NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS,
    collect_network_status_topology_overlay_datasource_ids,
    expand_widget_manifest_with_topology_overlay,
    view_sets_has_network_status_topology,
)

pytestmark = pytest.mark.django_db

CMDB_API, MONITOR_API = NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS


def _ds(ds_id, rest_api, *, builtin=True):
    return DataSourceAPIModel.objects.create(
        id=ds_id,
        name=rest_api,
        rest_api=rest_api,
        is_build_in=builtin,
        created_by="s",
        updated_by="s",
    )


def test_collect_overlay_ids_prefers_unique_builtin():
    _ds(31, CMDB_API)
    _ds(32, MONITOR_API)
    _ds(99, "other/query")
    assert collect_network_status_topology_overlay_datasource_ids() == {31, 32}


def test_collect_overlay_ids_skips_ambiguous_unless_unique_builtin():
    _ds(31, CMDB_API, builtin=False)
    _ds(41, CMDB_API, builtin=False)
    _ds(32, MONITOR_API)
    assert collect_network_status_topology_overlay_datasource_ids() == {32}

    DataSourceAPIModel.objects.filter(id=41).update(is_build_in=True)
    assert collect_network_status_topology_overlay_datasource_ids() == {32, 41}


def test_view_sets_detects_nested_dashboard_and_screen():
    dashboard = [{"itemType": "group", "subGridOpts": {"children": [{"valueConfig": {"chartType": "networkStatusTopology"}}]}}]
    screen = {"items": [{"valueConfig": {"chartType": "networkStatusTopology"}}]}
    assert view_sets_has_network_status_topology(dashboard) is True
    assert view_sets_has_network_status_topology(screen) is True
    assert view_sets_has_network_status_topology([{"valueConfig": {"chartType": "line"}}]) is False


def test_expand_manifest_emits_two_rows_per_topology_widget():
    _ds(31, CMDB_API)
    _ds(32, MONITOR_API)
    manifest = [
        {"widget_id": "topo-1", "widget_type": "networkStatusTopology", "datasource_id": None},
        {"widget_id": "line-1", "widget_type": "line", "datasource_id": 17},
    ]
    expanded = expand_widget_manifest_with_topology_overlay(manifest)
    topo_rows = [row for row in expanded if row["widget_id"] == "topo-1"]
    assert {(row["datasource_id"]) for row in topo_rows} == {31, 32}
    assert all(row["widget_type"] == "networkStatusTopology" for row in topo_rows)
    assert ["line-1" for row in expanded if row["widget_id"] == "line-1"]
```

导出测试追加：含 `networkStatusTopology` 且库中有两个 overlay 源时，`extract_canvas_dependencies` 包含它们，即使没有 `valueConfig.dataSource`。

分享：`allowed_share_query_keys` 在画布有该组件且 `data_source_id` 是 overlay id 时，允许 `inst_uuids`、`instance_ids`、`instance_id`、`limit`。没有该组件的画布即使请求 overlay id 也不因本逻辑放行（仍靠 `_canvas_data_source_ids` 拒绝）。

Render token：给含 `networkStatusTopology` 的冻结 `widget_manifest`（两行 overlay id）建 execution，断言 `POST get_source_data/{overlay_id}/` 通过、无关 id 仍 403。沿用 `test_dashboard_report_render_token.py` 现有 fixture 风格。

Dashboard adapter：`view_sets` 里放一个无 `dataSource` 的 `networkStatusTopology`，`build_manifest` 应含两行 overlay id。在 `expand_widget_manifest_with_named_option_datasources(...)` **之外**再包一层 overlay expand，顺序：先 topology overlay，再 named option（named option 只看已有 datasource_id）。

- [ ] **Step 2: Run to verify fail**

```bash
cd server && python -m pytest apps/operation_analysis/tests/test_network_status_topology_overlay.py -q
```

Expected: FAIL（模块不存在）。

- [ ] **Step 3: Implement collector and wire it**

`network_status_topology_overlay.py`：

```python
from apps.operation_analysis.services.named_option_datasources import _resolve_unique_rest_api_ids

NETWORK_STATUS_TOPOLOGY_CHART_TYPE = "networkStatusTopology"
NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS = (
    "cmdb/get_monitor_ids_by_inst_uuids",
    "monitor/query_latest_active_alerts",
)
NETWORK_STATUS_TOPOLOGY_OVERLAY_QUERY_KEYS = frozenset(
    {"inst_uuids", "instance_ids", "instance_id", "limit"}
)


def collect_network_status_topology_overlay_datasource_ids() -> set[int]:
    resolved = _resolve_unique_rest_api_ids(set(NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS))
    return {ds_id for ds_id in resolved.values() if ds_id is not None}


def view_sets_has_network_status_topology(value) -> bool:
    if isinstance(value, list):
        return any(view_sets_has_network_status_topology(item) for item in value)
    if not isinstance(value, dict):
        return False
    value_config = value.get("valueConfig") if isinstance(value.get("valueConfig"), dict) else {}
    chart_type = value_config.get("chartType") or value.get("chartType")
    if chart_type == NETWORK_STATUS_TOPOLOGY_CHART_TYPE:
        return True
    if value_config.get("sceneWidgetType") == NETWORK_STATUS_TOPOLOGY_CHART_TYPE:
        return True
    return any(view_sets_has_network_status_topology(child) for child in value.values())


def overlay_datasource_ids_for_view_sets(view_sets) -> set[int]:
    if not view_sets_has_network_status_topology(view_sets):
        return set()
    return collect_network_status_topology_overlay_datasource_ids()


def expand_widget_manifest_with_topology_overlay(manifest: list[dict] | None) -> list[dict]:
    if not manifest:
        return list(manifest or [])
    overlay_ids = collect_network_status_topology_overlay_datasource_ids()
    expanded: list[dict] = []
    seen = set()
    for item in manifest:
        if not isinstance(item, dict):
            continue
        widget_type = item.get("widget_type")
        if widget_type != NETWORK_STATUS_TOPOLOGY_CHART_TYPE:
            expanded.append(item)
            continue
        widget_id = item.get("widget_id")
        for ds_id in overlay_ids:
            key = (widget_id, ds_id)
            if key in seen:
                continue
            seen.add(key)
            expanded.append(
                {
                    "widget_id": widget_id,
                    "widget_type": widget_type,
                    "datasource_id": ds_id,
                }
            )
    return expanded
```

`_resolve_unique_rest_api_ids` 若不想用私有函数，把解析逻辑复制一份到本模块（不要改 named_option 语义）。优先复用：它已实现「唯一 / 唯一内置」。

接线：

1. `ExportService.extract_canvas_dependencies`：在 `collect_datasource_ids(normalized)` 之后 `datasource_ids |= overlay_datasource_ids_for_view_sets(normalized)`
2. `build_*_widget_manifest` 的 adapter `build_manifest` / `build_render_snapshot_fields`：

```python
return expand_widget_manifest_with_named_option_datasources(
    expand_widget_manifest_with_topology_overlay(build_dashboard_widget_manifest(...))
)
```

dashboard / screen / report 三处都改。`render_scope_service.collect_allowed_datasource_ids` 读 manifest，不必再特判——manifest 两行就够。

3. `share_view._canvas_data_source_ids`：递归结束后（或函数末尾）若 `view_sets_has_network_status_topology(value)` 则 `found |= collect_network_status_topology_overlay_datasource_ids()`。注意该函数递归子树；**只在顶层调用一次 overlay 收集**，不要每个 dict 都查库。改成：

```python
def _canvas_data_source_ids(value):
    found = _walk_data_source_ids(value)
    if view_sets_has_network_status_topology(value):
        found.update(collect_network_status_topology_overlay_datasource_ids())
    return found
```

把原来的递归抽到 `_walk_data_source_ids`。

4. `allowed_share_query_keys`：若 `data_source_id in overlay_datasource_ids_for_view_sets(dashboard.view_sets)`，则 `allowed |= NETWORK_STATUS_TOPOLOGY_OVERLAY_QUERY_KEYS`。不要依赖 `_matching_value_configs`（拓扑组件没有 `dataSource` 字段）。

- [ ] **Step 4: Run tests**

```bash
cd server && python -m pytest apps/operation_analysis/tests/test_network_status_topology_overlay.py apps/operation_analysis/tests/test_export_and_viewsets.py::test_extract_canvas_dependencies_collects_datasource_ids apps/operation_analysis/tests/test_canvas_report_adapter.py apps/operation_analysis/tests/test_share_service.py -q --tb=short
```

Expected: PASS。旧导出「只有显式 dataSource」用例仍然只收集显式 id（那些 fixture 没有 topology 组件）。

- [ ] **Step 5: Commit**（仅当用户要求提交）

---

### Task 5: 前端叠色纯函数与类型

**Files:**
- Create: `web/src/app/ops-analysis/components/widgets/networkStatusTopology/overlayModel.ts`
- Create: `web/src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/overlayModel.test.ts`
- Modify: `web/src/app/ops-analysis/types/sceneWidget.ts`
- Modify: `web/src/app/ops-analysis/components/widgets/networkStatusTopology/statusTopologyGraph.ts`
- Modify: `web/src/app/ops-analysis/components/widgets/networkStatusTopology/graphModel.ts`（删除 `buildAlertListUrl`）

- [ ] **Step 1: Write overlayModel tests**

```typescript
import { describe, expect, it } from 'vitest';
import {
  applyMonitorOverlay,
  canOpenAlertModal,
  mapMonitorLevelToNodeStatus,
} from '../overlayModel';

const baseNode = {
  id: 'dev-1',
  model_id: 'switch',
  name: 'SW-1',
  hop: 0,
};

describe('mapMonitorLevelToNodeStatus', () => {
  it('maps critical / error / warning and unknown non-empty as warning', () => {
    expect(mapMonitorLevelToNodeStatus('critical', 1)).toMatchObject({
      status: 'critical',
      pulse: true,
      color: 'red',
    });
    expect(mapMonitorLevelToNodeStatus('ERROR', 1)).toMatchObject({
      status: 'error',
      pulse: false,
      color: 'red',
    });
    expect(mapMonitorLevelToNodeStatus('info', 2)).toMatchObject({
      status: 'warning',
      pulse: false,
      color: 'yellow',
    });
  });
});

describe('applyMonitorOverlay', () => {
  it('marks missing mapping, empty monitor_id, and omitted summary as unknown', () => {
    const nodes = applyMonitorOverlay({
      nodes: [
        { ...baseNode, id: 'missing' },
        { ...baseNode, id: 'empty' },
        { ...baseNode, id: 'omitted' },
      ],
      mappings: [
        { inst_uuid: 'empty', model_id: 'switch', monitor_id: '' },
        { inst_uuid: 'omitted', model_id: 'switch', monitor_id: 'mon-9' },
      ],
      summaries: [],
    });
    expect(nodes.every((node) => node.status === 'unknown')).toBe(true);
    expect(nodes.every((node) => node.alert_count === 0)).toBe(true);
  });

  it('marks mapped zero as normal and critical summary as pulsing red', () => {
    const [quiet, noisy] = applyMonitorOverlay({
      nodes: [
        { ...baseNode, id: 'quiet' },
        { ...baseNode, id: 'noisy' },
      ],
      mappings: [
        { inst_uuid: 'quiet', model_id: 'switch', monitor_id: 'mon-q' },
        { inst_uuid: 'noisy', model_id: 'switch', monitor_id: 'mon-n' },
      ],
      summaries: [
        { instance_id: 'mon-q', count: 0, max_level: null },
        { instance_id: 'mon-n', count: 12, max_level: 'critical' },
      ],
    });
    expect(quiet).toMatchObject({ status: 'normal', alert_count: 0, pulse: false, color: 'green' });
    expect(noisy).toMatchObject({ status: 'critical', alert_count: 12, pulse: true, color: 'red' });
    expect(canOpenAlertModal(quiet)).toBe(false);
    expect(canOpenAlertModal(noisy)).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify fail**

```bash
cd web && pnpm exec vitest run src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/overlayModel.test.ts
```

Expected: FAIL（模块不存在）。

- [ ] **Step 3: Implement**

`sceneWidget.ts`：`NetworkNodeStatus` 增加 `'unknown'`；`color` 增加 `'gray'`。场景接口节点上 `status` / `alert_count` 改为可选（结构响应不再带）。叠色后的节点类型仍要有这些字段——组件内部用 overlay 输出类型，或在 merge 后断言完整。

`overlayModel.ts` 契约：

```typescript
export const NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS = [
  'cmdb/get_monitor_ids_by_inst_uuids',
  'monitor/query_latest_active_alerts',
] as const;

export function pickOverlayDataSourceIds(
  sources: Array<{ id: number; rest_api?: string; is_build_in?: boolean }>,
): { cmdbId?: number; monitorId?: number } {
  // 每个 rest_api：恰好一条则用它；多条则恰好一条 is_build_in 时用内置；否则缺省（叠色失败）
}

export function mapMonitorLevelToNodeStatus(level: string | null | undefined, count: number)
export function applyMonitorOverlay(input: {
  nodes: Array<{ id: string; model_id: string; name: string; hop: number; [key: string]: unknown }>;
  mappings: Array<{ inst_uuid: string; model_id?: string; monitor_id: string }>;
  summaries: Array<{ instance_id: string; count: number; max_level: string | null }>;
}): NetworkStatusTopologyNode[]
export function canOpenAlertModal(node: Pick<NetworkStatusTopologyNode, 'status' | 'alert_count'>): boolean
```

合并规则严格按 Spec：映射没有该 `id` / `monitor_id` 空 / summaries 没有该监控 ID → `unknown`（灰、无角标）。有 ID 且 count=0 → `normal`。`critical` 红+脉冲；`error` 红不脉冲；`warning` 或其它非空 → 黄。`canOpenAlertModal`：`status !== 'unknown' && alert_count > 0`。

节点上保留 `monitor_id`（内部字段，弹框用），不要画到浮层。

`statusTopologyGraph.ts`：`STATUS_TOPOLOGY_VISUAL.status.unknown` 用本文件现有 hex 写法补灰（例如 `'#9aa4b2'`），不要借此把整份调色板迁 token。`STATUS_COLOR_MAP.unknown` 指向它。角标 `alertBadge` / `alertBadgeText`：当 `alertCount > 0` 用 `PE_ALL` + `cursor: pointer`，否则保持 `PE_NONE`。新增 `isStatusTopologyBadgeTarget(event)`，用 `composedPath` 认 `circle`/`text` 且 selector 可通过 class 或 tag+位置判断——更稳：给 markup 加 `class: 'status-topo-alert-badge'`，path 上找该 class。

导出 `isStatusTopologyBadgeTarget`。删除 `graphModel.ts` 的 `buildAlertListUrl` 及告警中心 status 常量。其它文件若 import 它，改为走弹框。

- [ ] **Step 4: Run tests**

```bash
cd web && pnpm exec vitest run src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/overlayModel.test.ts
```

Expected: PASS。

- [ ] **Step 5: Commit**（仅当用户要求提交）

---

### Task 6: 组件编排叠色、角标弹框、右键

**Files:**
- Modify: `web/src/app/ops-analysis/components/widgets/networkStatusTopology/index.tsx`
- Modify: `web/src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/networkStatusTopology.fetch.test.tsx`
- Modify: `web/src/app/ops-analysis/locales/zh.json`、`en.json`
- Modify: `web/src/app/cmdb/components/networkTopology` 的 canvas 仅当需要让 `onNodeClick` 透传 `event`（可选第二参，现有调用方不改行为）

- [ ] **Step 1: Extend fetch tests**

现有测试 mock 了 `useNetworkStatusTopologyApi` 和 `post`。再 mock：

```typescript
const overlayState = vi.hoisted(() => ({
  getSourceDataByApiId: vi.fn(),
  dataSources: [
    { id: 31, rest_api: 'cmdb/get_monitor_ids_by_inst_uuids' },
    { id: 32, rest_api: 'monitor/query_latest_active_alerts' },
  ],
}));
```

`useOpsAnalysis` / `useDataSourceApi` 按组件实际 import 路径 mock。覆盖：

1. 拓扑成功后调用映射 NATS（`inst_uuids` = 节点 id 列表）和监控 NATS（非空 `monitor_id`，`limit: 1`）
2. 无 monitor_id 的节点浮层文案走 `dashboard.networkTopoUnmonitored`，不要显示 `0`
3. `count=0` 显示 0，且不可开弹框
4. 映射或监控失败：结构仍在（canvas 有节点 id），出现可重试叠色错误 `dashboard.networkTopoStatusLoadFailed`，节点按 unknown 处理
5. 点角标 / 右键查看告警：再打一次监控查询，`instance_ids: [该 monitor_id]`，`limit: 10`；铺图那次 `limit: 1` 的 items 不得被拿来填表
6. 分享态：CMDB 详情仍 disabled；查看告警可开弹框
7. `onReady` 在拓扑有节点时即调用，不等待叠色

不要断言 X6 内部 DOM。用测试 id 或按钮文案：弹框标题、重试按钮、右键菜单项。

- [ ] **Step 2: Run to verify fail**

```bash
cd web && pnpm exec vitest run src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/networkStatusTopology.fetch.test.tsx
```

Expected: FAIL（仍走告警中心 URL 或没有第二次取数）。

- [ ] **Step 3: Implement widget behavior**

取数顺序：

1. 现有 `getNetworkStatusTopology`
2. 从 `dataSources` 按 `NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS` 解析 id；context 没有则 `getDataSourceBriefList({ page_size: -1 })` 再匹配（同一 rest_api 多条时优先 `is_build_in`）
3. `getSourceDataByApiId(cmdbId, { inst_uuids })`
4. 收集非空 `monitor_id`，一次 `getSourceDataByApiId(monitorId, { instance_ids, limit: 1 })`
5. `applyMonitorOverlay`
6. 任一步失败：保留结构节点，全部当 unknown（不要调 overlay 当成全绿），设置 overlayError 可重试。重试只重跑 2–5，不重拉拓扑，除非用户点工具条刷新

弹框：Ant Design `Modal`。标题：`{设备名} · {t('dashboard.networkTopoPopoverAlerts')} {count}（{t('dashboard.networkTopoLatestItems', { n: items.length })}）`。表格列：级别、类型、内容、开始时间，字段对齐 `_build_monitor_alert_segment` 的 `level` / `alert_type` / `content` / `start_event_time`。关闭不改 `selectedNodeId`。失败时 Modal 内报错+重试。

点击：

- 图标：仍 toggle 选中（现有 `onNodeClick`）
- 角标：`isStatusTopologyBadgeTarget(event)` 为真则 `openAlertModal(nodeId)`，不要改成跳转告警中心
- 浮层告警数：unknown 或 0 时不是按钮；否则点击开弹框
- 右键「查看告警」：同样 `canOpenAlertModal` 才启用；分享态**不要**整菜单 disabled，只禁用「实例详情」

`faultPath` 条件从 `alert_count` 改为 `canOpenAlertModal` 或 `status === 'critical' | 'error' | 'warning'`（有活跃告警才高亮故障链）。unknown / normal 不画故障链。

文案（zh / en 都加）：

- `networkTopoUnmonitored`：未关联监控
- `networkTopoStatusUnknown`：未知
- `networkTopoLatestItems`：最新 {n} 条
- `networkTopoAlertModalRetry`：重新加载告警
- 改 `networkTopoStatusLoadFailed`：监控叠色加载失败
- 改 `networkStatusTopologyDesc`：基于 CMDB 网络结构叠加监控中心活跃告警

`getStatusLabelKey` 增加 unknown → `networkTopoStatusUnknown`。

`onReady`：拓扑请求成功且 `nodes.length > 0` 即调用，叠色失败不改。

若共用 canvas 的 `onNodeClick` 现在是 `(nodeId) => void`，增加可选 `(nodeId, event?)`；CMDB 编辑页不传 event 则行为不变。

- [ ] **Step 4: Run tests**

```bash
cd web && pnpm exec vitest run src/app/ops-analysis/components/widgets/networkStatusTopology
```

Expected: PASS。

- [ ] **Step 5: Commit**（仅当用户要求提交）

---

### Task 7: 内置大屏 YAML + 初始化断言

**Files:**
- Modify: `server/apps/operation_analysis/support-files/builtin_network_topology_screen.yaml`
- Modify: `server/apps/operation_analysis/tests/test_init_builtin_canvases.py`

- [ ] **Step 1: Write the assertion first**

在 `test_init_builtin_canvases.py` 增加：

```python
def test_builtin_network_topology_screen_refs_monitor_overlay_datasources():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))
    screens = {item["key"]: item for item in payload["screens"]}
    screen = screens["screen::网络状态拓扑大屏_内置"]
    assert set(screen["refs"]["datasource_keys"]) == {
        "CMDB 实例监控ID映射::cmdb/get_monitor_ids_by_inst_uuids",
        "监控活跃告警::monitor/query_latest_active_alerts",
    }
```

`test_all_builtin_canvas_datasource_references_resolve_after_merge` 会在 YAML 改完后自动要求这两个 key 能在 `source_api.json` 解析到。不要改 `instId: '220'`。

- [ ] **Step 2: Run to verify fail**

```bash
cd server && python -m pytest apps/operation_analysis/tests/test_init_builtin_canvases.py::test_builtin_network_topology_screen_refs_monitor_overlay_datasources -q
```

Expected: FAIL（refs 仍是 `[]`）。

- [ ] **Step 3: Update YAML**

```yaml
    refs:
      datasource_keys:
        - CMDB 实例监控ID映射::cmdb/get_monitor_ids_by_inst_uuids
        - 监控活跃告警::monitor/query_latest_active_alerts
      namespace_keys: []
```

desc 可改为「叠加监控中心活跃告警」；不要动 `instId`。

- [ ] **Step 4: Run tests**

```bash
cd server && python -m pytest apps/operation_analysis/tests/test_init_builtin_canvases.py -q --tb=short
```

Expected: PASS。

- [ ] **Step 5: Commit**（仅当用户要求提交）

---

## 验证清单（全部 Task 完成后）

后端：

```bash
cd server && python -m pytest \
  apps/monitor/tests/test_monitor_inherited_data_scope.py \
  apps/cmdb/tests/test_get_monitor_ids_by_inst_uuids_nats.py \
  apps/rpc/tests/test_misc_forwarding.py::test_cmdb_get_monitor_ids_by_inst_uuids \
  apps/operation_analysis/tests/test_network_status_topology.py \
  apps/operation_analysis/tests/test_network_status_topology_overlay.py \
  apps/operation_analysis/tests/test_init_builtin_canvases.py \
  apps/operation_analysis/tests/test_export_and_viewsets.py \
  apps/operation_analysis/tests/test_canvas_report_adapter.py \
  apps/operation_analysis/tests/test_share_service.py \
  apps/operation_analysis/tests/test_dashboard_report_render_token.py \
  -q --tb=short
```

前端：

```bash
cd web && pnpm exec vitest run \
  src/app/ops-analysis/components/widgets/networkStatusTopology \
```

手动：未推送监控=灰且浮层不是 0；已监控无告警=绿且写 0；致命=红脉冲；角标=总数（>99 为 99+）；弹框标题总数与表格最新 N 条；分享可开弹框不能跳 CMDB；叠色失败结构仍在且全灰，不是全绿。

---

## Spec 覆盖对照

| Spec 条目 | Task |
|---|---|
| 场景接口不再查告警中心、节点无状态字段 | 3 |
| CMDB NATS 批量 monitor_id、权限、上限 100、空字符串、不进 OpenAPI | 2 |
| 改造 `query_latest_active_alerts` 的 count / max_level / summaries / 全无权失败 | 1 |
| 前端 rest_api 编排、unknown vs normal、颜色、角标、弹框、分享禁用 CMDB | 5, 6 |
| 保存/导出/分享/报表按组件类型纳入两个数据源；分享查询键 | 4 |
| 内置大屏 refs | 7 |
| 编辑态无 dataSource 时按 rest_api 解析（brief list 回退） | 5, 6 |
| 报表 render token 允许 overlay 取数 | 4 |
| 配置抽屉不选数据源 | 不改抽屉（已满足） |
| 不修 instId 220、不改 CMDB 编辑页 | 明确不做 |
