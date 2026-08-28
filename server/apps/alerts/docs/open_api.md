# 告警 OpenAPI 接口说明

本文说明告警中心对外开放的查询与操作接口。推荐入口为统一网关 `/openapi/v1/alerts/*`（业务锚点为 `alert_id`）。存量路径 `{BK_LITE_BASE_URL}/api/v1/alerts/api/open` 本轮仍保留，关闭与筛选行为与网关对齐。

## 0. 统一网关（推荐）

基础地址：`{BK_LITE_BASE_URL}/openapi/v1`。认证走平台网关（`Authorization: Bearer <API_TOKEN>`），组织取令牌绑定团队，精确匹配、不级联。客户端不得传 `team` 或数据库主键 `id`，未知字段返回 `SCHEMA_INVALID`。分页 `page` 从 1 起，`page_size` 默认 20、上限 500、越限钳制。筛选字段与第 3 章列表参数一致（含 `resource_type` / `resource_id`）。

| 方法 | path | 锚点 |
|---|---|---|
| GET | `alerts/list` | 筛选字段 |
| GET | `alerts/detail` | query `alert_id` |
| GET | `alerts/events` | query `alert_id` |
| POST | `alerts/assign` | body `alert_id`、`assignee` |
| POST | `alerts/acknowledge` | body `alert_id` |
| POST | `alerts/reassign` | body `alert_id`、`assignee` |
| POST | `alerts/close` | body `alert_id`；待响应/处理中可关，不校验是否处理人 |
| POST | `alerts/batch-action` | body `action`、`alert_ids`（1 至 100） |

以下第 1 章起为存量 `/api/v1/alerts/api/open` 路径说明；该路径分页上限仍为 100，`alert_id` 可放在 URL 中。

## 1. 基础约定

### 1.1 基础地址

```text
{BK_LITE_BASE_URL}/api/v1/alerts/api/open
```

例如 BK-Lite 地址为 `https://bk-lite.example.com`，告警列表接口就是：

```text
https://bk-lite.example.com/api/v1/alerts/api/open/alerts
```

接口路径末尾不带 `/`。

### 1.2 认证方式

API Token 需要在 BK-Lite 产品页面申请，入口为：

```text
系统管理 → 平台设置 → 密钥
```

在该页面申请密钥后，将获得的 Token 作为接口认证凭据。本文中的“API Secret”与产品页面申请到的“API Token”指同一凭据。

所有接口都必须携带请求头：

```http
Api-Authorization: <API_SECRET>
```

API Secret 必须只绑定一个团队；接口只能访问该团队内、且绑定用户有权限访问的告警。跨团队告警会按不存在处理并返回 404，防止通过 ID 枚举数据。

写接口还必须携带：

```http
Content-Type: application/json
```

### 1.3 统一响应结构

成功响应：

```json
{
  "result": true,
  "data": {},
  "message": "",
  "code": "ok"
}
```

失败响应：

```json
{
  "result": false,
  "data": {},
  "message": "请求参数非法",
  "code": "alerts.validation.failed"
}
```

固定字段如下：

| 字段 | 类型 | 说明 |
|---|---|---|
| `result` | boolean | 调用是否成功 |
| `data` | object、array | 成功数据或错误上下文 |
| `message` | string | 成功时为空；失败时为可读错误信息 |
| `code` | string | 成功为 `ok`；失败为稳定错误码 |

### 1.4 路径参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `alert_id` | string | 告警 ID，例如 `A-20260812-001` |
| `action` | string | 操作类型：`assign`、`acknowledge`、`reassign`、`close` |

## 2. 接口总览

当前共 5 个 URL 模板、8 个操作。

| 方法 | URL | 接口名称 | 作用 |
|---|---|---|---|
| GET | `/alerts` | 查询告警列表 | 分页、过滤和排序查询告警 |
| GET | `/alerts/{alert_id}` | 查询告警详情 | 查询单个告警，含 `labels` 与 `enrichment` |
| GET | `/alerts/{alert_id}/events` | 查询告警事件 | 分页查询指定告警关联的事件 |
| POST | `/alerts/{alert_id}/assign` | 分派告警 | 将告警分派给处理人 |
| POST | `/alerts/{alert_id}/acknowledge` | 认领告警 | 当前用户认领已分派告警 |
| POST | `/alerts/{alert_id}/reassign` | 转派告警 | 将告警转派给其他处理人 |
| POST | `/alerts/{alert_id}/close` | 关闭告警 | 关闭告警 |
| POST | `/alerts/actions/{action}` | 批量操作告警 | 对 1 至 100 条告警执行相同操作 |

