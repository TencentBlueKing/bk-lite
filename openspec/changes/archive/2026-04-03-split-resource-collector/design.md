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
