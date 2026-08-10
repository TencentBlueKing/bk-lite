# CMDB 业务架构与业务流程

> 文档范围：`server/apps/cmdb/` 社区层及其 Enterprise Overlay 接口。<br>
> 文档依据：当前 `feature_windyzhao` 分支后端实现。<br>
> 图例约定：实线表示同步调用或数据读写，虚线表示异步任务、事件投递或补偿恢复。

## 1. 业务定位与边界

CMDB 是 BK-Lite 的配置数据中心，负责定义运维对象、维护资产实例和关系、接入自动采集与自定义上报，并向监控、告警、作业、运营分析等模块提供统一的资产查询、权限范围和变更事件。

CMDB 的核心业务闭环是：

1. 定义分类、模型、字段、唯一规则和模型关系。
2. 通过人工维护、文件导入、自动采集、节点同步或自定义上报形成资产实例。
3. 对实例及关系执行权限校验、唯一性校验、幂等写入和变更审计。
4. 基于资产数据提供拓扑、K8s、应用资源、网络机房和 IPAM 等业务视图。
5. 通过订阅、NATS/RPC 和审计镜像将变更可靠地传播给其他模块。

### 1.1 主要角色

| 角色 | 主要职责 |
|---|---|
| CMDB 管理员 | 管理分类、模型、字段、唯一规则、关联规则、采集任务和全局配置 |
| 资产管理员 | 在授权组织范围内维护实例、关系、文件、配置版本和导入导出 |
| 运维人员 | 查询资产、拓扑、K8s、应用资源、IPAM、采集结果和变更记录 |
| 采集代理 Stargazer | 接收采集参数，执行主机、数据库、中间件、网络、K8s、云和配置文件采集并回传结果 |
| Node Management | 提供节点、接入点、远程执行和节点同步能力 |
| 下游业务模块 | 通过 HTTP 或 NATS/RPC 查询 CMDB，消费资产上下文和变更事件 |
| Enterprise 上报方 | 使用任务凭证向自定义上报入口提交实例与关系数据 |

### 1.2 业务能力全景

```mermaid
flowchart TB
    subgraph Actors["业务参与者"]
        Admin["CMDB 管理员"]
        Operator["资产与运维人员"]
        Agent["Stargazer 采集代理"]
        Reporter["Enterprise 自定义上报方"]
        Consumer["监控 / 告警 / 作业 / 运营分析"]
    end

    subgraph Governance["建模与治理域"]
        Classification["分类管理"]
        Model["模型与字段"]
        Rules["唯一规则 / 模型关系 / 自动关联规则"]
        Presentation["字段分组 / 展示字段 / 公共枚举"]
    end

    subgraph Asset["资产数据域"]
        Instance["实例生命周期"]
        Relation["实例关系与拓扑"]
        Search["搜索 / 导入 / 导出 / 文件"]
        Change["变更记录与审计"]
    end

    subgraph Ingestion["数据接入域"]
        Collect["自动采集任务"]
        Credential["凭据池与命中状态"]
        NodeSync["Node Management 同步"]
        CustomReport["自定义上报"]
    end

    subgraph Specialized["专项资源域"]
        Config["配置文件版本"]
        K8s["K8s 资源视图"]
        AppResource["应用资源视图"]
        IPAM["子网 / IPAM 对账"]
        Infra["机房 / 机架 / 网络拓扑"]
    end

    subgraph Ecosystem["事件与生态域"]
        Subscription["变更订阅通知"]
        OpenAPI["HTTP / Open API"]
        NATS["NATS / RPC 服务"]
        Mirror["操作日志镜像"]
    end

    Admin --> Governance
    Operator --> Asset
    Operator --> Specialized
    Agent --> Collect
    Reporter --> CustomReport
    Governance --> Asset
    Ingestion --> Asset
    Asset --> Specialized
    Asset --> Change
    Change -.-> Subscription
    Change -.-> Mirror
    Asset --> OpenAPI
    Asset --> NATS
    OpenAPI --> Consumer
    NATS --> Consumer
```

## 2. 后端技术架构

