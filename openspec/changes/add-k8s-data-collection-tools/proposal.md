## Why

当前告警驱动 workflow 已经能够接收外部告警并触发 agent，但现有 Kubernetes 工具仍然偏向人工排障和已知对象查询。为了让数据采集 agent 在告警到分析的链路中稳定工作，需要补齐一套面向告警场景的数据采集能力，用于标准化告警输入、解析 Kubernetes 目标对象、自动收集证据，并向分析 agent 交付稳定的 evidence package。

## What Changes

- 增加面向 workflow 告警场景的 Kubernetes 数据采集能力。
- 增加告警标准化和 Kubernetes 目标解析能力，使数据采集 agent 可以直接处理外部告警 payload，而不是依赖调用方提供完整资源标识。
- 增加按目标类型自动编排采集路径的能力，能够根据 Pod、Node、Service、Deployment 等对象选择合适的 Kubernetes 查询方式。
- 增加标准化的 incident evidence package 输出，供下游分析 agent 以结构化方式消费采集结果，而不是依赖自由文本。
- 扩展重启类场景的日志采集能力，支持 previous container logs，并将现有 node diagnostics 能力正式暴露到工具集中，增强节点上下文采集。

## Capabilities

### New Capabilities
- `alert-driven-k8s-data-collection`: 标准化告警事件、解析 Kubernetes 目标对象、采集相关 Kubernetes 证据，并输出供下游分析使用的结构化 evidence package。
- `k8s-incident-log-context`: 采集告警场景所需的当前和 previous Pod 日志上下文、资源事件时间线，以及节点级采集上下文。

### Modified Capabilities

## Impact

- 影响代码：`server/apps/opspilot/metis/llm/tools/kubernetes/`、workflow agent 工具配置、告警驱动 workflow 的节点 prompt 与数据契约。
- 影响系统：OpsPilot workflow 执行链路、告警中心触发的数据采集流程、下游分析 agent 的输入契约。
- 依赖项：Kubernetes 工具加载与导出、现有 monitor 告警工具、workflow 节点间数据交接 schema。
