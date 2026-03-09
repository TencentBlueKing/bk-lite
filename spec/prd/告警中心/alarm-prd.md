# 告警中心（Alarm）产品PRD

版本：v1.0

日期：2026-03-03

## 1. 背景与目标

告警中心用于承接多源事件并形成可运营的告警与事故闭环，核心目标是降低噪声、提升分派效率、保证恢复闭环与处置留痕。

目标：
- 统一接入 HTTP/NATS 事件输入，形成标准化 Event 数据。
- 通过聚合与去重能力将事件收敛为可处理的 Alert。
- 支持告警处置全流程：分派、认领、转派、关闭、恢复、自动关闭。
- 提供 Incident 升级与多告警关联，承接复杂故障协同。
- 提供策略配置（分派、屏蔽、相关性）与操作日志，确保可审计。

非目标（本期不落地）：
- 不引入代码中未实现的升级链路（如 SLA 自动升级链）。
- 不引入未实现的工单系统后端联动。
- 不扩展超出现有权限模型的细粒度行级隔离策略。

## 2. 目标用户与使用场景

- 告警处理人（运维/值班）：处理告警列表，执行认领、关闭、恢复、转派。
- 团队负责人：维护分派策略、屏蔽策略、相关性规则，监控处理质量。
- 平台管理员：维护告警源接入配置、系统设置、权限与菜单。

典型场景：
- 多来源事件实时接入后自动聚合，减少重复告警。
- 告警自动分派到责任人并触发通知，责任人按流程处理。
- 多条相关告警升级为 Incident 进行统一协同处理。
- 恢复事件到达后自动恢复告警，避免人工漏关。

## 3. 本期范围与后续规划

本期范围（代码已体现）：
- 事件接入：REST receiver 与 NATS 接入。
- 告警聚合：match_rules + group_by + 窗口策略（session/sliding）聚合。
- 状态流转：Alert 与 Incident 的标准操作流。
- 策略中心：分派策略、屏蔽策略、相关性规则、系统设置。
- 处置协同：告警升级 Incident、操作日志、通知结果记录。
- 查询分析：告警/事件/事故列表筛选与趋势统计接口。

后续规划（待确认，不视为已实现）：
- 工单系统双向联动（创建、状态同步、回写）。
- SLA 驱动自动升级与值班排班协同。
- 更严格的租户/组织硬隔离查询策略。

## 4. 需求总览

- 告警事件接入
- 告警聚合与去重
- 告警状态处置
- 事故（Incident）管理
- 集成中心（Alert Source）
- 设置中心（策略、系统设置、操作日志）
- 通知与提醒
- 查询统计

## 5. 领域模型与状态机

### 5.1 领域模型

- Event：外部输入的原始事件。
- Alert：由 Event 聚合而成的可处理告警单元。
- Incident：由一个或多个 Alert 升级形成的事故对象。

关系：
- Alert 与 Event：多对多（同一告警可关联多事件，事件可按规则参与聚合）。
- Incident 与 Alert：多对多（一个事故可聚合多告警）。

配套模型：
- AlertAssignment：分派策略。
- AlertShield：屏蔽策略。
- AlarmStrategy：告警相关性/聚合策略。
- AlertReminderTask：提醒任务。
- NotifyResult：通知结果。
- OperatorLog：操作日志。
- AlertSource：告警源配置（支持软删除）。

### 5.2 Alert 状态机

状态枚举：
- `unassigned`：未分派
- `pending`：待处理（已分派未认领）
- `processing`：处理中（已认领）
- `resolved`：人工恢复
- `closed`：人工关闭
- `auto_close`：自动关闭
- `auto_recovery`：自动恢复

操作与迁移：
- assign：`unassigned -> pending`
- acknowledge：`pending -> processing`
- reassign：`processing -> pending`
- close：`processing -> closed`
- resolve：`processing -> resolved`

说明：
- 非法前置状态下操作会被拒绝。
- 操作过程中写入操作日志。

### 5.3 Incident 状态机

状态迁移：
- acknowledge：`pending -> processing`
- close：`processing -> closed`
- reopen：`closed -> processing`

### 5.4 Session 告警状态

