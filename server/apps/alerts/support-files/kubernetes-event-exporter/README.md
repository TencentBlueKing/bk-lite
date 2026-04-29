# BK-Lite Kubernetes Event Exporter

这是一个基于 `kubernetes-event-exporter` 的示例部署，用于把 Kubernetes 原生 `Event` 推送到 BK-Lite 告警中心。

该方案使用 BK-Lite 内置的 `k8s` 告警源，底层仍通过现有接收接口提交事件：

- 接口地址：`/api/v1/alerts/api/receiver_data/`
- 请求方法：`POST`
- 认证方式：请求头 `SECRET`
- 请求体格式：`{"source_id": "...", "events": [...]}`

## 目录说明

- `bk-lite-k8s-event-exporter.yaml`：Kubernetes 部署清单
- `secret.env.template`：通过 `kubectl create secret --from-env-file` 创建 Secret 的模板
- `secret.yaml.template`：直接 `kubectl apply` 的 Secret 模板

## 方案说明

这份配置默认只转发 Kubernetes `Warning` 类型事件，避免把大量 `Normal` 事件直接打进告警中心。

这是一份面向告警场景的 **best-effort** 示例配置，不是完整事件留存方案：

- `Normal` 事件会被主动丢弃
- `maxEventAgeSeconds: 60` 表示超过 60 秒的旧事件不会再发送
- 如果你需要完整审计或长期保留 Kubernetes Event，应额外接入日志/检索型存储

事件映射规则如下：

| Kubernetes Event | BK-Lite Event |
| --- | --- |
| `.Type` | `level`，`Warning -> 2`，其他 -> `3` |
| `.Reason` | `item` |
| `.Message` | `description` |
| `.GetTimestampMs` | `start_time` |
| `.UID` | `external_id` |
| `.InvolvedObject.UID` | `resource_id` |
| `.InvolvedObject.Name` | `resource_name` |
| `.InvolvedObject.Kind` | `resource_type`，优先映射到 `k8s_namespace / k8s_node / k8s_pod / k8s_workload` |
| `${CLUSTER_NAME}` | `location` |
| 固定值 | `source_id = k8s`，`service = kubernetes`，`action = created` |
| 可配置值 | `push_source_id` 默认 `k8s`，可按集群或推送链路修改 |

## 前置条件

1. BK-Lite 告警中心中已经初始化内置 `k8s` 告警源。
2. 你已经拿到了该告警源对应的：
   - `source_id`
   - `secret`
3. Kubernetes 集群可以访问 BK-Lite 服务地址。

## 步骤 1：准备 Secret

### 方式一：使用 env 文件

复制模板：

```bash
cp secret.env.template secret.env
```

编辑 `secret.env`：

```bash
CLUSTER_NAME=prod-cluster
BK_LITE_RECEIVER_URL=http://bk-lite-server:8001/api/v1/alerts/api/receiver_data/
BK_LITE_SOURCE_ID=k8s
BK_LITE_PUSH_SOURCE_ID=k8s
BK_LITE_SECRET=replace-with-your-alert-source-secret
```

创建 Secret：

```bash
kubectl create ns bk-lite-alerts
kubectl create -n bk-lite-alerts secret generic bk-lite-k8s-event-exporter-secret \
  --from-env-file=secret.env
```

### 方式二：使用 YAML

先创建命名空间：

```bash
kubectl create ns bk-lite-alerts
```

复制模板：

```bash
cp secret.yaml.template secret.yaml
```

修改 `secret.yaml` 中的实际值后执行：

```bash
kubectl apply -f secret.yaml
```

## 步骤 2：部署 Exporter

```bash
kubectl apply -f bk-lite-k8s-event-exporter.yaml
```

## 步骤 3：验证部署

查看 Pod 状态：

```bash
kubectl get pods -n bk-lite-alerts
```

查看日志：

```bash
kubectl logs -n bk-lite-alerts deploy/kubernetes-event-exporter
```

## 步骤 4：验证 BK-Lite 接口

在正式部署前，建议先用 curl 验证 BK-Lite 接口契约是否正确：

```bash
curl --location --request POST 'http://bk-lite-server:8001/api/v1/alerts/api/receiver_data/' \
  --header 'SECRET: your-alert-source-secret' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "source_id": "k8s",
    "events": [
      {
        "title": "K8s Warning FailedScheduling on Pod/default/demo",
        "description": "0/1 nodes are available",
        "level": "2",
        "item": "FailedScheduling",
        "start_time": "1751964596000",
        "external_id": "event-demo-001",
        "push_source_id": "k8s",
        "resource_id": "pod-uid-demo",
        "resource_name": "demo",
        "resource_type": "k8s_pod",
        "service": "kubernetes",
        "location": "prod-cluster",
        "action": "created",
        "tags": {
          "cluster": "prod-cluster",
          "namespace": "default",
          "kind": "Pod",
          "reason": "FailedScheduling",
          "type": "Warning"
        },
        "labels": {
          "cluster_name": "prod-cluster",
          "namespace": "default",
          "reason": "FailedScheduling",
          "type": "Warning",
          "kind": "Pod",
          "name": "demo"
        }
      }
    ]
  }'
```

返回 `{"status": "success", ...}` 表示接收成功。

## 步骤 5：制造一个测试事件

下面的示例会创建一个无法拉取镜像的 Pod，通常会产生 `Warning` 事件：

```bash
kubectl create ns bk-lite-event-test
kubectl run broken-image \
  -n bk-lite-event-test \
  --image=example.invalid/not-found:latest \
  --restart=Never
```

然后查看 exporter 日志：

```bash
kubectl logs -n bk-lite-alerts deploy/kubernetes-event-exporter
```

如果日志中出现 webhook 发送成功，同时 BK-Lite 事件列表里出现 `source_id = k8s` 的事件，说明链路正常。

## 注意事项

1. 这份配置默认丢弃 `Normal` 事件，只保留 `Warning`。
2. `resource_type` 优先映射到 BK-Lite 当前已有的 K8s 模型：
   - `Namespace -> k8s_namespace`
   - `Node -> k8s_node`
   - `Pod -> k8s_pod`
   - `Deployment / StatefulSet / DaemonSet / ReplicaSet / Job / CronJob -> k8s_workload`
3. 其他对象类型会回退为原始 `Kind` 字符串，避免事件因为 `resource_type` 为空而丢失定位信息。
4. `push_source_id` 默认值为 `k8s`，如需区分不同集群或链路，可在模板中修改 `BK_LITE_PUSH_SOURCE_ID`。
5. `ghcr.io/resmoio/kubernetes-event-exporter:latest` 适合快速验证，正式环境建议改成固定版本标签。

## 卸载

```bash
kubectl delete -f bk-lite-k8s-event-exporter.yaml
kubectl delete secret -n bk-lite-alerts bk-lite-k8s-event-exporter-secret
kubectl delete ns bk-lite-alerts
```