CMDB 后端采用 Django/DRF 作为接口与编排层，图数据库保存模型、实例和关系主数据，Django 关系库保存流程状态、任务、审计和配置元数据，MinIO 保存配置文件正文。Celery/Beat 处理采集、订阅、对账和补偿任务，NATS/RPC 负责跨模块调用与采集结果回传。

```mermaid
flowchart TB
    subgraph Entry["接入层"]
        Web["Web / Mobile"]
        HTTP["DRF API<br/>apps.cmdb.urls"]
        Open["Open API<br/>K8s / Custom Reporting"]
        RPC["NATS / RPC<br/>apps.cmdb.nats"]
        Beat["Celery Beat"]
    end

    subgraph Application["应用编排层"]
        Views["ViewSet + Serializer"]
        Permission["菜单权限 / 动作权限 / 组织与实例权限"]
        Services["领域 Service / Manage"]
        Collection["Collection Tasks / Plugins / Formatters"]
        Workers["Celery Workers"]
    end

    subgraph Domain["核心领域组件"]
        ModelDomain["Classification / Model / Field / Rule"]
        InstanceDomain["Instance / Relation / Search / Topology"]
        OperationDomain["Operation / Unique Lock / Outbox"]
        CollectDomain["Collect / Credential / Cleanup"]
        SubscriptionDomain["Subscription / Delivery"]
        SpecializedDomain["Config File / IPAM / K8s / App Resource"]
        AuditDomain["Change Record / Mirror Outbox"]
    end

    subgraph Storage["存储层"]
        Graph["图数据库<br/>FalkorDB 或兼容驱动"]
        SQL["Django 关系库"]
        MinIO["MinIO 对象存储"]
        Cache["Cache / 分布式状态"]
    end

    subgraph External["外部依赖"]
        Stargazer["Stargazer"]
        NodeMgmt["Node Management"]
        SystemMgmt["System Management<br/>组织 / 用户 / 通知"]
        Downstream["Alerts / Monitor / Job / Ops Analysis"]
    end

    Web --> HTTP
    HTTP --> Views
    Open --> Views
    RPC --> Services
    Beat -.-> Workers
    Views --> Permission
    Permission --> Services
    Services --> Domain
    Workers --> Domain
    Collection --> CollectDomain

    ModelDomain --> Graph
    InstanceDomain --> Graph
    OperationDomain --> SQL
    CollectDomain --> SQL
    SubscriptionDomain --> SQL
    SpecializedDomain --> SQL
    SpecializedDomain --> MinIO
    AuditDomain --> SQL
    Services --> Cache

    CollectDomain -.-> Stargazer
    CollectDomain -.-> NodeMgmt
    SubscriptionDomain -.-> SystemMgmt
    Services --> SystemMgmt
    RPC <--> Downstream
```

### 2.1 分层职责

| 层次 | 主要路径 | 职责 |
|---|---|---|
| 路由与协议层 | `urls.py`、`views/`、`nats/nats.py` | 注册 HTTP/NATS 入口、解析请求、返回稳定协议 |
| 权限与校验层 | `views/mixins.py`、`utils/permission_util.py`、Serializer/Validator | 校验功能权限、组织范围、实例权限、字段和业务参数 |
| 领域编排层 | `services/`、`collection/` | 编排建模、实例、采集、配置、订阅、IPAM、拓扑和审计业务 |
| 图访问层 | `graph/drivers/graph_client.py`、`graph/falkordb.py`、`graph/neo4j.py` | 提供统一的图查询、实体写入、关系写入和拓扑遍历接口 |
| 异步任务层 | `tasks/celery_tasks.py`、`config.py` | 执行采集、订阅、清理、同步、对账、Outbox 消费和故障恢复 |
| 状态持久层 | `models/` | 保存任务、版本、投递、审计、作业、锁和个性化配置 |
| 扩展层 | `extensions/`、`collect/extensions.py`、`instance_ops/extensions.py` | 提供社区层与 Enterprise Overlay 的稳定扩展边界 |

## 3. 领域对象与存储归属

