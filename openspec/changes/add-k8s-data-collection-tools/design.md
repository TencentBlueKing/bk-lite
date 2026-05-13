## Context

当前告警驱动 workflow 的主链路已经具备“告警接收 -> 数据采集 agent -> 告警分析 agent -> 通知”的基本结构，但数据采集阶段仍然依赖人工已知对象的 Kubernetes 查询方式。现有 K8S 工具能够覆盖资源详情、事件时间线、当前 Pod 日志、服务链路和部分变更上下文，但还缺少面向外部告警场景的统一入口、对象解析、采集编排和证据打包能力。

本次设计聚焦在数据采集 agent，不扩展到分析 agent 的根因推理和自动处置。目标是在 workflow 中把外部告警消息稳定转换为结构化 incident evidence package，为后续分析节点提供统一输入。

约束条件：
- 现有工具体系已经通过 `ToolsLoader` 暴露 Kubernetes、monitor 等工具，设计应尽量复用已有查询能力，而不是重建整套查询逻辑。
- workflow 节点之间更适合传递结构化数据，而不是长文本。
- 数据采集 agent 只负责收集事实，不负责最终诊断和执行动作。

## Goals / Non-Goals

**Goals:**
- 为外部告警驱动的 workflow 增加面向采集 agent 的统一告警输入标准化能力。
- 为采集 agent 增加 Kubernetes 目标对象解析能力，支持从告警消息映射到 Pod、Node、Service、Deployment 等对象。
- 根据目标对象类型自动选择采集路径，收集资源详情、事件、日志、节点上下文、服务链路和变更上下文。
- 定义稳定的 incident evidence package 结构，作为采集 agent 到分析 agent 的节点间契约。
- 补齐重启类场景所需的 previous container logs 能力，并将现有 node diagnostics 正式接入工具集。

**Non-Goals:**
- 不在本次设计中实现根因排序、解决方案生成或客户话术生成，这些属于分析 agent 职责。
- 不在本次设计中引入自动修复动作，如重启 Pod、回滚 Deployment、扩缩容等执行能力。
- 不在本次设计中覆盖所有外部监控系统的适配细节，只定义 workflow 所需的统一输入和采集契约。

## Decisions

### 1. 采用“双层能力”结构：原子查询工具 + 采集编排工具

决策：保留现有 Kubernetes 原子工具不变，在其上新增少量采集编排工具，用于适配 workflow 场景。

原因：
- 现有工具已经覆盖大部分底层查询能力，直接复用可降低实现成本。
- workflow 需要的是稳定、可重复的采集路径，而不是让 agent 每次通过 prompt 临时决定调用哪些工具。
- 通过新增编排工具，可以把对象类型判断、采集范围控制、证据包输出沉淀为显式能力。

主要新增能力：
- `normalize_alert_event`
- `resolve_k8s_target_from_alert`
- `collect_k8s_context_by_target_type`
- `build_incident_evidence_package`
- `get_kubernetes_previous_pod_logs`

备选方案：
- 方案 A：只靠 prompt 编排现有工具。
  - 未采用原因：输出不稳定，难以形成 workflow 节点契约，也不利于后续扩展。
- 方案 B：重写一个新的“全能采集工具”。
  - 未采用原因：会复制已有工具能力，维护成本高。

### 2. 数据采集 agent 只输出结构化 evidence package，不输出最终结论

决策：采集 agent 输出统一 JSON 结构，包含告警信息、目标对象、采集范围、各类证据块、缺失数据和错误信息。

原因：
- 分析 agent 需要稳定输入，避免依赖自由文本解析。
- 结构化输出能清晰区分“采集成功”“部分成功”“未采集”“采集失败”。
- 通知节点和回调节点也可以复用同一份结构化结果。

备选方案：
- 方案 A：采集 agent 输出自然语言摘要。
  - 未采用原因：不利于分析 agent 精准消费，也难以做字段级校验和回放。

### 2.1 将输出格式约束下沉到工具/编排层，而不是主要依赖 prompt

决策：evidence package 的结构统一由采集编排工具负责，prompt 只保留兜底约束，不承担主要格式控制职责。

原因：
- workflow 节点之间需要稳定的数据契约，工具层的结构化输出比 prompt 约束更可靠。
- 底层 Kubernetes 工具职责各不相同，不适合为了 workflow 场景逐个改造成最终输出格式；更适合在采集编排层统一包装。
- 将格式统一集中在编排层后，采集 agent prompt 可以更专注于“何时采集哪些证据”，而不是反复强调字段结构。

设计约束：
- 底层原子工具继续保留各自职责和原始返回风格。
- 新增或增强编排型工具，将底层工具结果包装为统一 evidence block，至少包含 `status`、`data`、`error`。
- `build_incident_evidence_package` 负责产出最终的 incident evidence package，作为采集 agent 的唯一标准输出边界。

备选方案：
- 方案 A：仅通过 prompt 强约束模型输出固定 JSON。
  - 未采用原因：属于软约束，易受模型生成偏差影响，难以作为 workflow 稳定契约。
- 方案 B：将所有底层 Kubernetes 工具都改成统一最终格式。
  - 未采用原因：改动面过大，会破坏现有工具兼容性，也不利于保持原子工具职责单一。

