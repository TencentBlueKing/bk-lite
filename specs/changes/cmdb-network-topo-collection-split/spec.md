# 网络设备采集与网络拓扑采集拆分

Status: done

## Decision Summary

- 页面与数据库中仍只有一个用户可见的 Network 采集任务，不创建第二条
  `CollectModels` 任务。
- 一个 Network 采集任务在底层拥有两个采集通道：
  `device`（网络设备与接口）和 `topology`（网络拓扑证据）。
- 两个采集通道生成不同的节点配置，进入独立的 Stargazer `CollectionRun`，
  分别拥有超时、周期、结果和失败语义；拓扑失败不得改变设备采集状态。
- 两个节点配置 ID 不同，但指标关联范围相同，统一使用
  `instance_id=cmdb_{collect_task_id}`，使拓扑证据能够与设备、接口数据关联。
- 拓扑周期由页面独立配置，默认是设备周期的 5 倍，最终转换为秒下发给
  Telegraf；它不是第二条 CMDB Celery 周期任务。
- 拓扑采集完成后通过正式运行完成事件触发 CMDB 幂等重放解析；不依赖固定一小时
  查询窗口猜测拓扑是否完成。
- Stargazer 总目标并发沿用 `MAX_ACTIVE_TARGETS`（默认 250）。拓扑目标并发由
  `NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS` 控制，默认 50、最大 100；普通任务
  保底为总并发减去拓扑上限，并可借用拓扑空闲容量。

## Problem Statement

客户环境使用 SNMP 采集网络设备（254 个目标，其中约 130 台在线），开启网络拓扑采集
（`has_network_topo=True`）后，全部目标采集失败。根因已在客户环境确认：拓扑采集
在 getBulk 遇到 `OID not increasing` 后降级为逐 OID 遍历，耗时急剧放大；它与设备
采集内联在同一次插件调用中，共享同一个 300 秒单目标预算。拓扑阶段耗尽预算后，设备
和接口结果也随之超时丢失。关闭拓扑采集后设备数据恢复正常。

即使把插件调用拆开，若仍共用无分类的 250 个目标并发槽位，大量长耗时拓扑目标仍可能
占满 Stargazer，使网络设备、主机、数据库等普通采集延迟。因此本变更同时解决失败隔离
和目标容量隔离。

## Goals

1. 拓扑采集慢、失败或被中断时，设备和接口数据仍按设备周期正常采集、入库和展示。
2. 页面仍以一个 Network 任务承载配置、权限、复制、编辑和删除，避免暴露内部拆分复杂度。
3. 设备与拓扑分别形成正式采集运行，拥有独立超时和运行身份；拓扑失败仅日志可追溯，
   不影响任务状态。
4. 拓扑周期可以独立配置，默认明显低于设备采集频率。
5. 拓扑证据晚到或先到都能够最终建边，不因跨周期时序错位丢失关系。
6. 拓扑目标不能占满全部 Stargazer 目标槽位，普通采集始终有明确保底容量。
7. 创建、更新、关闭关系采集和删除任务后，不遗留孤儿节点配置或接受旧配置结果。

## Domain Model

### Network 采集任务

用户在页面创建和管理的 Network 任务，对应唯一一条 `CollectModels` 记录。它是权限、
配置和用户操作的业务聚合，不因底层采集拆分而复制。

### 网络采集通道

Network 采集任务下的持续采集职责，固定为：

- `device`：采集网络设备基础信息和接口；
- `topology`：采集 LLDP/CDP/FDB/ARP 等拓扑证据。

采集通道不是第二条页面任务，也不是脱离运行时的后台协程。每次执行仍使用现有
`CollectionRun` 语义。

### 状态口径

- Network 任务的状态（`exec_status`）只反映 `device` 通道及其 CMDB 入库结果。
- `topology` 通道不提供面向用户的独立状态展示；其采集与解析失败仅记录日志
  （stargazer 运行汇总日志 + server 消费侧日志），作为排查入口。
- “设备成功、拓扑失败”表现为任务状态成功、拓扑关系沿用上一轮快照；不得折叠为
  Network 任务整体失败。

## Identity Contract

