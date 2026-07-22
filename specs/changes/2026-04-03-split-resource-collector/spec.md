# 2026 04 03 Split Resource Collector

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-04-03-split-resource-collector/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

当前 webhookd 通过 `infra/kubernetes.sh` 提供 K8s 采集器 YAML 渲染服务。模板文件 `bk-lite-metric-collector.yaml` 包含了指标采集（cadvisor + telegraf + vmagent）和资源信息采集（kube-state-metrics）两类功能，二者耦合在一起。

数据通路现状：
```
cadvisor ──┐
           ├──▶ vmagent (scrape) ──▶ telegraf-deployment ──▶ NATS
ksm ───────┘
```

拆分后：
```
metric 模板:
  cadvisor ──▶ vmagent (scrape) ──▶ telegraf-deployment ──▶ NATS

resource 模板:
  kube-state-metrics ──▶ telegraf-resource (inputs.prometheus) ──▶ NATS
```

## Goals / Non-Goals

**Goals:**
- metric 和 resource 模板完全独立，可单独部署，互不依赖
- 两份模板部署到同一集群时不产生资源名称冲突
- webhookd 支持 `type=resource` 渲染新模板

**Non-Goals:**
- 不修改 server 端代码（Django views/services）
- 不修改前端代码
- 不改变 NATS subject 或数据格式
- 不改变现有 metric/log 的行为

## Decisions

### 1. resource 数据通路：telegraf 直接 scrape，不经 vmagent

**选择**: resource 模板用 telegraf `inputs.prometheus` 直接抓取 kube-state-metrics

**替代方案**: 像 metric 模板一样用 vmagent 做中转

**理由**: kube-state-metrics 是单点 Deployment，只需抓一个固定 endpoint（kube-state-metrics:8080/metrics）。不需要 vmagent 的 kubernetes_sd_configs 服务发现能力。少一层组件更简洁、资源消耗更少。

### 2. 命名约定：resource 侧组件加 `-resource` 后缀

metric 模板保持原有名称（cadvisor、vmagent、telegraf-deployment 等），resource 模板中的同类组件加 `-resource` 后缀（telegraf-resource、telegraf-resource-config），避免同一 namespace 下的冲突。kube-state-metrics 本身名称不变，因为它只存在于 resource 模板。

### 3. Namespace 和 Secret 两边都声明

两份模板都包含 `Namespace: bk-lite-collector` 的声明。Secret 由 kubernetes.sh 渲染时统一追加。`kubectl apply` 是幂等的，不会冲突。

## Risks / Trade-offs

- **[已部署集群升级]** 用户如果已经部署了旧的 metric-collector（包含 ksm），升级后新的 metric-collector 不再包含 ksm，但旧的 ksm 资源不会被自动清理 → 在文档/发布说明中提示用户需要手动清理旧的 ksm 资源，或先 `kubectl delete` 再重新 apply
- **[两套 telegraf 资源开销]** resource 模板独立一套 telegraf → ksm 数据量不大，telegraf-resource 资源需求很低（128Mi/100m 足够）

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-03
```

## Capability Deltas

### resource-collector-template

## ADDED Requirements

### Requirement: Resource collector template contains kube-state-metrics
`bk-lite-resource-collector.yaml` SHALL contain a kube-state-metrics Deployment (v2.13.0) with associated ClusterRole, ClusterRoleBinding, ServiceAccount, and headless Service.

#### Scenario: kube-state-metrics resources present
- **WHEN** the resource collector template is rendered
- **THEN** the output YAML contains Deployment `kube-state-metrics`, Service `kube-state-metrics`, ClusterRole `kube-state-metrics`, ClusterRoleBinding `kube-state-metrics`, ServiceAccount `kube-state-metrics` in namespace `bk-lite-collector`

### Requirement: Resource collector template contains independent telegraf-resource data path
`bk-lite-resource-collector.yaml` SHALL contain a Deployment `telegraf-resource` that uses `inputs.prometheus` to scrape `kube-state-metrics:8080/metrics`, and `outputs.nats` to send data to NATS (subject `metrics.cloud`).

#### Scenario: telegraf-resource scrapes kube-state-metrics directly
- **WHEN** the resource collector is deployed
- **THEN** `telegraf-resource` scrapes kube-state-metrics endpoint via `inputs.prometheus` at `http://kube-state-metrics:8080/metrics`
- **THEN** scraped data is sent to NATS via `outputs.nats` on subject `metrics.cloud`

#### Scenario: telegraf-resource uses dedicated ConfigMap
- **WHEN** the resource collector template is rendered
- **THEN** the output contains ConfigMap `telegraf-resource-config` with telegraf configuration for prometheus input and nats output

### Requirement: Resource collector template includes instance tags
`telegraf-resource` SHALL tag all metrics with `instance_id`, `instance_type=k8s`, and `instance_name` using the `CLUSTER_NAME` environment variable from the Secret, consistent with the metric collector's tagging convention.

