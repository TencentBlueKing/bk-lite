# Historical Superpowers change: 2026-07-20-node-monitor-log-current-team-permission

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-20-node-monitor-log-current-team-permission.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Node Management、Monitor、Log 中现已接入数据权限的所有用户请求都以 `current_team` 为硬数据边界，超级管理员不能跨组织，同时保留授权组织分配、共享、转移和继承权限对象的正常业务能力。

**Architecture:** 在 `apps.core` 建立轻量 `CurrentTeamDataScope` 契约，并由三个模块显式传入各自 queryset；不使用全局中间件或自定义 Manager。直接对象先按组织收窄再与对象权限求交，子对象通过固定权限归属根过滤，外部数据必须从已授权本地根对象发起查询。目标组织使用独立的可分配组织范围，不复用 `current_team` 数据范围。

**Tech Stack:** Python 3.12、Django 4.2 ORM、Django REST Framework、pytest、NATS 本地 RPC。

## Global Constraints

- 超级管理员只绕过功能/动作授权，不绕过 `current_team` 数据边界。
- 默认只访问 `current_team`；仅显式 `include_children=1` 时包含授权子组织。
- 缺少、非法、未授权或空组织范围全部 fail-closed；`None` 和空列表绝不表示全量。
- 源对象必须在当前数据范围内；目标组织必须属于调用方独立的可分配组织集合。
- 子数据动态继承唯一权限归属根；父链缺失或不一致时拒绝，不取权限并集。
- 不处理当前完全没有数据权限的平台公共目录，不重构后台自发任务身份模型。
- 禁止原生 SQL；全部使用 Django ORM。
- 每个行为改动必须先写失败测试、确认 RED，再写最小实现并确认 GREEN。
- 修改代码覆盖率不低于 75%，批量越权请求必须零副作用。

---

### Task 1: 统一 current_team 与可分配组织契约

**Files:**
- Create: `server/apps/core/utils/current_team_scope.py`
- Create: `server/apps/core/tests/utils/test_current_team_scope.py`
- Modify: `server/apps/system_mgmt/nats/users.py`
- Modify: `server/apps/rpc/system_mgmt.py`
- Modify: `server/apps/system_mgmt/tests/test_nats_api_scoped_groups.py`

**Interfaces:**
- Produces: `CurrentTeamDataScope(current_team, data_team_ids, include_children, username, domain, is_superuser)`。
- Produces: `resolve_current_team_data_scope(request) -> CurrentTeamDataScope`。
- Produces: `scope_permission_queryset(model, permission, scope, team_key, id_key="id__in") -> QuerySet`。
- Produces: `resolve_assignable_organization_ids(request) -> frozenset[int]`。
- Produces: `validate_assignable_organizations(request, organization_ids) -> frozenset[int]`。
- Produces: `SystemMgmt.get_assignable_groups(actor_context)`，返回 `{"result": True, "data": [organization_id, ...]}`。

- [ ] **Step 1: 为组织范围解析和 queryset 交集编写失败测试**

```python
def test_superuser_scope_is_current_team_only(monkeypatch):
    request = make_request(is_superuser=True, current_team=1)
    patch_scoped_groups(monkeypatch, [1])
    assert resolve_current_team_data_scope(request).data_team_ids == frozenset({1})


def test_instance_permission_cannot_cross_current_team(monkeypatch, team_model):
    own = team_model.create_with_org(1)
    foreign = team_model.create_with_org(2)
    permission = {"team": [], "instance": [{"id": foreign.id, "permission": ["View"]}]}
    qs = scope_permission_queryset(
        team_model.model,
        permission,
        CurrentTeamDataScope(
            current_team=1,
            data_team_ids=frozenset({1}),
            include_children=False,
            username="admin",
            domain="domain.com",
            is_superuser=True,
        ),
        team_key=team_model.team_key,
    )
    assert list(qs.values_list("id", flat=True)) == []
    assert own.id != foreign.id


def test_missing_current_team_fails_closed():
    with pytest.raises(BaseAppException, match="current_team"):
        resolve_current_team_data_scope(make_request(current_team=None))
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `cd server && uv run pytest apps/core/tests/utils/test_current_team_scope.py -q`

Expected: FAIL，提示 `apps.core.utils.current_team_scope` 或目标接口尚不存在。

- [ ] **Step 3: 实现当前数据范围解析与权限交集**

```python
@dataclass(frozen=True)
class CurrentTeamDataScope:
    current_team: int
    data_team_ids: frozenset[int]
    include_children: bool
    username: str
    domain: str
    is_superuser: bool


def scope_permission_queryset(model, permission, scope, *, team_key, id_key="id__in"):
    organization_qs = model.objects.filter(**{team_key: list(scope.data_team_ids)})
    permission_qs = permission_filter(model, permission, team_key=team_key, id_key=id_key)
    return organization_qs.filter(id__in=permission_qs.values("id")).distinct()
```

`resolve_current_team_data_scope()` 必须通过 `SystemMgmt.get_authorized_groups_scoped()` 验证请求组织；返回为空、RPC 失败或 `current_team` 不在结果中时抛出 `BaseAppException`。`get_assignable_groups()` 中普通用户返回其真实授权组织及后代，超级管理员返回所有真实存在组织；不得相信请求体组织 ID。

- [ ] **Step 4: 运行 Task 1 测试确认 GREEN**

Run: `cd server && uv run pytest apps/core/tests/utils/test_current_team_scope.py apps/system_mgmt/tests/test_nats_api_scoped_groups.py apps/rpc/tests/test_system_mgmt_forwarding.py -q`

Expected: PASS。

- [ ] **Step 5: 提交统一契约**

```bash
git add server/apps/core/utils/current_team_scope.py server/apps/core/tests/utils/test_current_team_scope.py server/apps/system_mgmt/nats/users.py server/apps/rpc/system_mgmt.py server/apps/system_mgmt/tests/test_nats_api_scoped_groups.py
git commit -m "权限: 增加 current_team 数据范围契约"
```

### Task 2: 收紧节点、共享配置和任务节点权限

**Files:**
- Modify: `server/apps/node_mgmt/utils/permission.py`
- Modify: `server/apps/node_mgmt/services/node.py`
- Modify: `server/apps/node_mgmt/services/installer.py`
- Modify: `server/apps/node_mgmt/views/node.py`
- Modify: `server/apps/node_mgmt/views/installer.py`
- Modify: `server/apps/node_mgmt/views/collector_configuration.py`
- Create: `server/apps/node_mgmt/tests/test_current_team_data_scope.py`

**Interfaces:**
- Consumes: Task 1 的 `resolve_current_team_data_scope()`、`scope_permission_queryset()`、`validate_assignable_organizations()`。
- Produces: `get_authorized_node_queryset()` 对所有用户按 current_team 与对象权限求交。
- Produces: `get_mutable_collector_configuration_queryset()` 以“当前可见配置 + 全部受影响组织可分配”判断可写。

- [ ] **Step 1: 编写超级管理员、共享配置和任务投影失败测试**

```python
def test_superuser_node_queryset_excludes_sibling_team(superuser_request, nodes):
    assert set(get_authorized_node_queryset(superuser_request).values_list("id", flat=True)) == {nodes.team_a.id}


