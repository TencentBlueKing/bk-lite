# bk-lite Kubernetes 采集器

这是一个用于采集 Kubernetes 集群节点和容器性能指标的采集器，支持将指标和日志数据发送到 bk-lite 监控平台。

## 功能特性

- **节点指标采集**: 收集 CPU、内存、磁盘、网络等系统级指标
- **容器指标采集**: 通过 cAdvisor 收集容器运行时指标
- **Kubernetes 状态指标**: 通过 kube-state-metrics 收集集群状态信息
- **高性能数据传输**: 使用 Telegraf 和 VictoriaMetrics Agent 进行数据处理和传输
- **NATS 消息队列**: 支持通过 NATS 进行可靠的数据传输
- **日志采集**: 使用 Vector 采集和处理容器日志

## 组件说明

| 组件 | 类型 | 作用 |
|------|------|------|
| cadvisor | DaemonSet | 采集容器运行时指标 |
| telegraf-daemonset | DaemonSet | 采集节点系统指标 |
| kube-state-metrics | Deployment | 采集 Kubernetes 集群状态指标 |
| telegraf-deployment | Deployment | 作为指标接收和转发服务 |
| vmagent | Deployment | Prometheus 指标抓取和远程写入 |
| vector-daemonset | DaemonSet | 采集和处理容器日志 |

## 前置要求

- Kubernetes 集群版本 >= 1.16
- 集群节点需要有足够的资源（CPU、内存）
- 已部署 bk-lite 监控平台或具备 NATS 消息队列服务
- **单节点集群 / 控制平面跑业务的集群**：本包中的 Deployment（kube-state-metrics、
  telegraf-deployment、vmagent）不携带任何污点容忍，遵循集群默认调度语义。若集群
  唯一可调度节点仍保留 `node-role.kubernetes.io/control-plane:NoSchedule` 污点，
  这些组件会 Pending——请按 Kubernetes 标准实践先移除该污点：

  ```bash
  kubectl taint nodes --all node-role.kubernetes.io/control-plane-
  ```

  DaemonSet（cadvisor、telegraf-daemonset、vector-daemonset）已内置
  control-plane/master 两条精确容忍，无需处理；如集群还有其他自定义污点节点需要
  纳入节点级采集，请在各 DaemonSet 的 `tolerations` 处按注释追加**精确**容忍项，
  不要使用无 key 的通配容忍（会穿透 cordon 与专用节点隔离）

## 安装部署

### 步骤 1: 准备配置

首先复制并编辑配置模板：

```bash
cp secret.env.template secret.env
```

编辑 `secret.env` 文件，配置以下参数：

```bash
# 集群的唯一标识，用于在 BK-Lite 中区分不同集群
CLUSTER_NAME=your-cluster-name

# NATS 服务连接信息
NATS_URL=tls://your-nats-server:4222
NATS_USERNAME=your-nats-username
NATS_PASSWORD=your-nats-password
```
确保你有 CA 证书文件 `ca.crt`，用于与 NATS 服务器建立安全连接，可以从/opt/bk-lite/conf/cert/ca.crt 获取自签名的ca文件。

### 步骤 2: 创建 namespace 和 secret

```bash
# 创建命名空间
kubectl create ns bk-lite-collector

# 方式一：从环境文件创建 secret，然后添加 CA 证书
kubectl create -n bk-lite-collector secret generic bk-lite-monitor-config-secret \
  --from-env-file=secret.env

kubectl -n bk-lite-collector patch secret bk-lite-monitor-config-secret \
  --type='json' \
  -p="$(printf '[{"op":"add","path":"/data/ca.crt","value":"%s"}]' "$(base64 -w0 ca.crt)")"
```

方式二：使用 YAML 文件手动创建 secret：

```bash
# 复制模板文件
cp secret.yaml.template secret.yaml

# 生成 base64 编码的配置值并填入 secret.yaml
echo -n "your-cluster-name" | base64        # 填入 CLUSTER_NAME
echo -n "tls://your-nats-server:4222" | base64  # 填入 NATS_URL
echo -n "your-username" | base64            # 填入 NATS_USERNAME
echo -n "your-password" | base64            # 填入 NATS_PASSWORD
base64 -w0 ca.crt                           # 填入 ca.crt

# 编辑 secret.yaml 填入上述 base64 编码的值后，应用配置
kubectl apply -f secret.yaml
```