### 3. 按目标对象类型定义采集策略，而不是统一大而全采集

决策：根据 `target.resource_type` 选择不同的采集路径。

建议策略：
- Pod：资源详情 + 事件时间线 + 当前/previous 日志 + 关联 Node 上下文 + 可选变更上下文
- Node：节点详情 + 节点事件 + `diagnose_node_issues` + 相关活跃告警
- Service：服务详情 + `trace_service_chain` + 关联 Pod 事件与日志
- Deployment：资源详情 + 关联 Pod 概览 + 事件时间线 + revision history / diff

原因：
- 不同对象需要的证据不同，统一全量采集会增加噪声和执行时延。
- 采集策略显式化后，更容易在 workflow 中调试和扩展。

备选方案：
- 方案 A：每次默认采集所有类型上下文。
  - 未采用原因：成本高、结果冗余，且容易让分析 agent 淹没在低价值数据中。

### 4. 将 previous logs 作为 Pod 重启类场景的正式采集能力

决策：补充 `get_kubernetes_previous_pod_logs`，或在现有 `get_kubernetes_pod_logs` 上增加 `previous=true` 语义，但对 workflow 暴露为明确的重启类日志能力。

原因：
- CrashLoopBackOff、OOM 后重启等场景下，关键证据通常存在于上一个容器实例的日志中。
- 当前日志工具只支持当前运行容器日志，无法完整支撑重启类告警采集。

备选方案：
- 方案 A：仅保留当前日志采集。
  - 未采用原因：会导致高频故障场景证据缺失。

### 5. 将现有 `diagnose_node_issues` 正式纳入采集工具集

决策：复用现有 `node_diagnostics.py` 中的能力，并将其导出到 Kubernetes 工具集，供数据采集 agent 使用。

原因：
- 当前代码中已有较完整的节点健康、压力、碎片化、Taint 采集逻辑。
- Node 类告警如果只使用 `list_kubernetes_nodes` 和 `describe_kubernetes_resource`，证据深度不够。

备选方案：
- 方案 A：采集 agent 自行组合 Node 基础工具。
  - 未采用原因：重复逻辑较多，且难以保持节点采集结果的一致性。

## Risks / Trade-offs

- [告警对象信息不足] 外部告警可能只包含服务名或模糊标签，无法稳定映射到 Kubernetes 对象 -> 通过 `normalize_alert_event` 和 `resolve_k8s_target_from_alert` 显式处理，并在 evidence package 中输出 `missing_data`。
- [采集结果过重] 如果默认采集所有上下文，可能导致 agent 执行时延和 token 开销上升 -> 通过目标类型分流和采集范围控制参数约束采集深度。
- [工具边界混乱] 采集 agent 可能滥用分析型工具输出结论 -> 在工具配置上仅暴露查询型、上下文型和打包型能力，不暴露执行型工具。
- [Node 侧证据仍不完整] 即使接入 `diagnose_node_issues`，仍缺 kubelet/runtime/system log -> 在本次设计中先补齐节点状态上下文，节点日志能力作为后续增强项。
- [监控与 Kubernetes 数据不一致] 外部告警时间点和集群当前状态可能存在偏差 -> 在 evidence package 中保留告警触发时间、采集时间和时间窗口，供分析 agent 判断证据时效性。
- [输出格式漂移] 如果仍主要依赖 prompt 维持输出结构，下游节点可能收到不稳定结果 -> 通过编排型工具统一 evidence block 和 evidence package 输出，prompt 仅保留兜底约束。

## Migration Plan

1. 在 workflow 侧定义采集 agent 的输入输出 schema，并固定 incident evidence package 字段。
2. 暴露并接入 `diagnose_node_issues` 到 Kubernetes 工具集。
3. 增加告警标准化、目标解析、采集编排和 evidence package 打包工具，并由编排层统一输出结构化 evidence blocks。
4. 增加 previous logs 采集能力，并在 Pod 重启类采集路径中接入。
5. 更新数据采集 agent 的工具配置，仅保留查询型和采集型工具；prompt 中仅保留最小必要输出约束。
6. 通过技能测试接口验证结构化 evidence package 输出稳定性。
7. 通过典型告警场景验证链路：Pod CrashLoop、Pod Pending、Node NotReady、Service 不可用、发布后异常。

回滚策略：
- 如果新增采集编排工具不稳定，可暂时回退到原子工具直接调用方式，同时保留 workflow 节点契约不变。
- 如果 previous logs 或 node diagnostics 接入出现兼容性问题，可在 evidence package 中将对应证据块标记为 `failed` 或 `skipped`，不阻断主链路。

## Open Questions

- 外部告警 payload 的标准字段集合是否需要在 workflow 入口层统一约束，还是在 `normalize_alert_event` 中兼容多种格式。
- previous logs 能力是扩展现有日志工具还是新增独立工具，哪种方式更适合当前工具体系和 agent 配置模型。
- Service 类告警是否需要强制补采 Endpoints 级别信息，还是先依赖 `trace_service_chain` 的现有输出。
- Node 日志是否需要在后续通过外部日志系统补齐，以支持更完整的节点级故障采集。