def test_shared_configuration_write_requires_all_impacted_orgs(request_a, shared_config):
    patch_assignable_orgs({1})
    assert not get_mutable_collector_configuration_queryset(request_a).filter(id=shared_config.id).exists()


def test_collector_task_summary_counts_only_current_team_nodes(api_client, mixed_task):
    response = api_client.get(f"/api/v1/node_mgmt/installer/{mixed_task.id}/collector_install_nodes/")
    assert {item["node_id"] for item in response.json()["data"]["items"]} == {mixed_task.team_a_node.id}
    assert response.json()["data"]["summary"]["total"] == 1
```

- [ ] **Step 2: 运行节点测试确认 RED**

Run: `cd server && uv run pytest apps/node_mgmt/tests/test_current_team_data_scope.py -q`

Expected: FAIL，超级管理员仍看到同级组织、共享配置影响范围或任务统计仍未按当前组织投影。

- [ ] **Step 3: 实现节点根对象与影响范围校验**

`get_authorized_node_queryset()` 改用 Task 1 的交集 helper。`authorize_target_organizations()` 无论是否超管都调用 `validate_assignable_organizations()`。共享配置读取仍允许命中至少一个当前可见 Node；修改、删除、解绑时将配置关联 Node 的全部组织与 `resolve_assignable_organization_ids()` 比较，任一受影响组织无权则返回 403。未绑定配置保留创建者草稿语义。

- [ ] **Step 4: 去除任务服务超级管理员旁路**

```python
task_nodes = ControllerTaskNode.objects.filter(task_id=task_id).order_by("id")
if authorized_nodes is not None:
    authorized_ids = {str(node_id) for node_id in authorized_nodes.values_list("id", flat=True)}
    linked_nodes = list(task_nodes.filter(node_id__in=authorized_ids))
    legacy_nodes = [
        item
        for item in task_nodes.filter(Q(node_id="") | Q(node_id__isnull=True))
        if set(item.organizations or []) & set(scope.data_team_ids)
    ]
    task_nodes = linked_nodes + legacy_nodes
```

`ControllerTaskNode.node_id` 是字符串兼容字段，旧快照兜底必须在已按 `task_id` 收窄的小集合上用 Python 判断，禁止使用 PostgreSQL 专属 JSON `overlap` 查询。所有任务明细、汇总、动作结果和局部重试只使用过滤后的任务节点；有 Node 的记录以 Node 当前组织为准，只有无法关联 Node 的旧 `ControllerTaskNode` 才使用任务时 `organizations` 快照。

- [ ] **Step 5: 运行节点测试确认 GREEN 和回归**

Run: `cd server && uv run pytest apps/node_mgmt/tests/test_current_team_data_scope.py apps/node_mgmt/tests/test_architecture_support.py apps/node_mgmt/tests/test_node_config_asso_validation.py -q`

Expected: PASS。

- [ ] **Step 6: 提交节点权限收口**

```bash
git add server/apps/node_mgmt
git commit -m "权限: 收紧节点和任务 current_team 范围"
```

### Task 3: 收紧监控直接归属对象和组织分配

**Files:**
- Modify: `server/apps/monitor/views/monitor_policy.py`
- Modify: `server/apps/monitor/views/monitor_condition.py`
- Modify: `server/apps/monitor/views/monitor_instance.py`
- Modify: `server/apps/monitor/views/organization_rule.py`
- Modify: `server/apps/monitor/services/node_mgmt.py`
- Modify: `server/apps/monitor/tests/test_monitor_permission_guards.py`
- Modify: `server/apps/monitor/tests/test_monitor_instance_view.py`
- Modify: `server/apps/monitor/tests/test_monitor_object_view_extra.py`

**Interfaces:**
- Consumes: Task 1 的 current_team 和可分配组织 helper。
- Produces: Policy、Condition、Instance、OrganizationRule 对超级管理员和普通用户使用相同数据范围。

- [ ] **Step 1: 将现有“超管全量”测试改为 current_team 失败用例**

```python
def test_superuser_policy_queryset_stays_in_current_team(mocker):
    own = _policy(_monitor_object("own"), org=1)
    foreign = _policy(_monitor_object("foreign"), org=2)
    patch_scope(mocker, teams=[1], is_superuser=True)
    view = make_policy_view(current_team=1, is_superuser=True)
    assert set(view.get_queryset().values_list("id", flat=True)) == {own.id}
    assert foreign.id not in view.get_queryset().values_list("id", flat=True)
```

为 Condition、MonitorInstance、MonitorObjectOrganizationRule 对称增加列表、详情和写操作测试；增加“当前 A 的对象可分配到可分配 B”和“不可分配 C”正向/拒绝测试。

- [ ] **Step 2: 运行监控直接对象测试确认 RED**

Run: `cd server && uv run pytest apps/monitor/tests/test_monitor_permission_guards.py apps/monitor/tests/test_monitor_instance_view.py apps/monitor/tests/test_monitor_object_view_extra.py -q`

Expected: FAIL，失败点对应 `is_superuser` 全量分支或目标组织错误复用当前范围。

- [ ] **Step 3: 删除数据层 superuser 旁路并接入统一范围**

Policy、Condition、Instance 的 queryset 都执行：

```python
scope = resolve_current_team_data_scope(request)
permission = self._get_permission(...)
queryset = scope_permission_queryset(Model, permission, scope, team_key=MODEL_TEAM_KEY)
```

OrganizationRule 先要求 `rule.organizations` 与 `scope.data_team_ids` 有交集，再校验绑定实例；不得因 `is_superuser` 返回全量。所有 `_ensure_target_organizations()` 改用 `validate_assignable_organizations()`，不再用当前组织数据范围。

- [ ] **Step 4: 运行监控直接对象测试确认 GREEN**

Run: `cd server && uv run pytest apps/monitor/tests/test_monitor_permission_guards.py apps/monitor/tests/test_monitor_instance_view.py apps/monitor/tests/test_monitor_object_view_extra.py apps/monitor/tests/test_monitor_permission_business_flows.py -q`

Expected: PASS。

- [ ] **Step 5: 提交监控直接对象权限**

```bash
git add server/apps/monitor/views/monitor_policy.py server/apps/monitor/views/monitor_condition.py server/apps/monitor/views/monitor_instance.py server/apps/monitor/views/organization_rule.py server/apps/monitor/services/node_mgmt.py server/apps/monitor/tests
git commit -m "权限: 收紧监控对象 current_team 范围"
```

### Task 4: 让监控告警链固定继承策略权限

**Files:**
- Modify: `server/apps/monitor/views/monitor_alert.py`
- Modify: `server/apps/monitor/views/node_mgmt.py`
- Modify: `server/apps/monitor/tests/test_alert_permission_mixin.py`
- Modify: `server/apps/monitor/tests/test_monitor_alert_view.py`
- Create: `server/apps/monitor/tests/test_monitor_inherited_data_scope.py`

**Interfaces:**
- Consumes: Task 3 的受限 MonitorPolicy queryset。
- Produces: `AlertPermissionMixin.get_accessible_policy_queryset(request, require_operate=False)`。
- Produces: Alert、Event、RawData、Snapshot、Baseline 全部从受限策略 ID 子查询派生。

- [ ] **Step 1: 编写继承链和外部存储前置授权失败测试**

```python
def test_superuser_alert_inherits_policy_current_team(api_client, policies_and_alerts):
    response = api_client.get("/api/v1/monitor/monitor_alert/")
    assert response_ids(response) == {policies_and_alerts.team_a_alert.id}


