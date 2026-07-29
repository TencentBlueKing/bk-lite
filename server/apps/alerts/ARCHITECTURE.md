# Alerts 告警中心业务与技术架构

本文描述 `apps.alerts` 当前代码实现对应的业务边界、后端分层、核心数据模型和完整业务链路。图中流程以当前代码为准，覆盖告警接入、事件处理、告警生成、恢复、分派、通知、升级、自动处置和事故管理。

## 1. 模块定位

Alerts 是 BK-Lite 的告警中心，负责把不同监控系统产生的原始事件转换为统一事件，通过屏蔽、丰富、即时告警、周期聚合和恢复判断形成可运营的告警，再驱动分派、通知、提醒、升级、自动处置和事故协同。

核心业务对象分为三层：

- `Event`：来自监控源的原始或标准化事件，是接入、去重、屏蔽和聚合的输入。
- `Alert`：需要人员或自动化系统处理的告警实例，承载状态、责任人、提醒、升级和处置生命周期。
- `Incident`：由一个或多个相关告警组成的事故，用于更高层级的协同和跟踪。

模块不负责资产主数据、用户组织、作业执行和消息通道的具体实现，而是通过 CMDB、System Management、Job Management 等模块提供的 RPC/NATS 接口完成协作。

## 2. 业务架构图

```mermaid
flowchart LR
    subgraph Sources["事件来源"]
        REST["REST / Webhook"]
        NATS["NATS 内部事件"]
        PROM["Prometheus"]
        ZBX["Zabbix"]
        SNMP["SNMP Trap"]
        K8S["Kubernetes Event"]
    end

    subgraph Ingress["接入与事件治理"]
        AUTH["来源认证与租户校验"]
        ADAPTER["Source Adapter\n字段映射与标准化"]
        IDEMP["事件标识与幂等"]
        ENRICH["CMDB 事件丰富"]
        SHIELD["事件屏蔽"]
        EVENT[("Event")]
    end

    subgraph Detection["检测与告警生成"]
        INSTANT["即时告警策略"]
        AGG["周期聚合 / 降噪"]
        MISSING["缺失检测"]
        RECOVERY["恢复匹配"]
        FINGERPRINT["活跃指纹租约"]
        ALERT[("Alert")]
    end

    subgraph Operation["告警运营"]
        ASSIGN["自动 / 手动分派"]
        NOTIFY["通知"]
        REMIND["提醒"]
        ESCALATE["责任人升级"]
        AUTOCLOSE["自动关闭 / 会话超时"]
        ACTION["自动处置 Action"]
        INCIDENT[("Incident")]
    end

    subgraph External["外部业务能力"]
        CMDB["CMDB\n资产与组织数据"]
        SYS["System Management\n用户与通知通道"]
        JOB["Job Management\n脚本与作业执行"]
        CELERY["Celery Worker / Beat"]
    end

    REST & NATS & PROM & ZBX & SNMP & K8S --> AUTH
    AUTH --> ADAPTER --> IDEMP --> ENRICH --> SHIELD --> EVENT
    ENRICH --> CMDB
    EVENT --> INSTANT & AGG & MISSING & RECOVERY
    INSTANT & AGG & MISSING --> FINGERPRINT --> ALERT
    RECOVERY --> ALERT
    ALERT --> ASSIGN & NOTIFY & REMIND & ESCALATE & AUTOCLOSE & ACTION & INCIDENT
    ASSIGN & NOTIFY & REMIND & ESCALATE --> SYS
    ACTION --> JOB
    AGG & MISSING & REMIND & ESCALATE & AUTOCLOSE & ACTION --> CELERY
```

## 3. 后端技术架构

