# CMDB 全功能生产级审查总览

## 1. Summary

本次审查以 `server/apps/cmdb/BUSINESS_ARCHITECTURE.md` 为业务入口，覆盖 `server/apps/cmdb/`、Enterprise Overlay 全运行态和 CMDB 相关 Stargazer 链路，排除 Web。十三个业务功能域和一个跨域架构复核，共十四份报告均已完成；审查只修改报告，没有修改生产代码或测试。

整体风险为**极高**，不建议合并或按当前状态发布。共确认 **73 个主 Finding：P0 28 / P1 39 / P2 6 / P3 0**。`CMDB-F09` 已在实例写入复审时归并至 `CMDB-F04`，编号保留且不复用，因此有效主 Finding 是 `CMDB-F01`–`CMDB-F74` 中除 `CMDB-F09` 外的 73 项。

阻断问题不是单一模块缺陷，而是以下生产边界同时失守：关系、任务内资源、Node 同步、订阅、审计和 NATS 调用者的跨组织授权；Stargazer 最终执行边界的高危命令与资源预算；异步传播、采集、配置正文、IPAM、父子任务和快照的错误成功、旧 owner 副作用及不可恢复状态；敏感参数与外部错误跨日志、数据库、wire 和用户界面传播。最终 Recommendation 为 **Block**。

初始基线、逐域调用链、退出摘要、覆盖率和未验证项见 [evidence-index.md](evidence-index.md)，完整可复制命令见 [reproduction-commands.md](reproduction-commands.md)；73 项主 Finding 的归属与去重矩阵见 [13-cross-domain-architecture.md](13-cross-domain-architecture.md)。

| 功能域 | 状态 | P0 | P1 | P2 | P3 | Recommendation | 报告 |
|---|---|---:|---:|---:|---:|---|---|
| 01 模型治理 | 已完成 | 1 | 4 | 2 | 0 | Block | [模型治理](01-model-governance.md) |
| 02 实例写入 | 已完成 | 1 | 2 | 2 | 0 | Block | [实例写入](02-instance-write.md) |
| 03 查询与拓扑 | 已完成 | 1 | 4 | 1 | 0 | Block | [查询与拓扑](03-query-topology.md) |
| 04 自动采集 | 已完成 | 3 | 3 | 0 | 0 | Block | [自动采集](04-auto-collection.md) |
| 05 Stargazer 边界 | 已完成 | 3 | 4 | 0 | 0 | Block | [Stargazer 边界](05-stargazer-boundary.md) |
| 06 配置文件 | 已完成 | 2 | 1 | 0 | 0 | Block | [配置文件](06-config-file.md) |
| 07 IPAM | 已完成 | 2 | 3 | 0 | 0 | Block | [IPAM](07-ipam.md) |
| 08 专项资源视图 | 已完成 | 2 | 1 | 0 | 0 | Block | [专项资源视图](08-specialized-resources.md) |
| 09 Node 同步 | 已完成 | 4 | 4 | 0 | 0 | Block | [Node 同步](09-node-sync.md) |
| 10 Enterprise 自定义上报 | 已完成 | 3 | 3 | 0 | 0 | Block | [Enterprise 自定义上报](10-custom-reporting.md) |
| 11 变更与订阅 | 已完成 | 2 | 2 | 0 | 0 | Block | [变更与订阅](11-change-subscription.md) |
| 12 NATS / RPC | 已完成 | 1 | 2 | 0 | 0 | Block | [NATS / RPC](12-nats-rpc.md) |
| 13 跨域架构复核 | 已完成 | 0 | 0 | 0 | 0 | Block | [跨域架构复核](13-cross-domain-architecture.md) |
| 14 Enterprise Overlay | 已完成 | 3 | 6 | 1 | 0 | Block | [Enterprise Overlay](14-enterprise-overlay.md) |
| **合计（主 Finding）** | **已完成** | **28** | **39** | **6** | **0** | **Block** | **73 项** |

Enterprise 结论有明确 provenance 限制：根仓库 gitlink `7c7db340961d6b010d2c533de92970df253b545f` 在审查 worktree 未初始化；审查对象来自主工作区 ignored 安装态 Overlay。完整 78 个非缓存文件逐项哈希与聚合值 `9b82d0556665cc80c03a44c2b58e10e77ddc005fdc11aad6fcd27713ce139292` 见 [enterprise-overlay-provenance.md](enterprise-overlay-provenance.md)。该运行态与 gitlink commit 映射未知，因此当前分支不能单独重建审查对象。