def test_snapshot_denies_before_s3_field_access(api_client, foreign_snapshot, mocker):
    s3_read = mocker.patch.object(type(foreign_snapshot), "snapshots", new_callable=mocker.PropertyMock)
    response = api_client.get(f"/api/v1/monitor/monitor_alert/snapshots/{foreign_snapshot.alert_id}/")
    assert response.status_code == 404
    s3_read.assert_not_called()


def test_event_policy_mismatch_is_hidden(api_client, inconsistent_event):
    response = api_client.get(f"/api/v1/monitor/monitor_event/{inconsistent_event.id}/")
    assert response.status_code == 404
```

- [ ] **Step 2: 运行监控继承测试确认 RED**

Run: `cd server && uv run pytest apps/monitor/tests/test_monitor_inherited_data_scope.py apps/monitor/tests/test_alert_permission_mixin.py apps/monitor/tests/test_monitor_alert_view.py -q`

Expected: FAIL，超管策略集合仍可全量或快照在授权前按裸 ID 查询。

- [ ] **Step 3: 实现策略根 queryset 和一致性过滤**

`AlertPermissionMixin` 不再从 `MonitorPolicy.objects.all()` 开始，也不在 Python 中把管理员 `all` 解释为全库；它先取得 current_team 受限策略 queryset，再应用策略对象权限。详情和快照使用 `self.get_queryset().get(id=...)`。Event 与 Snapshot 同时带有告警/策略标识时增加 `policy_id=F("alert__policy_id")` 一致性条件；孤儿或不一致记录不可见。

- [ ] **Step 4: 修复 Monitor → Node Management 用户同步范围**

`server/apps/monitor/views/node_mgmt.py` 和 `services/node_mgmt.py` 必须传 `scope.data_team_ids`，超级管理员不得发送 `[]` 或 `None` 表示全部；用户入口缺少 actor scope 时拒绝调用。

- [ ] **Step 5: 运行监控继承与 RPC 回归确认 GREEN**

Run: `cd server && uv run pytest apps/monitor/tests/test_monitor_inherited_data_scope.py apps/monitor/tests/test_alert_permission_mixin.py apps/monitor/tests/test_monitor_alert_view.py apps/monitor/tests/test_node_mgmt_service.py -q`

Expected: PASS。

- [ ] **Step 6: 提交监控继承权限**

```bash
git add server/apps/monitor
git commit -m "权限: 统一监控告警策略归属根"
```

### Task 5: 收紧日志分组、采集实例和外部日志查询

**Files:**
- Modify: `server/apps/log/services/access_scope.py`
- Modify: `server/apps/log/views/search.py`
- Modify: `server/apps/log/views/collect_config.py`
- Modify: `server/apps/log/views/node.py`
- Modify: `server/apps/log/nats/log.py`
- Create: `server/apps/log/tests/test_current_team_data_scope.py`
- Modify: `server/apps/log/tests/test_nats_permission.py`
- Modify: `server/apps/log/tests/test_collect_instance_permission_guards.py`

**Interfaces:**
- Consumes: Task 1 范围和目标组织 helper。
- Produces: `LogAccessScopeService.get_accessible_group_queryset()` 对超管同样 current-team-scoped。
- Produces: 原始日志、字段、聚合、统计查询必须持有非空 `LogAccessScope`。

- [ ] **Step 1: 编写日志分组和原始查询失败测试**

```python
def test_superuser_log_group_scope_excludes_sibling_team(superuser_request, groups):
    scope = LogAccessScopeService.resolve_scope(superuser_request)
    assert scope.log_groups == [groups.team_a.id]


def test_nats_superuser_scope_is_not_none(monkeypatch):
    patch_scope(monkeypatch, current_team=1, group_ids=["group-a"])
    assert _resolve_log_group_scope(superuser_info()) == ["group-a"]


def test_empty_log_group_scope_never_calls_victorialogs(api_client, mocker):
    query = mocker.patch("apps.log.views.search.LogSearchService.query")
    response = api_client.post("/api/v1/log/search/", {"log_groups": []})
    assert response.status_code in {400, 403}
    query.assert_not_called()
```

- [ ] **Step 2: 运行日志直接/外部范围测试确认 RED**

Run: `cd server && uv run pytest apps/log/tests/test_current_team_data_scope.py apps/log/tests/test_nats_permission.py apps/log/tests/test_collect_instance_permission_guards.py -q`

Expected: FAIL，NATS 超管仍返回 `None`、节点查询仍传空组织或目标组织仍错误复用当前范围。

- [ ] **Step 3: 实现日志分组、采集实例和目标组织范围**

`LogAccessScopeService` 使用 `scope_permission_queryset()`；CollectInstance/CollectConfig 先按实例组织根收窄；LogGroup、CollectInstance、Policy 的 organizations 调用 `validate_assignable_organizations()`。`views/node.py` 统一传 `scope.data_team_ids`，不保留超管空列表/`None` 分支。

- [ ] **Step 4: 对所有 VictoriaLogs 查询强制注入 LogGroup 根**

`search.py` 的搜索、字段、聚合、统计 action 都先调用 `resolve_scope()`，再由服务端组合每个已授权 LogGroup 的 `rule`；零可见分组时在网络请求前失败。`nats/log.py::_resolve_log_group_scope()` 对所有用户返回明确分组 ID 列表，空列表为 deny-all。

- [ ] **Step 5: 运行日志直接/外部范围测试确认 GREEN**

Run: `cd server && uv run pytest apps/log/tests/test_current_team_data_scope.py apps/log/tests/test_nats_permission.py apps/log/tests/test_collect_instance_permission_guards.py apps/log/tests/test_search_query_limits.py -q`

Expected: PASS。

- [ ] **Step 6: 提交日志直接和外部数据权限**

```bash
git add server/apps/log
git commit -m "权限: 收紧日志分组和原始查询范围"
```

### Task 6: 让日志告警链固定继承策略权限

**Files:**
- Modify: `server/apps/log/views/policy.py`
- Create: `server/apps/log/tests/test_policy_inherited_data_scope.py`
- Modify: `server/apps/log/tests/test_alert_viewset_param_validation_3653.py`

**Interfaces:**
- Consumes: Task 1 的范围 helper。
- Produces: `get_accessible_log_policy_queryset(request, collect_type_id=None, require_operate=False)`。
- Produces: Alert、Event、EventRawData、AlertSnapshot 统一从受限 Policy queryset 派生。

- [ ] **Step 1: 编写日志继承链失败测试**

```python
def test_superuser_alert_and_event_follow_policy_team(api_client, policy_graph):
    assert alert_ids(api_client.get("/api/v1/log/alert/")) == {policy_graph.team_a_alert.id}
    assert event_ids(api_client.get("/api/v1/log/event/")) == {policy_graph.team_a_event.id}


