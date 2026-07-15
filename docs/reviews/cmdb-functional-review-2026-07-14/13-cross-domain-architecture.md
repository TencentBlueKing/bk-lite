# CMDB 跨域架构生产级复核

## 1. Summary

本复核以十三份已完成、已复审的功能报告为事实源，对 callback payload、错误映射、状态枚举、权限 helper、外部依赖 wrapper、布尔控制参数与 fallback 的定义位置进行横向归并，并按 framework、service、adapter、plugin、task orchestration、callback builder、error mapper、test fixture 判断职责归属。结论是：现有 `CMDB-F01`–`CMDB-F74` 已覆盖本轮能够满足证据门槛的结构性根因，**不新增 Finding，也不改动已复审 Finding 的事实、严重级别或主归属**。

编号中 `CMDB-F09` 不是漏项：Task 3 复审已将其“自动关系 Outbox 把 broker 接收当业务完成”归并到主 Finding `CMDB-F04`，编号按“一经分配不复用”保留。因此共有 **73 个主 Finding**，统计为 **P0 28 / P1 39 / P2 6 / P3 0**。跨域复核自身为 P0/P1/P2/P3 均 0，Recommendation 为 **Block**；阻断原因来自既有 28 个 P0 及其跨层依赖，而非为架构报告制造新数量。

### 1.1 跨域定义位置与建议归属

| 契约 | 当前定义位置与漂移 | 正确归属 |
|---|---|---|
| callback payload / ack | Stargazer `plugin_handler.py`、`nats_helper.py`，CMDB `nats/nats.py`，配置 `config_file_service.py`，凭据 push/hit-state 各自拼装；`result`、`processed`、publish/flush 与业务完成混用（F31/F33/F62） | adapter 注册表声明版本化 DTO；callback builder 只构造 envelope；领域 Service 持久化 application result；task orchestration 管恢复 |
| 错误映射 | `collect_dispatch_service.py` 解析英文文本，`celery_tasks.py` 拼安全摘要，Node/IPAM/订阅各自 `str(exc)`，NATS listener/client 使用 `message + pickled_exc/jsonpickle`（F22/F25/F63） | framework 只传结构化 `ErrorEnvelope`；adapter 把依赖异常映射为稳定 code；领域 Service 决定 retryable/category；统一 sanitizer 负责日志/DB/wire |
| 状态枚举 | `CmdbOperation/Outbox`、`CollectModels`、`ConfigFileVersion`、`IPAMReconcileRun`、`NodeMgmtSyncRun`、CustomReporting Batch、SubscriptionDelivery、MirrorOutbox 分别定义，但“已派发/已落库/业务完成”边界不同（F04/F20/F33/F38/F47/F50/F54/F60） | 每个领域保留自己的状态，但共享 execution/delivery 基元：owner、generation、lease、checkpoint、terminal aggregation；禁止 framework 用布尔值推导领域终态 |
| 权限 helper | HTTP 侧散落在 View/mixin/`permission_util.py`；NATS `_build_nats_permission_map` 仍信任 payload；custom provider `_allowed_orgs`、Node system 写和关系 Service 另建语义（F01/F02/F03/F14/F36/F45/F52/F58/F62） | framework 建可信 `CallerContext`；Service 入口统一解析 `AuthorizedResourceScope`；关系资源使用双端授权器；插件/Worker 只消费不可伪造 scope |
| 外部依赖 wrapper | `GraphClient` 双驱动、core NATS、NodeMgmt/SystemMgmt RPC、MinIO lifecycle wrapper 均存在，但 deadline、预算、错误和幂等没有统一契约（F15/F31/F51/F60/F63/F64） | adapter 负责 schema、timeout/cancel、错误码和调用相关 ID；Service 不直接解释裸 Response/异常文本；跨系统写由 durable delivery 编排 |
| 布尔控制参数 | `result`、`processed`、`delivery_detected`、`success`、`skip_permission_check`、空 `permission_map`、`return_entity`、`include_children`、`js=False` 在不同层改变安全或完成语义 | 布尔仅用于局部纯函数；身份、权限、投递、完成度改用枚举/类型化对象，危险 bypass 只允许封装在受审 system capability 内 |
| fallback | 临时兼容包括 NATS jsonpickle 旧协议（F63）与 Node display 旧数据源/展示结构；IPAM `subnet_id` 与关系查询是仍有生产者和内部读者的迁移期双轨契约；长期运行时策略包括 GraphClient 的 FalkorDB/Neo4j 选择（F15）；永久可选能力包括社区 CustomReporting 空 provider；订阅关系批查失败后还会逐实例 fallback（F61） | 不把所有 fallback 等同为待删除兼容代码：临时兼容归 compatibility layer 并声明版本、指标、失败语义和移除条件；迁移期双轨先停止/迁移生产者与读者并完成存量回填核对；图驱动归 adapter registry 与启动配置校验；可选 provider 以 capability 声明并 fail closed；订阅降级由 service/task orchestration 统一权限、预算和失败语义 |