| 层级 | 设备通道 | 拓扑通道 | 不变量 |
|---|---|---|---|
| 页面任务 | `CollectModels.id=T` | 同左 | 始终只有一个业务任务 |
| 逻辑通道身份 | `(T, device)` | `(T, topology)` | 组合键稳定唯一 |
| 节点配置 ID | `cmdb_T` | `cmdb_T_topology` | 全局唯一、确定性生成 |
| 指标关联范围 | `cmdb_T` | `cmdb_T` | 两通道共享 `instance_id` |
| Agent 插件 | `network` | `network_topo` | 插件和指标名区分数据 |
| 运行身份 | 独立请求指纹与 attempt | 独立请求指纹与 attempt | 不使用页面任务 ID 代替运行 ID |

当前节点参数实现把节点配置 ID 与指标 `instance_id` 都收敛在 `_instance_id`。实现时
必须把两者拆成清晰的 interface，例如 `config_id` 与 `metric_scope_id`，禁止通过给
`_instance_id` 简单加后缀而破坏消费侧关联。

每个采集通道还必须携带 `collection_role` 和单调变化的
`channel_config_version`。关闭拓扑或更新通道配置后，旧运行即使晚到，也不能覆盖当前
状态或重新建立关系。

## Frontend Design

### Information architecture and layout

页面继续使用现有 Network 新建/编辑抽屉和一条 Network 任务记录，不新增第二个表单、页签或
任务列表项。现有“周期”继续表示设备采集周期；开启“是否采集关系”后，在当前拓扑参数区域
最上方显示“拓扑采集周期”，其后才是拓扑协议、回退策略和最小置信度。

```text
周期                  每 [ 30 ] 分钟执行一次       ← 设备采集周期
是否采集关系          [ 开 ]
拓扑采集周期  (?)     [ 150 ] 分钟  [恢复推荐值]   ← 独立周期
                      推荐值：设备采集周期的 5 倍（150 分钟）
拓扑协议              [ LLDP | CDP | FDB | ARP ]
拓扑回退策略          [ 优先邻居协议，再使用 FDB / ARP 补充 ]
最小置信度            [ 0.00 ]
```

“拓扑采集周期”使用现有 Ant Design `Form.Item + InputNumber`，单位以 `addonAfter` 显示
“分钟”，沿用表单现有宽度和布局，不新增页面级样式。标签右侧使用现有
`QuestionCircleOutlined + Tooltip` 帮助入口。

帮助提示文案固定为：

> 拓扑采集需要遍历多类 SNMP OID，目标较多或设备响应较慢时可能耗时较长。建议将拓扑
> 采集周期设置为设备采集周期的 5 倍或更长。

输入框下方始终展示当前推荐值，例如“推荐值：设备采集周期的 5 倍（150 分钟）”。推荐值
是说明和快捷恢复目标，不强制用户只能填写 5 倍。

### Form state

前端表单增加两个字段：

```typescript
interface SnmpTopologyFormValues {
  topologyIntervalMinutes?: number;
  topologyIntervalMode?: 'recommended' | 'custom';
}
```

`topologyIntervalMode` 是明确的表单和持久化状态，不能只通过“当前值是否恰好等于 5 倍”
临时推断。这样用户手工输入 5 倍后仍视为自定义值，后续修改设备周期时不会被意外覆盖。

状态转换规则：

| 场景 | 拓扑周期 | 模式 |
|---|---|---|
| 新建任务，设备周期默认 30 分钟 | 自动填入 150 | `recommended` |
| 首次打开“是否采集关系”且没有历史值 | 自动填入当前设备周期 × 5 | `recommended` |
| 用户修改拓扑周期 | 保留用户输入 | 切换为 `custom` |
| 设备周期变化，当前为推荐模式 | 同步更新为新的设备周期 × 5 | 保持 `recommended` |
| 设备周期变化，当前为自定义模式 | 不覆盖用户输入，只重新校验 | 保持 `custom` |
| 点击“恢复推荐值” | 更新为当前设备周期 × 5 | 切换为 `recommended` |
| 关闭后在同一次编辑中重新打开 | 恢复关闭前的值和模式 | 不变 |
| 编辑有新字段的任务 | 使用服务端回显值和模式 | 使用回显模式 |
| 编辑缺少新字段的存量任务 | 按回显设备周期 × 5 补值 | `recommended` |
| 复制任务 | 复制原任务的值和模式；存量任务按上一条补值 | 与来源一致 |