### 步骤 3: 部署采集器

```bash
kubectl apply -f bk-lite-metric-collector.yaml
kubectl apply -f bk-lite-log-collector.yaml
```

### 步骤 4: 验证部署

检查所有组件是否正常运行：

```bash
# 查看 Pod 状态
kubectl get pods -n bk-lite-collector

# 查看 DaemonSet 状态
kubectl get ds -n bk-lite-collector

# 查看 Deployment 状态
kubectl get deploy -n bk-lite-collector

# 查看日志
kubectl logs -n bk-lite-collector -l app=telegraf
```

## 配置说明

### 资源配置

各组件的默认资源配置如下：

| 组件 | CPU 请求 | 内存请求 | CPU 限制 | 内存限制 |
|------|----------|----------|----------|----------|
| cadvisor | 400m | 400Mi | 800m | 2000Mi |
| telegraf-daemonset | 100m | 128Mi | 500m | 512Mi |
| kube-state-metrics | 50m | 64Mi | 200m | 256Mi |
| telegraf-deployment | 100m | 128Mi | 500m | 512Mi |
| vmagent | 100m | 128Mi | 500m | 512Mi |

### 网络配置

- telegraf-deployment 服务监听端口：9090
- cadvisor 服务监听端口：8080
- kube-state-metrics 服务监听端口：8080, 8081

## 从旧版本升级（重要）

早期版本下发的集群级资源使用了通用名字（ClusterRole / ClusterRoleBinding
`kube-state-metrics`、`vmagent-role`、`vmagent-role-binding`、`vector-daemonset`）。
这些名字与集群自带监控栈（kube-prometheus、KubeSphere 等）的默认命名相同，
`kubectl apply` 会整份覆盖对方而不是合并，导致对方的 kube-state-metrics 丢失
权限、监控页面无数据。

当前版本已把全部集群级资源改名为 `bk-lite-` 前缀。**改名后旧对象不会被自动
回收**，从旧版本升级时需要手动清理，否则它们会继续占用集群自带监控栈的名字。

```bash
# 1. 先确认这些对象确实属于 BK-Lite，再删除
#    subjects 指向 bk-lite-collector 命名空间的才是 BK-Lite 下发的
kubectl get clusterrolebinding kube-state-metrics -o yaml
kubectl get clusterrolebinding vmagent-role-binding -o yaml
kubectl get clusterrolebinding vector-daemonset -o yaml
```

```bash
# 2. 确认无误后删除旧的集群级资源
kubectl delete clusterrolebinding kube-state-metrics vmagent-role-binding vector-daemonset --ignore-not-found
kubectl delete clusterrole kube-state-metrics vmagent-role vector-daemonset --ignore-not-found
```

```bash
# 3. 应用新版本 manifest
kubectl apply -f bk-lite-metric-collector.yaml
kubectl apply -f bk-lite-log-collector.yaml
```

如果集群里原本就有自己的监控栈，第 2 步删除后需要重新应用该监控栈的 RBAC，
把被覆盖掉的 ClusterRole / ClusterRoleBinding 恢复回它自己的定义。

## 卸载

集群级资源不属于任何命名空间，删除 namespace 不会连带回收，必须显式删除。

```bash
# 删除命名空间内的全部资源
kubectl delete -f bk-lite-metric-collector.yaml --ignore-not-found
kubectl delete -f bk-lite-log-collector.yaml --ignore-not-found

# 删除集群级资源
kubectl delete clusterrolebinding bk-lite-kube-state-metrics bk-lite-vmagent bk-lite-vector-daemonset --ignore-not-found
kubectl delete clusterrole bk-lite-kube-state-metrics bk-lite-vmagent bk-lite-vector-daemonset --ignore-not-found

# 删除 namespace（可选）
kubectl delete ns bk-lite-collector
```