会话状态：
- `observing`：观察中
- `confirmed`：确认告警
- `recovered`：已恢复

规则：
- 观察期超时后由定时检查转为 `confirmed`。

## 6. 关键业务流程（代码事实版）

### 6.1 事件接入与标准化

REST 入站：
- 路径：`POST /alerts/api/receiver_data`
- 校验：`source_id`、`secret`、`events` 必填。
- 通过 source adapter 执行标准化处理。

NATS 入站：
- 通过消息通道接收事件并进入同一处理主流程。
- 记录 `pusher/source_id` 等来源信息。

### 6.2 屏蔽处理

- 事件入站后优先执行屏蔽规则匹配。
- 命中屏蔽策略的事件标记为 `SHIELD`，不进入后续有效告警链路。

### 6.3 聚合与去重

- 基于相关性策略（`match_rules`、`group_by`、窗口配置）计算分组键（fingerprint）。
- 对活跃告警按 fingerprint 更新而非重复创建，降低噪声。
- 支持窗口模板（session/sliding）聚合行为。

### 6.4 分派与认领

- 告警创建后可按策略自动分派至个人/团队。
- 分派成功后进入 `pending`，处理人认领后进入 `processing`。
- 转派用于处理中告警重新分配责任人。

### 6.5 通知与提醒

- 分派动作触发通知发送。
- 通知结果持久化到 `NotifyResult`。
- 未及时处理告警可通过提醒任务轮询重发提醒。

### 6.6 恢复与自动关闭

- 恢复事件通过 `external_id` 关联历史创建事件。
- 当创建事件均被更晚恢复事件覆盖时，告警自动转 `auto_recovery`。
- 支持按策略 `close_minutes` 自动关闭，以及定时兜底自动关闭。

### 6.7 升级 Incident

- 前端支持将告警升级为 Incident。
- Incident 创建后与目标 Alert 建立关联，进入事故协同流。

## 7. 功能需求

### 7.1 告警列表与详情

- 列表筛选：按级别、状态、来源、时间范围、我的告警、是否有 Incident 等过滤。
- 批量操作：批量分派、认领、关闭、恢复（按后端支持动作）。
- 详情展示：基础信息、关联事件、关联事故、操作记录、通知结果。
- 状态约束：仅允许在合法状态执行对应操作。

### 7.2 事件列表

- 支持按来源、级别、时间、状态等条件筛选。
- 支持查看原始事件字段与解析后内容。
- 可用于告警回溯与聚合效果排查。

### 7.3 Incident 管理

- Incident 列表与详情查看。
- 支持状态操作（认领、关闭、重开）。
- 支持查看关联告警集合与进展。

### 7.4 集成中心（Integration）

- 告警源管理：新增、编辑、删除、查询。
- 支持多接入适配能力（REST/NATS 等）。
- 提供 source 级别鉴权参数（如 secret）。

### 7.5 设置中心（Settings）

- 相关性规则：定义聚合匹配与分组规则。
- 分派策略：按条件匹配责任人/责任团队与触发行为。
- 屏蔽策略：按条件屏蔽特定来源或事件模式。
- 系统设置：告警中心全局配置项。
- 操作日志：策略与系统配置变更审计。

## 8. 接口与数据契约

### 8.1 REST API（后端已注册）

- `/alerts/api/alerts`
- `/alerts/api/alerts/operator/{action}`
- `/alerts/api/events`
- `/alerts/api/incident`
- `/alerts/api/incident/operator/{action}`
- `/alerts/api/alert_source`
- `/alerts/api/assignment`
- `/alerts/api/shield`
- `/alerts/api/alarm_strategy`
- `/alerts/api/settings`
- `/alerts/api/log`
- `/alerts/api/receiver_data`

### 8.2 NATS 接口（后端已实现）

- `receive_alert_events`：接收事件并进入处理流程。
- `get_alert_trend_data`：按分钟/小时/日/周/月返回趋势统计数据。

### 8.3 关键字段（摘要）