关闭“是否采集关系”时隐藏拓扑配置区，但不清空拓扑周期、协议等用户输入，避免误操作开关
造成配置丢失。提交时仍携带这些保存值，服务端在 `has_network_topo=false` 时不创建或调度
拓扑通道；用户以后重新开启时可以恢复原配置。

### Validation and feedback

开启“是否采集关系”时，拓扑采集周期必须满足：

1. 必填；
2. 正整数，最小值为 1 分钟；
3. 不得小于当前设备采集周期；
4. 允许不等于设备周期的 5 倍，此时仅保留推荐提示，不显示警告；
5. 当前基础周期不是“每 N 分钟执行一次”时，阻止提交并提示“请先将设备采集周期设置为
   按分钟执行”。

关闭关系采集时不执行拓扑字段校验。用户在自定义模式下修改设备周期，导致拓扑周期小于设备
周期时，保留原输入并在字段下显示校验错误，禁止提交；页面不得静默改写自定义值。

### Frontend data contract

创建、编辑和复制任务仍只提交一次 Network 任务请求。前端提交分钟数，不负责转换 Telegraf
秒数：

```json
{
  "scan_cycle": {
    "value_type": "cycle",
    "value": 30
  },
  "params": {
    "has_network_topo": true,
    "topology_interval_minutes": 150,
    "topology_interval_mode": "recommended",
    "topology_protocols": ["lldp", "cdp", "fdb", "arp"]
  }
}
```

服务端仍是默认值和合法性的最终裁决者，并把 `topology_interval_minutes * 60` 转换为拓扑
节点配置的 Telegraf interval。前端不得直接提交第二个采集任务或第二份节点配置。

现有 `getSnmpTopologyFormValues` 与 `buildSnmpTopologyParams` 所在模块作为表单与接口参数之间
的唯一 seam，集中隐藏以下 implementation：存量默认、推荐值计算、snake_case/camelCase
映射和模式规范化。`snmpTask.tsx` 只负责渲染和用户事件，不在创建、编辑、复制三个分支各自
实现一套 5 倍计算。

### Detail and actions

- 任务详情的拓扑配置摘要增加“拓扑采集周期”，显示如“150 分钟（推荐）”或
  “120 分钟（自定义）”；未开启时显示“未启用”，不展示保存但未生效的值。
- Network 任务列表仍只有一行，不增加拓扑任务行；页面不展示拓扑通道的独立运行状态。
- “立即执行”接纳两个已启用通道，但立即返回，不等待拓扑完成；页面状态只随设备通道更新。
- 关闭“是否采集关系”只停止后续拓扑采集，默认不删除已有拓扑关系；已有关系沿用快照
  语义保留。
- 删除 Network 任务时，同时删除两个确定性节点配置 ID 和对应通道状态。

新增字段、帮助文本、校验错误、推荐/自定义标识和“恢复推荐值”必须同时补齐中英文 i18n；
帮助图标支持键盘聚焦并具有可读的无障碍名称。

## Node Configuration Reconciliation

定义一个集中处理网络采集配置的模块，其 interface 接收一条 Network 采集任务并对账到
期望节点配置集合：

```text
reconcile_network_collection_configs(network_task)
```

期望集合：

- `has_network_topo=False`：仅 `device`；
- `has_network_topo=True`：`device + topology`；
- 删除任务：空集合。

该模块隐藏节点配置 ID、模板渲染、凭据环境变量、版本和补偿逻辑。创建、编辑、开关切换、
删除和存量任务对账都必须经过同一个 interface，不能在各调用方散落“删旧再建新”的分支。

对账要求：

1. 创建或更新两份配置时按期望集合整体提交；重复执行结果一致。
2. 删除时始终尝试清理 `cmdb_T` 与 `cmdb_T_topology`，不依赖当前开关值。
3. 外部写入部分失败时保留可重试事实，由对账补偿恢复，不留下不可发现的幽灵配置。
4. 两个通道共享目标、凭据、接入点、组织和指标范围；拓扑参数只进入拓扑通道。
5. 凭据仍只在 Network 任务中保存一份，节点配置通过环境变量引用，不复制明文。

