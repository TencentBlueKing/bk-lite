# 告警中心 OpenAPI 网关接入与作业参数告警 ID

Status: implemented

## Completion Evidence

- 作业字段绑定下拉含「告警 ID」/`alert_id`；动作匹配规则字段集合未扩大。
- 告警 OpenAPI 整组经 `@openapi_expose` 挂到 `/openapi/v1/alerts/{list,detail,events,assign,acknowledge,reassign,close,batch-action}`，锚点为业务 `alert_id`；请求未知字段（含数据库 `id`、`team`）→ `SCHEMA_INVALID`。
- 接口关闭（网关与旧 `/api/open` 共用 `AlertsOpenAPIService`）：待响应/处理中可关，不校验处理人；未分派/已处理/已关闭类状态拒绝。页面关闭仍仅处理中且须为当前处理人。
- 列表筛选补 `resource_type` / `resource_id` 精确匹配，页面、旧路径、网关同时生效。
- 双租户测试已登记 8 个 path。
- 验证（2026-08-28，本机 Postgres，`uv run pytest ... --no-cov`）：
  - `apps/alerts/tests/test_alert_operator.py` API 关闭 + 默认关闭：**passed**
  - `apps/alerts/tests/test_filters.py`：**8 passed**
  - `apps/alerts/tests/test_open_api_operator_service.py`：**7 passed**
  - `apps/alerts/tests/test_openapi_gateway.py`：**27 passed**（含 `page_size` 越限钳制为 500）
  - `apps/alerts/tests/test_open_api_serializers_pure.py`：旧路径上限 100、网关上限 500 **passed**
  - `apps/alerts/tests/test_open_api_query_{service,views}.py`、`test_open_api_operator_views.py`、`test_action_payload_pure.py`：回归 **passed**
  - `apps/core/openapi/tests/test_governance.py::test_every_exposed_endpoint_registered_in_coverage`：**passed**
  - `web`：`pnpm exec tsx scripts/alarm-job-binding-alert-id-test.ts`：**passed**
  - 说明：同文件 `test_governance.py` 的 `test_every_coverage_reference_resolves` / `test_stale_coverage_entries_flagged` 因本分支既有 `job-mgmt/*`、`patch-mgmt/module-data` 登记与 INSTALLED_APPS 不一致失败，与本次告警暴露无关。

## Problem Statement

告警自愈作业需要拿到稳定的业务告警 ID，但动作规则把告警字段绑到作业脚本参数时，下拉里没有「告警 ID」。第三方和自动化也需要按页面同款条件拉告警、并转派 / 认领 / 关闭，但现有对外接口还挂在散落路径上，没有进入统一网关；关闭还要求调用方必须是当前处理人，自动化关单走不通。

## Solution

作业字段绑定增加「告警 ID」。把现有告警 OpenAPI（列表、详情、事件、分派、认领、转派、关闭、批量）注册到统一网关；查询与操作一律用业务 `alert_id` 定位，不用数据库主键。接口关闭允许从待响应或处理中直接关闭，不校验是否本人。页面关闭逻辑不变。旧散落路径本轮保留，关闭与筛选行为与网关对齐。

## User Stories

1. As an 告警处理规则配置人, I want 把作业脚本参数绑定到告警 ID, so that 作业平台能按业务告警 ID 回调或查单。
2. As an 自动化或第三方调用方, I want 经统一网关按与页面一致的条件查询告警列表, so that 筛到的结果和告警中心页面一致。
3. As an 自动化或第三方调用方, I want 用业务告警 ID 查询详情和关联事件, so that 不必依赖会变化的数据库主键。
4. As an 自动化或第三方调用方, I want 用业务告警 ID 分派、认领、转派和关闭告警, so that 外部流程能驱动告警生命周期。
5. As an 自动化调用方, I want 接口关闭不要求我是当前处理人，且待响应或处理中都可以关, so that 外部流程能直接关单。
6. As an 告警值班人员, I want 页面上的关闭、转派、认领规则保持不变, so that 人手操作仍受处理人身份和状态机约束。
7. As an 已接入旧告警 OpenAPI 的调用方, I want 旧路径本轮继续可用且关闭/筛选行为对齐, so that 迁移窗口内不必立刻改调用地址。

## Implementation Decisions