```mermaid
flowchart LR
    subgraph GraphStore["图数据库主数据"]
        G1["分类"]
        G2["模型与字段"]
        G3["模型关系与规则"]
        G4["资产实例"]
        G5["实例关系"]
    end

    subgraph SQLStore["关系库流程与治理数据"]
        S1["CollectModels / CredentialHit"]
        S2["ChangeRecord"]
        S3["SubscriptionRule / Delivery"]
        S4["ConfigFileVersion"]
        S5["IPAMReconcileSource / Run"]
        S6["CmdbOperation / Outbox / UniqueWriteLock"]
        S7["FieldGroup / ShowField / PublicEnumLibrary"]
        S8["NodeMgmtSync / UserPersonalConfig"]
    end

    subgraph ObjectStore["对象存储"]
        O1["配置正文临时对象"]
        O2["配置正文正式对象"]
        O3["实例文件"]
    end

    G2 --> G4
    G3 --> G5
    S1 -.-> G4
    S2 -.-> G4
    S3 -.-> S2
    S4 --> O1
    S4 --> O2
    S6 -.-> G4
    S7 -.-> G2
```

### 3.1 一致性边界

- 图数据库与关系库不处于同一数据库事务中。实例创建/更新通过 `CmdbOperation`、图写入标记和 Outbox 收敛跨存储状态。
- 配置版本元数据与 MinIO 正文不处于同一事务中。正文采用临时对象、`PENDING` 状态、事务提交后发布和周期补偿。
- 变更记录镜像到 System Management 不在主写事务中完成。批量审计通过 `ChangeRecordMirrorOutbox` 异步投递。
- 自动采集结果以 `task_id` 作为执行代次，旧 Worker 或超时任务不能覆盖新执行结果。

## 4. 核心业务流程

### 4.1 模型治理流程

```mermaid
flowchart TD
    Start["管理员发起模型变更"] --> Auth["校验模型管理权限与组织范围"]
    Auth --> Validate["校验分类、模型 ID、字段类型和约束"]
    Validate --> Action{"变更类型"}

    Action -->|创建或复制| CreateModel["创建模型基础信息"]
    Action -->|字段治理| Attr["新增 / 更新 / 删除字段"]
    Action -->|关系治理| Association["维护模型关系"]
    Action -->|规则治理| Rule["维护唯一规则和自动关联规则"]
    Action -->|布局治理| Layout["保存模型布局快照"]

    CreateModel --> GraphWrite["写入图数据库"]
    Attr --> FieldGuard["检查既有实例、唯一规则和字段引用"]
    FieldGuard --> GraphWrite
    Association --> GraphWrite
    Rule --> RuleValidate["校验字段组合、关系方向和规则冲突"]
    RuleValidate --> GraphWrite
    Layout --> GraphWrite

    GraphWrite --> DisplaySync["同步展示字段 / 字段分组 / 枚举引用"]
    DisplaySync --> Audit["记录操作与变更结果"]
    Audit --> Done["返回最新模型定义"]
```

关键规则：

- 删除字段前必须检查实例数据、唯一规则、自动关联规则和展示配置引用。
- 模型关系与自动关联规则分离：模型关系定义可连接性，自动关联规则定义如何根据字段生成实例关系。
- 公共枚举库是字段选项的治理来源，字段分组和展示字段只影响展示，不改变实例真实属性。

### 4.2 实例创建与更新的可靠写入流程

```mermaid
sequenceDiagram
    actor User as 资产管理员
    participant API as InstanceViewSet
    participant Perm as 权限与组织范围
    participant Inst as InstanceManage
    participant Lock as UniqueWriteLockService
    participant Op as OperationService
    participant Graph as GraphClient
    participant SQL as 关系库
    participant Outbox as CmdbOperationOutbox
    participant Worker as Celery Worker

    User->>API: 创建或更新实例 + Idempotency-Key
    API->>Perm: 校验 Edit 权限、组织范围和实例权限
    Perm-->>API: 授权范围
    API->>Inst: 规范化字段并执行业务校验
    Inst->>Lock: 按唯一规则签名抢占租约锁
    Lock-->>Inst: 获得写入权或返回冲突
    Inst->>Op: 创建或复用 CmdbOperation
    Op->>SQL: 保存请求哈希、目标和 PENDING 状态
    Op->>Op: 条件抢占 GRAPH_WRITING owner
    Op->>Graph: 写入实例及 _cmdb_operation_id
    Graph-->>Op: 返回图写结果
    Op->>SQL: 更新 GRAPH_COMMITTED
    Op->>Outbox: 创建 change_record 与 auto_relation 事件
    Op-->>API: 返回幂等结果
    API-->>User: 创建或更新成功

    Outbox-->>Worker: 异步消费
    Worker->>SQL: 写 ChangeRecord
    Worker->>Graph: 对账自动实例关系
    Worker->>Outbox: 标记 SUCCESS 或 RETRY
    Outbox->>SQL: 全部成功后 Operation 进入 COMPLETED
```