def test_event_with_mismatched_alert_policy_is_hidden(api_client, mismatched_event):
    assert api_client.get(f"/api/v1/log/event/{mismatched_event.id}/").status_code == 404


def test_snapshot_permission_checked_before_blob_read(api_client, foreign_snapshot, mocker):
    blob = mocker.patch.object(type(foreign_snapshot), "snapshots", new_callable=mocker.PropertyMock)
    response = api_client.get(f"/api/v1/log/alert/snapshots/{foreign_snapshot.alert_id}/")
    assert response.status_code == 404
    blob.assert_not_called()
```

- [ ] **Step 2: 运行日志继承测试确认 RED**

Run: `cd server && uv run pytest apps/log/tests/test_policy_inherited_data_scope.py -q`

Expected: FAIL，策略 ID 仍可由对象权限跨 current_team 穿透，或父链一致性未校验。

- [ ] **Step 3: 实现日志策略根 queryset**

`get_accessible_log_policy_ids()` 改为对 `get_accessible_log_policy_queryset()` 取 ID。Alert、Event、RawData、Snapshot 的列表、详情、统计、关闭和快照 action 只从该 queryset 派生。Event 使用 `policy_id=F("alert__policy_id")`；AlertSnapshot 使用 `policy_id=F("alert__policy_id")`；父策略缺失或不一致均返回 404，且在 S3JSONField 读取前完成。

- [ ] **Step 4: 运行日志继承测试确认 GREEN 和回归**

Run: `cd server && uv run pytest apps/log/tests/test_policy_inherited_data_scope.py apps/log/tests/test_alert_viewset_param_validation_3653.py apps/log/tests/test_collect_instance_permission_guards.py -q`

Expected: PASS。

- [ ] **Step 5: 提交日志策略继承权限**

```bash
git add server/apps/log/views/policy.py server/apps/log/tests
git commit -m "权限: 统一日志告警策略归属根"
```

### Task 7: 三模块回归、静态门禁与真实组织验收

**Files:**
- Modify only if a verification failure is caused by this change; return to the owning task's TDD cycle before editing.

**Interfaces:**
- Consumes: Tasks 1–6 的全部行为。
- Produces: 可发布的三模块 current_team 权限实现和验收证据。

- [ ] **Step 1: 运行聚焦权限回归**

Run:

```bash
cd server
uv run pytest \
  apps/core/tests/utils/test_current_team_scope.py \
  apps/system_mgmt/tests/test_nats_api_scoped_groups.py \
  apps/node_mgmt/tests/test_current_team_data_scope.py \
  apps/node_mgmt/tests/test_architecture_support.py \
  apps/monitor/tests/test_monitor_permission_guards.py \
  apps/monitor/tests/test_monitor_inherited_data_scope.py \
  apps/monitor/tests/test_monitor_permission_business_flows.py \
  apps/log/tests/test_current_team_data_scope.py \
  apps/log/tests/test_policy_inherited_data_scope.py \
  apps/log/tests/test_collect_instance_permission_guards.py -q
