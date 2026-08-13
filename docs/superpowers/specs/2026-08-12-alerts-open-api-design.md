# 统一告警中心 Open API 设计

日期：2026-08-12  
状态：已对齐，待实现计划

## 1. 背景与目标

CMDB 已通过 `/api/v1/cmdb/api/open` + `Api-Authorization` 向第三方/平台内脚本开放稳定 REST 契约。统一告警中心目前仅有 Web 内部 API（`/api/v1/alerts/api/alerts/` 等）和 K8s 安装类 `open_api/k8s`，缺少同风格的告警拉取与流转 Open API。

**目标：** 为平台内其他模块/脚本（同租户自动化）开放告警查询与流转接口，契约对齐 CMDB Open API，能力对齐现有告警中心内部能力（不含事故 Incident）。

## 2. 已确认决策

| 项 | 决策 |
|---|---|
| 使用方 | 平台内模块/脚本集成，查询 + 流转都要 |
| 范围 | 仅 Alert；不含 Incident |
| 流转动作 | `assign` / `acknowledge` / `reassign` / `close`（不含 `resolve`） |
| 对外 ID | 一律使用业务 `alert_id`（如 `ALERT-xxxx`） |
| 筛选粒度 | 对齐现有内部 `AlertModelFilter` |
| 实现路径 | 独立 `server/apps/alerts/open_api/` 包（对齐 CMDB，不薄封装 ViewSet） |

## 3. 架构

### 3.1 包结构

```text
server/apps/alerts/open_api/
  auth.py          # Api-Authorization 上下文（用户 + 单团队）
  views.py         # 薄 APIView
  services.py      # 查询 / 流转编排
  serializers.py   # 入参校验与对外字段裁剪
  errors.py        # alerts.* 错误码
  responses.py     # {result, data, message, code}
```

路由挂载在 `server/apps/alerts/urls.py`，前缀：

```text
{BK_LITE_BASE_URL}/api/v1/alerts/api/open
```

路径末尾不带 `/`。与现有 `open_api/k8s`（安装 YAML）隔离，互不混用。

### 3.2 复用边界

- **复用：** 平台 `UserAPISecret` + `APISecretMiddleware`；现有告警查询过滤逻辑；`AlertOperator` 流转状态机与校验。
- **不改：** Web `/api/alerts`、`/api/events` 行为；接入/Webhook；K8s render。
- **风格：** 对齐 `server/apps/cmdb/open_api/`（views → service → domain），而非 `OpenAPIViewSet`。

### 3.3 鉴权与权限

1. Header：`Api-Authorization: <API_SECRET>`
2. 写接口另需：`Content-Type: application/json`
3. 密钥绑定用户 + **单一团队**；数据按该团队 `team` 过滤
4. 查看：`Alarms-View`；流转：`Alarms-Edit`
5. 不可见/跨团队资源返回 **404**（防枚举），与 CMDB 一致
6. 流转操作者 = 密钥绑定用户；`acknowledge` / `reassign` / `close` 仍须该用户在 `alert.operator` 中

