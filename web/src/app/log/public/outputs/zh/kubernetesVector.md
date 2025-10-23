### Vector k8s简介

- &zwnj;**基本功能**&zwnj;
  - 采集 Pod 容器日志
  - 自动解析日志字段
  - 附加 Kubernetes 元数据
  - 支持多源多目标转发
  - 提供结构化日志输出

- &zwnj;**主要特点**&zwnj;
  - 轻量级高性能
  - 资源占用低
  - 插件化扩展灵活

### Vector k8s 输出字段


| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| file | required、string、literal | 日志来源文件的绝对路径，用于标识该日志行对应的具体容器日志文件。通常路径中包含 Pod 的命名空间、名称和 UID。 | /var/log/pods/pod-namespace_pod-name_pod-uid/container/1.log |
| kubernetes.container_id | optional、string、literal | 容器运行时生成的唯一 ID，用于区分不同的容器实例。一般包含运行时前缀（如 docker://）。 | docker://f24c81dcd531c5d353751c77fe0556a4f602f7714c72b9a58f9b26c0628f1fa6 |
| kubernetes.container_image | optional、string、literal | 容器所使用的镜像名称及版本标签，用于标识镜像来源。 | busybox:1.30 |
| kubernetes.container_image_id | optional、string、literal | 容器镜像的唯一 ID，通常以镜像 digest 形式表示，比镜像名更精确。 | busybox@sha256:1e7b63c09af457b93c17d25ef4e6aee96b5bb95f087840cffd7c4bb2fe8ae5c6 |
| kubernetes.container_name | optional、string、literal | 容器的逻辑名称，用于区分同一 Pod 内的不同容器。 | coredns |
| kubernetes.namespace_labels | optional、object | Namespace 上附加的一组标签，通常用于分组、选择和管理资源。 | { "mylabel": "myvalue" } |
| kubernetes.pod_annotations | optional、object | Pod 上的注解集合，通常用于存储辅助性、非标识性的信息。 | { "myannotation": "myvalue" } |
| kubernetes.pod_ip | optional、string、literal | Pod 分配的 IPv4 地址，供服务间通信使用。 | 192.168.1.1 |
| kubernetes.pod_ips | optional、string、literal | Pod 的 IP 地址列表，可能同时包含 IPv4 和 IPv6。 | 192.168.1.1, ::1 |
| kubernetes.pod_labels | optional、object | Pod 上附加的一组标签，常用于服务发现、选择器匹配和策略控制。 | { "mylabel": "myvalue" } |
| kubernetes.pod_name | optional、string、literal | Pod 的唯一名称，由系统或用户定义，用于区分不同 Pod。 | coredns-qwertyuiop-qwert |
| kubernetes.pod_namespace | optional、string、literal | Pod 所属的命名空间，用于逻辑隔离 Kubernetes 资源。 | kube-system |
| kubernetes.pod_node_name | optional、string、literal | Pod 实际运行所在的节点名称，帮助定位日志来源的物理/虚拟机。 | minikube |
| kubernetes.pod_owner | optional、string、literal | Pod 的拥有者对象（如 ReplicaSet、Deployment），用于追踪控制器与 Pod 的关系。 | ReplicaSet/coredns-565d847f94 |
| kubernetes.pod_uid | optional、string、literal | Pod 的唯一 UID，由 Kubernetes 自动分配，用于唯一标识 Pod 实例。 | ba46d8c9-9541-4f6b-bbf9-d23b36f2f136 |
| message | required、string、literal | Pod 日志的原始内容，表示容器标准输出或标准错误中的一行日志数据。 | 53.126.150.246 - - [01/Oct/2020:11:25:58 -0400] "GET /disintermediate HTTP/2.0" 401 20308 |
| source_type | required、string、literal | 日志来源的类型标识，用于区分不同采集器或数据源。 | kubernetes_logs |
| stream | required、string、literal | 日志输出的流名称，通常为容器的标准输出（stdout）或标准错误（stderr）。 | stdout / stderr |
| timestamp | required、timestamp | Kubernetes 处理该日志事件的精确时间戳，通常用于日志排序与时序分析。 | 2020-10-10T17:07:36.452332Z |


### Vector k8s 输出样例

```json
{
"file": "/var/log/pods/kube-system_storage-provisioner_93bde4d0-9731-4785-a80e-cd27ba8ad7c2/storage-provisioner/1.log",
  "kubernetes.container_image": "gcr.io/k8s-minikube/storage-provisioner:v3",
  "kubernetes.container_name": "storage-provisioner",
  "kubernetes.namespace_labels": {
    "kubernetes.io/metadata.name": "kube-system"
  },
  "kubernetes.pod_annotations": {
    "prometheus.io/scrape": "false"
  },
  "kubernetes.pod_ip": "192.168.1.1",
  "kubernetes.pod_ips": [
    "192.168.1.1",
    "::1"
  ],
  "kubernetes.pod_labels": {
    "addonmanager.kubernetes.io/mode": "Reconcile",
    "gcp-auth-skip-secret": "true",
    "integration-test": "storage-provisioner"
  },
  "kubernetes.pod_name": "storage-provisioner",
  "kubernetes.pod_namespace": "kube-system",
  "kubernetes.pod_node_name": "minikube",
  "kubernetes.pod_uid": "93bde4d0-9731-4785-a80e-cd27ba8ad7c2",
  "message": "F1015 11:01:46.499073       1 main.go:39] error getting server version: Get \"https://10.96.0.1:443/version?timeout=32s\": dial tcp 10.96.0.1:443: connect: network is unreachable",
  "source_type": "kubernetes_logs",
  "stream": "stderr",
  "timestamp": "2020-10-15T11:01:46.499555308Z"
}