- Event 关键字段：`event_id`、`source_id`、`external_id`、`level`、`status`、`event_time`。
- Alert 关键字段：`fingerprint`、`status`、`assignee`、`team`、`source_name`、`latest_event_time`。
- Strategy 关键字段：`match_rules`、`group_by`、`window`、`close_minutes`。
- Shield 关键字段：`suppression_time`、匹配条件集合。

## 9. 权限与组织边界

### 9.1 权限模型

- 基于菜单与权限点进行鉴权（View/Add/Edit/Delete）。
- 告警中心包含 Alarms、Incidents、Integration、Settings 等模块权限。
- 后端接口通过权限装饰器进行访问控制。

### 9.2 组织维度

- 策略中存在 `team/dispatch_team` 维度并写入告警归属。
- 当前代码层面可见团队字段承载，但未形成统一强制硬隔离查询规则。

## 10. 查询统计与审计

### 10.1 查询过滤

- Alert、Event、Incident、OperatorLog 均支持条件过滤。
- 支持时间范围筛选与分页查询。

### 10.2 趋势统计

- 提供趋势聚合接口，支持多时间粒度输出。

### 10.3 审计留痕

- 告警处置、策略变更、系统设置变更写入 OperatorLog。
- 支持按时间与类型查看操作记录。

## 11. 异常处理与边界

- 入站接口对缺失参数、非法方法进行显式错误返回。
- 自动分派/屏蔽流程中存在容错保护，单条失败通常不阻断整体处理。
- 通知失败会记录结果；提醒重发依赖轮询任务，不体现指数退避机制。

风险提示（代码已暴露）：
- 提醒任务停止流程中使用 `completed_at` 字段，但模型定义未显式体现该字段，需进一步确认。

## 12. 需求优先级（MoSCoW）

- Must：事件接入、告警聚合去重、告警状态流转、Incident 管理、策略配置、操作日志。
- Should：趋势统计、通知结果可视化、提醒轮询机制。
- Could：更丰富的告警详情联动展示、更多来源适配模板。
- Won’t（本期不做）：SLA 自动升级链、完整工单联动、复杂排班引擎。

## 13. 验收标准（按场景）

- 入站聚合场景：
  - 给定合法 source 与事件后，可创建或更新告警，重复事件按 fingerprint 收敛。
- 分派处置场景：
  - 告警可按状态执行分派/认领/转派/关闭/恢复，非法迁移被拒绝。
- 恢复闭环场景：
  - 恢复事件到达后能正确关联并触发自动恢复判定。
- 自动关闭场景：
  - 满足策略或兜底条件的告警可进入 `auto_close`。
- Incident 场景：
  - 告警可升级 Incident，Incident 支持认领、关闭、重开。
- 配置审计场景：
  - 策略与系统设置变更后可在操作日志检索到对应记录。

## 14. Event 接入数据说明（REST Receiver）

### 14.1 接口与鉴权约束

- 接口：`POST /alerts/api/receiver_data/`。
- 仅支持 `POST`，其他方法返回 400。
- 顶层参数 `source_id`、`events` 必须提供。
- 密钥优先从请求头 `SECRET` 获取；若请求头无值，则读取 body 中 `secret`。
- `source_id` 对应的告警源不存在时返回 400；密钥校验失败返回 403。

### 14.2 顶层请求体规范

| 字段 | 类型 | 必填 | 说明 | 影响功能 |
| --- | --- | --- | --- | --- |
| source_id | string | 是 | 告警源ID，定位告警源配置与字段映射 | 无法定位告警源时整包拒绝（400） |
| events | array<object> | 是 | 事件数组，至少 1 条 | 为空时整包拒绝（400） |
| secret | string | 条件必填 | 请求头未传 `SECRET` 时必填 | 缺失/错误导致鉴权失败（400/403） |

### 14.3 单条 Event 字段规范（默认 mapping）

说明：平台按告警源 `config.event_fields_mapping` 把上送字段映射到 Event 模型。下表按默认映射说明；若映射被修改，应按映射后的字段名上送。

