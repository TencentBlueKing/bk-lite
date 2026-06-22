# CMDB + Alert 接入操作日志 / 错误日志 — 设计

- 日期：2026-06-15
- 分支：feature_windyzhao
- 状态：已评审通过，待实现

## 1. 背景与目标

系统管理「平台设置 → 审计日志」提供统一的**操作日志**（操作日志 / 登录日志两个子 tab）和独立的**错误日志** tab。目标是把 CMDB 与 Alert 两个应用接入这套统一日志：

- **操作日志**：记录两个应用的**所有"操作类"写操作**（创建 / 编辑 / 删除 / 执行），用于审计"谁在什么时候做了什么管理操作"。
- **错误日志**：把两个应用的后台报错纳入统一错误日志。

### 关键边界（已与需求方确认）

- CMDB 的**实例（instance）增删改全部不进操作日志**。实例的数据变化已由 CMDB 自有的 `change_record` 覆盖，操作日志只记**模型 / 分类 / 属性 / 关联类型 / 自定义上报等管理类、结构性操作**。
- Alert 已有自己的 `OperatorLog` 表。本次采用**双写**：在写 `OperatorLog` 的同一处额外写一条统一 `OperationLog`，`OperatorLog` 原样保留，两套独立互不影响。

## 2. 现状（探索结论）

### 2.1 操作日志（system_mgmt）

| 角色 | 位置 |
|---|---|
| 模型 `OperationLog` | `server/apps/system_mgmt/models/operation_log.py`（字段 `username` / `source_ip` / `app` / `action_type` / `summary` / `domain` / `created_at`；`action_type` ∈ {create, update, delete, execute}） |
| 进程内写入工具 `log_operation(request, action_type, app, summary)` | `server/apps/system_mgmt/utils/operation_log_utils.py` |
| 跨服务写入 `save_operation_log(...)`（NATS RPC） | `server/apps/system_mgmt/nats_api.py` |
| 读取 ViewSet / 过滤 | `server/apps/system_mgmt/viewset/operation_log_viewset.py` |
| 前端页面 | `web/src/app/system-manager/components/security/operationLogs.tsx` |
| 「操作模块」下拉来源 | 前端拉 `/core/api/get_client/`（读 `App` 表 `name`/`display_name`），**非硬编码枚举** |

**写入方式现状**：全代码库 50+ 处**纯手动埋点**（job / opspilot / system_mgmt 等在业务成功后显式调 `log_operation`）。**无装饰器、无 Mixin、无 signal、无 `perform_*` 钩子**。`app` 字符串与 `App.name` 对齐才能被前端下拉筛到。

**CMDB / Alert 现状**：CMDB 完全未接入；Alert 用的是**另一套** `OperatorLog` 模型（字段为 `action` / `target_type` / `operator_object` / `overview` / `target_id`，与 `OperationLog` 不兼容）。

CMDB viewset 基类是 `viewsets.ViewSet`（**不是 ModelViewSet**），增删改均为自定义 `@action`，因此没有 DRF 的 `perform_create/update/destroy` 可统一拦截。

### 2.2 错误日志（system_mgmt）

| 角色 | 位置 |
|---|---|
| 模型 `ErrorLog` | `server/apps/system_mgmt/models/error_log.py` |
| **自动捕获中间件** `ErrorLogMiddleware` | `server/apps/system_mgmt/middleware/error_log_middleware.py`（注册于 `config/components/app.py`） |
| 异步落库 Celery 任务 `write_error_log_async` | `server/apps/system_mgmt/tasks.py` |
| 读取 ViewSet | `server/apps/system_mgmt/viewset/error_log_viewset.py` |
| 前端页面 | `web/src/app/system-manager/(pages)/settings/error-logs/page.tsx` |

**写入方式现状**：中间件 `process_exception` **全局自动捕获** `/api/v1/<app>/<module>/` 的异常，按 URL 正则提取 `app`/`module`，异步落库。**无需 per-app 接入**，但受白名单 `ALLOWED_APPS` 约束。

- CMDB：URL 为 `/api/v1/cmdb/...` → 提取 `app="cmdb"`，**已在白名单，零改动即生效**。
- Alert：应用目录为 `alerts`，URL 经 `app_name.removeprefix("apps.")` 挂在 `/api/v1/alerts/` → 提取 `app="alerts"`；但白名单写的是 `"alarm"` → **不匹配，Alert 报错被静默丢弃**（见 §5 bug）。

## 3. 方案选型

操作日志埋点机制候选：

- **方案 A 纯手动埋点**：对齐现有 50+ 处。零新抽象、风险最低，但 CMDB 管理类 action 多，样板重复、文案分散。
- **方案 B 轻量装饰器（选定）**：新增 `@operation_log(...)` 贴在 action 上，成功后自动写日志。声明式、集中、CMDB/Alert 复用、不动存储与读取层。
- **方案 C 中间件全自动**：仿 ErrorLogMiddleware 按 URL 自动记。零埋点但 summary 无业务语义、难表达"排除实例"规则、与现有手动日志风格割裂。**否决**。

**结论：方案 B**。

## 4. 设计

