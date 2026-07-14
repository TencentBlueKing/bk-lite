# CMDB 全功能生产级审查总览

本台账跟踪 CMDB 12 个业务功能域及 1 个跨域架构复核任务。审查仅记录可复现证据和结论，不在本阶段修改生产代码或新增测试。

- 初始基线与统一证据字段：[evidence-index.md](evidence-index.md)
- 主 Finding ID：全局按 `CMDB-FNN` 编号（`NN` 为两位递增序号）；同一根因只建立一个主 Finding，其他报告仅引用。
- 完成条件：真实入口、主要调用链、权限/状态/失败/恢复/资源/职责边界、测试证明力、验证命令和未验证项均已记录，并给出明确 Recommendation。

| 功能域 | 状态 | P0 | P1 | P2 | P3 | Recommendation | 报告链接 |
|---|---|---:|---:|---:|---:|---|---|
| 01 模型治理 | 已完成 | 1 | 4 | 2 | 0 | Request changes | [01-model-governance.md](01-model-governance.md) |
| 02 实例写入 | 已完成 | 1 | 2 | 2 | 0 | Request changes | [02-instance-write.md](02-instance-write.md) |
| 03 查询与拓扑 | 已完成 | 1 | 4 | 1 | 0 | Request changes | [03-query-topology.md](03-query-topology.md) |
| 04 自动采集 | 已完成 | 3 | 3 | 0 | 0 | Request changes | [04-auto-collection.md](04-auto-collection.md) |
| 05 Stargazer 边界 | 已完成 | 3 | 4 | 0 | 0 | Block | [05-stargazer-boundary.md](05-stargazer-boundary.md) |
| 06 配置文件 | 已完成 | 2 | 1 | 0 | 0 | Block | [06-config-file.md](06-config-file.md) |
| 07 IPAM | 已完成 | 2 | 3 | 0 | 0 | Block | [07-ipam.md](07-ipam.md) |
| 08 专项资源视图 | 已完成 | 2 | 1 | 0 | 0 | Block | [08-specialized-resources.md](08-specialized-resources.md) |
| 09 Node 同步 | 已完成 | 4 | 4 | 0 | 0 | Block | [09-node-sync.md](09-node-sync.md) |
| 10 Enterprise 自定义上报 | 已完成 | 3 | 3 | 0 | 0 | Block | [10-custom-reporting.md](10-custom-reporting.md) |
| 11 变更与订阅 | 已完成 | 2 | 2 | 0 | 0 | Block | [11-change-subscription.md](11-change-subscription.md) |
| 12 NATS / RPC | 已完成 | 1 | 2 | 0 | 0 | Block | [12-nats-rpc.md](12-nats-rpc.md) |
| 13 跨域架构复核 | 已完成 | 0 | 0 | 0 | 0 | Block | [13-cross-domain-architecture.md](13-cross-domain-architecture.md) |

08 专项资源视图新增 `CMDB-F41`–`CMDB-F43`（P0 2/P1 1）；应用导出、应用/网络遍历和跨模型权限分别引用既有 `CMDB-F17/F18/F14`，不重复计数。

09 Node 同步新增 `CMDB-F44`–`CMDB-F51`（P0 4/P1 4）；父子采集终态断裂与 NodeMgmt 参数交付半完成分别独立登记 `CMDB-F50/F51`，外部错误泄露引用既有 `CMDB-F25`，不重复计数。

10 Enterprise 自定义上报新增 `CMDB-F52`–`CMDB-F57`（P0 3/P1 3）；关系双端授权、批写唯一锁、删除恢复和资源预算分别引用既有 `CMDB-F14/F10/F11/F23`。本域 Overlay 来自主工作区 ignored 安装态，根 gitlink 未初始化，结论可复核当前运行态但不能由当前主仓库分支单独重建。

11 变更与订阅新增 `CMDB-F58`–`CMDB-F61`（P0 2/P1 2）；`CMDB-F61` 独立负责订阅规则/Delivery/实例/关系/ChangeRecord 扫描的稳定游标、总预算、deadline 与可恢复 checkpoint，`CMDB-F23` 只作为其他域相似模式及 Mirror 调用方批量参考；原始事件与异常日志引用既有 `CMDB-F25`。Delivery 的租约、代次和永久错误骨架通过聚焦测试，但规则授权、ChangeRecord View 与规模恢复均缺负向证明。

12 NATS / RPC 新增 `CMDB-F62`–`CMDB-F64`（P0 1/P1 2）：消息体 scope/user_info 无可信调用者绑定、通用 listener 回传原始异常对象且客户端保留条件反序列化兼容路径、adapter 无统一 schema/批量预算和服务端 deadline。关系对端、ChangeRecord、领域错误脱敏、Stargazer 投递、配置 callback、Room3D 预算和 Node 父子终态分别引用既有 `CMDB-F14/F59/F25/F31/F33/F43/F50`，不重复计数。26 个注册入口已逐项盘点；brief 六文件 64 passed，但 NATS 主模块覆盖率仅 54%，listener/client 和多数裸读写入口没有业务安全断言。

13 跨域架构复核不新增 Finding：`CMDB-F09` 已在 Task 3 复审时归并到主项 `CMDB-F04`，编号保留且不复用；最终共有 63 个主 Finding，P0 25/P1 33/P2 5/P3 0。复核确认 CallerContext/授权 scope、execution/delivery、ErrorEnvelope、ResourceBudget、callback builder 与共享契约测试是主要跨域收敛点；现状 Recommendation 为 Block。