实例写入状态：

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> GRAPH_WRITING: owner 条件抢占
    GRAPH_WRITING --> GRAPH_COMMITTED: 图写成功并持久化结果
    GRAPH_WRITING --> ERROR: 图写失败
    GRAPH_COMMITTED --> COMPLETED: 所有 Outbox 事件成功
    GRAPH_COMMITTED --> GRAPH_COMMITTED: Outbox 重试或等待恢复
    PENDING --> GRAPH_COMMITTED: 恢复任务发现图侧事实
    GRAPH_WRITING --> GRAPH_COMMITTED: 租约过期后核对图侧事实
```

### 4.3 实例查询、拓扑与权限裁剪流程

```mermaid
flowchart TD
    Request["用户查询实例 / 搜索 / 拓扑"] --> FeaturePerm["校验 View 功能权限"]
    FeaturePerm --> Scope["解析当前组织与实例授权范围"]
    Scope --> QueryType{"查询类型"}
    QueryType -->|列表与全文搜索| EntityQuery["图数据库分页查询实例"]
    QueryType -->|关联与拓扑| RelationQuery["查询实例关系和拓扑邻居"]
    QueryType -->|专项资源视图| SpecializedQuery["K8s / 应用 / IPAM / 机房服务"]
    EntityQuery --> Filter["按模型、组织、实例权限裁剪"]
    RelationQuery --> ParentGuard["先裁剪父资源，再构造子资源"]
    SpecializedQuery --> ParentGuard
    ParentGuard --> Filter
    Filter --> Enrich["补充字段定义、枚举名称和展示信息"]
    Enrich --> Page["返回稳定分页、统计或拓扑结构"]
```

权限语义：

- 功能权限决定用户能否进入某个动作，例如 `asset_info-View`、`asset_info-Edit`。
- 组织范围决定用户可见的团队或组织数据。
- 实例权限用于对具体资产执行二次裁剪，不能只依赖前端过滤。
- 层级资源采用父级优先的 fail-closed 策略：父 Namespace、应用或集群不可见时，其子资源也不可见。

### 4.4 自动采集完整流程

```mermaid
sequenceDiagram
    actor User as 运维人员
    participant API as CollectModelViewSet
    participant Service as CollectModelService
    participant DB as CollectModels
    participant Celery as Celery Worker
    participant Dispatch as CollectDispatchService
    participant Agent as Stargazer / NodeMgmt
    participant Plugin as Collection Plugin
    participant Merge as Management / InstanceManage
    participant Graph as 图数据库
    participant Audit as ChangeRecord

    User->>API: 创建或执行采集任务
    API->>Service: 校验权限、任务类型、目标、接入点和凭据
    Service->>DB: 保存任务和组织范围
    Service-->>Celery: 事务提交后派发 execution_id
    Celery->>DB: 条件抢占 NOT_START/终态到 RUNNING
    Celery->>Dispatch: 解析目标与凭据池
    Dispatch->>Agent: 按目标和凭据分批下发
    Agent-->>Plugin: 执行主机 / DB / 中间件 / 网络 / K8s / 云采集
    Plugin-->>Dispatch: 返回原始数据或回调
    Dispatch->>Dispatch: 区分凭据失败与任务失败并尝试下一凭据
    Dispatch-->>Celery: 汇总有效结果
    Celery->>Merge: 格式化 add/update/delete/association
    Merge->>Graph: 有界批量写入实例和关系
    Merge->>Audit: 批量生成变更记录或镜像 Outbox
    Celery->>DB: 仅按当前 execution_id 写回终态和摘要
    DB-->>User: 展示任务状态、差异、拓扑摘要和错误