### Device configuration

- 节点配置 ID：`cmdb_T`；
- `model_id=network`；
- Telegraf interval：设备周期；
- 不携带 `has_network_topo`、拓扑协议、回退策略和置信度参数；
- 使用 `network` 插件，只发布设备和接口指标。

### Topology configuration

- 节点配置 ID：`cmdb_T_topology`；
- `model_id=network_topo`；
- Telegraf interval：`topology_interval_minutes * 60`；
- 使用同一批目标和凭据；
- 只携带拓扑协议、回退策略、置信度和通道版本；
- 使用已注册的独立 `network_topo` 插件。

## Stargazer Runtime

### Independent collection

拓扑通道进入 `CollectionRuntime` 的完整生命周期：租约、目标调度、凭据尝试、插件超时、
结果发布、运行汇总和终态。禁止由设备插件创建进程内后台任务。

结构拆分完成后：

- `network` 插件不再调用 `SnmpTopo`；
- 旧请求残留的 `has_network_topo` 和拓扑参数由设备插件忽略，不得重新内联采集；
- 独立 `network_topo` 插件继续沿用清单声明的单目标超时；
- 任何过渡期内联拓扑子预算仅作为临时止血，最终必须删除。

### Run completion event

现有 `collection_run_summary` 只写日志，不能触发 CMDB 重放。Stargazer 需要在所有目标
发布完成并形成终态后，发送正式的内部运行完成事件。事件至少包含：

- 稳定 `event_id`；
- `collect_task_id`；
- `collection_role`；
- `channel_config_version`；
- `run_id` 与唯一 `run_attempt_id`；
- `plugin_ref`、终态、开始/完成时间；
- 目标成功、失败、不可达和发布失败汇总。

指标行需要增加可查询的 `collection_run_attempt_id` 标签，使消费侧能够精确选择本次运行
证据，不以“最后一小时内最新数据”代替运行身份。事件重复投递必须幂等；事件发布失败不能
把已经确认写入的设备或拓扑指标改成未知结果，但必须可重试和可观测。

**完成信号统一决定（2026-08-24）**：本事件与
`cmdb-collection-round-gated-sync` 的「轮次完成标记」实施时统一为同一个完成信号机制，
不建两套完成语义或第二条事件通道。以轮次完成标记为基础，拓扑通道的标记携带本节要求的
通道角色、配置版本与运行身份字段；拓扑重放的触发方式即守门任务发现拓扑通道出现新的
完整轮次标记。

## Capacity Isolation

### Capacity class

把独立拓扑插件归入受信任的 `network_topology` workload class。分类由插件清单和执行计划
确定，不接受调用方任意覆盖。其他任务统一视为普通 workload。

当前 `capacity_group` 只影响计划和指标命名。实现时应把 workload class 传入全局调度器，
由调度器统一维护总容量、分类容量、等待队列和归还规则；禁止再叠加第二个不透明 Semaphore
形成两套容量真相。

### Configuration

- `MAX_ACTIVE_TARGETS`：总目标并发，现有默认值 250；
- `NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS`：拓扑目标硬上限；
- 拓扑环境变量未配置或为空时默认 50；
- 合法值为 1～100，`0` 不表示无限；
- 非整数、超出 1～100，或不小于总目标并发时，启动配置校验失败，不静默截断；
- 配置按 Stargazer 进程/Pod 生效，修改后重启生效。

普通任务保底容量按以下公式计算：

```text
general_reserved =
    MAX_ACTIVE_TARGETS - NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS
```

默认配置得到 `250 - 50 = 200`。若拓扑上限配置为 80，普通任务保底变为 170；配置为
最大值 100 时，普通任务保底为 150。

### Work-conserving bulkhead

调度器必须满足：

1. 总 active targets 不超过总目标并发；
2. topology active targets 不超过拓扑硬上限；
3. 拓扑有等待任务时，普通任务至少保有 `general_reserved`；
4. 拓扑没有等待任务时，普通任务可以借用全部空闲槽位，最高使用总容量；
5. 拓扑不得突破配置的硬上限；
6. 不取消或抢占已经运行的目标；拓扑到达时，通过普通目标自然完成逐步归还容量；
7. 同一 workload 内继续按 CollectionRun 公平轮询，避免一个大任务独占该类容量。

