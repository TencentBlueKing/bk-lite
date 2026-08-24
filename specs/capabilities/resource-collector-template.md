## ADDED Requirements

### Requirement: Resource collector template contains kube-state-metrics
`bk-lite-resource-collector.yaml` SHALL contain a kube-state-metrics Deployment (v2.13.0) with associated ClusterRole, ClusterRoleBinding, ServiceAccount, and headless Service.

#### Scenario: kube-state-metrics resources present
- **WHEN** the resource collector template is rendered
- **THEN** the output YAML contains Deployment `kube-state-metrics`, Service `kube-state-metrics`, ServiceAccount `kube-state-metrics` in namespace `bk-lite-collector`, plus cluster-scoped ClusterRole `bk-lite-kube-state-metrics` and ClusterRoleBinding `bk-lite-kube-state-metrics`

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

### Requirement: Metric collector ships the shared kube-state-metrics and scrapes it
`bk-lite-metric-collector.yaml` SHALL contain the kube-state-metrics Deployment, Service, RBAC, and ServiceAccount identical (same names, namespace, and container args) to the resource collector's copy, so that metric-only, resource-only, and combined deployments are all functional and apply order is irrelevant. The vmagent ConfigMap SHALL contain a `kubernetes-kube-state-metrics` scrape job: the monitor product's K8s derivative-object instance discovery (Pod/Node) and the web K8s dashboards consume the `prometheus_remote_write_kube_*` metrics produced only by this job. Its metric filters SHALL stay identical to the manually-applied `deploy/dist/bk-lite-kubernetes-collector/bk-lite-metric-collector.yaml`.

#### Scenario: KSM present in metric template
- **WHEN** the metric collector template is rendered
- **THEN** the output YAML contains Deployment, Service, ServiceAccount named `kube-state-metrics` in namespace `bk-lite-collector`, plus cluster-scoped ClusterRole and ClusterRoleBinding named `bk-lite-kube-state-metrics`
- **THEN** the vmagent-config ConfigMap contains both the `kubernetes-cadvisor` and `kubernetes-kube-state-metrics` scrape jobs

#### Scenario: metric collector deployed alone is fully functional
- **WHEN** only the metric collector is applied to a cluster
- **THEN** KSM is deployed by the metric collector itself and scraped by the `kubernetes-kube-state-metrics` job
- **THEN** K8s monitor objects (Cluster/Pod/Node) instance discovery and dashboards work without the resource collector

#### Scenario: both collectors applied to the same cluster in any order
- **WHEN** both the metric and resource collector templates are applied to the same cluster, in any order
- **THEN** the shared KSM (`bk-lite-collector/kube-state-metrics`) and its cluster-scoped RBAC (`bk-lite-kube-state-metrics`) carry identical definitions in every template, so the last-applied copy is equivalent and both pipelines keep working

### Requirement: Cluster-scoped resources are namespaced by name
Cluster-scoped objects are unique per cluster and `kubectl apply` replaces a
same-named object wholesale instead of merging it. Every ClusterRole and
ClusterRoleBinding shipped by `bk-lite-metric-collector.yaml`,
`bk-lite-resource-collector.yaml`, `bk-lite-log-collector.yaml` and the
manually-applied copies under `deploy/dist/bk-lite-kubernetes-collector/` SHALL
be named with a `bk-lite-` prefix, and SHALL NOT carry a `metadata.namespace`
field. Generic names such as `kube-state-metrics`, `vmagent-role` or
`vector-daemonset` collide with the monitoring stacks clusters already run
(kube-prometheus, KubeSphere), silently stripping their permissions.

#### Scenario: BK-Lite collector applied to a cluster that already runs kube-prometheus
- **WHEN** any K8S collector manifest is applied to a cluster whose own monitoring stack owns ClusterRole/ClusterRoleBinding `kube-state-metrics`
- **THEN** no BK-Lite object shares a name with it, so the existing binding keeps its subjects and the existing role keeps its rules
- **THEN** BK-Lite's own RBAC is named `bk-lite-kube-state-metrics`, `bk-lite-vmagent` and `bk-lite-vector-daemonset`

#### Scenario: ClusterRoleBinding subjects stay inside BK-Lite namespaces
- **WHEN** a BK-Lite ClusterRoleBinding is rendered
- **THEN** its `roleRef` resolves to a ClusterRole declared in the same manifest
- **THEN** every subject is a ServiceAccount in a `bk-lite-` prefixed namespace

### Requirement: Collector workloads tolerate control-plane NoSchedule
DaemonSets and Deployments in `bk-lite-metric-collector.yaml`,
`bk-lite-resource-collector.yaml`, `bk-lite-log-collector.yaml`, the dist
copies, and the K3S metric manifest SHALL include a toleration
`{operator: Exists, effect: NoSchedule}`. Control-plane nodes (and single-node
clusters) default to `node-role.kubernetes.io/control-plane:NoSchedule`;
without this toleration the collectors stay Pending and metrics or logs for
those nodes are empty.

#### Scenario: Apply onto a tainted control-plane node
- **WHEN** the collector is applied to a cluster whose schedulable node has
  `node-role.kubernetes.io/control-plane:NoSchedule`
- **THEN** cadvisor, telegraf-daemonset, kube-state-metrics, vmagent,
  telegraf-deployment, telegraf-resource and vector-daemonset are not left
  Pending due to an untolerated taint