#### Scenario: Metrics have correct instance tags
- **WHEN** telegraf-resource sends data to NATS
- **THEN** each metric includes tags `instance_id=<CLUSTER_NAME>`, `instance_type=k8s`, `instance_name=<CLUSTER_NAME>`

### Requirement: Resource collector template declares shared namespace
`bk-lite-resource-collector.yaml` SHALL declare `Namespace: bk-lite-collector` so it can be deployed independently without requiring the metric collector.

#### Scenario: Independent deployment
- **WHEN** only the resource collector template is applied to a cluster (without metric collector)
- **THEN** the namespace `bk-lite-collector` is created and all resources deploy successfully

### Requirement: No naming conflicts with metric collector
All resource-specific components (telegraf, ConfigMap) SHALL use `-resource` suffix to avoid name collisions with the metric collector template when both are deployed to the same cluster.

#### Scenario: Both templates deployed to same cluster
- **WHEN** both metric collector and resource collector are applied to the same cluster
- **THEN** no resource name conflicts occur — metric has `telegraf-deployment`/`telegraf-config`, resource has `telegraf-resource`/`telegraf-resource-config`

### Requirement: Metric collector no longer contains kube-state-metrics
After the split, `bk-lite-metric-collector.yaml` SHALL NOT contain kube-state-metrics Deployment, Service, RBAC, or ServiceAccount. The vmagent ConfigMap SHALL NOT contain the `kubernetes-kube-state-metrics` scrape job.

#### Scenario: kube-state-metrics removed from metric template
- **WHEN** the metric collector template is rendered
- **THEN** the output YAML does not contain any resources named `kube-state-metrics`
- **THEN** the vmagent-config ConfigMap only contains the `kubernetes-cadvisor` scrape job

### webhookd-resource-type

## ADDED Requirements

### Requirement: webhookd accepts type=resource
`kubernetes.sh` SHALL accept `type=resource` in addition to existing `metric` and `log` values.

#### Scenario: Valid resource type
- **WHEN** a request is sent with `"type": "resource"`
- **THEN** kubernetes.sh validates successfully and proceeds to render

#### Scenario: Invalid type rejected
- **WHEN** a request is sent with `"type": "invalid"`
- **THEN** kubernetes.sh returns an error: "Invalid type: must be 'metric', 'log' or 'resource'"

### Requirement: webhookd renders resource-collector template
When `type=resource`, kubernetes.sh SHALL load `bk-lite-resource-collector.yaml` as the template, render it with the Secret, and return the combined YAML.

#### Scenario: Resource template rendered with Secret
- **WHEN** a request is sent with `"type": "resource"` and valid NATS credentials
- **THEN** the response `yaml` field contains the resource collector template concatenated with the rendered Secret

### Requirement: API documentation updated
`infra/API.md` SHALL document `resource` as a valid value for the `type` parameter.

#### Scenario: API docs reflect new type
- **WHEN** a developer reads `infra/API.md`
- **THEN** the type parameter description lists `metric`, `log`, and `resource` as valid values

## Work Checklist

## 1. 新建 resource-collector 模板

- [x] 1.1 创建 `agents/webhookd/bk-lite-resource-collector.yaml`，包含: Namespace、kube-state-metrics Deployment、ClusterRole、ClusterRoleBinding、ServiceAccount、headless Service（从现有 metric-collector 中提取，保持配置不变）
- [x] 1.2 在 resource-collector 模板中添加 Deployment `telegraf-resource`，使用 `inputs.prometheus` 直接 scrape `http://kube-state-metrics:8080/metrics`，`outputs.nats` 输出到 `metrics.cloud`
- [x] 1.3 在 resource-collector 模板中添加 ConfigMap `telegraf-resource-config`，配置 prometheus input（urls = kube-state-metrics:8080/metrics）和 nats output，添加 instance_id/instance_type/instance_name tags

## 2. 精简 metric-collector 模板

- [x] 2.1 从 `agents/webhookd/bk-lite-metric-collector.yaml` 中移除 kube-state-metrics Deployment、Service、ClusterRole、ClusterRoleBinding、ServiceAccount
- [x] 2.2 修改 vmagent-config ConfigMap，移除 `kubernetes-kube-state-metrics` scrape job，只保留 `kubernetes-cadvisor`

## 3. 更新 webhookd kubernetes.sh

- [x] 3.1 在 `kubernetes.sh` 顶部加载新模板: `RESOURCE_TEMPLATE=$(cat "$WEBHOOKD_DIR/bk-lite-resource-collector.yaml")`
- [x] 3.2 修改 `validate_type()` 函数，接受 `metric|log|resource`
- [x] 3.3 修改 `render_k8s_config()` 函数中的模板选择逻辑，增加 `resource` 分支
- [x] 3.4 更新错误提示信息，将 "must be 'metric' or 'log'" 改为 "must be 'metric', 'log' or 'resource'"

## 4. 更新文档

- [x] 4.1 更新 `agents/webhookd/infra/API.md`，type 参数说明加入 `resource`，添加渲染 resource collector 的 curl 示例