目标槽位不是唯一共享资源。实现与验收还必须覆盖：

- topology Run 不得占满全局 `MAX_ACTIVE_RUNS`，使普通请求在进入目标调度前持续 busy；
- 大型拓扑结果不得长期占满共享发布队列，导致普通结果发布饥饿；
- 容量指标按 workload 输出 active、pending、peak、首次调度等待和队列等待。

本阶段优先采用同进程容量舱壁。若在目标上限降至合理值后仍出现事件循环延迟、CPU/内存或
发布队列互相影响，再把拓扑路由到独立 Stargazer Worker/Pod；独立进程部署不作为本变更
首选实现。

## Server Ingestion and Topology Replay

### Device path

设备通道沿用 Network 任务的上方周期执行 CMDB 入库，只查询并处理设备和接口指标。它不等待
拓扑证据，也不运行拓扑关系解析。

### Topology path

拓扑运行成功终态事件触发一次幂等重放：

1. 校验 Network 任务仍存在、`has_network_topo=True`，且事件
   `channel_config_version` 仍是当前版本；
2. 按共享 `instance_id` 和当前 `collection_run_attempt_id` 读取本次拓扑证据；
3. 读取已入库或时序库中的设备和接口数据，重建接口索引；
4. 执行现有“证据聚合 → 拓扑解析 → 接口 connect 关系”流水线；
5. 保存新的拓扑快照、关系结果和拓扑通道状态。

不得继续使用固定 `last_over_time(...[1h:])` 作为拓扑完成判断。查询窗口必须与通道周期和
运行身份匹配，且不能把上一轮成功证据误当成本轮失败结果。

### Ordering and retry

不能假设拓扑一定晚于设备完成：

- 已有设备和接口时，拓扑可以直接重放；
- 新任务中拓扑先到、设备或接口尚未入库时，拓扑状态进入可重试的 pending 状态；
- 设备入库完成后主动唤醒 pending 重放，后台同时提供有界退避补偿；
- 重放可以重复执行，重复事件和重复唤醒不得生成重复关系；
- 任务删除、关闭拓扑或版本变化后，旧事件直接作为 stale 忽略。

## State and Failure Semantics

不新增面向用户的通道状态存储与展示。仅保留拓扑重放正确性所需的最小内部状态：
当前拓扑配置版本（stale 事件 fencing 依据）与 pending 重放记录（拓扑先到时的重试
依据）；两者都是实现细节，不进入页面。

- `device` 采集或入库失败：按现有逻辑更新 Network 任务状态（`exec_status`）；
- `topology` 采集失败/超时：记录日志，保留上一轮关系和快照，不改变任务状态；
- 拓扑证据成功但重放失败：记录日志，保留上一轮关系，允许补偿重试；
- 部分目标成功：保存成功目标的证据，关系替换策略继续遵守现有快照语义；
- Stargazer 重启导致运行 abandoned：记录本轮失败，下个拓扑周期整轮重采，不做断点续跑；
- 凭据认证事实仍按同一个 Network 任务共享；拓扑的普通超时和插件失败不得错误冷冻凭据。

## Lifecycle Scenarios

### Create with topology enabled

创建一条 Network 任务，整体对账两份节点配置。页面保存成功不等待拓扑完成。

### Create with topology disabled

只创建 device 配置，不生成拓扑配置。

### Enable topology

保持 `cmdb_T` 不变，新增或修复 `cmdb_T_topology`，生成新拓扑配置版本并开始独立周期。

### Disable topology

删除 `cmdb_T_topology`，递增/失效拓扑配置版本，忽略所有晚到旧结果；已有关系默认保留。

### Update shared targets or credentials

两个通道同时切换到新配置版本并整体对账。运行中的旧版本允许自然结束，但其完成事件不能写入
当前状态或关系。

### Change only topology period or protocol

只更新 topology 配置与版本，不重建或中断 device 配置。

### Delete task

删除两个确定性节点配置、拓扑内部状态（配置版本与 pending 记录）和页面任务；删除后
晚到事件按 missing/stale 幂等忽略。

