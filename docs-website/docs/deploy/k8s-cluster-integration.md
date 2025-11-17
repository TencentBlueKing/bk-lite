---
sidebar_position: 1
---

# Kubernetes 集群接入指南

本指南介绍如何将 Kubernetes 集群接入 BK-Lite 监控平台，实现集群节点、容器和日志的统一监控。

---

## 功能特性

BK-Lite Kubernetes 采集器提供以下监控能力：

- **节点指标采集**：收集 CPU、内存、磁盘、网络等系统级指标
- **容器指标采集**：通过 cAdvisor 收集容器运行时指标
- **Kubernetes 状态指标**：通过 kube-state-metrics 收集集群状态信息
- **容器日志采集**：使用 Vector 采集和处理容器日志
- **高性能数据传输**：使用 Telegraf 和 VictoriaMetrics Agent 进行数据处理和传输
- **可靠消息队列**：支持通过 NATS 进行可靠的数据传输

---

## 采集器组件说明

| 组件 | 部署方式 | 作用 |
|------|---------|------|
| cadvisor | DaemonSet | 采集容器运行时指标 |
| telegraf-daemonset | DaemonSet | 采集节点系统指标 |
| kube-state-metrics | Deployment | 采集 Kubernetes 集群状态指标 |
| telegraf-deployment | Deployment | 作为指标接收和转发服务 |
| vmagent | Deployment | Prometheus 指标抓取和远程写入 |
| vector-daemonset | DaemonSet | 采集和处理容器日志 |

---

## 前置要求

在开始部署之前，请确保满足以下条件：

- Kubernetes 集群版本 **≥ 1.16**
- 集群节点需要有足够的资源（建议每个节点预留 1 Core CPU 和 2GB 内存）
- 已部署 BK-Lite 监控平台
- 具备集群管理员权限（kubectl）

---

## 部署步骤

### 步骤 1：获取部署文件

从 BK-Lite 部署包中获取 Kubernetes 采集器的部署文件：

```bash
cd /opt/bk-lite/deploy/dist/bk-lite-kubernetes-collector
```

或从源码仓库获取：

```bash
git clone https://github.com/WeOps-Lab/bk-lite.git
cd bk-lite/deploy/dist/bk-lite-kubernetes-collector
```

### 步骤 2：准备配置文件

复制配置模板并编辑：

```bash
cp secret.env.template secret.env
```

编辑 `secret.env` 文件，配置以下参数：

```bash
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

**参数说明：**

- `CLUSTER_NAME`：集群的唯一标识，在 BK-Lite 平台中用于区分不同的 Kubernetes 集群，建议使用描述性名称
- `NATS_URL`：NATS 服务器地址，通常为 BK-Lite 平台提供的 NATS 服务地址
- `NATS_USERNAME` 和 `NATS_PASSWORD`：NATS 服务的认证凭据

### 步骤 3：获取 CA 证书

从 BK-Lite 平台获取 NATS 服务的 CA 证书文件：

```bash
# 如果是本地部署，可以从以下路径获取
cp /opt/bk-lite/conf/cert/ca.crt .
```

如果是远程部署，请联系 BK-Lite 平台管理员获取 `ca.crt` 文件。

### 步骤 4：创建 Namespace 和 Secret

**方式一：使用环境文件创建（推荐）**

```bash
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

**方式二：使用 YAML 文件创建**

如果你更习惯使用 YAML 文件管理配置：

```bash
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

```bash
# 部署指标采集器（包含 cAdvisor、Telegraf、kube-state-metrics、vmagent）
kubectl apply -f bk-lite-metric-collector.yaml

# 部署日志采集器（Vector）
kubectl apply -f bk-lite-log-collector.yaml
```

### 步骤 6：验证部署

检查所有组件是否正常运行：

```bash
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

**预期结果：**

所有 Pod 应该处于 `Running` 状态，DaemonSet 应该在每个节点上都有实例运行。

---

## 配置调整

### 资源配置

各组件的默认资源配置如下：

| 组件 | CPU 请求 | 内存请求 | CPU 限制 | 内存限制 |
|------|----------|----------|----------|----------|
| cadvisor | 400m | 400Mi | 800m | 2000Mi |
| telegraf-daemonset | 100m | 128Mi | 500m | 512Mi |
| kube-state-metrics | 50m | 64Mi | 200m | 256Mi |
| telegraf-deployment | 100m | 128Mi | 500m | 512Mi |
| vmagent | 100m | 128Mi | 500m | 512Mi |
| vector-daemonset | 100m | 128Mi | 500m | 512Mi |

如果你的集群资源紧张或需要更高性能，可以修改 YAML 文件中的资源配置：

```yaml
resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi
```

### 采集频率调整

默认采集间隔为 30 秒，如需调整可以修改 Telegraf 配置中的 `interval` 参数。

---

## 常见问题

### 1. Pod 一直处于 Pending 状态

**原因：** 集群资源不足

**解决方案：**
- 检查节点资源使用情况：`kubectl top nodes`
- 调整资源请求值或增加集群节点

### 2. Pod 无法连接 NATS 服务

**原因：** 网络不通或认证信息错误

**解决方案：**
- 检查 NATS 服务地址是否正确
- 验证网络连通性：在 Pod 中执行 `ping` 或 `telnet` 测试
- 检查用户名和密码是否正确
- 查看 Pod 日志获取详细错误信息

### 3. CA 证书验证失败

**原因：** CA 证书文件错误或过期

**解决方案：**
- 重新从 BK-Lite 平台获取最新的 CA 证书
- 确保证书文件格式正确（PEM 格式）
- 重新创建 Secret

### 4. 数据未在 BK-Lite 平台显示

**原因：** 集群标识配置错误或数据传输失败

**解决方案：**
- 检查 `CLUSTER_NAME` 配置是否正确
- 查看采集器日志确认数据是否正常发送
- 在 BK-Lite 平台确认集群是否已注册

---

## 卸载采集器

如需卸载采集器，执行以下命令：

```bash
# 删除采集器资源
kubectl delete -f bk-lite-metric-collector.yaml
kubectl delete -f bk-lite-log-collector.yaml

# 删除 Secret
kubectl delete secret -n bk-lite-collector bk-lite-monitor-config-secret

# 删除 Namespace（可选，会删除命名空间下所有资源）
kubectl delete namespace bk-lite-collector
```

---

## 下一步

集群接入成功后，你可以：

1. 在 BK-Lite 平台查看集群监控数据
2. 配置告警规则监控集群健康状态
3. 使用 OpsPilot AI 进行智能运维
4. 接入更多 Kubernetes 集群实现多集群统一监控

如需更多帮助，请参考 [BK-Lite 官方文档](https://bklite.ai) 或联系技术支持。