```mermaid
flowchart TB
    subgraph Interface["接口层"]
        API["DRF ViewSet / Receiver API"]
        NATSAPI["NATS RPC Handler"]
        TASK["Celery Task / Beat"]
        CALLBACK["Job Callback"]
    end

    subgraph Application["业务编排层"]
        ADAPTER["Source Adapter"]
        AGGREGATION["Aggregation Processor"]
        LIFECYCLE["Alert Lifecycle Service"]
        ACTIONENGINE["Action Engine"]
        ASSIGNMENT["Assignment Operator"]
        REMINDER["Reminder Service"]
        ESCALATION["Escalation Service"]
        OUTBOX["Outbox Service"]
    end

    subgraph Domain["领域与规则层"]
        MATCHER["策略 / 条件匹配"]
        BUILDER["Alert / Synthetic Builder"]
        RECOVERY["Recovery Handler / Checker"]
        SCOPE["租户与权限范围"]
        FP["Active Fingerprint Lease"]
    end

    subgraph Persistence["持久化层"]
        EVENT[("Event")]
        ALERT[("Alert")]
        INCIDENT[("Incident")]
        CONFIG[("策略 / 规则 / 提醒 / 升级")]
        OUTBOXDB[("AlertOutbox")]
        EXECUTION[("ActionExecution")]
    end

    subgraph Integration["集成层"]
        CMDBRPC["CMDB RPC / NATS"]
        SYSTEMRPC["System Management RPC"]
        JOBRPC["Job Management RPC"]
        BROKER["Celery Broker"]
    end

    API & NATSAPI --> ADAPTER
    TASK --> AGGREGATION & REMINDER & ESCALATION & OUTBOX
    CALLBACK --> ACTIONENGINE
    ADAPTER --> MATCHER & SCOPE
    AGGREGATION --> MATCHER & BUILDER & RECOVERY
    BUILDER --> FP & LIFECYCLE
    LIFECYCLE --> ASSIGNMENT & ACTIONENGINE
    ASSIGNMENT & ACTIONENGINE & REMINDER & ESCALATION --> OUTBOX
    ADAPTER --> EVENT
    BUILDER --> ALERT
    API --> INCIDENT & CONFIG
    ACTIONENGINE --> EXECUTION
    OUTBOX --> OUTBOXDB
    OUTBOXDB --> BROKER
    ADAPTER --> CMDBRPC
    ASSIGNMENT & REMINDER & ESCALATION --> SYSTEMRPC
    ACTIONENGINE --> JOBRPC
```

### 3.1 分层职责

| 层级 | 主要职责 | 关键目录或文件 |
| --- | --- | --- |
| 接口层 | 认证、参数解析、权限校验、HTTP/NATS 响应适配 | `views/`、`nats/nats.py` |
| 接入适配 | 来源配置、字段映射、标准化、事件入库、接入统计 | `common/source_adapter/` |
| 聚合检测 | 即时匹配、周期聚合、缺失检测、会话超时 | `aggregation/` |
| 生命周期 | 统一分发 created、assigned 等生命周期副作用 | `service/alert_lifecycle.py` |
| 告警运营 | 分派、通知、提醒、升级、自动关闭 | `common/assignment.py`、`service/` |
| 自动处置 | 动作规则匹配、目标解析、作业执行、callback | `action/`、`views/action.py` |
| 可靠投递 | 事务内记录副作用、提交后投递、失败重试 | `service/outbox.py`、`models/outbox.py` |
| 权限边界 | 当前团队、子团队、对象权限和 JSON team 查询 | `utils/permission_scope.py`、`core/utils/viewset_utils.py` |

## 4. 核心数据模型及关系

```mermaid
erDiagram
    AlertSource ||--o{ Event : produces
    AlarmStrategy ||--o{ Alert : generates
    Event }o--o{ Alert : aggregated_into
    Alert }o--o{ Incident : grouped_into
    Alert ||--o{ ReminderTask : schedules
    Alert ||--o{ EscalationRecord : escalates
    Alert ||--o{ ActionExecution : triggers
    ActionRule ||--o{ ActionExecution : defines
    Alert ||--o| ActiveAlertFingerprint : owns
    AlertOutbox }o--|| Alert : references_by_payload

    Event {
        bigint id PK
        string event_id
        string external_id
        string source_id
        string push_source_id
        json team
        string action
        string status
        datetime start_time
    }

    Alert {
        bigint id PK
        string alert_id
        string fingerprint
        json team
        string status
        string level
        json operator
        datetime created_at
    }

    Incident {
        bigint id PK
        string incident_id
        json team
        string status
        string level
    }

    AlertOutbox {
        bigint id PK
        string kind
        string idempotency_key UK
        string status
        int attempts
        datetime next_retry_at
        json payload
    }
```

