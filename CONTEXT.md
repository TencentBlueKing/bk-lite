# BK-Lite Shared Context

本文件只维护跨模块共享术语。业务规则、验收和运行边界读取 `specs/capabilities/`；难以回滚的决定读取 `docs/adr/`。

## Canonical terms

- **BK-Lite**：面向运维管理员的轻量、AI-first 运维平台。
- **Control Console**：`web/` 中的主控制台，不包含移动端壳和嵌入式 WebChat。
- **Node**：由 `server/node_mgmt` 管理、通过 Sidecar/Collector 与平台通信的受管节点。
- **Collector**：采集基础设施、日志、指标或配置数据并通过 NATS 等通道上报的运行单元。
- **监控实例**：当前受平台纳管的一个具体监控目标。
- **实例事实（Instance Fact）**：由监控插件接入输入或受信任平台数据推导出的、用于识别监控实例的标准化非敏感摘要信息；不是采集配置副本或监控指标。
- **日志采集实例**：用户配置的一条具体日志来源，以全局唯一的实例 ID 标识；它是日志权限、数据范围和提取规则归属的共同对象。_Avoid_：日志源、采集任务。
- **日志提取器**：把日志事件中的属性提取为结构化属性的一条有序规则。_Avoid_：解析器、清洗规则、Vector 规则。
- **Stargazer**：`agents/stargazer/` 中的云资源与外部资源采集代理。
- **Capability contract**：`specs/capabilities/<capability>.md` 中长期有效的业务、验收、架构和运行约束。
- **Change spec**：`specs/changes/<feature>/spec.md` 中跨会话的变更意图、实现决定和测试接缝。
- **Ticket**：仅在 change 超出一个上下文窗口时创建的可独立验证纵向切片。
- **Grill**：对模糊、跨域或难回滚问题逐问收敛的显式工作流；不是日常改动的默认前置。
- **Incident 负责人**：`Incident.operator` 中对该 Incident 具有管理职责的用户。_Avoid_：Incident 管理员、群管理员。
- **Incident 当前期望成员**：Incident 当前负责人和协作人去重后的集合；它描述本地协作关系，不等同于外部 IM 群的实际成员集合。_Avoid_：群成员、组织成员。
- **Incident IM 可加入成员**：在所选 IM 通道下已有唯一有效账号映射、可提交给平台入群的当前期望成员；待映射、映射冲突或被平台判定账号不可用的成员仍是当前期望成员，但本次不阻塞其他人建群。_Avoid_：已映射即已入群、无效成员阻断建群。
- **Incident IM 群绑定**：一个 Incident 与创建时所选 IM 通道及外部群之间不可切换的管理关系。_Avoid_：飞书群绑定、可切换渠道绑定。
- **持续同步**：开启后把新增的 Incident 当前期望成员补充加入已绑定外部群的单向行为；不自动移除成员，也不强制修复用户主动退群。_Avoid_：成员双向同步、群成员强一致。

## Maintenance

- 新术语只有在两个及以上模块共享、且名称歧义会影响实现时才加入。
- 不在这里写状态机、字段清单、实现计划或一次性决定。
