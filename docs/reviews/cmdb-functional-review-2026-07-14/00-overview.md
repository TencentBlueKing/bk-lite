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
| 06 配置文件 | 未开始 | 0 | 0 | 0 | 0 | 待评审 | [06-config-file.md](06-config-file.md) |
| 07 IPAM | 未开始 | 0 | 0 | 0 | 0 | 待评审 | [07-ipam.md](07-ipam.md) |
| 08 专项资源视图 | 未开始 | 0 | 0 | 0 | 0 | 待评审 | [08-specialized-resource-views.md](08-specialized-resource-views.md) |
| 09 Node 同步 | 未开始 | 0 | 0 | 0 | 0 | 待评审 | [09-node-sync.md](09-node-sync.md) |
| 10 Enterprise 自定义上报 | 未开始 | 0 | 0 | 0 | 0 | 待评审 | [10-enterprise-custom-reporting.md](10-enterprise-custom-reporting.md) |
| 11 变更与订阅 | 未开始 | 0 | 0 | 0 | 0 | 待评审 | [11-change-subscription.md](11-change-subscription.md) |
| 12 NATS / RPC | 未开始 | 0 | 0 | 0 | 0 | 待评审 | [12-nats-rpc.md](12-nats-rpc.md) |
| 13 跨域架构复核 | 未开始 | 0 | 0 | 0 | 0 | 待评审 | [13-cross-domain-architecture.md](13-cross-domain-architecture.md) |