### 4.1 Alert 状态机

```mermaid
stateDiagram-v2
    [*] --> unassigned: 告警生成
    unassigned --> pending: 自动或手动分派
    pending --> processing: 认领 / 开始处理
    processing --> resolved: 处理完成
    pending --> resolved: 直接处理
    unassigned --> closed: 手动关闭
    pending --> closed: 手动关闭
    processing --> closed: 手动关闭
    unassigned --> auto_close: 自动关闭
    pending --> auto_close: 自动关闭
    processing --> auto_close: 自动关闭
    unassigned --> auto_recovery: 恢复事件
    pending --> auto_recovery: 恢复事件
    processing --> auto_recovery: 恢复事件
    resolved --> [*]
    closed --> [*]
    auto_close --> [*]
    auto_recovery --> [*]
```

进入 `resolved`、`closed`、`auto_close` 或 `auto_recovery` 等非活跃状态后，告警释放活跃指纹租约，后续同一指纹可以重新形成新告警。

## 5. 告警接入与生成主流程

```mermaid
flowchart TD
    START(["HTTP / NATS 接收事件"]) --> SOURCE{"告警源存在且认证通过?"}
    SOURCE -- 否 --> REJECT["拒绝请求并返回错误"]
    SOURCE -- 是 --> NORMALIZE["Adapter 字段映射、时间和级别标准化"]
    NORMALIZE --> VALIDATE{"必填字段与格式有效?"}
    VALIDATE -- 否 --> SKIP["计入 skipped / errored"]
    VALIDATE -- 是 --> EXTERNAL["生成或解析 external_id、event_id"]
    EXTERNAL --> ENRICH["按事件 team 调用 CMDB 丰富"]
    ENRICH --> SAVE["幂等写入 Event"]
    SAVE --> SHIELD{"命中屏蔽规则?"}
    SHIELD -- 是 --> SHIELDED["Event 标记 SHIELD，不进入建警"]
    SHIELD -- 否 --> RECOVERY{"是否恢复事件?"}
    RECOVERY -- 是 --> RECOVERY_FLOW["进入恢复匹配流程"]
    RECOVERY -- 否 --> INSTANT{"命中即时策略?"}
    INSTANT -- 是 --> BUILD_INSTANT["即时创建 Alert"]
    INSTANT -- 否 --> WAIT_AGG["等待 Celery Beat 周期聚合"]
    WAIT_AGG --> MATCH_STRATEGY["匹配降噪 / 缺失检测策略"]
    MATCH_STRATEGY --> BUILD_AGG["聚合或合成 Alert"]
    BUILD_INSTANT & BUILD_AGG --> CLAIM{"成功占用活跃 fingerprint?"}
    CLAIM -- 否 --> DEDUP["复用或跳过已有活跃告警"]
    CLAIM -- 是 --> ALERT["写入 Alert 并关联 Event"]
    ALERT --> LIFECYCLE["分发 created 生命周期事件"]
    LIFECYCLE --> OUTBOX["记录自动分派与 Action outbox"]
    OUTBOX --> RESULT["返回 received / accepted / skipped / errored"]
    SKIP --> RESULT
    SHIELDED --> RESULT
```

### 5.1 接入结果契约

- 全部接受：HTTP `200`，NATS `result=true`。
- 部分接受：HTTP `207`，响应携带接受、跳过和错误数量。
- 全部拒绝：HTTP `422`，NATS `result=false`。
- 接入层返回实际处理结果，不以输入数组长度冒充成功写入数量。