存储层（`OperationLog`/`ErrorLog`）、读取 API、前端**均不改动**。

### 4.1 核心组件：`@operation_log` 装饰器

新增于 `server/apps/system_mgmt/utils/operation_log_utils.py`（与 `log_operation` 同处，沿用 job/opspilot 既有的跨应用 import 习惯）。

```python
@operation_log(
    app="cmdb",
    action_type="create",                       # 可省略，省略时按 HTTP method 推断
    summary=lambda req, resp, view, *a, **k: f"新增模型: {resp.data['name']}",
)
def create(self, request, *args, **kwargs):
    ...
```

行为约定：

1. **action_type**：可显式传；不传时按 HTTP method 推断（`POST→create` / `PUT,PATCH→update` / `DELETE→delete`）。批量 / 导入 / 执行类（如 `batch_delete`、`import`、`execute`）必须显式传。
2. **summary**：支持字符串常量或 `callable(request, response, view, *args, **kwargs) -> str`，由 callable 从 request/response 提业务语义文案（批量操作可在 callable 内拼接 N 个对象名）。
3. **仅成功时写**：仅当被装饰方法正常返回且响应状态为 2xx 时写日志；抛异常或非 2xx 不写（异常交由错误日志中间件处理）。
4. **失败安全**：写日志过程中任何异常都不得影响业务响应（底层 `log_operation` 已 try/except，装饰器再包一层兜底）。
5. **零侵入存储**：内部仍调用现有 `log_operation(request, action_type, app, summary)`，不新增写路径。

### 4.2 CMDB 埋点范围

- **装饰**：模型、分类、属性、关联类型、自定义上报等**所有管理类 viewset 的写操作 action**。
- **明确排除**：`server/apps/cmdb/views/instance.py` 的全部写操作（由 `change_record` 覆盖，不双记）。
- `app` 字符串固定为 `"cmdb"`（与 `App.name`、错误日志一致，保证前端「操作模块」下拉可筛）。
- 具体 action 清单在实现计划阶段逐文件枚举。

### 4.3 Alert 埋点范围（双写）

- 在 Alert 现有写 `OperatorLog` 的管理类 action 上加同一个 `@operation_log` 装饰器，额外写一条 `OperationLog`。
- `OperatorLog` 原样保留，两套独立。

### 4.4 命名一致性（实现前必须核实）

`alerts` 应用在 `App` 表中的 `name` 决定三处必须对齐的值：

1. 操作日志埋点时传给装饰器的 `app` 字符串；
2. 错误日志中间件白名单 `ALLOWED_APPS` 中的条目；
3. 前端「操作模块」下拉的 value（= `App.name`）。

下拉显示文案是 "Alarm"，实际 `name` 可能是 `alarm` 或 `alerts`，存在目录名（`alerts`）/URL（`alerts`）/展示名（Alarm）三者不一致风险。**实现第一步先查 `App` 表确定 canonical 值，再让上述三处统一对齐**，否则前端筛不到数据。

### 4.5 错误日志：修白名单

将 `ErrorLogMiddleware.ALLOWED_APPS` 中 Alert 条目对齐为中间件实际从 URL 提取的值（依 §4.4 核实结果，预计为 `"alerts"`）。CMDB 无需改动。

## 5. 范围外：附带 bug（单独 worktree 任务）

前端操作日志列表发送 `start_time` / `end_time`，而后端 `OperationLogFilter` 期望 `operation_time_start` / `operation_time_end` → **时间筛选可能失效**。

此 bug **不在本 spec 实现范围内**，单独在独立 git worktree 中处理：用 systematic-debugging 定位根因（确认是否真为参数不匹配、是否有中间映射层），TDD 写失败测试再修复（前端或后端二选一对齐）。

## 6. 测试策略（TDD）

遵循 `server/docs/testing-guide.md` 的分层约定：

- **装饰器单测**（`_pure` / `_service`，mock `log_operation`）：
  - method → action_type 推断正确（POST/PUT/PATCH/DELETE）；
  - summary 为 callable 时被正确调用并取值；
  - 仅 2xx 响应写日志，非 2xx / 抛异常不写；
  - 写日志失败不影响业务响应（业务返回值原样透传）。
- **CMDB viewset 测试**（`_views`，DRF）：
  - 管理类 action（模型/分类/属性/关联/上报）成功后断言生成对应 `OperationLog` 行（`app="cmdb"`、`action_type`、`summary`）；
  - 实例 action 断言**不生成** `OperationLog`。
- **Alert 双写测试**：管理类 action 成功后断言**同时**存在 `OperatorLog` 与 `OperationLog`。
- **错误日志回归**：`/api/v1/alerts/` 路径抛异常时能落 `ErrorLog`（白名单修复回归）。

## 7. 实现顺序建议

1. 核实 `App` 表中 alerts 的 `name`（§4.4），确定 canonical app 值。
2. TDD 实现 `@operation_log` 装饰器 + 单测。
3. CMDB 管理类 action 埋点 + viewset 测试（排除 instance）。
4. Alert 管理类 action 双写埋点 + 测试。
5. 修错误日志白名单 + 回归测试。
6.（独立 worktree）修时间过滤参数不匹配 bug。
