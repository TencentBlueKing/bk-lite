# BK-Lite Shared Context

本文件只维护跨模块共享术语。业务规则、验收和运行边界读取 `specs/capabilities/`；难以回滚的决定读取 `docs/adr/`。

## Canonical terms

- **BK-Lite**：面向运维管理员的轻量、AI-first 运维平台。
- **Control Console**：`web/` 中的主控制台，不包含移动端壳和嵌入式 WebChat。
- **Node**：由 `server/node_mgmt` 管理、通过 Sidecar/Collector 与平台通信的受管节点。
- **Collector**：采集基础设施、日志、指标或配置数据并通过 NATS 等通道上报的运行单元。
- **日志采集实例**：用户配置的一条具体日志来源，以全局唯一的实例 ID 标识；它是日志权限、数据范围和提取规则归属的共同对象。_Avoid_：日志源、采集任务。
- **日志提取器**：绑定日志采集实例、按用户指定顺序执行的一条结构化字段提取规则。_Avoid_：解析器、清洗规则、Vector 规则。
- **Stargazer**：`agents/stargazer/` 中的云资源与外部资源采集代理。
- **Capability contract**：`specs/capabilities/<capability>.md` 中长期有效的业务、验收、架构和运行约束。
- **Change spec**：`specs/changes/<feature>/spec.md` 中跨会话的变更意图、实现决定和测试接缝。
- **Ticket**：仅在 change 超出一个上下文窗口时创建的可独立验证纵向切片。
- **Grill**：对模糊、跨域或难回滚问题逐问收敛的显式工作流；不是日常改动的默认前置。

## Maintenance

- 新术语只有在两个及以上模块共享、且名称歧义会影响实现时才加入。
- 不在这里写状态机、字段清单、实现计划或一次性决定。