以下章节中的 URL 均省略基础地址 `/api/v1/alerts/api/open`。

## 3. 查询接口

查询接口需要绑定用户具备 `Alarms-View` 功能权限。超级管理员不受此限制。

### 3.1 查询告警列表

- 方法与 URL：`GET /alerts`
- 作用：在团队与权限范围内分页查询告警；不返回观察中（`observing`）或未转正恢复（`recovered`）的会话告警。
- 成功状态码：200。

Query 参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `page` | integer | 否 | 1 | 页码，最小 1 |
| `page_size` | integer | 否 | 20 | 每页数量，范围 1 至 100 |
| `ordering` | string | 否 | `-created_at` | 排序字段；仅支持 `created_at`、`-created_at` |
| `title` | string | 否 | 空 | 告警标题，模糊匹配（不区分大小写） |
| `content` | string | 否 | 空 | 告警内容，模糊匹配（不区分大小写） |
| `alert_id` | string | 否 | 空 | 告警 ID，精确匹配 |
| `activate` | string | 否 | 空 | 传入任意值时，排除已关闭类状态（`closed`、`auto_close`、`auto_recovery`） |
| `my_alert` | string | 否 | 空 | 传入 `1` / `true` / `yes` 时，仅返回当前绑定用户为处理人的告警；仍受绑定组织约束 |
| `level` | string | 否 | 空 | 告警级别，多个值用英文逗号分隔 |
| `status` | string | 否 | 空 | 告警状态，多个值用英文逗号分隔 |
| `source_name` | string | 否 | 空 | 告警源名称，多个值用英文逗号分隔 |
| `created_at_after` | string | 否 | 空 | 创建时间下限（含），格式与系统存储一致 |
| `created_at_before` | string | 否 | 空 | 创建时间上限（含），格式与系统存储一致 |
| `incident_id` | string | 否 | 空 | 关联事故 ID，精确匹配 |
| `has_incident` | string | 否 | 空 | 是否有关联事故；`true` 或 `false` |
| `rule_id` | string | 否 | 空 | 规则 ID，精确匹配 |
| `resource_type` | string | 否 | 空 | 资源类型，精确匹配 |
| `resource_id` | string | 否 | 空 | 资源 ID，精确匹配 |

`data` 返回字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `count` | integer | 符合条件的告警总数 |
| `page` | integer | 当前页码 |
| `page_size` | integer | 当前每页数量 |
| `items` | array[告警对象] | 当前页告警 |

告警对象的主要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `alert_id` | string | 告警 ID |
| `title` | string | 告警标题 |
| `content` | string | 告警内容 |
| `status` | string | 告警状态，例如 `pending`、`processing`、`closed` |
| `level` | string | 告警级别 |
| `source_name` | string | 告警源名称 |
| `operator` | array[string] | 当前处理人列表 |
| `item` | string | 监控项 |
| `resource_id` | string | 资源 ID |
| `resource_type` | string | 资源类型 |
| `resource_name` | string | 资源名称 |
| `rule_id` | string | 规则 ID |
| `fingerprint` | string | 告警指纹 |
| `dimensions` | object | 维度标签 |
| `first_event_time` | string | 首次事件时间，`YYYY-MM-DD HH:MM:SS` |
| `last_event_time` | string | 最近事件时间 |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 更新时间 |
| `event_count` | integer | 关联事件数量 |
| `duration` | string | 持续时长展示文本 |

列表响应不包含数据库内部 ID、`labels`、`enrichment` 及事件明细。

### 3.2 查询告警详情

- 方法与 URL：`GET /alerts/{alert_id}`
- 作用：查询单个可见告警的完整信息。
- 入参：路径参数 `alert_id`。
- 成功状态码：200。
- 返回：`data` 为告警对象，字段含义与列表一致，并额外包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `labels` | object | 告警标签 |
| `enrichment` | object | 富化信息 |

- 不存在、跨团队或不可见：404，`alerts.alert.not_found`。

### 3.3 查询告警事件

- 方法与 URL：`GET /alerts/{alert_id}/events`
- 作用：分页查询指定告警关联的事件，按 `received_at` 倒序。
- 入参：路径参数 `alert_id`；分页参数 `page`、`page_size` 与列表接口一致。
- 成功状态码：200。
- 告警不存在：404，`alerts.alert.not_found`。

`data` 返回字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `count` | integer | 事件总数 |
| `page` | integer | 当前页码 |
| `page_size` | integer | 当前每页数量 |
| `items` | array[事件对象] | 当前页事件 |