```

采集任务控制点：

- 创建/更新任务后的外部同步使用 `transaction.on_commit`，避免数据库回滚后遗留幽灵任务。
- 同一任务通过数据库条件更新抢占执行权，重复触发不会并发覆盖。
- 多凭据派发记录目标与凭据命中状态；凭据错误允许换凭据，业务错误不会盲目重试全部凭据。
- 格式化结果统一为 `add`、`update`、`delete`、`association`，再进入 CMDB 合并链路。
- 周期巡检每 5 分钟检查超时任务，且以 execution ID 防止旧 Worker 覆盖新执行。

### 4.5 配置文件版本与正文生命周期

```mermaid
sequenceDiagram
    actor User as 运维人员
    participant Task as 配置采集任务
    participant Agent as Stargazer
    participant API as ConfigFileService
    participant Temp as MinIO 临时对象
    participant DB as ConfigFileVersion
    participant Commit as transaction.on_commit
    participant Formal as MinIO 正式对象
    participant Recover as 周期补偿任务

    User->>Task: 发起配置文件采集
    Task->>Agent: 下发文件路径、目标和 execution_id
    Agent-->>API: 回传状态、版本、正文和 execution_id
    API->>API: 校验任务代次、实例归属和业务键
    API->>Temp: 写入临时对象
    API->>DB: 创建 PENDING 元数据
    DB-->>Commit: 注册提交后发布
    Commit->>Formal: 将临时正文发布到正式键
    Commit->>DB: 更新 READY 并清理临时键
    DB-->>User: 提供版本列表、正文和同文件 diff

    Commit--xFormal: 发布失败
    Commit->>DB: 标记 ERROR 并保留可恢复信息
    Recover-->>DB: 扫描 PENDING / ERROR / DELETE_PENDING
    Recover->>Formal: 幂等发布或删除
    Recover->>DB: 收敛 READY 或删除元数据
```

正文状态：

```mermaid
stateDiagram-v2
    [*] --> PENDING: 临时正文与元数据已建立
    PENDING --> READY: 正文发布成功
    PENDING --> ERROR: 发布失败
    ERROR --> READY: 补偿发布成功
    READY --> DELETE_PENDING: 请求删除
    DELETE_PENDING --> [*]: 对象与元数据删除成功
    DELETE_PENDING --> DELETE_PENDING: 删除失败等待补偿
```

关键约束：

- 自动采集版本以 `(collect_task, instance_id, version)` 为业务唯一键。
- 同业务键、同正文是幂等重投；同业务键、不同正文是协议冲突，不覆盖旧数据。
- 正文读取和 diff 必须分别校验两个版本所属实例的读取权限，并拒绝跨实例或跨文件比较。

### 4.6 订阅检测与可靠通知流程

```mermaid
sequenceDiagram
    participant Beat as Celery Beat
    participant Rule as SubscriptionRule
    participant Trigger as SubscriptionTriggerService
    participant Delivery as SubscriptionDelivery
    participant Worker as 发送 Worker
    participant System as System Management

    Beat->>Rule: 每 5 分钟加载启用规则
    Rule->>Trigger: 检测新增、变化或满足条件的实例事件
    Trigger-->>Rule: 返回 TriggerEvent 列表
    Rule->>Delivery: 按规则、事件、渠道生成去重键并持久化
    Rule-->>Worker: 仅派发 delivery_id
    Worker->>Delivery: 条件抢占 PENDING/RETRY/租约过期 SENDING
    Worker->>System: 解析组织接收人并发送通知
    System-->>Worker: 返回发送结果
    Worker->>Delivery: 标记 SENT

    System--xWorker: 发送或网络失败
    Worker->>Delivery: 记录 RETRY、退避时间和安全错误摘要
    Beat-->>Delivery: 下轮扫描恢复待发送或租约过期记录
    Delivery-->>Worker: 重新派发，最多 3 次
    Worker->>Delivery: 超过上限后标记 FAILED
```

投递状态：

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> SENDING: 条件抢占
    SENDING --> SENT: 通知成功
    SENDING --> RETRY: 可重试失败
    SENDING --> FAILED: 达到尝试上限或永久错误
    RETRY --> SENDING: 到达 next_retry_at
    SENDING --> SENDING: 租约过期后由新 Worker 接管
```

### 4.7 IPAM 对账流程