| 字段 | 类型 | 必填级别 | 默认行为 | 对后续功能影响 |
| --- | --- | --- | --- | --- |
| title | string | 必填 | 无默认；缺失则该事件被丢弃 | 事件无法入库，后续聚合/分派/通知均不生效 |
| action | string | 强烈建议 | 默认 `created` | 决定是否作为恢复/关闭事件参与恢复链路 |
| external_id | string | 强烈建议 | 缺失时按 `item+resource_name+source_id` 自动生成 | 影响恢复事件与历史创建事件关联准确性 |
| level | string | 建议 | 缺失或非法时回落为最低级别 | 影响告警级别、策略匹配、展示优先级 |
| start_time | string(timestamp) | 建议 | 缺失时使用当前时间 | 影响窗口聚合与时序统计准确性 |
| end_time | string(timestamp) | 否 | 无 | 用于结束时间展示与分析 |
| description | string | 否 | 无 | 影响详情展示、屏蔽/分派规则匹配 |
| item | string | 否 | 无 | 影响聚合维度与自动生成 external_id |
| resource_id | string | 否 | 无 | 影响对象定位、规则匹配 |
| resource_name | string | 否 | 无 | 影响对象展示、规则匹配、external_id 回退生成 |
| resource_type | string | 否 | 无 | 影响对象类型筛选与规则匹配 |
| rule_id | string | 否 | 无 | 用于追溯触发规则 |
| value | number | 否 | 无 | 用于数值型事件展示/分析 |
| service | string | 否 | 无 | 用于服务维度查询与聚合匹配 |
| location | string | 否 | 无 | 用于位置维度筛选 |
| tags | object | 否 | 默认为空对象 | 用于扩展标签筛选 |
| labels | object | 否 | 默认为空对象 | 可承载扩展元数据；部分映射缺失时会从 labels 回退取值 |

补充：
- 时间戳支持 10 位秒级与 13 位毫秒级。
- `action` 可选值：`created`、`closed`、`recovery`。

### 14.4 必填/选填对业务链路的影响

- 入站创建：`title` 缺失会导致该条事件转换失败并跳过。
- 屏蔽策略：`source_id/level/resource/content/title` 等字段缺失会降低命中率，导致应屏蔽事件未被屏蔽。
- 聚合降噪：`level/item/resource_*` 缺失会影响分组维度质量，可能出现误聚合或不聚合。
- 自动恢复：`action` 与 `external_id` 不规范会导致恢复事件无法正确回挂到活跃告警。
- 自动分派：告警继承字段不完整会降低分派规则命中率。

### 14.5 推荐上送最小字段集（监控系统对接）

为保证“可入库 + 可聚合 + 可恢复 + 可分派”，建议每条事件至少包含：

- `title`
- `action`
- `external_id`
- `level`
- `start_time`
- `resource_id`
- `resource_name`
- `resource_type`

### 14.6 请求示例

```json
{
  "source_id": "restful",
  "events": [
    {
      "title": "gateway timeout high",
      "description": "5xx ratio exceeded threshold",
      "action": "created",
      "external_id": "gateway-timeout-20260303-001",
      "level": "1",
      "start_time": "1772476800",
      "item": "http_5xx_ratio",
      "resource_id": "gateway-01",
      "resource_name": "gateway-01",
      "resource_type": "service",
      "service": "api-gateway",
      "location": "shanghai",
      "labels": {
        "cluster": "prod-cn",
        "namespace": "gateway"
      }
    }
  ]
}
```

## 15. 实现差异与待确认项

### 15.1 前后端接口差异

- 前端存在 `aggregation_rule` 接口调用痕迹，但后端路由未注册同名接口。
- 处理策略：PRD 以已注册后端接口为准，`aggregation_rule` 标注为遗留/待确认。

### 15.2 能力待确认（代码未闭环）

- 工单联动：前端文案存在“转工单”语义，后端未发现工单联动接口。
- 组织强隔离：存在团队字段但未明确全链路强制隔离策略。
- 提醒任务字段一致性：`completed_at` 字段需确认模型定义与迁移状态。

### 15.3 确认位置（供研发核对）

- 后端路由：`server/apps/alerts/urls.py`
- 前端 API：`web/src/app/alarm/api/settings.ts`
- 提醒服务：`server/apps/alerts/service/reminder_service.py`
- 提醒模型：`server/apps/alerts/models/alert_operator.py`