## Compatibility and Rollout

1. 存量 `has_network_topo=True` 任务无需用户重新保存；对账任务按设备周期 × 5 生成缺失
   拓扑周期和第二份节点配置。
2. 新 Server 在正式切换前必须能够识别旧内联拓扑指标；切换完成后设备配置不再发送拓扑参数。
3. 新 Agent 对旧设备请求中残留的拓扑参数采取忽略或过渡期降级，不能因未知参数失败。
4. 独立拓扑完成事件上线前，Server 先具备幂等消费和版本 fencing；事件消费者缺失不能影响
   设备指标发布。
5. 通过对账确认双配置稳定后，删除 `network` 插件中的内联拓扑调用和临时止血逻辑。
6. 回滚时 device 配置和基础设备入库必须保持可用；不得以恢复内联拓扑作为回滚前提。

## Observability

日志和指标必须能够按 `collect_task_id`、`collection_role`、`run_id`、
`run_attempt_id`、`channel_config_version` 和 workload class 检索。

至少需要观察：

- device/topology Run 数、成功率、耗时和失败分桶；
- topology active/pending/peak 与硬上限；
- 普通任务首次调度等待和保底容量是否成立；
- 事件循环当前/P99 延迟；
- 发布队列深度、利用率和等待 P99；
- 拓扑完成事件重复、失败、stale 和重放重试次数；
- 当前节点配置期望数与实际数的对账差异。

## Acceptance Criteria

1. 开启拓扑后，设备与接口采集不再执行拓扑代码；拓扑单目标耗尽 300 秒也不改变设备结果。
2. 页面和数据库始终只有一个可见 Network 任务；开关打开时节点管理存在两份稳定配置。
3. 两个配置的 ID 不同、指标 `instance_id` 相同、Agent 运行身份不同。
4. 拓扑周期默认是设备周期 5 倍；推荐模式随设备周期联动，自定义模式不被覆盖，并支持恢复
   推荐值、编辑/复制回显、校验和帮助提示；Telegraf 收到对应秒数。
5. 默认总并发 250、拓扑上限 50、普通保底 200；环境变量可把拓扑上限配置到 1～100。
6. 拓扑压测期间普通任务仍获得保底容量，拓扑不超过硬上限；拓扑空闲时普通任务可使用全部容量。
7. 拓扑成功事件触发幂等关系重放；拓扑先到、重复到、晚到旧版本都不会丢关系或污染当前状态。
8. 拓扑失败和解析失败保留上一轮关系并有日志可查；任务状态只反映设备采集与入库结果，
   页面不展示拓扑独立状态。
9. 开关切换、共享配置更新和删除任务后，无孤儿节点配置，旧版本事件不能恢复已关闭拓扑。
10. 存量任务在不重新编辑的情况下自动转换为双通道配置。

## Testing Decisions

已锁定（2026-08-24）。分层与 CI 策略如下。

### 分层与 CI

| 层 | 范围 | CI |
|---|---|---|
| L1 Web | 表单默认/联动/回显/校验；单行任务；无拓扑独立状态；立即执行只随 device 更新状态 | 必跑 |
| L2 Server | 双配置对账、生命周期、版本 fencing、pending 唤醒、重放幂等、`exec_status` 只跟 device、凭据不因拓扑普通失败冷冻 | 必跑 |
| L3 Agent | 插件/Run 独立、完成标记字段与成功契约、容量舱壁确定性模拟、旧参数兼容 | 必跑 |
| L4 E2E | 主路径、时序、失败隔离、存量迁移、删任务晚到；与 `cmdb-collection-round-gated-sync` **共用完成标记夹具** | 必跑子集 |
| L5 压测 | 真·总并发 250、拓扑上限 50/100、保底与借用、事件循环/资源回归 | **不进默认 CI**；发布前手工/脚本 |

L5 策略取 A：CI 只做 L3 缩小并发的确定性模拟（如总 10 / 拓扑 3），不做真 250 自动化。

完成信号：拓扑重放触发复用轮次完成标记；不为拓扑另建假事件总线。契约：**仅成功完整轮次发完成标记；失败不发成功标记**。

不测（与 Out of Scope 对齐）：getBulk OID 降级、拓扑增量、`operation_analysis` 拓扑链路、独立进程舱壁。

