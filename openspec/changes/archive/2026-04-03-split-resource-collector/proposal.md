## Why

当前 `bk-lite-metric-collector.yaml` 把指标采集（cadvisor、telegraf、vmagent）和 Kubernetes 资源信息采集（kube-state-metrics）混在一起。用户无法单独部署 kube-state-metrics 来采集集群资源状态，也无法在不部署 kube-state-metrics 的情况下只采集节点指标。拆分后两份模板各自独立，可以按需组合部署。

## What Changes

- 从 `bk-lite-metric-collector.yaml` 中移除所有 kube-state-metrics 相关资源（Deployment、Service、RBAC），以及 vmagent-config 中对 kube-state-metrics 的 scrape job
- 新建 `bk-lite-resource-collector.yaml`，包含 kube-state-metrics 和独立的 telegraf-resource 数据通路（用 telegraf inputs.prometheus 直接 scrape ksm，不经过 vmagent）
- webhookd `kubernetes.sh` 的 type 枚举从 `metric|log` 扩展为 `metric|log|resource`，加载并渲染新模板
- 更新 webhookd `infra/API.md` 文档

## Capabilities

### New Capabilities
- `resource-collector-template`: 独立的 kube-state-metrics 采集模板，包含 ksm Deployment、telegraf-resource（直接 scrape ksm 并输出到 NATS）、以及相关 RBAC/Service/ConfigMap
- `webhookd-resource-type`: webhookd kubernetes.sh 支持 type=resource，渲染 resource-collector 模板

### Modified Capabilities

## Impact

- `agents/webhookd/bk-lite-metric-collector.yaml` — 移除 kube-state-metrics 相关资源
- `agents/webhookd/bk-lite-resource-collector.yaml` — 新文件
- `agents/webhookd/infra/kubernetes.sh` — type 校验和模板分支扩展
- `agents/webhookd/infra/API.md` — 文档更新
- 不涉及 server 端代码变更，不涉及前端变更
