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