## 2. Findings

所有 Finding 已按 P0 → P1 → P2 → P3 排序并保留用户要求的十个字段；本总览不复制 73 项正文，以免产生第二份可漂移事实源。逐项证据、触发、影响、测试漏检、最小安全修复和回归测试均在上表对应报告中，跨域主归属在 [去重矩阵](13-cross-domain-architecture.md) 中。

P0 可按外部后果归为四组：

1. **权限绕过与跨租户读写**：`CMDB-F14/F36/F42/F44/F45/F52/F53/F58/F59/F62`。关系对端、任务引用资源、父级资源、全局配置/同步、Enterprise token、订阅/审计和 NATS CallerContext 均存在确定的授权断点。
2. **远程执行、敏感信息与资源耗尽**：`CMDB-F25/F26/F27/F28/F65`。最终 Agent 边界可放行控制面已禁止的命令，空命令被报成功，文件/CIDR 可无界物化，凭据和外部错误缺统一脱敏。
3. **任务错误成功、数据丢失与不可恢复副作用**：`CMDB-F04/F08/F21/F33/F35/F46/F50/F54/F66/F67`。公共枚举、文件台账、混合采集、配置正文、Node 更新/父子终态和自定义快照会把失败标为成功、静默删尾、制造伪资产或丢失子对象。
4. **并发代次与副作用 fencing 缺失**：`CMDB-F20/F38/F41`。采集 execution、IPAM 租约和公开安装 token 的旧 owner/并发消费可突破状态与使用边界。

P1 主要覆盖错误模型失真、批量/跨存储 Operation 缺失、幂等与唯一性竞态、callback/delivery 不一致、timeout/清理/回滚缺口、查询和作业资源预算以及核心业务路径缺少有效回归证明。P2 集中于字段分组、布局、唯一锁 fencing、Outbox 最终失败闭环和 IPAM 主题回归；没有为了数量制造 P3。

## 3. Test Review

现有测试证明了一批局部正确骨架：单实例 Operation/Outbox 的部分 owner 与恢复行为；配置正文 PENDING/READY/ERROR/DELETE_PENDING 局部转换；IPAM 单活行与终态 owner 条件；订阅 Delivery 的事务 checkpoint、租约、代次和退避；若干 HTTP 权限正向、参数校验和小数据分页行为。

测试结果不能汇总为“全套通过”。各域 fresh evidence 同时包含：模型字段删除、查询主题和实例删除夹具失败；Stargazer IP 插件收集失败、fixtures 6 项失败、lint 配置缺失；Enterprise 自定义上报 38 passed，collect Server 26 passed/1 failed，Enterprise Stargazer 9 passed，附件扩展 21 passed。覆盖率多数低于相关模块 80% / 核心路径 90%：实例写入合计 45%、查询拓扑 33%、自动采集 65%、配置文件 46%、专项资源 63%、Node 同步 66%、Enterprise 自定义上报59%、Enterprise collect约72%、附件扩展72%、NATS 主模块54%；Stargazer 未能获得 coverage。

主要无效或不足的测试模式包括：直接调用 Service/handler 绕过 HTTP/NATS 调用者身份；Mock Graph/RPC/publish 后只验证调用；把空扫描置离线、超限正文静默截断、自报 scope 接受等缺陷行为锁成正向断言；未验证外部可观察终态、拒绝路径零副作用、真实并发/重投、部分成功、deadline、恢复 checkpoint 和 canary secret。

每个 P0/P1 都已在对应报告给出 Required tests。修复阶段应先写跨层负向回归，再实施最小修复；至少覆盖可信 CallerContext/组织与关系双端权限、Agent 高危命令与资源硬上限、generation/owner fencing、父子/快照完整终态、应用级 callback ack、跨存储恢复、错误脱敏，以及真实或等价契约的 FalkorDB/Neo4j、NATS、Celery 多 Worker、Redis、MinIO 和 NodeMgmt 故障路径。

## 4. Maintainability Verdict

