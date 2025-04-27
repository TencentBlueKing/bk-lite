# 工具集

##  时间工具集

### langchain:current_time

| 函数名 | 中文名称 | 作用 |
|-------|---------|------|
| `get_current_time` | 获取当前时间 | 返回当前的系统时间，可用于记录操作时间或日志记录 |

## 搜索工具集

### langchain:duckduckgo

| 函数名 | 中文名称 | 作用 |
|-------|---------|------|
| `duckduckgo_search` | DuckDuckGo搜索 | 通过DuckDuckGo搜索引擎进行网络信息检索，获取相关查询结果 |


## Jenkins工具集

### langchain:jenkins

**运行时参数**
| 参数名 | 中文名称 | 作用 |
|-------|---------|------|
|`jenkins_url` | Jenkins服务器地址 | Jenkins服务器的URL地址 |
|`jenkins_username` | Jenkins用户名 | 用于身份验证的用户名 |
|`jenkins_password` | Jenkins密码 | 用于身份验证的密码 |

| 函数名 | 中文名称 | 作用 |
|-------|---------|------|
| `list_jenkins_jobs` | 列出Jenkins任务 | 获取Jenkins服务器上所有可用的构建任务列表 |
| `trigger_jenkins_build` | 触发Jenkins构建 | 远程触发指定的Jenkins任务执行构建操作 |

## Kubernetes工具集

| 函数名 | 中文名称 | 作用 |
|-------|---------|------|
| `get_kubernetes_namespaces` | 获取Kubernetes命名空间 | 列出集群中所有的命名空间 |
| `list_kubernetes_pods` | 列出Kubernetes容器组 | 列出指定命名空间或所有命名空间的Pod |
| `list_kubernetes_nodes` | 列出Kubernetes节点 | 获取集群中所有节点信息 |
| `list_kubernetes_deployments` | 列出Kubernetes部署 | 列出指定命名空间或所有命名空间的Deployment |
| `list_kubernetes_services` | 列出Kubernetes服务 | 列出指定命名空间或所有命名空间的Service |
| `list_kubernetes_events` | 列出Kubernetes事件 | 获取集群中的事件信息，用于诊断问题 |
| `get_failed_kubernetes_pods` | 获取失败的Kubernetes容器组 | 筛选并返回处于失败状态的Pod |
| `get_pending_kubernetes_pods` | 获取等待中的Kubernetes容器组 | 筛选并返回处于pending状态的Pod |
| `get_high_restart_kubernetes_pods` | 获取高重启次数的Kubernetes容器组 | 识别重启次数异常的Pod，帮助定位问题 |
| `get_kubernetes_node_capacity` | 获取Kubernetes节点容量 | 返回节点的资源使用情况和容量信息 |
| `get_kubernetes_orphaned_resources` | 获取Kubernetes孤立资源 | 发现并列出集群中的孤立资源，如未被使用的PVC等 |
| `get_kubernetes_resource_yaml` | 获取Kubernetes资源YAML | 导出指定资源的YAML配置，方便查看和编辑 |
| `get_kubernetes_pod_logs` | 获取Kubernetes容器组日志 | 获取指定Pod的日志信息，用于问题诊断和监控 |
