### 说明
采集 Kubernetes 集群的核心对象（节点、命名空间、工作负载、Pod），标准化同步至 CMDB。

> 此类与其他插件不同：**无需填写用户名/密码**。数据来源于目标集群内部署的 K8S 采集器（kube-state-metrics + 指标上报），由采集器把指标上报后同步到 CMDB。

### 操作入口与执行位置
本插件提供页面内的 **引导式接入向导**，无需你手写部署清单：

1. 在 CMDB Web 页面：进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”，选择 **K8S 集群** 插件后进入引导式接入向导。
2. 向导会生成一条带 token 的安装命令，复制该命令在目标集群内执行（部署 kube-state-metrics 与指标上报组件）。
3. 执行后向导自动轮询验证上报是否成功；`cluster_name` 由向导/部署参数设置，需与所选集群实例一致。

### 操作步骤
#### 步骤 1：进入向导并执行安装命令
在插件页面选择 K8S 集群后进入引导式接入向导，复制向导生成的、带 token 的安装命令，在目标集群内执行，部署 kube-state-metrics 与指标上报组件。`cluster_name` 由向导/部署参数设置。

#### 步骤 2：等待向导验证上报
执行安装命令后，向导会自动轮询验证指标上报是否成功；同时确认所选 CMDB K8S 集群实例的标识与 `cluster_name` 一致（`collector_cluster_id` 用于关联上报数据）。

#### 步骤 3：验证结果
- 保存并执行后，在任务详情查看 `新增 / 更新 / 删除` 摘要；在 CMDB 中应能查询到该集群下的节点、命名空间、工作负载、Pod 实例。
- 若清单为空，多为采集器未正常上报、集群标识与实例不一致，或 ServiceAccount 权限不足，核对后重采。

### 接入说明
本插件无需用户名/密码凭据，接入要点如下：
- 接入命令由页面引导式向导生成（带 token），复制后在目标集群内执行即可部署采集组件，无需手写部署清单。
- 集群标识：`cluster_name` 由向导/部署参数设置，需与所选 CMDB K8S 集群实例保持一致，`collector_cluster_id` 用于关联上报数据。
- 采集器需在目标集群内运行，并能正常向平台上报指标。

### 前置要求 / 权限
1. 集群内已部署 K8S 采集器（kube-state-metrics + 指标上报），且可访问 kube-state-metrics 指标。
2. 采集器使用的 ServiceAccount 需具备相应 ClusterRole，对以下资源拥有 `get` / `list` / `watch` 权限：
   `pods`、`nodes`、`namespaces`、`deployments`、`daemonsets`、`statefulsets`、`jobs`、`cronjobs`、`replicasets`。

### 采集内容（字段字典）
**节点（k8s_node）**

| Key 名称 | 含义 |
| :--- | :--- |
| name | 节点名称 |
| ip_addr | 节点 IP |
| os_version | 操作系统版本 |
| kernel_version | 内核版本 |
| kubelet_version | Kubelet 版本 |
| container_runtime_version | 容器运行时版本 |
| pod_cidr | 节点 Pod CIDR |
| cpu | CPU 总量 |
| memory | 内存总量 |
| storage | 存储容量 |
| role | 节点角色 |

**Pod（k8s_pod）**

| Key 名称 | 含义 |
| :--- | :--- |
| name | Pod 名称 |
| ip_addr | Pod IP |
| namespace | 所属命名空间 |
| node | 调度节点 |
| created_by_kind | 上游控制器类型 |
| created_by_name | 上游控制器名称 |
| limit_cpu | CPU Limit |
| limit_memory | 内存 Limit |
| request_cpu | CPU Request |
| request_memory | 内存 Request |

**工作负载（k8s_workload）**

| Key 名称 | 含义 |
| :--- | :--- |
| name | 工作负载名称 |
| workload_type | 工作负载类型（deployment / daemonset / statefulset / job / cronjob / replicaset） |
| replicas | 副本数 |
| labels | 标签 |

**命名空间（k8s_namespace）**

| Key 名称 | 含义 |
| :--- | :--- |
| name | 命名空间名称 |

**关联关系**
- `namespace belong cluster`：命名空间归属集群。
- `node group cluster`：节点归属集群。
- `workload belong namespace`：工作负载归属命名空间。
- `pod run node`：Pod 运行在节点上。
- `pod group workload`：Pod 归属工作负载。
