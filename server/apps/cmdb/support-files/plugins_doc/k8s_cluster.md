## 说明
本插件用于从 Kubernetes 集群按需拉取四类资源实例指标，统一整理为结构化实例数据：k8s_namespace、k8s_workload、k8s_pod、k8s_node。
采集来源为指标采集插件，配置采集任务会从数据库中周期同步到CMDB中。

## 前置要求
### 1. k8s集群接入
*   [在线Kubernetes 集群接入指南](https://bklite.ai/docs/deploy/k8s-cluster-integration)
*   [离线Kubernetes 集群接入指南-概要版](#K8S接入指南)
### 2. k8s采集任务配置说明
*   集群接入时，在secret.env文件中配置了集群名称的参数：CLUSTER_NAME={your-cluster-name}，此集群名称为上报数据的核心维度
*   采集任务需要选择对应的CMDB的k8s集群实例，这个k8s集群实例的实例名，需要与前面配置的{your-cluster-name}保持一致。

## 采集内容
| key | 含义 |
| :-- | :-- |
| k8s.namespace.inst\_name | 命名空间实例展示名：`{namespace}({cluster})` |
| k8s.namespace.name | 命名空间名称 |
| k8s.namespace.self\_cluster | 所属集群名称 |
| k8s.namespace.assos | 关联关系（指向集群） |
| k8s.workload.inst\_name | Workload 展示名：`{workload}({cluster}/{namespace})` 或 ReplicaSet 特殊格式 |
| k8s.workload.name | Workload 名称 |
| k8s.workload.workload\_type | Workload 类型（deployment/statefulset/daemonset/job/cronjob/replicaset） |
| k8s.workload.replicas | 副本数 |
| k8s.workload.labels | 从注解解析出的标签串（`key=value` 逗号分隔） |
| k8s.workload.self\_ns | 所属命名空间编码：`{instance\_id}/{namespace}` |
| k8s.workload.self\_cluster | 所属集群 |
| k8s.workload.replicaset\_name | 若来源 ReplicaSet 填其名称 |
| k8s.workload.assos | 关联关系（指向命名空间） |
| k8s.pod.inst\_name | Pod 展示名：`{pod}({cluster}/{namespace})` |
| k8s.pod.name | Pod 名称 |
| k8s.pod.ip\_addr | Pod IP |
| k8s.pod.namespace | 命名空间名称 |
| k8s.pod.node | 调度节点名 |
| k8s.pod.created\_by\_kind | 上游控制器类型（小写） |
| k8s.pod.created\_by\_name | 上游控制器名称 |
| k8s.pod.limit\_cpu | CPU Limit（核） |
| k8s.pod.limit\_memory | 内存 Limit（Gi） |
| k8s.pod.request\_cpu | CPU Request（核） |
| k8s.pod.request\_memory | 内存 Request（Gi） |
| k8s.pod.self\_ns | 所属命名空间编码：`{instance\_id}/{namespace}` |
| k8s.pod.self\_cluster | 所属集群 |
| k8s.pod.k8s\_workload | 关联工作负载名称（若可溯源） |
| k8s.pod.k8s\_namespace | 若无法溯源工作负载则退化为命名空间引用 |
| k8s.pod.assos | 关联关系（节点、工作负载或命名空间） |
| k8s.node.inst\_name | 节点展示名：`{node}({cluster})` |
| k8s.node.name | 节点名称 |
| k8s.node.ip\_addr | 节点 Internal IP |
| k8s.node.os\_version | 操作系统镜像版本 |
| k8s.node.kernel\_version | 内核版本 |
| k8s.node.kubelet\_version | Kubelet 版本 |
| k8s.node.container\_runtime\_version | 容器运行时版本 |
| k8s.node.pod\_cidr | 节点 Pod CIDR |
| k8s.node.cpu | CPU 总量（核） |
| k8s.node.memory | 内存总量（Gi） |
| k8s.node.storage | 临时存储容量（Gi） |
| k8s.node.role | 节点角色（逗号分隔） |
| k8s.node.self\_cluster | 所属集群 |
| k8s.node.assos | 关联关系（指向集群） |



## K8S接入指南
### 前置要求
在开始部署之前，请确保满足以下条件： 
* Kubernetes 集群版本 ≥ 1.16
* 集群节点需要有足够的资源（建议每个节点预留 1 Core CPU 和 2GB 内存）
* 已部署 BK-Lite 监控平台
* 具备集群管理员权限（kubectl）
### 步骤 1：获取部署文件
从 BK-Lite 部署包中获取 Kubernetes 采集器的部署文件：
```
cd /opt/bk-lite/deploy/dist/bk-lite-kubernetes-collector
```
或从源码仓库获取：
```
git clone https://github.com/WeOps-Lab/bk-lite.git
cd bk-lite/deploy/dist/bk-lite-kubernetes-collector
```
### 步骤 2：准备配置文件
复制配置模板并编辑：
```
cp secret.env.template secret.env
```

编辑 secret.env 文件，配置以下参数：
```
# 集群的唯一标识，用于在 BK-Lite 中区分不同集群
# 建议使用有意义的名称，如：prod-k8s-cluster-01
CLUSTER_NAME=your-cluster-name

# NATS 服务连接信息
# NATS 服务地址，使用 TLS 加密连接
NATS_URL=tls://your-nats-server:4222

# NATS 认证信息
NATS_USERNAME=your-nats-username
NATS_PASSWORD=your-nats-password
```

参数说明：
* `CLUSTER_NAME`：集群的唯一标识，在 BK-Lite 平台中用于区分不同的 Kubernetes 集群，建议使用描述性名称
* `NATS_URL`：NATS 服务器地址，通常为 BK-Lite 平台提供的 NATS 服务地址
* `NATS_USERNAME` 和 `NATS_PASSWORD`：NATS 服务的认证凭据
### 步骤 3：获取 CA 证书
从 BK-Lite 平台获取 NATS 服务的 CA 证书文件：
```
# 如果是本地部署，可以从以下路径获取
cp /opt/bk-lite/conf/cert/ca.crt .
```
如果是远程部署，请联系 BK-Lite 平台管理员获取 ca.crt 文件。

### 步骤 4：创建 Namespace 和 Secret
方式一：使用环境文件创建（推荐）
```
# 创建命名空间
kubectl create namespace bk-lite-collector

# 从环境文件创建 Secret
kubectl create -n bk-lite-collector secret generic bk-lite-monitor-config-secret \
  --from-env-file=secret.env

# 添加 CA 证书到 Secret
kubectl -n bk-lite-collector patch secret bk-lite-monitor-config-secret \
  --type='json' \
  -p="$(printf '[{"op":"add","path":"/data/ca.crt","value":"%s"}]' "$(base64 -w0 ca.crt)")"
```
方式二：使用 YAML 文件创建

如果你更习惯使用 YAML 文件管理配置：
```
# 复制模板文件
cp secret.yaml.template secret.yaml

# 生成 base64 编码的配置值
echo -n "your-cluster-name" | base64              # 填入 CLUSTER_NAME
echo -n "tls://your-nats-server:4222" | base64    # 填入 NATS_URL
echo -n "your-username" | base64                  # 填入 NATS_USERNAME
echo -n "your-password" | base64                  # 填入 NATS_PASSWORD
base64 -w0 ca.crt                                 # 填入 ca.crt

# 编辑 secret.yaml，将上述 base64 编码的值填入对应字段
vim secret.yaml

# 应用配置
kubectl apply -f secret.yaml
```

### 步骤 5：部署采集器
部署指标采集器和日志采集器：
```
# 部署指标采集器（包含 cAdvisor、Telegraf、kube-state-metrics、vmagent）
kubectl apply -f bk-lite-metric-collector.yaml

# 部署日志采集器（Vector）
kubectl apply -f bk-lite-log-collector.yaml
```

### 步骤 6：验证部署
检查所有组件是否正常运行：
```
# 查看所有 Pod 状态
kubectl get pods -n bk-lite-collector

# 查看 DaemonSet 状态
kubectl get ds -n bk-lite-collector

# 查看 Deployment 状态
kubectl get deploy -n bk-lite-collector

# 查看具体组件日志
kubectl logs -n bk-lite-collector -l app=telegraf --tail=100
kubectl logs -n bk-lite-collector -l app=cadvisor --tail=100
kubectl logs -n bk-lite-collector -l app=vector --tail=100
```
预期结果：
所有 Pod 应该处于 Running 状态，DaemonSet 应该在每个节点上都有实例运行。

### 卸载采集器的方式
如需卸载采集器，执行以下命令：
```
# 删除采集器资源
kubectl delete -f bk-lite-metric-collector.yaml
kubectl delete -f bk-lite-log-collector.yaml

# 删除 Secret
kubectl delete secret -n bk-lite-collector bk-lite-monitor-config-secret

# 删除 Namespace（可选，会删除命名空间下所有资源）
kubectl delete namespace bk-lite-collector
```