```mermaid
flowchart TD
    Trigger["人工触发或每小时 Beat"] --> Permission["人工入口校验 asset_info-Edit"]
    Permission --> Enqueue["IPAMReconcileJob.enqueue"]
    Enqueue --> SingleActive{"是否已有 PENDING / RUNNING 作业"}
    SingleActive -->|有| Reuse["复用单活作业"]
    SingleActive -->|无| Create["创建 IPAMReconcileRun"]
    Reuse --> Dispatch
    Create --> Dispatch["派发 execute_ipam_reconcile_task"]
    Dispatch --> Claim["owner_token + lease 条件抢占"]
    Claim --> Scan["按稳定 ID 游标分批扫描来源 CI"]
    Scan --> Parse["规范化 IP / CIDR / 子网归属"]
    Parse --> Compare["与已有 IP 和占用者集合对账"]
    Compare --> Limit{"参考集或占用者是否超限"}
    Limit -->|是| Error["失败关闭并记录 ERROR"]
    Limit -->|否| Persist["批量创建或更新 IPAM 结果"]
    Persist --> Success["记录统计并标记 SUCCESS"]
    Error --> Release["释放 active_scope"]
    Success --> Release
```

关键语义：

- `active_scope='global'` 的可空唯一值在关系库中裁决全局单活，避免多个全量对账同时执行。
- 扫描采用 ID 游标和批次上限，不依赖全量加载或重复 COUNT。
- 来源 CI、子网、已有 IP 和占用者都有资源上限，超过上限时失败关闭而不是继续无界占用内存。
- 日志和数据库只保存脱敏错误摘要，不持久化 broker 连接信息或凭据。

### 4.8 K8s 与应用资源视图流程

```mermaid
flowchart TD
    Request["请求集群或应用资源视图"] --> ClusterPerm["校验入口权限与根实例权限"]
    ClusterPerm --> ParentPage["分页获取 Namespace / 应用父资源候选"]
    ParentPage --> ParentFilter["按组织和实例权限裁剪父资源"]
    ParentFilter --> ChildQuery["仅查询可见父资源下的 Workload / Pod / 资源"]
    ChildQuery --> BatchRelation["批量查询当前页关系"]
    BatchRelation --> ViewType{"视图类型"}
    ViewType -->|K8s 概览| K8sOverview["Namespace / Workload / 状态统计"]
    ViewType -->|Workload Pod 页| PodPage["当前页 Pod 与 Node 状态"]
    ViewType -->|应用资源| AppTopo["应用拓扑、资源清单和实例导出"]
    ViewType -->|网络与机房| InfraView["网络拓扑、机房和机架布局"]
    K8sOverview --> Response["返回有界分页与层级结果"]
    PodPage --> Response
    AppTopo --> Response
    InfraView --> Response
```

查询原则：

- 默认概览不加载全量 Pod，只读取概览所需的父层和批量关系。
- Workload Pod 页只查询当前页 Pod，并批量查询当前页 Pod 到 Node 的关系。
- 不可见父资源的子资源不会进入候选集合，避免通过子资源名称或数量泄露父级存在性。

### 4.9 自定义上报流程

> 自定义上报通过社区层稳定入口加载 Enterprise 实现；Enterprise 不可用时由兼容层维持 Django migration/runtime 注册一致性。

```mermaid
sequenceDiagram
    actor Admin as CMDB 管理员
    actor Reporter as 外部上报方
    participant Task as CustomReportingTaskViewSet
    participant Credential as 任务凭证
    participant Ingest as CustomReportingIngestViewSet
    participant Model as 快速模型或已有模型
    participant Merge as 上报合并服务
    participant Graph as 图数据库
    participant Batch as 批次 / 待关联 / 审核

    Admin->>Task: 创建上报任务并绑定组织与模型模式
    Task->>Model: 绑定已有模型或定义快速模型
    Task->>Credential: 签发独立凭证
    Task-->>Admin: 返回接入文档
    Reporter->>Ingest: 携带凭证上报实例与关系
    Ingest->>Credential: 校验有效性、组织和任务范围
    Ingest->>Batch: 创建上报批次
    Ingest->>Model: 解析身份键并登记允许的新字段
    Ingest->>Merge: 在授权组织内执行幂等匹配
    Merge->>Graph: 创建或更新实例及关系
    Merge->>Batch: 保存待关联、清理审核和批次结果
    Batch-->>Reporter: 返回成功、失败和待处理摘要
    Admin->>Task: 审核清理项、轮换或作废凭证
```

