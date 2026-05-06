## 1. 工具能力补齐

- [x] 1.1 将 `diagnose_node_issues` 暴露到 Kubernetes 工具集和工具元数据中
- [x] 1.2 为 Kubernetes 日志能力补充 previous container logs 查询接口
- [x] 1.3 为外部告警接入增加 `normalize_alert_event` 工具，统一告警输入结构
- [x] 1.4 增加 `resolve_k8s_target_from_alert` 工具，将告警映射为 Pod、Node、Service 或 Deployment 目标

## 2. 数据采集编排与证据包

- [x] 2.1 定义数据采集 agent 使用的 incident evidence package schema
- [x] 2.2 增加 `collect_k8s_context_by_target_type` 工具，按目标类型选择采集路径
- [x] 2.3 为日志、事件、节点、服务链路和变更上下文定义统一 evidence block 结构（`status` / `data` / `error`）
- [x] 2.4 增加 `build_incident_evidence_package` 工具，统一汇总采集结果、错误信息和缺失数据
- [x] 2.5 确保最终 evidence package 的格式由工具/编排层输出，而不是主要依赖 prompt 约束
- [x] 2.6 为 Pod、Node、Service、Deployment 四类目标补齐对应的采集路径与输出字段

## 3. 技能配置与节点联调

- [x] 3.1 通过技能测试接口验证数据采集 agent 的 prompt、工具集和结构化输出能力
- [x] 3.2 更新数据采集 agent 的工具配置，只保留查询型、上下文型和打包型工具
- [x] 3.3 将告警接收节点输出与数据采集 agent 输入对齐到统一告警 schema
- [x] 3.4 将数据采集 agent 输出与告警分析 agent 输入对齐到 incident evidence package schema
- [x] 3.5 基于技能测试接口验证在弱 prompt 约束下仍能稳定输出统一 evidence package
- [x] 3.6 基于现有 workflow 节点完成端到端联调，验证无需新增节点类型即可跑通主链路

## 4. 场景验证

- [x] 4.1 验证 Pod CrashLoop 告警能够采集当前日志、previous logs、事件时间线和节点上下文
- [ ] 4.2 验证 Pod Pending 告警能够采集资源详情、事件时间线和节点上下文（当前真实集群无 Pending Pod 基线，场景脚本按 SKIP 处理）
- [x] 4.3 验证 Node 告警能够采集节点诊断上下文和相关告警信息
- [x] 4.4 验证 Service 异常告警能够采集服务链路和后端 Pod 上下文
- [x] 4.5 验证发布后异常告警能够采集 revision history、版本差异和相关运行上下文