## 6. 即时告警、周期聚合与缺失检测

```mermaid
flowchart LR
    EVENT[("未屏蔽 Event")] --> ROUTE{"策略类型"}

    ROUTE -->|instant| CACHE["加载即时策略缓存"]
    CACHE --> MATCH1["规则匹配"]
    MATCH1 --> BATCH["同步或有界异步批量建警"]

    ROUTE -->|smart_denoise| BEAT["Celery Beat 聚合任务"]
    BEAT --> LOCK["聚合任务互斥锁"]
    LOCK --> WINDOW["按时间窗口查询候选事件"]
    WINDOW --> MATCH2["策略匹配与 group_by 聚合"]
    MATCH2 --> BUILD["AlertBuilder 创建或更新告警"]

    ROUTE -->|missing_detection| HEARTBEAT["检查心跳 / cron / 宽限期"]
    HEARTBEAT --> MISSING{"超过 deadline 且仍缺失?"}
    MISSING -- 是 --> SYNTHETIC["SyntheticAlertBuilder 创建合成告警"]
    MISSING -- 否 --> KEEP["更新运行时状态"]

    BATCH & BUILD & SYNTHETIC --> LEASE["ActiveAlertFingerprint 数据库唯一租约"]
    LEASE --> CREATED["Alert created"]
    CREATED --> SIDE_EFFECT["统一生命周期副作用"]
```

三条建警入口共享相同约束：

- 使用数据库唯一活跃指纹租约避免周期任务、即时任务或重试并发重复建警。
- 创建成功后统一触发 `created` Action 和自动分派，不允许入口各自遗漏生命周期钩子。
- Celery 核心任务异常继续向上抛出，使任务保持失败状态并可被监控或重试。

## 7. 恢复与自动关闭流程

```mermaid
flowchart TD
    RECOVERY_EVENT[("恢复 Event")] --> KEY["构造复合恢复键\nsource_id + push_source_id + external_id + team"]
    KEY --> FIND["查找同租户同来源的活跃 Event / Alert"]
    FIND --> UNIQUE{"匹配是否唯一且有效?"}
    UNIQUE -- 否 --> IGNORE["记录无法匹配或歧义，不跨来源恢复"]
    UNIQUE -- 是 --> LINK["关联恢复 Event"]
    LINK --> UPDATE["Alert 状态改为 auto_recovery"]
    UPDATE --> RELEASE["释放活跃 fingerprint 租约"]
    RELEASE --> STOP["停止提醒与升级"]
    STOP --> DONE["恢复流程结束"]

    TIMER(["Celery Beat"]) --> AUTOCLOSE["按主键游标分批扫描活跃告警"]
    AUTOCLOSE --> EXPIRED{"达到自动关闭条件?"}
    EXPIRED -- 是 --> CLOSE["状态改为 auto_close"]
    EXPIRED -- 否 --> NEXT["进入下一批"]
    CLOSE --> RELEASE

    TIMER --> SESSION["分批扫描 observing 会话告警"]
    SESSION --> TIMEOUT{"session_end_time 已到?"}
    TIMEOUT -- 是 --> CONFIRM["确认告警并触发分派"]
    TIMEOUT -- 否 --> NEXT
```

恢复匹配禁止仅按 `external_id` 跨全局查询，以免同一外部标识在不同来源或团队之间串写状态。

## 8. 告警分派、通知、提醒与升级