### L1 Web（11，全进 CI）

1. 开拓扑时拓扑周期默认 = 设备周期 × 5，模式为推荐。
2. 推荐模式下改设备周期 → 拓扑周期联动为新值 × 5。
3. 自定义模式 → 改设备周期不覆盖用户拓扑周期。
4. 「恢复推荐」→ 写回设备周期 × 5 并切回推荐模式。
5. 编辑/复制回显 `topologyIntervalMode` 与拓扑周期（不得仅用「数值是否等于 5 倍」推断模式）。
6. 拓扑周期非法值校验拦截；帮助文案 key 存在（若产品已定义）。
7. 任务列表仍一行 Network，无第二条拓扑任务行。
8. 详情/列表不展示拓扑通道独立运行状态。
9. 「立即执行」触发已启用双通道且 UI 立即返回；页面状态只随 device 更新（device 成功而 topology 仍失败/未完成时页面仍显示 device 结果）。
10. 关拓扑保存不要求清关系；前端不把拓扑失败折叠为任务失败。
11. 开/关与共享字段变更的提交 payload 含对账所需字段（与现有 `formatTaskValues` 契约一致）。

### L2 Server（16，全进 CI）

**双配置与生命周期**

1. 开拓扑创建 → 两份节点配置，ID 不同、`instance_id` 同。
2. 关拓扑 → 删 `*_topology`，升版本；已有关系默认保留。
3. 删任务 → 两配置与 pending/版本内部态清除；晚到标记幂等忽略。
4. 只改拓扑周期/协议 → 只动 topology 配置与版本，device 不中断重建。
5. 改共享目标/凭据 → 两通道一起升版本；旧版本完成标记不写当前关系。
6. 存量 `has_network_topo=True` → 对账自动补拓扑周期（设备 × 5）和第二份配置，无需用户再保存。

**完成标记 → 重放**

7. 有设备+接口 + 拓扑完整轮次标记 → 触发一次重放，关系更新。
8. 拓扑先到、设备未入库 → pending；设备入库后唤醒；关系生成且不重复。
9. 同一 `run_attempt_id` 重复投递 → 重放幂等，关系不翻倍。
10. `channel_config_version` 过期 → stale，忽略，不改当前关系。
11. 任务已删或 `has_network_topo=False` → missing/stale，忽略。

**失败与状态口径**

12. device 失败 → `exec_status` 按现有逻辑更新；与拓扑无关。
13. 拓扑采集失败/超时 → 不改 `exec_status`，保留上一轮关系，有日志。
14. 拓扑证据在、重放失败 → 保留上一轮关系，允许补偿；不改任务状态。
15. 序列化/API 不暴露拓扑通道独立用户状态字段。
16. 拓扑普通超时/插件失败 → 不得错误冷冻共享凭据。

### L3 Agent（15，全进 CI）

**插件 / Run**

1. device 通道不执行拓扑采集代码（LLDP/CDP/FDB/ARP 等）。
2. topology 通道只采证据，不走 device 入库路径。
3. 两通道 `run_id` / `run_attempt_id` 不同；指标带同一 `instance_id` 与可区分 `collection_role`。
4. 拓扑单目标超时不影响同任务 device 已产出结果。

**完成标记**

5. 通道一轮全部目标终态且批次发布成功后发一轮完成标记（非仅 summary 日志）。
6. 标记至少含：`collect_task_id`、`collection_role`、`channel_config_version`、`run_attempt_id`（及约定轮次/时间戳）。
7. 失败终态不发成功完成标记。
8. 部分批次发布失败 → 不发成功完成标记。

**容量（确定性模拟）**

9. 拓扑 active 不超过配置上限（缩小版，如总 10 / 拓扑 3）。
10. 拓扑打满时普通 workload 仍获保底（总 − 拓扑上限）。
11. 拓扑无等待时普通可借用至总容量。
12. 拓扑新到达不取消/不抢占已在跑的普通目标；靠自然完成归还。
13. 同 workload 内多 CollectionRun 公平轮询。
14. 拓扑上限非法（非 1～100 或 ≥ 总并发）→ 启动校验失败，不静默截断。

**兼容**