### 1.2 Fallback 分类与治理条件

| 类别 | 当前实例 | 必须具备的生产级契约 |
|---|---|---|
| 临时协议/数据兼容 | NATS `pickled_exc/jsonpickle.decode` 旧响应；Node display 对旧采集摘要、实例行和展示结构的兼容 | 在 adapter/compatibility layer 明示支持的生产者与消费者版本、命中/拒绝/失败指标、fail-closed 失败语义和移除条件；未知版本、越权实体、超预算或无法判定完整性的旧数据不得按成功/空结果继续。jsonpickle 兼容还必须有禁用版本与迁移窗口，不能无限期保留跨进程对象反序列化。只有观测证明旧流量归零且发布窗口结束后才能移除。 |
| 迁移期双轨字段/关系契约 | IPAM 同时保留 `subnet_id` 字段与 subnet→IP 关系路径；当前 `_upsert_ip_instance` 仍写 `subnet_id`，`_writeback_subnet_utilization` 仍依赖该字段 | 不能把 `subnet_id` 当成只读历史 fallback 直接删除。退场前必须先停止或迁移所有字段生产者，将内部读者切到有权限与预算约束的关系契约，完成存量字段/关系回填与双向一致性核对；迁移期间对字段/关系分歧 fail closed 并记录指标。仅在旧字段读写命中归零、一致性达到发布门槛且跨过约定发布窗口后移除双轨。 |
| 长期运行时策略 | `GraphClient` 按部署配置选择 FalkorDB 或 Neo4j | 这是支持多运行时的 adapter strategy，不以“清退 fallback”为目标。由显式 adapter registry/启动配置校验选择唯一驱动；启动时拒绝缺失、冲突或不支持的组合，并以同一结构化查询、排序、预算、错误和契约测试证明双驱动语义一致。环境变量只应承载已校验配置，不能让领域 Service 猜测运行时。 |
| 永久可选能力 | 社区 `_EMPTY_CUSTOM_REPORTING` provider | 这是 Enterprise Overlay 未安装时的 optional-provider，不要求设置移除条件。framework 应显式暴露 capability availability/version：只读空结果必须可区分“能力未安装”和“已安装但业务数据为空”，所有写入、凭据、审核与 ingest 在无 provider 时稳定 fail closed；provider 注册与启动校验负责确认实现完整。 |
| 运行期降级路径 | 订阅关系批查失败后逐实例 RPC fallback | 降级前后必须使用同一可信 `CallerContext/AuthorizedResourceScope` 和关系双端权限，不得因 fallback 扩大可见范围；按单规则限制 fallback 实例数、RPC 次数、关系边、响应字节与单调 deadline。批查或降级失败、超限时持久化结构化且可重试的失败/checkpoint，不推进 `last_check_time` 或快照，也不得把部分/空结果解释为成功。 |
| Enterprise 实现降级 | Enterprise collector import 失败后默认选择同名 OSS（F69） | 只有 manifest 显式声明 schema/credential/error 版本等价并通过镜像 smoke 才允许降级；否则 `strict_enterprise=true` fail closed，记录来源、版本和失败码。 |

### 1.3 职责错放与复制成本