```mermaid
flowchart TD
    CREATED[("新建 Alert")] --> ASSIGN_INTENT["记录 auto_assignment outbox"]
    ASSIGN_INTENT --> WORKER["Outbox Worker"]
    WORKER --> RULE["匹配自动分派规则"]
    RULE --> FOUND{"找到有效责任人?"}
    FOUND -- 是 --> ASSIGN["写 operator，状态变为 pending"]
    FOUND -- 否 --> UNASSIGNED["保持 unassigned"]
    ASSIGN --> ASSIGNED_ACTION["触发 assigned 生命周期 Action"]
    ASSIGN --> NOTICE["构造分派通知"]
    NOTICE --> NOTIFY_OUTBOX["记录 notification outbox"]

    ASSIGN --> REMINDER["创建或更新 ReminderTask"]
    REMINDER --> DUE{"到达 next_reminder_time?"}
    DUE -- 是 --> REMINDER_OUTBOX["事务内记录 reminder notification outbox\n并推进提醒次数与下次时间"]
    DUE -- 否 --> WAIT["等待下一轮 Beat"]

    ASSIGN --> ESCALATION["创建升级状态"]
    ESCALATION --> ESC_DUE{"达到当前升级层级时限?"}
    ESC_DUE -- 是 --> ESC_OUTBOX["事务内记录 escalation notification outbox\n并推进层级"]
    ESC_DUE -- 否 --> WAIT

    NOTIFY_OUTBOX & REMINDER_OUTBOX & ESC_OUTBOX --> DELIVER["System Management 消息通道"]
    DELIVER --> CHANNEL["邮件 / 短信 / 企微 / 飞书等"]
```

### 8.1 Outbox 可靠投递

```mermaid
stateDiagram-v2
    [*] --> pending: 业务事务内创建
    pending --> delivering: Worker 条件抢占
    delivering --> delivered: 外部副作用成功
    delivering --> pending: 失败且可重试
    delivering --> failed: 达到最大尝试次数
    pending --> delivering: Beat 重扫 next_retry_at
    delivering --> pending: delivering 租约超时恢复
    delivered --> [*]
    failed --> [*]
```

Outbox 保证数据库业务状态和待执行副作用同时提交。Broker 首次入队失败时记录仍保持 `pending`，周期扫描会继续投递。`idempotency_key` 防止提醒、升级、动作和自动分派因重复请求产生重复副作用。

## 9. Action 自动处置完整链路

```mermaid
sequenceDiagram
    participant Lifecycle as Alert Lifecycle
    participant Outbox as AlertOutbox
    participant Engine as ActionEngine
    participant Rule as ActionRule
    participant Resolver as TargetResolver
    participant Job as Job Management
    participant Callback as Action Callback API
    participant Execution as ActionExecution

    Lifecycle->>Outbox: 记录 action(alert_id, event_name)
    Outbox->>Engine: 投递生命周期动作
    Engine->>Rule: 按事件类型、告警字段和 team 匹配规则
    Rule-->>Engine: 返回匹配规则
    Engine->>Execution: 以幂等键创建 running 记录
    Engine->>Resolver: 计算 alert.team 与 rule.team 的有效交集
    Resolver->>Job: 按有效团队读取脚本并解析目标
    Job-->>Engine: 返回 job_task_id 或业务失败
    Engine->>Execution: 更新 running / config_error / failed
    Job->>Callback: 签名 callback(job_task_id, status, result)
    Callback->>Execution: 幂等更新 success / failed
    Callback-->>Job: 返回稳定 callback 响应
```

关键约束：

- 当前已接入 Action 的生命周期事件包括 `created`、`assigned`、`acknowledged`、`reassigned`、`closed` 和 `resolved`；自动恢复目前只更新告警状态并停止提醒，不派发独立的 `recovered` Action。
- 自动触发使用稳定幂等键，同一规则、告警和已接入 Action 的生命周期事件只产生一次执行。
- 手工触发要求调用方提供幂等键，网络重试不会重复执行远程作业。
- 脚本查询、目标解析和作业下发统一使用 `alert.team ∩ rule.team`，禁止通过多团队规则扩大执行范围。
- Job 回调需要签名校验，重复 callback 不产生重复状态副作用。
- 业务失败必须反映到 `ActionExecution` 和 API 返回值，Celery 不把异常任务标记为成功。

## 10. Incident 事故协同流程