15. 新 Agent 收到旧 device 请求残留拓扑参数 → 忽略/降级，不因未知参数失败。

### L4 E2E（10 条进 CI；与守门共用完成标记夹具）

1. 主路径：device 入库成功 → 拓扑完整轮次标记 → 重放落关系；`exec_status` 只反映 device。
2. 双配置：节点两配置 ID 不同、指标 `instance_id` 同、Run 身份不同。
3. 拓扑先到 → pending → 设备入库唤醒 → 关系一致、无重复边。
4. 重复同一 `run_attempt_id` → 关系不翻倍。
5. 关拓扑/改配置升版本后旧标记到达 → stale；关系策略符合「默认保留已有」。
6. device 成功 + 拓扑无成功标记 → 任务状态成功；上一轮关系保留；有失败日志。
7. device 成功 + 重放失败 → 任务状态仍成功；关系保留上一轮；不污染为任务失败。
8. device 失败 → `exec_status` 按现有口径；与拓扑是否成功无关。
9. 存量仅旧单配置 + `has_network_topo=True` 对账 → 自动第二份拓扑配置与推荐周期。
10. 删任务后晚到拓扑标记 → 幂等忽略；无关系回写、无孤儿配置。

**不进默认 CI（发布前 / 可选）**

- 真·250/50 容量与事件循环延迟（L5）；
- 全链路 Stargazer 重启 abandoned 后整轮重采（L3 可单测模拟）；
- 新旧 Agent/Server 长滚动升级（L2/L3 兼容切片已覆盖关键路径）。

### 落点提示

- Web：现有任务表单/`formatTaskValues` 相关测。
- Server：扩 `test_network_topology_*`、pipeline；完成标记夹具与 round-gated 共用。
- Agent：`agents/stargazer/tests/`；容量用假调度器/槽位计数。
- E2E：扩 `server/apps/cmdb/tests/e2e/test_network_pipeline.py`。

## Out of Scope

- 修改 getBulk 的 `OID not increasing` 降级算法；
- 拓扑增量采集或差异计算，每轮拓扑仍采集全量证据；
- operation_analysis 的 `network_status_topology` 链路；
- 默认拆分成独立 Stargazer 进程或 Pod；
- 新增对外 API 或对外端口；
- 把网络拓扑暴露为第二条用户可管理的 CMDB 采集任务。

## Confirmation Checklist（已确认 2026-08-24）

以下决定已确认，作为后续实现和测试讨论的输入：

1. 一个 Network 任务、两个采集通道，不创建第二条 `CollectModels`；
2. 任务状态只反映 device 通道；topology 失败仅日志可追溯，不做面向用户的通道状态；
3. 两份节点配置 ID 不同、指标范围相同，并通过配置版本阻止旧结果；
4. 拓扑周期默认 5 倍；推荐模式自动联动，自定义模式保留用户值并可恢复推荐值；该字段仅
   控制拓扑 Telegraf interval；
5. 正式运行完成事件触发拓扑重放，拓扑先到时进入可重试 pending；
6. 总目标并发默认 250，拓扑环境变量默认 50、范围 1～100；
7. 普通任务保底等于总并发减去拓扑上限，并可借用拓扑空闲容量；
8. 不抢占运行目标，通过自然完成逐步归还容量；
9. 关闭拓扑默认保留已有关系，旧版本结果不得恢复关系；
10. 测试细案已锁定（见 Testing Decisions：L1–L5，2026-08-24）。

## Verification Evidence（2026-08-25）

- L1：`web` `professCollection.test.ts` 4 passed（拓扑周期推荐/自定义）。
- L2：`test_network_channel_split.py`、`test_node_params_multicred.py` 网络双通道
  用例通过（双配置 ID、fencing、pending、幂等 skipped、gate→replay）。
- L3：`tests/test_concurrency_env_limits.py`、`tests/test_round_complete.py`、
  `tests/test_collection_scheduler.py` 通过。
- L4 子集：`apps/cmdb/tests/e2e/test_network_pipeline.py` 通过（含设备路径不查
  topo、force_topology_replay 拓扑路径）；与 round-gated 共用完成标记。
- L5 真·250/50 压测按约定不进默认 CI，发布前手工。