- **framework**：NATS registry 只保存 callable，身份、schema、预算和错误协议下放给 26 个 handler，导致 F62–F64；Enterprise extension/plugin/NodeParams registry 又可覆盖键、吞 import failure 或发布半成品（F70）。框架应拥有 CallerContext、DTO/预算声明、correlation/deadline、纯 JSON envelope，以及原子 capability manifest、唯一性和 readiness 校验。
- **service**：多个 Service 同时承担权限解析、外部 RPC、状态终结、展示兼容和错误文本拼接；Node sync 是最明显案例（F44–F51）。Service 应只编排领域规则，外部协议与持久化 execution 分离。
- **adapter**：Graph/NATS/NodeMgmt/SystemMgmt/MinIO wrapper 没有共同 timeout、错误码、幂等和响应大小契约；Enterprise 多对象 metric 路由与真实协议 I/O 也缺 adapter 契约（F66/F67/F69）。新增依赖调用会复制映射与防护。
- **plugin**：Stargazer 插件自行维护命令策略、shell 转义、资源上限、callback identity 和错误分类（F26–F30），把框架安全职责推给每个插件。
- **task orchestration**：`on_commit`、`.delay()` 或 RPC 返回常被当作业务完成；父子、租约接管、部分成功和跨存储恢复各自实现（F04/F20/F33/F38/F47/F50/F51/F54/F60）；附件 GC 无批次/deadline 且部分失败仍 SUCCESS（F74）。
- **callback builder / error mapper**：payload 与错误在 handler、plugin、Service、Worker 四层重复拼装；新增 callback 或错误类型必须联改多处，且已有 `result=true/processed=false`、未知投递布尔和 jsonpickle 分叉。
- **test fixture**：大量测试直接调用 Service/handler、Mock 图/RPC/发布或把缺陷行为写成正向断言；共享 fixture 没有强制 CallerContext、generation、budget、canary secret 与跨组织对端，导致跨层契约持续漏检。

## 2. Findings

本报告**不新增结构性 Finding**。以下矩阵保留每个已分配 ID，明确主归属、依赖/同根关系与去重结果；“相关”表示设计基元可共享但触发、影响和修复责任独立，不进行错误归并。

