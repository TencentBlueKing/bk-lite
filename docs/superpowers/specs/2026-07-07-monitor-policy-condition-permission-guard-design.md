# 监控策略与条件对象级权限围栏设计

## 背景

代码检查发现 `MonitorPolicyViewSet` 与 `MonitorConditionViewSet` 只有列表接口按权限过滤，按裸 ID 的读取、更新、删除和组织关联写入仍可能绕过对象级边界。该问题会影响监控策略、监控条件、策略定时任务、告警关闭和组织关联等核心业务闭环。

本设计只收口这两个 P0 权限问题，不处理采集配置假成功和节点管理 NATS 配置接口契约收口。

## 目标

- 监控策略和监控条件的读写删必须受对象级权限约束。
- 写入 `organizations` 前必须服务端校验目标组织属于当前用户授权范围。
- 策略批量模板创建必须校验 `asset_ids` 属于当前用户授权范围，混入越权资产时整体失败。
- 保持现有正常业务逻辑不变：同组织操作、超管操作、策略定时任务维护、无数据基准线、告警关闭逻辑继续按原语义工作。
- 补齐测试围栏，覆盖允许路径、越权路径、边界路径和副作用不发生。

## 非目标

- 不改前端 payload 或 API 字段结构。
- 不改 serializer 字段定义。
- 不改告警扫描任务实现。
- 不改节点管理、NATS、采集配置链路。
- 不抽全局权限框架，不重构无关监控 ViewSet。

## 推荐方案

采用“统一 queryset + 写入围栏”：

1. 在 `MonitorPolicyViewSet` 和 `MonitorConditionViewSet` 增加统一 `get_queryset()`。
2. `list`、`retrieve` 使用当前用户 `View` 范围。
3. `update`、`partial_update`、`destroy` 使用当前用户 `Operate` 范围。
4. `create` 和组织关联更新前校验 `organizations`。
5. `bulk_create_from_templates` 在创建任何策略前校验所有资产授权，失败时整体回滚。

不采用仅在单个 action 内加判断的最小补丁，因为容易漏掉自定义 action；不采用抽全局 guard 的方案，因为会扩大本次风险面。

## 权限模型

现有权限结果同时包含组织级权限和实例级权限：

```text
permission
  ├─ team: 组织级默认权限
  └─ instance: 单对象权限
```

实现必须保留 `permission_filter(..., team_key=..., id_key=...)` 的既有语义。读操作允许 `View`，写操作要求 `Operate`。如果现有 helper 无法直接表达“只保留 Operate 实例规则”，在 ViewSet 内增加局部 helper 做规整或二次判断，不把新抽象扩散到其他模块。

超管保持现有全量能力。

## 策略围栏

`MonitorPolicyViewSet` 需要收口以下路径：

- `list`：保持现有分页和过滤行为，但复用统一可读 queryset。
- `retrieve`：只能读取可见策略。
- `update` / `partial_update`：只能修改可操作策略。
- `destroy`：只能删除可操作策略；无权限时不能清理定时任务、清理策略组织、关闭告警或清理基准线。
- `create`：创建前校验请求中的 `organizations`。
- `bulk_create_from_templates`：先校验所有 `asset_ids`，再构造 payload；任一资产越权或不存在时整体失败，不创建任何策略、定时任务或组织关联。

`update_policy_organizations()` 只接收已校验过的组织集合，不再直接信任请求体。

## 条件围栏

`MonitorConditionViewSet` 需要收口以下路径：

- `list`：保持现有分页和过滤行为，但复用统一可读 queryset。
- `retrieve`：只能读取可见条件。
- `update` / `partial_update`：只能修改可操作条件。
- `destroy`：只能删除可操作条件；无权限时不能删除 `MonitorConditionOrganization`。
- `create`：创建前校验请求中的 `organizations`。

`update_condition_organizations()` 只接收已校验过的组织集合，不再直接信任请求体。

## 数据流

```text
用户请求
  │
  ▼
构建 actor context
  │
  ▼
get_queryset()
  ├─ list/retrieve -> View 范围
  └─ update/delete -> Operate 范围
  │
  ▼
get_object()/serializer
  │
  ▼
组织或资产写入前二次校验
  │
  ▼
业务写入与副作用
```

失败策略：

- 对象不存在或不在可见范围内，按现有 DRF 查询集收口表现为找不到。
- 目标组织越权，返回无权限错误。
- 批量创建中任一资产越权，整体失败并回滚。

## 测试矩阵

### 监控策略

- 同组织用户可以列表、详情、更新、删除授权策略。
- 跨组织用户列表看不到他人策略。
- 跨组织用户按裸 `policy_id` 详情、更新、删除失败。
- 更新策略时传入未授权 `organizations` 失败，原组织不变。
- 删除跨组织策略失败，且不删除 `PeriodicTask`、不删除 `PolicyOrganization`、不关闭告警、不清理基准线。
- `bulk_create_from_templates` 混入未授权 `asset_ids` 时整体失败，不创建策略、定时任务或组织关联。
- 超管路径保持可用。

### 监控条件

- 同组织用户可以列表、详情、更新、删除授权条件。
- 跨组织用户列表看不到他人条件。
- 跨组织用户按裸 `condition_id` 详情、更新、删除失败。
- 更新条件时传入未授权 `organizations` 失败，原组织不变。
- 删除跨组织条件失败，且不删除 `MonitorConditionOrganization`。
- 超管路径保持可用。

### 回归测试

- 策略更新仍正常维护 `PeriodicTask`。
- 无数据告警基准线逻辑仍按原条件触发。
- 删除可操作策略仍会关闭当前策略的新告警。
- 条件分页和过滤器仍可用。

## 验证命令

优先运行新增/相关测试：

```bash
cd server && uv run pytest apps/monitor/tests -k "policy or condition"
```

提交前目标运行：

```bash
cd server && make test
```

如果完整测试受数据库或环境阻塞，需要记录阻塞原因，并至少运行新增测试文件和相关 ViewSet 测试。

## 风险控制

- 不做数据库迁移，回滚面限制在两个 ViewSet 和测试文件。
- 不改 API 字段结构，避免前端适配风险。
- 不改告警扫描和节点管理链路，避免扩大业务影响。
- 权限失败必须发生在副作用前，防止无权限请求产生部分写入。
- 批量创建使用事务保证全有或全无。

## 待实施文件

- `server/apps/monitor/views/monitor_policy.py`
- `server/apps/monitor/views/monitor_condition.py`
- `server/apps/monitor/tests/` 下新增或补充策略、条件权限测试。