```

Expected: PASS，0 failures。

- [ ] **Step 2: 运行格式、静态和迁移门禁**

Run:

```bash
cd server
uv run black --check apps/core/utils/current_team_scope.py apps/system_mgmt/nats/users.py apps/rpc/system_mgmt.py apps/node_mgmt/utils/permission.py apps/node_mgmt/services/node.py apps/node_mgmt/services/installer.py apps/node_mgmt/views/node.py apps/node_mgmt/views/installer.py apps/node_mgmt/views/collector_configuration.py apps/monitor/views/monitor_policy.py apps/monitor/views/monitor_condition.py apps/monitor/views/monitor_instance.py apps/monitor/views/organization_rule.py apps/monitor/views/monitor_alert.py apps/monitor/views/node_mgmt.py apps/monitor/services/node_mgmt.py apps/log/services/access_scope.py apps/log/views/search.py apps/log/views/collect_config.py apps/log/views/node.py apps/log/nats/log.py apps/log/views/policy.py
uv run isort --check-only apps/core/utils/current_team_scope.py apps/system_mgmt/nats/users.py apps/rpc/system_mgmt.py apps/node_mgmt/utils/permission.py apps/node_mgmt/services/node.py apps/node_mgmt/services/installer.py apps/node_mgmt/views/node.py apps/node_mgmt/views/installer.py apps/node_mgmt/views/collector_configuration.py apps/monitor/views/monitor_policy.py apps/monitor/views/monitor_condition.py apps/monitor/views/monitor_instance.py apps/monitor/views/organization_rule.py apps/monitor/views/monitor_alert.py apps/monitor/views/node_mgmt.py apps/monitor/services/node_mgmt.py apps/log/services/access_scope.py apps/log/views/search.py apps/log/views/collect_config.py apps/log/views/node.py apps/log/nats/log.py apps/log/views/policy.py
uv run flake8 apps/core/utils/current_team_scope.py apps/system_mgmt/nats/users.py apps/rpc/system_mgmt.py apps/node_mgmt/utils/permission.py apps/node_mgmt/services/node.py apps/node_mgmt/services/installer.py apps/node_mgmt/views/node.py apps/node_mgmt/views/installer.py apps/node_mgmt/views/collector_configuration.py apps/monitor/views/monitor_policy.py apps/monitor/views/monitor_condition.py apps/monitor/views/monitor_instance.py apps/monitor/views/organization_rule.py apps/monitor/views/monitor_alert.py apps/monitor/views/node_mgmt.py apps/monitor/services/node_mgmt.py apps/log/services/access_scope.py apps/log/views/search.py apps/log/views/collect_config.py apps/log/views/node.py apps/log/nats/log.py apps/log/views/policy.py
uv run python manage.py makemigrations --check --dry-run
```

Expected: 全部退出码 0；如本地虚拟环境缺少格式工具，使用 `uv run` 执行相同版本工具并记录证据。

- [ ] **Step 3: 运行新增代码覆盖率门禁**

Run:

```bash
cd server
uv run pytest apps/core/tests/utils/test_current_team_scope.py apps/node_mgmt/tests/test_current_team_data_scope.py apps/monitor/tests/test_monitor_inherited_data_scope.py apps/log/tests/test_current_team_data_scope.py apps/log/tests/test_policy_inherited_data_scope.py --cov=apps.core.utils.current_team_scope --cov=apps.node_mgmt.utils.permission --cov=apps.monitor.views --cov=apps.log.services.access_scope --cov=apps.log.views.policy --cov-report=term-missing
```

Expected: 本次新增或修改代码覆盖率不低于 75%。

- [ ] **Step 4: 真实组织端到端验收**

准备同级 `Default`、`WeOps` 和无权组织，分别用普通用户与超级管理员验证：列表/详情/统计/快照/原始日志、裸 ID、共享、转移、跨授权组织分配、`include_children`、批量零副作用、共享配置影响范围及任务局部投影。必须确认超级管理员在 `Default` 看不到 `WeOps` 数据，切换到 `WeOps` 后才可见。

- [ ] **Step 5: 最终提交**

```bash
git status --short
git log --oneline --decorate -8
git diff master...HEAD --check
```

Expected: 仅包含本计划文件、权限实现和测试；无密钥、测试报告或无关工作区文件。

## Self-Review

- Spec coverage：覆盖超管边界、直接对象、继承对象、外部数据、目标组织、共享配置、任务投影、同步 RPC、批量零副作用和真实业务闭环。
- Placeholder scan：无 TBD、TODO、“类似前一任务”或未定义接口。
- Type consistency：三个模块统一消费 `CurrentTeamDataScope`、`scope_permission_queryset()`、`validate_assignable_organizations()`；权限归属根仍由模块内 queryset 负责。
- Scope control：没有给公共目录新增权限，没有引入全局 Manager/中间件，没有改变后台自发任务身份模型，没有数据库迁移。

## specs: 2026-07-20-node-monitor-log-current-team-permission-design.md

- 日期：2026-07-20
- 范围：`server/apps/node_mgmt`、`server/apps/monitor`、`server/apps/log` 及三者的用户来源同步 RPC
- 目标：保证超级管理员与普通用户都不能越过当前选择组织的业务数据范围，同时保留组织共享、转移和跨授权组织分配等正常业务能力

## 1. 背景与问题

当前系统把两类权限语义混在了 `is_superuser` 中：

1. 菜单、按钮和动作权限，超级管理员应当拥有全部能力；
2. 当前组织的数据范围，超级管理员仍应受 `current_team` 约束。

节点管理、监控和日志模块的大部分普通用户查询已经通过 `get_permission_rules()`、`get_permissions_rules()`、`permission_filter()` 或组织关联查询收窄，但部分路径把超级管理员、空组织列表或 `None` 解释成“全平台数据”。这会导致超级管理员选择 `Default` 时仍能读取或操作 `WeOps` 等同级组织的数据。

典型问题包括：

- 监控策略、条件、组织规则、实例和统计接口对超级管理员返回全量；
- 日志 NATS 查询以 `None` 表示超级管理员不限制日志分组；
- 节点安装任务和组织分配校验对超级管理员提前放行；
- Monitor、Log 调用 Node Management 时存在以空 `organization_ids` 表示全量的旧语义；
- 实例级对象授权与组织权限使用 OR 关系时，可能让其他组织的对象 ID 越过 `current_team`。

2026-07-07 的《监控策略与条件对象级权限围栏设计》中“超管保持现有全量能力”的结论被本设计替代。新的统一语义是：**超级管理员只绕过功能和动作授权，不绕过当前组织的数据边界。**

## 2. 已确认范围

### 2.1 纳入范围

1. 三个 App 中已经接入组织级或对象级数据权限的用户 HTTP 接口；
2. 由这些用户接口同步发起的 NATS/RPC 数据查询和操作；
3. 列表、详情、统计、原始数据、按裸 ID 查询、更新、删除、启停、关闭、重试、批量操作；
4. 对象的组织创建、共享、转移和重新分配；
5. 依赖父对象确定权限的告警、事件、快照、配置和任务节点。

### 2.2 不纳入范围

1. 当前完全没有组织数据权限设计的平台公共列表或目录，例如监控对象、插件、指标定义、单位、采集器、安装包、CollectType 和云区域列表；
2. 监控定时扫描、Sidecar 主动回传、系统初始化等后台自发任务的身份模型重构；
3. 全项目其他 App 的权限整改；
4. 新建全局权限中间件、自动过滤 Manager 或新的权限 DSL；
5. 数据模型迁移和组织关系重构。

后台异步任务仍必须由用户入口在提交前完成目标校验，但本轮不重新设计任务执行时的 `current_team`。

## 3. 产品与权限原则

### 3.1 功能权限与数据权限分离

权限链统一为：

```text
认证用户
  -> 功能/动作权限
  -> current_team 组织范围
  -> 对象级权限
  -> 业务读写
```

- 超级管理员继续绕过菜单、按钮、模块和动作权限；
- 普通用户继续校验 `View`、`Operate`、`Edit`、`Delete` 等动作；
- `is_superuser` 只能影响功能/动作层，不能让业务 queryset 变成全量。

### 3.2 current_team 是源对象硬边界

- 默认数据范围严格等于 `current_team`；
- 只有显式 `include_children=1` 时才包含当前组织下的授权子组织；
- 超级管理员与普通用户遵守相同范围；
- 超级管理员可以通过组织选择器切换组织，切换后只能访问新 `current_team` 范围；
- 缺少、非法或无法解析 `current_team` 时 fail-closed；
- `None`、空列表和空权限结果不能表示“全部组织”。

### 3.3 组织分配与源对象范围分离

`current_team` 决定“当前能读取和操作哪些源对象”；用户的组织管理授权决定“源对象可以分配给哪些目标组织”。

```text
源对象访问范围 = current_team 数据权限
目标组织分配范围 = 用户有权管理、分配的组织集合
```

- 超级管理员可以把当前有权操作的源对象分配给任意合法组织；
- 普通用户只能分配给其已有组织管理授权范围内的组织；
- 目标组织范围不受当前 `include_children` 开关限制，也不能从业务对象权限反推；
- 分配对象给目标组织，不代表调用方可以读取目标组织的其他业务数据；
- 目标组织必须真实存在，任一目标无权时整个请求失败。

### 3.4 真实业务可用性

权限修复不能阻断以下正常闭环：

- 在当前组织创建对象并直接分配给另一个有权组织；
- 把当前组织对象共享给多个有权组织；
- 把对象从当前组织转移到另一个有权组织；
- 父组织通过显式 `include_children=1` 查看授权子组织数据；
- 批量分配、批量安装和批量策略创建；
- 合法用户继续完成节点选择、配置下发、策略管理和日志查询。

## 4. 统一技术契约

### 4.1 当前数据范围上下文

建立轻量统一上下文，供三个模块的本地 adapter 使用：

```text
CurrentTeamDataScope
  current_team: int
  data_team_ids: set[int]
  include_children: bool
  username: str
  domain: str
  is_superuser: bool
```

解析规则：

1. 从现有认证请求中读取 `current_team`；
2. 通过现有 `SystemMgmt.get_authorized_groups_scoped()` 校验并解析当前组织范围；
3. 超级管理员在 `include_children=0` 时得到 `[current_team]`，打开开关后得到当前组织及其子组织；
4. 普通用户只能得到其在当前组织上下文下的授权范围；
5. 无合法范围时返回空范围并拒绝业务访问。

不建设自动修改所有 queryset 的全局框架。三个模块显式调用统一上下文，再通过各自组织关联字段构建 queryset。

### 4.2 可分配组织上下文

建立独立的目标组织校验能力：

```text
AssignableOrganizationScope
  organization_ids: set[int]