1. **六个月后，其他开发者能否快速理解逻辑？** 不能稳定做到。相同 SUCCESS 在不同域分别代表提交、派发、落库或正文 READY，完成条件缺少统一状态图。
2. **新增同类插件是否需要复制代码？** 需要。权限 scope、命令策略、资源预算、callback identity、错误 payload 和 delivery 判断仍由插件或 handler 各自实现。
3. **新增错误类型是否需要修改多个模块？** 需要。插件、dispatch、Celery、NATS listener/client、领域状态和展示均有独立映射。
4. **新增 callback 模式是否容易扩展？** 注册容易，安全扩展困难。默认缺 publisher provenance、版本化 schema、event ID、应用确认、重放和持久化恢复。
5. **当前接口是否容易被误用？** 是。空 permission map、自报 `allowed_org_ids/user_info`、`skip_permission_check`、裸关系 Service、`.delay()` 返回和布尔投递状态均可能被误当授权或完成证明。
6. **日志是否足以排障且不会泄露敏感数据？** 否。owner/generation/checkpoint/correlation 信息不足，同时原始异常、凭据、配置或设备输出仍可能进入日志、DB、wire 和 UI。
7. **状态异常时能否判断任务停在哪个阶段？** 仅少数局部链路可以；父子任务、外部 delete→push、单向 callback、旧 owner 图副作用和 snapshot generation 无法从单一状态实体重建。
8. **当前设计降低复杂度了吗？** Operation/Outbox、配置正文生命周期和 Delivery lease 降低了局部复杂度，但相似基元被复制且完成边界不同，整体复杂度被移动到故障恢复和人工对账。

剩余结构性缺陷及正确归属为：framework 提供可信 CallerContext 与 schema/deadline；service 消费 AuthorizedResourceScope 和关系双端授权；adapter 统一外部错误、预算、取消与幂等；plugin 只声明能力和单位成本；task orchestration 管 owner/generation/checkpoint/父子终态；callback builder 只构造版本化 envelope；error mapper/sanitizer 统一安全错误；test fixture 提供跨组织、代次、预算和 canary-secret 契约。

### 最小安全修复优先级与长期设计取舍

| 优先级 | 当前范围内的最小安全修复 | 推荐长期设计 | 影响与取舍 |
|---|---|---|---|
| 1 | 逐入口关闭全部 P0 越权、远程执行、数据丢失和错误成功；拒绝路径必须零副作用 | `CallerContext + AuthorizedResourceScope + RelationAuthorization` 与执行端共享安全策略 | 最快阻断事故，但若只逐入口修补仍需维护完整入口清单 |
| 2 | 为采集/IPAM/Node/配置/自定义上报补 owner、generation、明确 PARTIAL/FAILED、父子聚合、应用 ack 和恢复扫描 | 共享 `Execution/Delivery/ParentChildAggregation` 基元 | 最小方案改动较小但保留多套状态机；长期方案迁移面大、能消除完成语义漂移 |
| 3 | wire 删除 `pickled_exc`，日志/DB/UI 统一 safe code、category、retryable 和 sanitizer | 跨语言 `ErrorEnvelope` 与 adapter 错误映射表 | 需要旧消费者迁移窗口，但不能继续反序列化语言对象换取兼容 |
| 4 | 为在线入口和后台作业增加 bytes/rows/IDs/pages/time/deadline 硬上限，超限零副作用；大任务改小批 checkpoint | 分层 `ResourceBudget`，在线查询、adapter 与持久作业各自收紧 | 硬上限会改变大客户行为，应以异步导出/作业替代，而不是无限放宽 |
| 5 | 修正插件注册、shell-specific 参数、Node delivery，并加启动时 registry 校验 | plugin manifest / adapter registry / capability 声明 | 增加注册元数据，但把运行期故障提前到启动与契约测试期 |

上述长期方案超出本次只读 Review 范围；本报告不授权自动重构。建议另开修复计划，按 P0 事故面拆批实施 TDD，关闭一批后重跑对应域和跨域契约复审。

## 5. Recommendation

**Block**。

原因：28 个 P0 中包含确定的权限绕过、远程执行风险、敏感信息泄露、资源耗尽、任务错误成功、数据丢失和旧 owner 不可恢复副作用；39 个 P1 又表明幂等、状态、callback、错误与资源契约尚未形成生产闭环。现有测试既未覆盖这些关键负向路径，也未普遍达到相关模块 80% / 核心路径 90% 目标。

只有在 P0 全部关闭、相关 P1 的跨层契约与恢复路径完成、每项都有明确回归测试，并补齐 Enterprise 可重建 provenance 后，才应重新评估合并结论。