| ID | 主归属 / 主题 | 去重与依赖结论 |
|---|---|---|
| F01 | 模型子资源授权 | 主项；与 F03/F14/F62 共用 AuthorizedResourceScope，但对象不同 |
| F02 | 自动关联双端授权 | 主项；关系定义治理，相关 F14 实例关系双端授权 |
| F03 | 公共枚举组织授权 | 主项；引用统一组织 scope，不并入 F01 |
| F04 | 异步传播完成/恢复 | 主项；吸收原 F09，并被自动关系、采集 CRUD、Agent callback 引用 |
| F05 | SQLite 字段删除 | 主项；局部跨数据库错误，后果受 F06 跨存储放大 |
| F06 | 字段分组双写补偿 | 主项；与 F07/F11 共享 operation 模式，边界独立 |
| F07 | 布局部分回滚 | 主项；配置整包 revision，不并入字段分组 |
| F08 | 图成功后文件台账失败 | 主项；单实例 hook 阶段，依赖 F11/F13 的恢复基元 |
| F09 | 已归并/保留空号 | 原内容并入 F04；禁止复用，非主 Finding |
| F10 | 批量唯一锁/候选 | 主项；导入、采集、自定义上报引用 |
| F11 | 批量跨存储 Operation | 主项；导入、采集、自定义清理引用 |
| F12 | 唯一写锁 fencing | 主项；与 F20/F38/F47 共享 generation 原则，owner 范围不同 |
| F13 | Outbox 最终失败闭环 | 主项；依赖 F04 的完成语义，负责 Operation 终态 |
| F14 | 跨模型关系双端授权 | 主项；导入导出、IPAM、专项视图、custom/NATS 引用 |
| F15 | 排序/双图驱动契约 | 主项；归 adapter 结构化 Sort |
| F16 | 在线查询返回上限 | 主项；IPAM View 引用，区别离线作业预算 |
| F17 | 导入导出全量/N+1 | 主项；应用导出引用，长期转有状态作业 |
| F18 | 通用拓扑遍历预算 | 主项；应用/网络遍历引用 |
| F19 | IPAM 主题旧分支回带 | 主项；局部回归，不提升为架构根因 |
| F20 | 采集 execution owner/fencing | 主项；相关 F12/F38/F47，不归并 |
| F21 | 多凭据 outcome 丢失 | 主项；依赖统一状态/错误类型，负责目标级终态 |
| F22 | 文本错误分类 | 主项；领域 error mapper，F63 为传输错误协议 |
| F23 | 采集/清理批次预算 | 主项；配置孤儿清理/custom ingest 引用 |
| F24 | 自动删除审计 | 主项；应接入 F11 Operation/Outbox |
| F25 | 跨层敏感错误脱敏 | 主项；Agent、IPAM、Node、订阅、NATS 引用 |
| F26 | Agent 命令策略 | 主项；最终执行边界，不能只依赖控制面 |
| F27 | 空命令成功 | 主项；plugin request schema fail-closed |
| F28 | Agent 文件/CIDR 预算 | 主项；配置大小端到端链引用 |
| F29 | PowerShell 转义 | 主项；归 shell adapter |
| F30 | IP 插件注册路径 | 主项；归 plugin registry/启动校验 |
| F31 | NATS 未知投递三态 | 主项；F33/F50 使用其完成语义但领域终态独立 |
| F32 | 凭据 cursor 非唯一 | 主项；归 checkpoint `(time,id)` |
| F33 | 配置 READY 与 callback 成功 | 主项；通用 ack 引用 F04/F31 |
| F34 | 手动版本身份碰撞 | 主项；归持久身份/幂等键 |
| F35 | 超限正文静默截断 | 主项；端到端预算依赖 F28，产品语义独立 |
| F36 | 任务引用子网授权 | 主项；统一 AuthorizedResourceScope 的领域实例 |
| F37 | 空结果/完整快照混淆 | 主项；与 F54 共用 snapshot generation，数据源不同 |
| F38 | IPAM lease 无副作用 fencing | 主项；相关 F12/F20/F47，不归并 |
| F39 | IPAM occupant/总预算 | 主项；ReconcileBudget，区别 F23/F64 入口 |
| F40 | CIDR 集合并发约束 | 主项；区间 registry，不并入值唯一锁 F10 |
| F41 | K8s token 原子消费/TTL | 主项；cache capability 独立 |
| F42 | K8s 不可见父级泄露 | 主项；父级 fail-closed，相关 F14 |
| F43 | 专项视图查询总预算 | 主项；Room3D 引用；adapter 上限另由 F64 |
| F44 | Node 配置写权限 | 主项；权限 action 选择错误 |
| F45 | Node 全局执行/展示组织范围 | 主项；与 F62 CallerContext 相关，HTTP 边界独立 |
| F46 | Node 已有主机未更新 | 主项；局部事实/计数错误 |
| F47 | Node execution 单活/恢复 | 主项；相关 fencing 族，负责 Node run |
| F48 | Node 外部分页预算 | 主项；归 NodeMgmt adapter + 流式 Service |
| F49 | singleton/system_code 身份 | 主项；数据库业务唯一性 |
| F50 | 父子采集终态 | 主项；task orchestration，不能并入传输 ack |
| F51 | Node delete→push delivery | 主项；跨系统投影 delivery，相关 F04/F11 |
| F52 | 自定义任务组织/token scope | 主项；capability policy |
| F53 | 自定义实例 source ownership | 主项；organization 不等于来源身份 |
| F54 | partial snapshot 错删 | 主项；与 F37 共用 completeness 类型，不归并 |
| F55 | 空 identity_keys | 主项；task schema 局部错误 |
| F56 | schema 扩展未接线 | 主项；归 provider/adapter validator |
| F57 | Beat task 未注册 | 主项；归 task registry 启动一致性 |
| F58 | 订阅数据/收件人 scope | 主项；统一 AuthorizedResourceScope |
| F59 | ChangeRecord 全局查询 | 主项；NATS trend 引用 |
| F60 | 镜像单条/批量事务分叉 | 主项；统一 MirrorOutbox delivery |
| F61 | 订阅游标/预算/deadline | 主项；区别 F23 采集与 F64 adapter 预算 |
| F62 | NATS CallerContext/ACL | 主项；NATS 裸关系证据引用 F14 |
| F63 | NATS 错误对象协议 | 主项；脱敏引用 F25，领域分类引用 F22 |
| F64 | NATS schema/预算/deadline | 主项；adapter 通用边界，领域预算仍保留 |
| F65 | Enterprise secret schema | 主归属 credential/framework；相关 F25 脱敏但本项是落库/API 字段分类，不归并 |
| F66 | 无 I/O collector 伪成功 | 主归属 plugin/adapter；相关 F21 的真实失败聚合，但本项根本没有外部 attempt，不归并 |
| F67 | IBM MQ 多对象路由断裂 | 主归属 adapter DTO；相关 F21/F30，但模块可加载且失败点是 object_type→metric 契约，不归并 |
| F68 | stale 首行终止 fresh 结果 | 主归属 formatter/query normalization；相关 F21/F23，但触发是无序时序结果，不归并 |
| F69 | Enterprise import 静默 OSS fallback | 主归属 capability routing；相关 F30 模块加载，但本项是加载后 schema/认证降级策略，不归并 |
| F70 | registry 非原子且冲突可静默 | 主归属 framework registry；相关 F30 单一路径错误，但本项是完整 manifest 发布/唯一性，不归并 |
| F71 | 文件一对多引用覆盖 owner | 主归属 storage reference state；相关 F10/F12 竞态，但基数与 claim/CAS 根因独立 |
| F72 | 字段删除绕过文件回收 | 主归属 model/storage lifecycle；相关 F11 副作用恢复，但入口与生命周期 hook 不同 |
| F73 | multipart 解析前无总量边界 | 主归属 framework/resource budget；相关 F28 Agent 预算，但本项是 Django 入站字节边界 |
| F74 | GC 无预算且部分失败 SUCCESS | 主归属 task orchestration/storage；相关 F33/F35 终态，但独立周期队列与失败模型不归并 |

