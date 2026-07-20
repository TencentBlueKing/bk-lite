# 节点管理、监控、日志 current_team 数据权限实施计划

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
        CurrentTeamDataScope.for_test(1),
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
    task_nodes = task_nodes.filter(Q(node_id__in=authorized_ids) | Q(node_id="", organizations__overlap=list(scope.data_team_ids)))
```

所有任务明细、汇总、动作结果和局部重试只使用过滤后的任务节点；有 Node 的记录以 Node 当前组织为准，只有无法关联 Node 的旧 `ControllerTaskNode` 才使用任务时 `organizations` 快照。

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