### 4.10 变更记录与跨模块镜像流程

```mermaid
flowchart LR
    Source["人工维护 / 自动采集 / 自定义上报"] --> Change["生成 ChangeRecord"]
    Change --> Query["CMDB 变更查询、枚举和导出"]
    Change --> Batch["批量聚合镜像 payload"]
    Batch --> Outbox["ChangeRecordMirrorOutbox"]
    Outbox -.-> Worker["consume_change_record_mirror_outbox"]
    Worker -.-> System["System Management OperationLog"]
    Worker --> Result{"投递结果"}
    Result -->|成功| Success["SUCCESS"]
    Result -->|失败| Retry["RETRY + 退避"]
    Retry -.-> Recover["每 5 分钟恢复扫描"]
    Recover -.-> Worker
```

批量变更记录不在采集主任务中逐条同步调用下游 RPC；主链路只写持久化 Outbox，由 Worker 有界消费、租约接管和失败退避。

## 5. 业务状态与异常处理总览

| 业务链路 | 幂等或并发控制 | 失败处理 | 恢复入口 |
|---|---|---|---|
| 实例创建/更新 | `operator + Idempotency-Key`；唯一规则租约锁；图写 owner | 图写失败进入 `ERROR`；后置事件进入 `RETRY/FAILED` | `reconcile_cmdb_operations_task` |
| 自动采集 | `CollectModels.task_id` 执行代次；数据库条件抢占 | 当前执行写安全错误摘要；旧执行结果被忽略 | `sync_periodic_update_task_status` |
| 配置正文 | 业务唯一键；正式对象内容哈希比对 | 保留 `PENDING/ERROR/DELETE_PENDING` 和临时键 | `reconcile_config_file_content_task` |
| 订阅通知 | SHA-256 去重键；投递 owner 与租约 | 3 次退避重试，永久错误进入 `FAILED` | `check_subscription_rules` 的恢复扫描 |
| IPAM 对账 | `active_scope='global'` 单活；owner 与租约 | 超限或执行异常进入 `ERROR` 并释放单活键 | `reconcile_ipam_task` |
| 审计镜像 | Outbox event_id；owner 与租约 | 有界重试、退避、安全错误摘要 | `recover_change_record_mirror_outbox_task` |

## 6. 外部系统交互

```mermaid
flowchart LR
    CMDB["CMDB"]
    Stargazer["Stargazer"]
    NodeMgmt["Node Management"]
    SystemMgmt["System Management"]
    Alerts["Alerts"]
    Monitor["Monitor"]
    Job["Job Management"]
    Ops["Operation Analysis / OpsPilot"]

    CMDB -->|采集参数 / execution_id| Stargazer
    Stargazer -->|原始结果 / 配置回调| CMDB
    CMDB <-->|节点、接入点、远程执行、同步| NodeMgmt
    CMDB -->|组织用户解析、通知、操作日志镜像| SystemMgmt
    Alerts -->|资产查询与丰富| CMDB
    Monitor -->|对象、字段和实例查询| CMDB
    Job -->|目标解析和资产范围| CMDB
    Ops -->|统计、拓扑、变更趋势| CMDB
    CMDB -->|NATS / RPC 数据服务| Alerts
    CMDB -->|NATS / RPC 数据服务| Monitor
    CMDB -->|NATS / RPC 数据服务| Ops
```

主要 NATS/RPC 能力包括：

- 模型、字段、分类、实例和关系查询。
- 带授权范围的实例创建、更新、删除和批量搜索。
- 配置文件与凭据命中结果回调。
- CMDB 统计、模型实例统计、采集统计和变更趋势。
- 机房 3D 布局、模型实例数量和展示字段同步。

## 7. API 与代码入口索引