## 3. Test Review

跨域复核不运行新的业务测试，也不把静态汇总包装成新鲜业务验证。综合证据来自各域审查时的 fresh tests：模型治理六文件 102 passed，另有字段删除定向测试 1 failed；实例写入 49 passed/1 failed；查询拓扑 115 passed/1 failed；自动采集、配置文件、IPAM、专项资源、Node 同步、变更订阅与 NATS/RPC 分别为 82、66、54、51、36、82、64 passed。Stargazer 分拆结果为 49 passed、fixtures 154 passed/6 failed；Enterprise 自定义上报 38 passed、社区降级 6 passed，Enterprise collect Server 26 passed/1 failed、Stargazer 9 passed，附件扩展 21 passed。精确命令、退出码、覆盖率和环境限制均保留在 `evidence-index.md` 与 [reproduction-commands.md](reproduction-commands.md)，不得汇总为“全套测试通过”。

测试结构性缺口与 Finding 分布一致：

- handler/Service 直调绕开真实 HTTP/NATS framework，无法证明 CallerContext、ACL、双端授权与拒绝路径零副作用；
- Fake Graph/Mock RPC/Mock publish 证明调用形状，不证明 owner、重投、部分成功、deadline、跨存储恢复与应用 ack；
- 缺少共享的跨域契约 fixture：`generation + owner`、`ResourceBudget`、`ErrorEnvelope`、canary secret、跨组织同名/关系双端、父子 execution 与 snapshot completeness；
- 多个测试把缺陷行为锁成正向断言，例如空扫描置离线、静默截断和自报 scope 接受；修复时必须先改为业务契约测试，而非仅更新 Mock。

本次文档终验使用 [可复制命令附录](reproduction-commands.md) 检查：主 Finding 数量/唯一性/严重度、F09 归并、报告十字段、内部统计、跨报告引用目标、14 份报告齐套和 `git diff --check`。不运行 server/Stargazer 业务套件的原因是本任务没有修改业务代码或测试，且功能域 fresh evidence 已逐域留档。

## 4. Maintainability Verdict