事件对象的主要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_id` | string | 事件 ID |
| `title` | string | 事件标题 |
| `description` | string | 事件描述 |
| `level` | string | 事件级别 |
| `action` | string | 事件动作 |
| `status` | string | 事件状态 |
| `source` | integer | 告警源 ID，无来源时为 `null` |
| `source_name` | string | 告警源名称 |
| `resource_id` | string | 资源 ID |
| `resource_type` | string | 资源类型 |
| `resource_name` | string | 资源名称 |
| `item` | string | 监控项 |
| `value` | number | 指标值 |
| `start_time` | string | 事件开始时间 |
| `end_time` | string | 事件结束时间，未结束时为 `null` |
| `received_at` | string | 接收时间 |

## 4. 操作接口

操作接口需要绑定用户具备 `Alarms-Edit` 功能权限。超级管理员不受此限制。

支持的操作（`action`）：

| 值 | 说明 |
|---|---|
| `assign` | 分派 |
| `acknowledge` | 认领 |
| `reassign` | 转派 |
| `close` | 关闭 |

### 4.1 单条告警操作

- 方法与 URL：`POST /alerts/{alert_id}/{action}`
- 作用：对单条告警执行指定操作。
- 成功状态码：200。
- 返回：`data` 为操作结果，通常包含更新后的 `alert_id`、`status`、`operator` 等字段。

请求体按操作类型如下：

#### assign / reassign

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `assignee` | array[string] | 是 | 处理人用户名列表，至少 1 个非空字符串 |
| `assignment_id` | integer | 否 | 分派规则 ID |

```json
{
  "assignee": ["alice", "bob"],
  "assignment_id": 3
}
```

#### acknowledge

请求体可为空对象 `{}`，无需额外字段。

#### close

接口关闭不校验当前用户是否为处理人；告警处于「待响应」或「处理中」即可关闭。页面关闭逻辑不变。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `reason` | string | 否 | 关闭原因 |

```json
{
  "reason": "问题已修复"
}
```

### 4.2 批量告警操作

- 方法与 URL：`POST /alerts/actions/{action}`
- 作用：对多条告警执行相同操作；逐条处理，部分失败不影响其他条目。
- 成功状态码：200。

请求体字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `alert_ids` | array[string] | 是 | 1 至 100 个告警 ID；元素为非空字符串 |
| 其余字段 | — | — | 与单条操作请求体一致，例如 `assignee`、`reason` |

```json
{
  "alert_ids": ["A-1", "A-2"],
  "assignee": ["alice"]
}
```

返回 `data`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `succeeded` | array[string] | 操作成功的告警 ID |
| `failed` | array[object] | 操作失败的告警；每项含 `alert_id`、`code`、`message` |

```json
{
  "succeeded": ["A-1"],
  "failed": [
    {
      "alert_id": "A-2",
      "code": "alerts.alert.not_found",
      "message": "告警不存在"
    }
  ]
}
```

## 5. 常见状态码与错误码

| HTTP 状态码 | `code` | 说明 |
|---|---|---|
| 400 | `alerts.validation.failed` | 请求参数、分页、排序或操作字段非法 |
| 400 | `alerts.operator.assignee_invalid` | 处理人未指定、不存在或不在允许范围内 |
| 403 | `alerts.auth.api_secret_required` | 未通过 API Secret 认证 |
| 403 | `alerts.auth.invalid_team` | API Secret 未绑定唯一团队 |
| 403 | `alerts.permission.denied` | 用户缺少 `Alarms-View` 或 `Alarms-Edit` 等功能权限 |
| 403 | `alerts.operator.not_assignee` | 当前用户不是告警处理人，无法认领或转派 |
| 404 | `alerts.alert.not_found` | 告警不存在、跨团队或不可见 |
| 409 | `alerts.operator.invalid_state` | 告警当前状态不允许执行该操作 |
| 500 | `alerts.request.failed` | 未归类的请求处理失败 |

## 6. 不在本接口范围内

以下能力不在告警 OpenAPI 范围内，请使用产品内 Web UI 或其他专用接口：

| 能力 | 说明 |
|---|---|
| 事故（Incident） | 事故创建、更新、查询等 |
| 恢复（resolve） | 告警恢复操作；OpenAPI 仅支持 `assign`、`acknowledge`、`reassign`、`close` |
| 全局事件列表 | 不开放 `/events` 级别的全局事件查询，仅支持按告警 ID 查询关联事件 |
| K8s 渲染 | `/open_api/k8s/render/` 等 K8s 集成接口 |
| Web UI | 告警中心页面交互、通知配置、策略管理等 |