| 业务域 | HTTP 入口 | 核心服务/实现 | 主要持久化对象 |
|---|---|---|---|
| 分类 | `api/classification` | `services/classification.py` | 图数据库分类节点 |
| 模型治理 | `api/model` | `services/model.py`、`views/model.py` | 图数据库模型、字段、关系和规则 |
| 实例与拓扑 | `api/instance` | `services/instance.py`、`services/operation_service.py` | 图实例/关系、`CmdbOperation`、Outbox |
| 采集任务 | `api/collect` | `services/collect_service.py`、`collection/` | `CollectModels`、凭据命中状态 |
| 采集调试 | `api/collect_tool` | `services/collect_tool_service.py` | 调试缓存与任务结果 |
| 配置文件 | `api/config_file_versions` | `services/config_file_service.py`、`config_file_content_lifecycle.py` | `ConfigFileVersion`、MinIO 正文 |
| 变更记录 | `api/change_record` | `utils/change_record.py`、`change_record_mirror.py` | `ChangeRecord`、Mirror Outbox |
| 订阅 | `api/subscription` | `subscription_trigger.py`、`subscription_task.py` | `SubscriptionRule`、`SubscriptionDelivery` |
| IPAM | `api/instance/ipam_*` | `ipam_reconcile.py`、`ipam_reconcile_job.py` | 图实例、`IPAMReconcileSource/Run` |
| K8s 安装与资源 | `api/k8s_setup`、`api/instance/*k8s*` | `k8s_setup.py`、`k8s_resource_overview.py` | 图实例与关系、安装令牌缓存 |
| 应用资源 | `api/instance/*application_resource*` | `application_resource_overview.py` | 图实例与关系 |
| Node 同步 | `api/node_mgmt_sync` | `node_mgmt_sync_service.py` | `NodeMgmtSyncConfig/Run` |
| 字段展示治理 | `api/field_groups`、`api/public_enum_libraries` | `field_group.py`、`display_field/` | `FieldGroup`、`ShowField`、`PublicEnumLibrary` |
| 用户配置 | `api/user_configs` | `views/user_personal_config.py` | `UserPersonalConfig` |
| 自定义上报 | `api/custom_reporting/tasks`、`api/custom_reporting/ingest` | `custom_reporting/` 与 Enterprise Overlay | 上报任务、批次、待关联、凭证和审核数据 |
| 跨模块服务 | `apps/cmdb/nats/nats.py` | NATS 注册函数 | 图数据、关系库统计和下游响应 |

## 8. Celery 调度与恢复矩阵

| 调度项 | 周期 | 业务作用 |
|---|---:|---|
| `sync_periodic_update_task_status` | 每 5 分钟 | 关闭超时采集任务，防止任务永久停留在执行中 |
| `check_subscription_rules` | 每 5 分钟 | 检测订阅规则，并恢复待发送或租约过期投递 |
| `daily_data_cleanup_task` | 每日 02:00 | 按清理策略处理过期采集数据 |
| `reconcile_ipam_task` | 每小时 | 创建或复用全局 IPAM 对账作业 |
| `reconcile_config_file_content_task` | 每 15 分钟 | 补偿配置正文发布、删除和临时对象清理 |
| `reconcile_cmdb_operations_task` | 每 5 分钟 | 恢复跨图/关系库实例操作及后置 Outbox |
| `recover_change_record_mirror_outbox_task` | 每 5 分钟 | 恢复批量变更记录镜像投递 |

## 9. 架构约束与维护原则

1. 图数据库是模型、实例和关系的主数据源；关系库用于承载流程状态，不能在两个存储中维护互相竞争的实例真相。
2. 所有 HTTP、Open API 和 NATS 写入口都必须在服务端校验授权范围，调用方传入的组织 ID 不能直接作为可信边界。
3. 跨存储和跨服务副作用必须通过状态机、Outbox、`transaction.on_commit` 或补偿任务收敛，不能依赖一次同步调用必然成功。
4. 自动采集和对账必须有批次、游标、超时、资源上限和幂等语义，禁止无界全量加载。
5. 业务错误应区分权限拒绝、协议冲突、凭据失败、任务失败、超时、部分成功和待补偿，避免统一压缩成模糊的成功/失败。
6. 新增模型、采集类型或专项视图时，应复用现有 `ViewSet → Service → Graph/ORM → Outbox/Task` 链路，并补充权限、状态转换和异常恢复测试。