1. **六个月后能否快速理解系统？** 不能稳定做到。业务架构文档给出正确纵切，但真实完成语义分散在 View、Service、Worker、callback 与外部 wrapper；同名 SUCCESS 在不同领域代表提交、投递、落库或内容 READY。
2. **新增同类插件是否需要复制代码？** 会。权限 scope、命令策略、资源预算、callback identity、错误 payload 和 delivery 判断仍由插件/handler 重写。
3. **新增错误类型是否需改多个模块？** 会。当前需联改插件、dispatch、Celery、NATS listener/client、领域状态和展示；F22/F25/F63 已证明漂移。
4. **新增 callback 模式是否容易扩展？** 注册容易，安全扩展困难。默认缺 caller provenance、schema、event ID、application ack、重放和持久化恢复，复制成本会产生 F31/F33 类分叉。
5. **当前接口是否容易被误用？** 是。空 permission map、自报 `allowed_org_ids/user_info`、`skip_permission_check`、裸关系 Service、`.delay()` 返回和布尔 `delivery_detected` 都会把调用形状误当授权或完成证明。
6. **日志是否足够且不泄密？** 否。状态关联 ID、owner/generation/checkpoint 不齐，同时原始异常、凭据、配置/设备输出仍可能跨日志、DB、wire 与 UI 扩散。
7. **状态异常时能否判断停在哪个阶段？** 局部可以（Operation、ConfigFileVersion、Delivery），跨域通常不行；父子任务、外部 delete→push、callback 单向 publish 和旧 owner 图副作用无法从单一状态实体重建。
8. **设计是否降低复杂度？** 已有 Operation/Outbox、配置正文生命周期、Delivery lease、IPAM 单活等基元降低了局部复杂度，但未抽成共享契约；复制后的相似状态机边界不同、语义漂移，整体复杂度仍转移到故障恢复和人工对账。

### 4.1 最小安全修复与长期设计取舍

| 主题 | 最小安全修复 | 长期设计 | 影响与取舍 |
|---|---|---|---|
| 身份与权限 | 先关闭所有 P0 越权入口：关系双端、任务内资源、Node/custom/subscription scope、ChangeRecord、NATS CallerContext | 统一 `CallerContext + AuthorizedResourceScope + RelationAuthorization` | 最小方案改动面较小但仍需入口清单；长期方案迁移广，能消除每入口重复授权 |
| 状态与交付 | 对已有链补 owner/generation、明确 PENDING/PARTIAL/FAILED、应用 ack 和恢复扫描；禁止派发即 SUCCESS | 共享 Execution/Delivery/ParentChildAggregation 基元 | 最小方案更快止血但会保留多套模型；长期方案降低复制，需迁移与可观测性建设 |
| 错误与脱敏 | 移除 wire `pickled_exc`，统一 safe code/category/retryable，所有日志/DB/UI 经 sanitizer | 类型化跨语言 `ErrorEnvelope` 与依赖 adapter 映射表 | 兼容窗口可能影响旧消费者；应提供只读版本降级而非继续反序列化 |
| 资源预算 | 在入口增加 bytes/rows/IDs/page/time 上限，超限零副作用；高风险全量任务先小批 checkpoint | 统一 `ResourceBudget`，在线查询、adapter、作业分别覆写更严格预算 | 硬上限可能改变大客户行为；需异步导出/作业替代而非简单拒绝全部需求 |
| 插件与外部系统 | 将命令策略、shell adapter、callback schema、Node delivery 修到最终边界 | plugin manifest/adapter registry 启动校验与 capability 声明 | 初期增加注册元数据，但能把运行期失败提前到启动/测试期 |
| Enterprise storage/task | 拒绝文件多归属、字段删除立即撤销引用、multipart 最外层限流，并给 GC 批次/deadline/失败终态 | durable file reference/claim 状态机 + 有界 cleanup queue；storage adapter 幂等删除、task orchestration 管 checkpoint/重试/死信 | 短期会拒绝部分旧调用；长期需迁移现有台账与对象引用，但能消除图/SQL 双真相和静默泄漏 |
| 测试 | 为每个 P0/P1 先加跨层负向契约和真实状态断言，保留各域 fresh commands | 建共享 contract suite，所有 HTTP/NATS/plugin/adapter 实现必须通过 | 测试时间上升；换取跨域一致性和显著降低 Mock 绿灯假象 |

## 5. Recommendation

**Block**。

最小上线门槛不是一次性重写全部架构，而是按风险顺序关闭：第一批 P0 权限/远程执行/数据丢失与错误成功；第二批 execution fencing、父子终态、跨系统 delivery 与 callback 应用 ack；第三批统一脱敏和硬资源预算。长期再把已经在多个域重复出现的 CallerContext、AuthorizedResourceScope、Execution/Delivery、ErrorEnvelope、ResourceBudget 与 contract fixture 抽成共享基元。

不建议以新增条件判断、继续传自报 scope、延长租约、只限制 page size、只截断日志或把更多异常 catch 成 SUCCESS/PARTIAL 作为替代。这些做法能降低单点症状，却会继续扩大复制成本和语义分叉。
