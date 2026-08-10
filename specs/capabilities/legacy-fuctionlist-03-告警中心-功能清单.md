# 告警中心 · 功能清单

> Migrated from `spec/fuctionlist/03-告警中心-功能清单.md` as legacy capability evidence.

**文档版本：** V1.1
**发布日期：** 2026-06-18
**适用范围：** BK-Lite 告警中心模块（`/alarm`）
**编制依据：** 告警中心 PRD v1.2（2026-05-28）与 `server/apps/alerts`、`web/src/app/alarm` 源代码核对；本次增量更新基于 2026-06-18 代码核对（base.py:552-568、aggregation_processor.py:136,419、instant_dispatcher.py:273,310,315）

---

## 一、模块定位

告警中心承接多源事件输入，经标准化、屏蔽、聚合去重收敛为可处理的告警（Alert），并提供分派、认领、转派、关闭、恢复、自动关闭的处置闭环；可将一个或多个告警升级为事故（Incident）进行跨团队协作研判；通过缺失检查（心跳哨兵）主动监测期望事件并对缺失合成告警。Event / Alert / Incident 均按组织（team）归属裁剪查询范围。本清单仅列代码已实现能力，PRD 明确的相关告警推荐、SLA 自动升级链、完整工单联动、复杂排班引擎本期不做。

## 二、功能清单

### 1. 事件接入

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| REST 接入 | 通用接收地址接入事件 | `POST /alerts/api/receiver_data`；仅支持 POST，其他方法返回 400；`source_id`、`events` 必填；密钥优先取请求头 `SECRET`，否则取 body `secret` | GA |
| 告警源专属 webhook | 按告警源 ID 暴露独立 webhook 接入地址 | `POST /alerts/api/source/{source_id}/webhook` | GA |
| NATS 接入 | 通过 NATS 消息通道接收事件并进入同一处理主流程 | 记录 `pusher/source_id` 等来源信息 | GA |
| K8s 接入 YAML | K8s 告警源生成部署 YAML 便于集群侧接入 | `/alerts/open_api/k8s/render` | GA |
| 字段标准化 | 经 source adapter 按告警源字段映射标准化为 Event 模型 | 默认 mapping，`title` 必填（缺失丢弃）；`external_id` 缺失按 `item+resource_name+source_id` 生成；`level` 缺失/非法回落最低级别；`start_time` 缺失用当前时间 | GA |
| 时间戳兼容 | 兼容 10 位秒级与 13 位毫秒级时间戳 | — | GA |
| 事件动作 | 事件 action 取值 | `created`（产生，默认）/ `closed`（关闭）/ `recovery`（恢复） | GA |
| 告警源类型 | 内置告警源类型 | Prometheus、Zabbix、Webhook、日志、监控、云监控、NATS、RESTful | GA |

### 2. 屏蔽处理

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 入站屏蔽 | 事件入站后优先匹配屏蔽规则，命中即标记 `SHIELD`；屏蔽在 `main()` 中位于即时旁路与聚合主路径之前执行，已屏蔽事件不产出任何告警（聚合与即时旁路均排除） | `event_operator()` 执行顺序先于 `InstantAlertDispatcher.dispatch()` 与聚合调度（`base.py:557`）；聚合查询显式 `.exclude(status=EventStatus.SHIELD)`（`aggregation_processor.py:136`）；即时旁路在 dispatch 前通过 `_exclude_shielded` 按库内最新状态二次过滤（`instant_dispatcher.py:273,310`） | GA |
| 屏蔽策略 | 屏蔽策略的配置，按条件屏蔽特定来源或事件模式 | 含匹配类型（全部匹配 / 过滤匹配）、匹配规则、屏蔽时间配置 | GA |

### 3. 聚合与去重

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 指纹聚合 | 基于相关性策略计算分组键（fingerprint），对活跃告警按 fingerprint 更新而非重复创建；聚合事件查询显式排除状态为 `SHIELD` 的事件，已屏蔽事件不参与指纹聚合 | 策略参数含 `match_rules`、`group_by`、窗口配置；`.exclude(status=EventStatus.SHIELD)`（`aggregation_processor.py:136`） | GA |
| 窗口策略 | 支持会话窗口与滑动窗口聚合行为 | 会话窗口告警有独立会话状态：`observing` 观察中 / `confirmed` 已确认 / `recovered` 已恢复；观察期超时由定时检查转 `confirmed` | GA |
| 智能降噪规则 | 相关性规则类型之一，配置聚合匹配与分组 | 策略类型 `smart_denoise`；含关联组织（可见范围）与分派组织（聚合后归属） | GA |