```

- 超级管理员范围为全部合法组织；
- 普通用户范围复用现有组织管理授权和组织选择器的数据来源；
- 该范围不能用 `permission["team"]` 或 `data_team_ids` 代替；
- 创建、更新、共享、转移时都校验 `requested_organizations <= assignable_organizations`。

### 4.3 权限归属根与继承权限

已经接入数据权限、但自身不直接绑定组织的数据，必须声明唯一、稳定的“权限归属根解析器”，不能由各接口临时选择一个上层对象判断权限。

权限归属分为三类：

1. **直接归属**：对象自身拥有组织关联，直接按该关联与 `data_team_ids` 求交；
2. **继承归属**：对象通过固定父链继承权限，例如监控告警固定继承监控策略；
3. **查询归属**：外部存储中的数据没有本地组织字段，只能从已授权的本地入口对象发起查询，例如 VictoriaLogs 原始日志固定继承日志分组。

统一规则：

- 读子数据要求其权限归属根在当前数据范围内，并具备根对象对应的查看权限；
- 更新、关闭、重试、删除等子数据动作要求根对象在当前数据范围内，并具备对应操作权限；
- 子数据不重复增加组织关系，根对象共享、转移或调整组织后，全部历史子数据立即跟随根对象的当前组织范围；
- 父对象不存在、已删除、不可解析或父链断裂时 fail-closed，孤儿数据不能退化成全平台可见；
- 同一记录冗余保存多个父标识时，必须验证它们解析到同一个权限归属根；不一致时拒绝访问、记录异常并等待数据修复，不能取多个父对象权限的并集；
- 任何原始数据、对象存储或时序/日志查询，都必须先完成根对象授权，再读取存储键或发送查询；客户端传入的条件不能覆盖服务端注入的数据范围；
- 列表、详情、统计、导出、关联选项和自定义 action 必须复用同一个根解析器，不允许同一模型在不同接口继承不同父对象；
- 实现优先使用受限根 queryset 的 ID 子查询过滤子数据，避免逐行 Python 权限判断和遗漏分页、统计口径。

权限归属根总表：

| 模块 | 数据对象 | 权限归属根 | 说明 |
|---|---|---|---|
| 节点管理 | Node | Node 自身组织 | 直接归属 |
| 节点管理 | NodeCollectorInstallStatus、CollectorTaskNode、CollectorActionTaskNode、Action | Node | 节点转移后历史结果跟随节点当前组织 |
| 节点管理 | ControllerTaskNode | 可解析的 Node | 仅旧数据无法关联 Node 时使用任务时组织快照兜底 |
| 节点管理 | CollectorConfiguration | 绑定的 Node 集合 | 读取至少命中一个可见节点；写入另按影响范围校验 |
| 节点管理 | ChildConfig | CollectorConfiguration → Node 集合 | 沿父配置继承 |
| 节点管理 | ControllerTask、CollectorTask、CollectorActionTask | 当前可见的任务节点 | 主记录无独立组织，明细和统计只投影可见任务节点 |
| 监控 | MonitorPolicy | PolicyOrganization | 直接归属 |
| 监控 | MonitorAlert、MonitorEvent、MonitorEventRawData、MonitorAlertMetricSnapshot、PolicyInstanceBaseline | MonitorPolicy | 告警、事件、原始数据、快照和基线统一继承策略 |
| 监控 | MonitorInstance | MonitorInstanceOrganization | 直接归属 |
| 监控 | CollectConfig、实例指标与时序查询 | MonitorInstance | 必须先授权实例，再发起指标查询 |
| 监控 | MonitorCondition | MonitorConditionOrganization | 直接归属 |
| 监控 | MonitorObjectOrganizationRule | 规则自身 organizations | 直接归属 |
| 日志 | Policy | PolicyOrganization | 直接归属 |
| 日志 | Alert、Event、EventRawData、AlertSnapshot | Policy | 告警、事件、原始数据和快照统一继承策略 |
| 日志 | CollectInstance | CollectInstanceOrganization | 直接归属 |
| 日志 | CollectConfig | CollectInstance | 沿采集实例继承 |
| 日志 | LogGroup | LogGroupOrganization | 直接归属 |
| 日志 | VictoriaLogs 原始日志、字段、聚合与统计 | LogGroup | 查询归属；无可见日志分组时 deny-all |
| 日志 | SearchCondition | organization | 直接归属 |

#### 4.3.1 多根共享对象的影响范围

`CollectorConfiguration` 可能同时绑定多个组织的节点。为了同时满足 current_team 源对象边界和正常共享维护：

- 当前组织存在至少一个可见绑定节点时，可以读取这份共享配置；
- 修改配置内容、删除配置或解绑节点会影响全部或部分已绑定节点，必须额外校验所有受影响节点所属组织都在调用方的可分配组织范围内；
- 新增绑定时，源配置必须在当前数据范围可见，新增节点必须来自调用方可合法选择/分配的目标组织范围；
- 无权覆盖全部受影响组织时，不允许静默修改全局共享配置；应支持只对已授权目标拆分或复制配置，避免用户只能看到却无法继续维护；
- 未绑定配置继续使用现有创建者草稿语义，本轮不新增组织字段。

#### 4.3.2 任务主记录的权限投影

没有独立组织关系的任务主记录从任务节点反向投影权限：

- 至少存在一个当前可见任务节点时，任务主记录可见；
- 接口只能返回当前范围内的任务节点、目标和统计，不得返回完整跨组织目标列表、凭据或其他敏感执行参数；
- 重试等操作默认只作用于已明确选择且已授权的任务节点；如果现有动作必然影响整项任务，则必须校验全部受影响节点，不能利用主任务 ID 跨组织执行；
- 节点转移组织后，历史任务节点跟随 Node 的当前组织；仅无法关联 Node 的历史 `ControllerTaskNode` 使用已有任务时组织快照兜底。

### 4.4 对象范围必须使用交集

现有 `permission_filter()` 会把组织级和实例级权限组合为 OR。模块 adapter 必须先建立当前组织 queryset，再在其中应用对象权限：

```text
organization_queryset
  = base_queryset.filter(object_organization in data_team_ids)

effective_queryset
  = organization_queryset
    INTERSECT
    permission_queryset(team permission OR instance permission)