- 走「包装现有告警 OpenAPI 服务」：网关函数只做契约与身份注入，业务查询、组织过滤和状态机仍复用现有告警 OpenAPI 服务与告警操作器。不重写第二套开关单逻辑。
- 网关 service 名为 `alerts`。查询注入授权组织集合和可信用户身份（不级联子组织）；写操作同样注入，操作者取认证用户名。权限：查询用告警查看位，写操作用告警编辑位，权限应用为告警中心客户端。
- 操作与详情锚点只接受业务 `alert_id`（以及批量里的 `alert_ids`）。请求、响应均不暴露、不接受数据库主键 `id`。跨组织或不可见统一按不存在处理。
- 网关路径（发布后冻结）：
  - `GET alerts/list`：分页列表
  - `GET alerts/detail`：query `alert_id`
  - `GET alerts/events`：query `alert_id`
  - `POST alerts/assign` / `alerts/acknowledge` / `alerts/reassign` / `alerts/close`：body 含 `alert_id`
  - `POST alerts/batch-action`：body 含 `alert_ids`（1 至 100 条）及与单条相同的操作字段
- 网关没有 URL 路径变量，`alert_id` 放在 query（读）或 JSON body（写）。旧散落路径可继续把 `alert_id` 放在 URL 里，语义相同。
- 列表筛选与页面生效条件对齐，并补上页面会传但当前过滤集会丢掉的字段：`level`、`status`、`source_name`、`created_at_after` / `created_at_before`、`activate`、`my_alert`、`alert_id`、`title`、`content`、`has_incident`、`incident_id`、`rule_id`，新增 `resource_type`、`resource_id` 精确匹配。这些过滤对页面列表、旧 OpenAPI 和网关列表同时生效。
- 网关分页遵循平台规范：`page` 从 1 起，`page_size` 默认 20、上限 500、越限钳制。旧路径分页上限维持现有 100，避免改变已有调用方。排序仍只允许 `created_at` 与 `-created_at`。
- 分派 / 认领 / 转派的状态机与「必须是当前处理人」（认领、转派）保持现状。仅关闭走 API 模式：
  - 允许前置状态：待响应、处理中
  - 不校验调用方是否在处理人集合中
  - 未分派、已处理、已关闭 / 自动关闭 / 自动恢复一律拒绝
- API 关闭模式由操作路径显式打开，网关与旧 OpenAPI 共用。页面关闭继续走原路径：仅处理中，且必须是当前处理人。
- 作业字段绑定下拉增加「告警 ID」，取值路径为 `alert_id`。后端匹配 payload 已包含该顶层字段，解析逻辑不改。动作匹配规则的可选字段集合不因此扩大。
- 暴露使用专用请求 serializer，不复用内部业务 serializer。每个网关端点登记双租户测试。
- 本轮不下线旧散落 OpenAPI。不新增数据库字段或迁移。

## Testing Decisions

好测试只锁对外行为：给定组织身份和业务 `alert_id`，断言可见范围、状态迁移、拒绝原因和响应字段；不锁函数名或内部调用链。

- 网关每个暴露端点必须有双租户测试（读隔离、写不落到其他组织），并登记到网关覆盖表。跨组织 `alert_id` 与伪造身份头按不存在或忽略处理。
- 关闭：待响应可关、处理中可关、未分派 / 已处理 / 已关闭类状态不可关；非处理人经接口可关；同一告警走页面关闭路径时非处理人仍被拒绝。
- 认领、转派经接口时非处理人仍被拒绝。
- 操作只认 `alert_id`：只传数据库主键不能命中目标告警。
- 列表在网关和页面过滤上都能按 `resource_type`、`resource_id` 命中；其它页面条件（级别、状态、告警源、时间、活动/历史、我的告警、告警 ID / 标题 / 内容）继续可用。
- 作业字段绑定可选项包含 `alert_id` / 告警 ID。
- 优先复用现有告警 OpenAPI 查询/操作测试、告警过滤测试、动作 payload 解析测试，以及网关侧 cmdb/job 的双租户接入写法；在现有服务接缝上补 API 关闭模式，而不是只测网关包装层。

## Out of Scope

- 下线或重定向 `/api/v1/alerts/api/open`
- 修改页面关闭、转派、认领的交互和权限
- 接口从「未分派」或「已处理」关闭
- 接口转派 / 认领跳过处理人校验
- 把告警 ID 加入动作匹配规则可选字段
- 工单、Webhook 等尚未启用的动作类型
- 改统一网关本身的认证、envelope 或路由机制

## Further Notes

关闭放宽只服务自动化关单，不是放宽人手处置。业务身份与 CMDB `inst_uuid` 同一原则：对外用稳定业务键，不用内部自增主键。