```mermaid
flowchart TD
    ALERTS[("当前团队可见 Alert")] --> CREATE["创建 Incident"]
    CREATE --> VALIDATE["校验全部 Alert 均在当前授权范围"]
    VALIDATE --> INCIDENT[("Incident")]
    INCIDENT --> ADD["追加关联告警"]
    INCIDENT --> REMOVE["移除关联告警"]
    INCIDENT --> UPDATE["更新事故状态、级别和负责人"]
    ADD & REMOVE & UPDATE --> REVALIDATE["重新执行同一租户权限校验"]
    REVALIDATE --> AUDIT["记录操作日志"]
```

list、detail、create、update、add-alert 和 remove-alert 使用一致的团队范围。未授权告警 ID 不会被用于查询或回显标题，避免通过错误响应枚举跨团队敏感信息。

## 11. 权限、事务和资源边界

### 11.1 租户与权限

- HTTP 请求从当前团队 Cookie 和用户组织树计算查询范围。
- NATS/RPC 从显式 `user_info`、团队和权限规则计算范围；缺少组织或授权上下文时 fail closed。
- JSON `team` 成员查询通过统一跨数据库 helper 实现，兼容支持 JSON contains 的数据库和 SQLite fallback。
- Alert、Event、Incident、ActionRule、ActionExecution、EnrichmentRule 及统计接口使用相同范围语义。

### 11.2 事务与幂等

- 告警状态更新与 outbox 创建处于同一数据库事务。
- AlertOutbox、ActionExecution 和 ActiveAlertFingerprint 使用数据库唯一约束裁决并发。
- 提醒次数、升级层级和对应通知意图在同一事务内推进，避免状态已更新但通知永久丢失。
- 恢复、关闭和自动恢复终态统一释放活跃指纹租约。

### 11.3 资源边界

- 自动关闭和会话超时使用主键游标分批扫描，不一次性加载全部告警。
- 即时告警和自动分派按配置阈值或固定批次处理。
- Outbox 设置最大尝试次数、指数退避、重试时间和 delivering 超时恢复。
- 接入结果和日志记录统计及标识，不记录完整敏感事件正文、凭据或大 payload。

## 12. 可观测性与排障入口

| 排障目标 | 主要标识或数据 |
| --- | --- |
| 接入是否丢事件 | `received`、`accepted`、`skipped`、`errored`、`source_id` |
| Event 是否形成 Alert | `event_id`、`external_id`、策略 ID、fingerprint |
| 是否发生重复建警 | `ActiveAlertFingerprint.fingerprint`、关联 Alert |
| 自动分派停在哪一步 | Alert 状态、operator、auto_assignment outbox 状态 |
| 通知是否投递 | AlertOutbox kind、status、attempts、next_retry_at、last_error |
| 自动处置是否执行 | ActionExecution idempotency_key、status、job_task_id |
| 恢复为何未生效 | source_id、push_source_id、external_id、team 复合键 |
| 定时任务是否失败 | Celery 任务状态、异常日志、扫描批次和游标 |

## 13. 关键代码导航

- 接入入口：`views/receiver.py`、`nats/nats.py`
- 来源适配：`common/source_adapter/base.py`
- 即时告警：`aggregation/processor/instant_dispatcher.py`
- 周期聚合：`aggregation/processor/aggregation_processor.py`
- 告警构建：`aggregation/builder/alert_builder.py`
- 缺失检测：`aggregation/builder/synthetic_alert_builder.py`
- 恢复处理：`aggregation/recovery/recovery_handler.py`
- 生命周期：`service/alert_lifecycle.py`
- 活跃指纹：`service/active_fingerprint.py`
- 自动分派：`common/assignment.py`
- 通知：`common/notify/dispatcher.py`
- 提醒和升级：`service/reminder_service.py`、`service/escalation_service.py`
- 可靠投递：`service/outbox.py`
- 自动处置：`action/engine.py`、`action/handlers/job.py`
- 权限范围：`utils/permission_scope.py`
- 定时任务：`tasks/tasks.py`