```

这样即使权限规则中出现另一个组织的对象 ID，也不能越过 `current_team`。

超级管理员仍调用现有权限服务。权限服务会为管理员返回当前组织的 team 权限，因此其结果是“当前组织内全部对象和全部动作”，不是全平台对象。

### 4.5 详情和写操作

- 列表、详情和原始数据从 `effective_queryset` 查询；
- 按裸 ID 查询范围外对象统一表现为 404；
- 更新、删除、启停、关闭、重试等先从可操作 queryset 获取对象；
- 请求体中的源对象 ID、节点 ID、配置 ID、任务节点 ID不能直接用于业务写入；
- 批量请求先完成全部源对象和目标组织校验，再开启事务或创建异步任务；
- 任一越权时不产生数据库写入、NATS 调用、Celery 任务或其他副作用。

### 4.6 共享对象语义

对象只要与当前数据范围有组织交集，并具备动作权限，即可按现有共享对象语义维护。不能要求对象的所有关联组织都属于当前范围，否则会使共享、转移和重新分配无法使用。

- 共享：保留当前组织并增加其他有权目标组织；
- 转移：移除当前组织并增加其他有权目标组织；
- 转移成功后对象从当前列表消失是正常结果；
- 删除共享对象属于高影响操作，保留现有删除能力，但需在响应/页面提示影响范围并记录审计。

## 5. 节点管理设计

### 5.1 纳入的业务对象

- Node、NodeOrganization；
- 与节点绑定的 CollectorConfiguration、ChildConfig；
- ControllerTaskNode、CollectorTaskNode 等用户任务节点结果；
- 用户来源同步 RPC 返回的节点、配置和云区域代理地址。

### 5.2 查询和操作

1. 保留 `get_node_permission()` 和 `get_authorized_node_queryset()` 的主路径，但确保超级管理员也消费 current-team-scoped 权限结果；
2. 节点搜索、详情、更新、删除、配置绑定、采集器操作均从授权节点 queryset 获取源对象；
3. 父配置和子配置继续通过其绑定节点继承数据范围；未绑定配置保持现有创建者草稿语义，本轮不增加组织字段；
4. 共享配置按“当前组织可见绑定节点 + 全部受影响组织授权”区分读写，不允许通过一个可见节点修改无权组织节点正在使用的配置；
5. 安装任务节点查询删除超级管理员全量分支，优先通过任务节点关联的 Node 收窄；仅无法解析 Node 的旧 `ControllerTaskNode` 使用任务时组织快照；
6. 任务主记录通过可见任务节点反向投影，明细、数量和重试目标只包含当前范围；
7. 控制器重试、卸载、采集器安装等入口在提交 Celery 前校验所有目标节点；
8. 用户来源 `node_list`、`get_authorized_nodes_by_ids` 等 RPC 必须携带当前组织上下文，接收方不能把空组织解释为全量；
9. `get_cloud_region_proxy_address` 已有节点组织访问语义，超级管理员也必须证明当前组织在该云区域存在可访问节点。

### 5.3 组织分配

`authorize_target_organizations()` 不再因 `is_superuser` 提前返回。它改为调用可分配组织上下文：

- 源节点必须来自当前数据范围；
- 新组织集合必须全部可分配；
- 允许把节点共享或转移给其他有权组织；
- 组织变更成功后继续同步 Sidecar 属性。

### 5.4 不处理的目录

云区域列表、采集器目录、安装包目录等当前无组织数据权限的公共列表保持不变。

## 6. 监控模块设计

### 6.1 纳入的业务对象

- MonitorInstance、MonitorInstanceOrganization、CollectConfig；
- MonitorPolicy、PolicyOrganization、MonitorCondition、MonitorConditionOrganization；
- MonitorObjectOrganizationRule；
- MonitorAlert、MonitorEvent、MonitorEventRawData、MonitorAlertMetricSnapshot、PolicyInstanceBaseline；
- 用户来源监控统计和指标实例数据。

### 6.2 查询和操作

1. 删除策略、条件、组织规则、实例服务中的超级管理员全量 queryset 分支；
2. `_get_authorized_monitor_instances()` 始终根据当前组织权限构建 queryset；
3. 采集配置通过其 MonitorInstance 继承范围；
4. `query_by_instance` 对超级管理员也校验实例属于当前数据范围；
5. 策略批量创建中的每个资产必须属于当前范围，任一越权整体失败；
6. 告警、事件、原始数据、快照和基准线固定通过当前可见策略 ID 间接收窄，不能改用创建者、告警 ID 或实例 ID 绕过策略归属；
7. 事件、快照等同时保存策略 ID 和告警关系时，验证两条链指向同一策略；不一致或策略不存在时拒绝；
8. 快照、原始数据和时序数据必须先授权策略或实例，再读取对象存储或发起外部查询；
9. 监控统计中的实例、配置、策略、告警、事件、快照和基准线都从受限策略/实例 queryset 派生；
10. Monitor 调用 Node Management 的节点、配置同步查询时透传当前组织上下文；
11. CollectDetect 任务继续按 `created_by + current_team` 查询，监控对象功能权限的超管放行保持不变。

### 6.3 组织分配

实例、策略、条件和组织规则都采用“源对象当前范围 + 目标组织可分配范围”：

- 更新源对象前按 current_team 获取；
- `organizations` 独立校验；
- 允许创建到其他有权组织、共享和转移；
- 批量策略创建先校验全部资产和全部目标组织。

### 6.4 不处理的目录

监控对象、对象类型、插件、指标定义、指标分组和单位等当前平台公共目录保持不变。

## 7. 日志模块设计

### 7.1 纳入的业务对象

- LogGroup、LogGroupOrganization、SearchCondition；
- CollectInstance、CollectInstanceOrganization、CollectConfig；
- Policy、PolicyOrganization、Alert、Event、EventRawData、AlertSnapshot；
- 原始日志查询和日志统计结果；
- Log 调用 Node Management 的节点和云区域代理地址。

### 7.2 查询和操作

1. NATS `_resolve_log_group_scope()` 删除“超级管理员返回 None 表示不限”的语义；
2. 原始日志查询对所有用户解析当前组织可访问日志分组，无身份、无组织或无分组时使用 deny-all；
3. HTTP 日志搜索继续复用 `LogAccessScopeService`，补齐超级管理员 current_team 场景；
4. 日志策略、告警、事件、原始事件和快照固定通过当前可见策略 ID 收窄；
5. Event、AlertSnapshot 等多父关联必须解析到同一策略，不一致或策略不存在时拒绝；
6. EventRawData、AlertSnapshot 和 VictoriaLogs 查询必须先授权策略或日志分组，再读取外部数据；
7. 字段、聚合、统计等非列表接口也必须注入同一日志分组范围，客户端 query 不能覆盖服务端范围；
8. 采集实例和配置先按当前组织定位源对象，再校验 View/Operate；
9. Log 节点选择不能为超级管理员传空组织表示全量；
10. 云区域代理地址必须验证当前组织存在可访问节点；
11. SearchCondition 继续按其 organization 字段严格匹配 current_team。

### 7.3 组织分配

日志分组、采集实例和策略的组织创建、共享、转移使用统一目标组织校验。源对象访问范围不因目标组织授权而扩大。

### 7.4 不处理的目录

CollectType 等当前无组织数据权限的公共列表保持不变。

## 8. 用户体验与失败语义

### 8.1 组织切换

- 切换组织后重新请求数据，不复用上一组织的业务列表缓存；
- `include_children=0` 只看当前组织，`include_children=1` 才包含授权子组织；
- 超级管理员遵守同一开关。

### 8.2 共享和转移反馈

- 共享后对象在源组织和目标组织均可见；
- 转移后对象从当前组织列表消失；
- 创建或转移到其他组织成功时，响应保留对象 ID，并提示“请切换到目标组织查看”；
- 不把转移后的当前组织 404误报为保存失败。

### 8.3 错误状态

| 场景 | 结果 |
|---|---|
| 缺少或非法 current_team | 400，提示重新选择组织或重新登录 |
| 裸 ID 请求范围外对象 | 404，不泄露对象是否存在 |
| 对象可见但缺少动作权限 | 403 |
| 目标组织不存在或不可分配 | 403，返回不可分配组织 ID |
| 批量请求存在越权对象 | 整体失败，返回越权对象 ID，零副作用 |
| 用户同步 RPC 缺少组织上下文 | fail-closed，不返回全量 |
| 子数据父链缺失或无法解析 | 404，不退化为全局数据 |
| 子数据多个父标识归属不一致 | 拒绝并记录数据异常 |
| 共享配置写操作包含无权影响节点 | 403；允许改为拆分/复制后仅作用于授权目标 |

## 9. 审计设计

复用现有操作日志，不新增审批流。以下行为必须记录：

- 对象增加、移除或替换组织；
- 对象从当前组织转移出去；
- 删除共享对象；
- 节点安装、卸载、重试和采集器下发；
- 批量策略、实例和配置操作；
- 被拒绝的跨组织操作。

审计至少包含用户、domain、current_team、动作、对象类型、对象 ID、组织变更前后集合和结果。日志不得记录密码、Token、配置密文或原始日志正文。

## 10. 测试设计

实现阶段必须 TDD，先把当前错误的超级管理员全量测试改成失败用例，再进行最小实现。

### 10.1 通用契约测试

三个模块都覆盖：

1. 超级管理员选择组织 A，只能列表、详情、更新和删除 A 的对象；
2. 超级管理员使用组织 B 的裸对象 ID 返回 404；
3. 即使存在 B 对象的实例级授权，也不能越过 `current_team=A`；
4. `include_children=1` 可访问授权子组织，关闭后不可访问；
5. 缺少 current_team 时拒绝，不回退全量；
6. 用户可以把 A 中对象分配给自己有权的 B；
7. 用户不能分配给无权组织 C；
8. 共享给 B 后 A/B 均可见；
9. 从 A 转移到 B 后 A 不可见、B 可见；
10. 批量操作混入越权对象时零写入、零异步任务、零关联副作用。
11. 根对象转移或共享后，历史子数据立即跟随新的当前组织范围；
12. 父对象缺失和多父标识不一致时 fail-closed；
13. 子数据列表、详情、统计、导出和自定义 action 使用同一权限归属根。

### 10.2 节点管理专项

- 节点查询、修改、删除和配置绑定；
- 控制器/采集器任务节点查询；
- 任务主记录只投影当前可见任务节点和统计，裸主任务 ID 不扩大范围；
- 节点转移后历史任务跟随新组织，旧孤儿任务仅按任务时组织快照兜底；
- 跨组织共享采集配置可读，修改时校验全部受影响组织，并支持授权范围内拆分/复制；
- 安装、卸载和重试提交前校验；
- Monitor/Log 节点选择；
- 当前组织无节点时云区域代理地址不泄露。

### 10.3 监控专项

- 实例、采集配置、策略、条件和组织规则；
- 指标实例查询；
- 策略批量创建；
- 告警、事件、原始数据、快照和基准线；
- 策略共享/转移后历史告警同步变更可见范围；
- 事件、快照父链不一致或策略缺失时拒绝；
- 快照和时序查询在访问外部存储前完成根对象授权；
- 超级管理员统计只包含当前组织。

### 10.4 日志专项

- 日志分组和原始日志搜索；
- 采集实例和配置；
- 策略、告警、事件、原始事件和快照；
- 策略共享/转移后历史告警和事件同步变更可见范围；
- 多父关联不一致和父策略缺失时拒绝；
- 字段、聚合、统计与原始搜索统一继承受限日志分组；
- NATS 原始日志查询不再对超级管理员返回未改写 query；
- 节点选择和代理地址。

测试必须同时覆盖拒绝路径和合法创建、共享、转移、父子组织查看、批量操作、异步任务正常提交等正向业务流，禁止只测试“越权被拒绝”。新增或修改代码覆盖率不低于 75%。

## 11. 实施与发布策略

按依赖顺序实施：

1. current_team 数据范围与可分配组织 helper；
2. Node Management 源对象和同步 RPC；
3. Monitor 权限收口；
4. Log 权限收口；
5. 三模块联调和真实组织切换验证。

三模块在同一发布中上线，不保留“旧超管全量模式”兼容开关。无数据库迁移。

发布前至少准备以下组织结构：

```text
父组织
├─ Default
├─ WeOps
└─ 无权组织
```

使用普通用户和超级管理员分别验证节点选择、监控策略、指标数据、原始日志、共享、转移、批量拒绝和 `include_children`。

## 12. 验收标准

1. 超级管理员选择 `Default` 时，节点、监控和日志业务数据均不包含同级 `WeOps` 数据；
2. 超级管理员切换到 `WeOps` 后可以使用其全部功能并访问 WeOps 数据；
3. 所有已接数据权限的详情、写操作和同步 RPC 都不能通过裸 ID、空组织或实例授权越过 current_team；
4. 普通用户原有组织级和实例级权限语义不回归；
5. 用户可以把当前有权源对象分配、共享或转移给自己有权的其他组织；
6. Monitor、Log 节点选择和配置操作与 Node Management 采用同一组织口径；
7. 原始日志和监控统计不再向超级管理员返回全平台数据；
8. 批量越权请求零副作用；
9. 当前无数据权限的公共目录和后台自发任务不受本次改动影响；
10. 所有间接权限对象都有唯一权限归属根，父链异常时 fail-closed，父组织变更后历史子数据动态跟随；
11. 共享配置和任务主记录不会通过多节点关系泄露或操作其他组织数据，同时保留授权范围内拆分、复制和局部重试能力；
12. 三模块聚焦测试、Server 对应门禁和真实组织端到端验证通过。

## 13. 自检结果

1. 占位符检查：无 TBD、TODO 或未决实现占位；
2. 一致性检查：current_team 只约束源对象，目标组织使用独立授权，两者无冲突；
3. 范围检查：只处理三模块现有数据权限和用户同步 RPC，不扩张到公共目录或后台任务；
4. 可用性检查：保留创建、共享、转移、跨授权组织分配和父子组织查看；
5. 歧义检查：已明确超管、include_children、空组织、实例级授权、批量副作用和错误响应语义。
6. 继承检查：已为直接归属、继承归属、外部查询归属和多根共享对象定义统一权限根及异常规则；
7. 历史数据检查：已明确策略/节点组织变更后的动态继承、孤儿数据 fail-closed 与旧任务快照兜底。