### 4. 缺失检查（心跳哨兵）

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 缺失检测规则 | 相关性规则类型之一，对期望心跳事件做周期性缺失监测 | 策略类型 `missing_detection`；按监听目标条件组匹配（不支持 ALL 全匹配） | GA |
| 检测周期与宽限期 | 使用 Cron 表达式配置检测周期，配合必填宽限期判定缺失 | 检测模式 `cron`；超过"期望时间 + 宽限期"未收到匹配心跳即合成缺失告警 | GA |
| 激活方式 | 规则激活方式 | `immediate` 立即激活（保存即进入监控）/ `first_heartbeat` 首条心跳激活 | GA |
| 心跳状态 | 心跳监测状态机 | `waiting` 待激活 / `monitoring` 监控中 / `alerting` 缺失告警中 | GA |
| 合成告警 | 缺失触发时按模板（名称/级别/摘要）生成告警；合成告警在事务提交后自动进入分派链路，与常规聚合/即时告警保持一致 | 未恢复期间不重复生成缺失告警；通过 `transaction.on_commit` 延迟调度 `_schedule_auto_assignment`，避免事务回滚后空跑（`aggregation_processor.py:419`） | GA |
| 自动恢复 | 再次收到任意 1 条匹配心跳即自动恢复并回到 `monitoring` | 自动恢复开关默认开启 | GA |

### 5. 告警处置

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 告警列表 | 按级别、状态、来源、时间范围、我的告警、是否有 Incident 等筛选 | — | GA |
| 告警详情 | 展示基础信息、关联事件、关联事故、操作记录、通知结果 | — | GA |
| 告警状态机 | 告警状态枚举与迁移 | 状态：`unassigned` 未分派 / `pending` 待处理 / `processing` 处理中 / `resolved` 人工恢复 / `closed` 人工关闭 / `auto_close` 自动关闭 / `auto_recovery` 自动恢复；默认 `unassigned` | GA |
| 状态操作 | 分派、认领、转派、关闭、恢复 | assign：`unassigned→pending`；acknowledge：`pending→processing`；reassign：`processing→pending`；close：`processing→closed`；resolve：`processing→resolved`；非法前置状态操作被拒绝 | GA |
| 批量操作 | 批量分派、认领、关闭、恢复 | 按后端支持动作执行 | GA |
| 自动恢复 | 恢复事件经 `external_id` 关联历史创建事件，创建事件均被更晚恢复事件覆盖时转 `auto_recovery` | — | GA |
| 自动关闭 | 按策略 `close_minutes` 自动关闭，并有定时兜底自动关闭 | `close_minutes` 默认 120 分钟；`auto_close` 默认开启 | GA |
| 操作留痕 | 处置过程写入操作日志 | — | GA |

### 6. 事件列表

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 事件查询 | 按来源、级别、时间、状态等筛选 | 事件级别：`remain` 提醒 / `warning` 预警 / `severity` 严重 / `fatal` 致命 | GA |
| 原始内容查看 | 查看原始事件字段与解析后内容，用于告警回溯与聚合排查 | — | GA |

### 7. 事故（Incident）管理与协作研判

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 告警升级 | 前端将一个或多个告警升级为 Incident 并建立关联 | Incident 与 Alert 多对多 | GA |
| Incident 列表与详情 | 列表与详情查看，查看关联告警集合与进展 | — | GA |
| 状态操作 | 认领、关闭、重开 | acknowledge：`pending→processing`；close：`processing→closed`；reopen：`closed→processing` | GA |
| 协作研判 | 负责人/协作者发布结构化协作更新 | 更新类型：观察 / 进展 / 结论 / 下一步；含作者与时间；仅负责人或协作者可发布 | GA |
| 更新回复与附件 | 协作更新支持回复与附件 | — | GA |
| 关键信息摘要 | 负责人可将更新标记为关键信息，系统输出当前判断/确认事实/下一步动作摘要 | — | GA |
| 跨团队协同 | Incident 可指定多个管理组织并关联不同归属团队的 Alert | Incident 可见不放大其内 Alert 的对象权限，Alert 查看与处置始终以自身权限为准 | GA |