## 4. 查询接口

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/alerts` | 分页拉取告警列表 |
| GET | `/alerts/{alert_id}` | 单个告警详情 |
| GET | `/alerts/{alert_id}/events` | 该告警下 Event 列表 |

### 4.1 列表筛选

对齐内部 `AlertModelFilter`：

| 参数 | 说明 |
|---|---|
| `title` / `content` | 模糊匹配 |
| `alert_id` | 精确业务 ID |
| `level` / `status` / `source_name` | 逗号分隔多选 |
| `created_at_after` / `created_at_before` | 时间范围 |
| `activate` | 有值则排除已关闭类状态 |
| `my_alert` | 有值则筛选当前密钥用户在 `operator` 中的告警 |
| `incident_id` / `has_incident` / `rule_id` | 事故关联与规则 |
| `page` / `page_size` | 分页，默认 1 / 20，上限 100 |
| `ordering` | 仅 `created_at` / `-created_at` |

列表 `data`：

```json
{"count": 0, "page": 1, "page_size": 20, "items": []}
```

默认行为与内部 list 一致：queryset 排除 `session_status` 属于 `SessionStatus.NO_CONFIRMED`（`observing` / `recovered`）的记录。

### 4.2 Alert 对外字段

- **列表/详情共有：** `alert_id`, `title`, `content`, `status`, `level`, `source_name`, `operator`, `item`, `resource_id`, `resource_type`, `resource_name`, `rule_id`, `fingerprint`, `dimensions`, `first_event_time`, `last_event_time`, `created_at`, `updated_at`, `event_count`, `duration`
- **详情额外：** `labels`, `enrichment`
- **不暴露：** 数据库 `id`、`events` M2M、权限辅助字段

### 4.3 Event 列表

同分页结构；默认排序 `-received_at`。

字段：`event_id`, `title`, `description`, `level`, `action`, `status`, `source`, `source_name`, `resource_id`, `resource_type`, `resource_name`, `item`, `value`, `start_time`, `end_time`, `received_at`。

不提供全局 Event 列表 Open API（仅告警下挂载）。

## 5. 流转接口

### 5.1 单告警（主契约）

| 方法 | 路径 | 状态流转 | Body |
|---|---|---|---|
| POST | `/alerts/{alert_id}/assign` | `unassigned` → `pending` | `assignee`（必填，username 数组）；可选 `assignment_id` |
| POST | `/alerts/{alert_id}/acknowledge` | `pending` → `processing` | 无或 `{}` |
| POST | `/alerts/{alert_id}/reassign` | `processing` → `pending` | `assignee`（必填）；可选 `assignment_id` |
| POST | `/alerts/{alert_id}/close` | `processing` → `closed` | 可选 `reason`（默认「告警已处理完成」） |

成功 `data`：更新后的 Alert 摘要（至少 `alert_id`、`status`、`operator`、`updated_at`）。

### 5.2 批量（本轮一并交付）

```http
POST /alerts/actions/{action}
```

`action` ∈ `assign|acknowledge|reassign|close`  
Body：`alert_ids`（业务 ID 数组，1–100）+ 与单条相同的附加字段。

返回按条汇总：

```json
{
  "succeeded": ["ALERT-1"],
  "failed": [
    {
      "alert_id": "ALERT-2",
      "code": "alerts.operator.invalid_state",
      "message": "..."
    }
  ]
}
```

### 5.3 规则

- 服务层调用现有 `AlertOperator`，不复制状态机
- 状态不匹配 → 业务错误（非 500）
- 不可见告警 → 404
- 不开放：`resolve`、升级、评论、事故流转

## 6. 响应与错误码

统一 envelope：

```json
{"result": true, "data": {}, "message": "", "code": "ok"}
{"result": false, "data": {}, "message": "...", "code": "alerts.validation.failed"}
```

| code | HTTP | 场景 |
|---|---|---|
| `alerts.auth.api_secret_required` | 403 | 未带/无效 Secret |
| `alerts.auth.invalid_team` | 403 | 团队绑定非法 |
| `alerts.permission.denied` | 403 | 缺菜单权限 |
| `alerts.validation.failed` | 400 | 参数非法 |
| `alerts.alert.not_found` | 404 | 告警不存在或不可见 |
| `alerts.operator.invalid_state` | 409 | 状态不允许该动作 |
| `alerts.operator.not_assignee` | 403 | 非当前处理人 |
| `alerts.operator.assignee_invalid` | 400 | 分派对象不合法 |
| `alerts.request.failed` | 500 | 未预期错误 |

## 7. 文档与测试

### 7.1 文档

- 必交付：`server/apps/alerts/docs/open_api.md`（结构对齐 CMDB `open_api.md`）
- 可后置：`open_api_calling_guide.md`、示例客户端

### 7.2 测试

对齐 CMDB `test_open_api_*` 风格，测 HTTP 外部行为：

- 鉴权：无 Secret / 错团队 / 权限不足
- 查询：筛选、分页、详情、events 归属
- 流转：四动作成功路径；错误状态 / 非处理人 / 不可见 404
- 批量：部分成功汇总

优先复用现有 Alert 工厂/fixture；不测 ViewSet 内部实现细节。

## 8. 非范围

- Incident 查询与流转
- `resolve`
- 告警接入 / Webhook / 源配置
- 通知、提醒、升级策略配置 API
- Web / Mobile UI 改动
- 全局 Event 列表 Open API
- 改动现有 Web 内部 API 契约

## 9. 实现落点（摘要）

1. 新增 `server/apps/alerts/open_api/` 包与 URL 注册
2. 实现查询三接口 + 单告警四动作 + 批量 actions
3. 编写 `docs/open_api.md` 与对应测试
4. 验证权限、团队隔离、状态机错误码与 CMDB 风格 envelope
