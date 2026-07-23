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