### 8. 集成中心（告警源）

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 告警源管理 | 告警源的新增、编辑、删除、查询 | 支持软删除 | GA |
| 接入类型 | 告警源接入类型 | `built_in` 内置 / `customize` 自定义 | GA |
| 多接入适配 | 支持 REST / NATS 等多接入适配能力 | 提供 source 级鉴权参数（如 secret） | GA |

### 9. 设置中心

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 相关性规则 | 配置智能降噪与缺失检测两类规则 | 见"聚合与去重""缺失检查" | GA |
| 告警丰富规则 | 配置丰富规则的提供方、入参绑定、出参投影与启停 | 支持规则 CRUD、分页列表与启停；入参绑定须为对象映射，出参投影须为列表结构；提供 `metrics` 统计接口返回总规则数、启用占比、自建规则数与已丰富告警占比 | GA |
| 告警处理规则 | 配置动作规则的触发事件、匹配条件、动作类型与动作配置 | 当前已落地动作类型为 `job`；支持规则 CRUD、启停与手动触发 | GA |
| 执行记录 | 查看自动/手动触发后的动作执行记录 | 记录字段含规则名、告警标题、触发方式、触发事件、执行状态、作业链接、触发时间；支持按状态筛选 | GA |
| 分派策略 | 按条件匹配责任人/责任团队与触发行为 | 含匹配类型（全部/过滤）、匹配规则、分派人员、通知渠道、通知场景（分派/恢复）、通知频率配置 | GA |
| 屏蔽策略 | 见"屏蔽处理" | — | GA |
| 系统设置 | 告警中心全局配置项 | — | GA |
| 操作日志 | 策略与系统配置变更审计 | 日志目标类型：事件/告警/事故/系统；操作类型：添加/修改/删除/执行 | GA |

### 10. 通知与提醒

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 分派通知 | 分派动作触发通知发送 | 通知渠道来源于系统管理配置 | GA |
| 通知结果记录 | 通知结果持久化 | 结果状态：成功 / 失败 / 部分成功 | GA |
| 提醒任务 | 未及时处理告警通过提醒任务轮询重发提醒 | 冗余存储当前提醒频率与最大提醒次数；依赖轮询任务，不含指数退避机制 | GA |

### 11. 查询统计

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 条件过滤 | Alert / Event / Incident / OperatorLog 支持条件过滤、时间范围筛选与分页 | — | GA |
| 趋势统计 | 趋势聚合统计 | 支持分钟/小时/日/周/月多粒度（NATS 接口 `get_alert_trend_data`） | GA |
| 告警源统计 | 统计可见告警关联的告警源数量、启用率与活跃量 | 非超管仅统计当前组织与对象权限范围内可见告警反推出来的告警源 | GA |
| 通知效果统计 | 统计通知总量、成功量、失败量与成功率 | 仅统计当前组织与对象权限范围内可见告警关联的通知结果 | GA |
| 通知渠道统计 | 按通知渠道统计成功率 | 仅统计当前组织与对象权限范围内可见告警关联的通知结果 | GA |

相关 PRD：[[spec/prd/告警中心/告警.md#3. 关键能力]]；相关架构：[[spec/ARD/modules/alerts.md#5. 任务与 NATS【已实现/已存在】]]
> 证据来源：server/apps/alerts/nats/nats.py:78-137，server/apps/alerts/nats/nats.py:403-536　|　同步基线：a9d981aeb　|　【已实现】

## 三、能力边界与约束

本期不实现：告警详情侧的相关告警自动推荐与一键关联辅助、工单系统双向联动、SLA 驱动自动升级链与值班排班协同。前端存在 `aggregation_rule` 接口调用痕迹但后端未注册同名接口，以已注册后端接口为准。前端文案存在"转工单"语义但后端无工单联动接口。告警状态迁移严格按状态机执行，非法前置状态下操作被拒绝。Event / Alert 为单一数据归属对象，归属确定后不变（Event 由接入层按告警源绑定确定，Alert 由相关性规则的分派组织决定）；Incident 为协同对象，可关联多团队 Alert 但不放大其对象权限。缺失检测规则的监听目标不支持 ALL 全匹配。提醒重发依赖轮询，无指数退避。屏蔽在事件接入后、聚合与即时旁路执行前生效（`base.py:557`）：聚合主路径通过 `.exclude(status=EventStatus.SHIELD)` 排除已屏蔽事件（`aggregation_processor.py:136`），即时旁路通过 `_exclude_shielded` 按库内最新状态二次过滤（`instant_dispatcher.py:273,310`），屏蔽对两条产出路径均全链路生效。告警处理当前仅开放作业型动作，ITSM 与 Webhook 仍未启用；执行结果依赖签名回调异步回写。

## 四、平台协同

告警中心是平台统一的多源事件汇聚与处置中枢：监控系统、日志系统的告警事件可作为告警源经 REST / NATS 标准化接入；通知渠道与组织用户来源于系统管理统一配置；Event / Alert / Incident 按组织归属裁剪，组织与权限点由系统管理 RBAC 提供；K8s 告警源可生成部署 YAML 由集群侧接入。

## 五、支持的告警源与状态枚举范围

以下范围均取自 `server/apps/alerts/constants`（`constants.py` 枚举 + `init_data.py` 初始化数据），全部为开箱即用的内置能力。

### 5.1 内置告警源（接入通道）

平台随包初始化 **6 个**内置告警源（`access_type=built_in`），覆盖 **8 类**告警源类型（`AlertsSourceTypes`）。源类型可由自定义告警源（`customize`）复用。

| 内置告警源 | source_type | 接入方式 |
|---|---|---|
| RESTful | restful | REST API 推送标准 Event |
| NATS | nats | 经 NATS 网关接收 |
| Prometheus | prometheus | 兼容 Alertmanager Webhook，自动转标准事件 |
| Zabbix | zabbix | Webhook Media Type，按 ProblemId 闭环恢复 |
| K8s | restful（复用） | Kubernetes Event Exporter 经该通道推送 |
| SNMP Trap | restful（复用） | 独立 bridge 经 source webhook 推送规范化事件 |

> 告警源类型枚举（`AlertsSourceTypes`，共 8 类）：`prometheus`、`zabbix`、`webhook`、`log`（日志）、`monitor`（监控）、`cloud`（云监控）、`nats`、`restful`。其中 K8s、SNMP Trap 复用 RESTful 适配器接入。

### 5.2 事件等级体系

| 维度 | 取值 |
|---|---|
| 事件级别（`EventLevel`，4 级） | remain 提醒 / warning 预警 / severity 严重 / fatal 致命 |
| 初始化级别（`init_data.DEFAULT_LEVEL`） | Critical 严重 / Error 错误 / Warning 警告 / Info 提醒（Event 4 级；Alert、Incident 各 3 级，不含 Info） |
| 事件类型（`EventType`） | 0 告警事件 / 1 恢复事件 |
| 事件动作（`EventAction`） | created 产生 / closed 关闭 / recovery 恢复 |

### 5.3 状态机取值

| 状态机 | 取值（中文） |
|---|---|
| 事件状态（`EventStatus`） | received 已接收 / pending 待响应 / processing 处理中 / resolved 已处理 / closed 已关闭 / shield 已屏蔽 |
| 告警状态（`AlertStatus`） | pending 待响应 / processing 处理中 / resolved 已处理 / closed 已关闭 / unassigned 未分派 / auto_close 自动关闭 / auto_recovery 自动恢复（活跃态：pending/processing/unassigned；关闭态：closed/auto_close/auto_recovery） |
| 会话 Alert 状态（`SessionStatus`） | observing 观察中 / confirmed 已确认 / recovered 已恢复 |
| 事故状态（`IncidentStatus`） | pending 待响应 / processing 处理中 / resolved 已处理 / closed 已关闭 |
| 告警操作（`AlertOperate`） | acknowledge 认领 / close 关闭 / reassign 转派 / assign 分派 |

### 5.4 相关性规则窗口类型

| 维度 | 取值 |
|---|---|
| 窗口类型（`WindowType`，定义 3 类） | sliding 滑动窗口 / fixed 固定窗口 / session 会话窗口 |
| 窗口对齐（`Alignment`） | day 天对齐 / hour 小时对齐 / minute 分钟对齐 |
| 策略类型（`AlarmStrategyType`） | smart_denoise 智能降噪 / missing_detection 缺失检测 |
| 心跳激活方式（`HeartbeatActivationMode`） | first_heartbeat 首条心跳激活 / immediate 立即激活 |
| 分派/屏蔽匹配（`AlertAssignmentMatchType` / `AlertShieldMatchType`） | all 全部匹配 / filter 过滤匹配 |

### 5.5 通知渠道

通知渠道类型不在告警中心硬编码，而来源于系统管理统一配置（告警分派/屏蔽与未分派告警通知均引用 `notify_channels`）。分派通知场景（`AlertAssignmentNotificationScenario`）支持 assignment 分派 / recovered 恢复；通知结果（`NotifyResultStatus`）枚举 success / failed / partial_success。

> 说明：以上枚举均直接取自 `apps/alerts/constants` 源码。窗口类型常量定义 3 类（sliding/fixed/session），其中运行时窗口工厂 `aggregation/window/factory.py` 当前在 sliding 与 session 间选择（缺失检测口径与"窗口类型不支持 ALL 全匹配"约束见第三章）。源码中内置告警源与上述枚举均未标注 Beta，全部为 GA。


## 六、枚举与对象取值明细附录

> 本附录列出 告警中心 模块的关键枚举与对象取值，取自源码常量定义。共 26 类、91 项取值。

### 事件动作

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 产生 | `created` | 事件产生（创建） |
| 关闭 | `closed` | 关闭该事件不再追踪 |
| 恢复 | `recovery` | 事件恢复正常 |

### 事件状态

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 待响应 | `pending` | 事件待响应处理 |
| 处理中 | `processing` | 事件正在处理中 |
| 已处理 | `resolved` | 事件已处理完成 |
| 已关闭 | `closed` | 事件已关闭归档 |
| 已屏蔽 | `shield` | 事件被屏蔽忽略 |
| 已接收 | `received` | 事件已接收待分流 |

### 事件类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 告警事件 | `0` | 告警类事件，表示异常 |
| 恢复事件 | `1` | 恢复类事件，表示恢复 |

### 事件级别

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 提醒 | `remain` | 最低级别的提醒类事件 |
| 预警 | `warning` | 预警级别事件 |
| 严重 | `severity` | 严重级别事件 |
| 致命 | `fatal` | 最高级别的致命事件 |

### 事故操作

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 认领 | `acknowledge` | 认领该起事故 |
| 关闭 | `close` | 关闭该起事故 |
| 转派 | `reassign` | 转派事故给他人 |
| 分派 | `assign` | 分派该起事故 |

### 事故状态

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 待响应 | `pending` | 事故待响应处理 |
| 处理中 | `processing` | 事故正在处理中 |
| 已处理 | `resolved` | 事故已处理完成 |
| 已关闭 | `closed` | 事故已关闭归档 |

### 会话告警状态

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 观察中 | `observing` | 观察中的虚拟告警 |
| 已确认 | `confirmed` | 已确认为正式告警 |
| 已恢复 | `recovered` | 虚拟告警未转正即恢复 |

### 内置告警源

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| RESTful | `restful` | 内置 RESTful 告警源 |
| NATS | `nats` | 内置 NATS 告警源 |
| Prometheus | `prometheus` | 内置 Prometheus 告警源 |
| Zabbix | `zabbix` | 内置 Zabbix 告警源 |
| K8s | `k8s` | 内置 K8s 告警源（基于 RESTful） |
| SNMP Trap | `snmp_trap` | 内置 SNMP Trap 告警源（基于 RESTful） |

### 分派匹配类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 全部匹配 | `all` | 分派规则匹配全部 |
| 过滤匹配 | `filter` | 分派规则按过滤条件匹配 |

### 分派通知场景

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 分派 | `assignment` | 告警分派时通知 |
| 恢复 | `recovered` | 告警恢复时通知 |

### 协作更新类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 观察 | `observation` | 事故协作中的观察记录 |
| 进展 | `progress` | 事故协作中的进展记录 |
| 结论 | `conclusion` | 事故协作中的结论记录 |
| 下一步 | `next_step` | 事故协作中的下一步计划 |

### 告警操作

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 认领 | `acknowledge` | 认领该条告警 |
| 关闭 | `close` | 关闭该条告警 |
| 转派 | `reassign` | 转派告警给他人 |
| 分派 | `assign` | 分派该条告警 |

### 告警源接入类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 内置 | `built_in` | 系统内置的告警源 |
| 自定义 | `customize` | 用户自定义接入的告警源 |

### 告警源类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| Prometheus | `prometheus` | 对接 Prometheus 的告警源 |
| Zabbix | `zabbix` | 对接 Zabbix 的告警源 |
| Webhook | `webhook` | 通过 Webhook 推送的告警源 |
| 日志 | `log` | 来自日志的告警源 |
| 监控 | `monitor` | 来自监控中心的告警源 |
| 云监控 | `cloud` | 来自云监控的告警源 |
| NATS | `nats` | 通过 NATS 接入的告警源 |
| RESTFul | `restful` | 通过 RESTful 接口接入的告警源 |

### 告警状态

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 待响应 | `pending` | 告警待响应处理 |
| 处理中 | `processing` | 告警正在处理中 |
| 已处理 | `resolved` | 告警已处理完成 |
| 已关闭 | `closed` | 告警已关闭归档 |
| 未分派 | `unassigned` | 告警尚未分派 |
| 自动关闭 | `auto_close` | 告警被系统自动关闭 |
| 自动恢复 | `auto_recovery` | 告警被系统自动恢复 |

### 告警策略类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 智能降噪 | `smart_denoise` | 智能降噪策略 |
| 缺失检测 | `missing_detection` | 缺失检测（心跳）策略 |

### 对象级别类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 事件 | `event` | 对象为事件级别 |
| 告警 | `alert` | 对象为告警级别 |
| 事故 | `incident` | 对象为事故级别 |

### 屏蔽匹配类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 全部匹配 | `all` | 屏蔽规则匹配全部 |
| 过滤匹配 | `filter` | 屏蔽规则按过滤条件匹配 |

### 心跳检测模式

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| Cron 表达式 | `cron` | 按 Cron 表达式做心跳检测 |

### 心跳激活模式

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 首条心跳激活 | `first_heartbeat` | 收到首条心跳后激活 |
| 立即激活 | `immediate` | 创建后立即激活 |

### 心跳状态

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 待激活 | `waiting` | 心跳待激活状态 |
| 监控中 | `monitoring` | 心跳正在监控中 |
| 缺失告警中 | `alerting` | 心跳缺失正在告警 |

### 操作日志目标类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 事件 | `event` | 操作日志目标为事件 |
| 告警 | `alert` | 操作日志目标为告警 |
| 事故 | `incident` | 操作日志目标为事故 |
| 系统 | `system` | 操作日志目标为系统 |

### 日志操作类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 添加 | `add` | 新增类操作记录 |
| 修改 | `modify` | 修改类操作记录 |
| 删除 | `delete` | 删除类操作记录 |
| 执行 | `execute` | 执行类操作记录 |

### 窗口对齐方式

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 天对齐 | `day` | 窗口按天对齐 |
| 小时对齐 | `hour` | 窗口按小时对齐 |
| 分钟对齐 | `minute` | 窗口按分钟对齐 |

### 窗口类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 滑动窗口 | `sliding` | 聚合采用滑动窗口 |
| 固定窗口 | `fixed` | 聚合采用固定窗口 |
| 会话窗口 | `session` | 聚合采用会话窗口 |

### 通知结果

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 成功 | `success` | 通知发送成功 |
| 失败 | `failed` | 通知发送失败 |
| 部分成功 | `partial_success` | 通知部分成功 |
