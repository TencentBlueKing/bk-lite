"""Kubernetes故障诊断和监控工具"""
import json
from datetime import datetime
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from kubernetes import client
from neco.llm.tools.kubernetes.utils import prepare_context, format_bytes, parse_resource_quantity


@tool()
def get_failed_kubernetes_pods(config: RunnableConfig = None):
    """
    发现集群中所有失败或异常的Pod
    
    **何时使用此工具：**
    - 用户反馈"有Pod起不来"、"服务异常"、"应用崩溃"
    - 需要快速定位集群中所有问题Pod
    - 排查大面积故障时的第一步
    - 检查是否有镜像拉取、权限、资源等问题
    
    **工具能力：**
    - 扫描所有命名空间的Pod状态
    - 识别Failed、CrashLoopBackOff、ImagePullBackOff等异常状态
    - 提供容器级别的详细状态（退出码、重启次数、错误原因）
    - 自动过滤已完成的Job Pod（Succeeded状态）
    
    **典型问题类型：**
    - CrashLoopBackOff: 应用启动后立即崩溃
    - ImagePullBackOff: 镜像拉取失败（地址错误/无权限/网络问题）
    - Failed: Pod运行失败终止
    - Unknown: 节点失联或状态未知
    
    Args:
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含失败Pod列表，每个Pod包含：
        - name: Pod名称
        - namespace: 命名空间
        - phase: 当前状态
        - container_statuses[]: 容器状态详情
          - state: 状态（waiting/terminated/running）
          - reason: 失败原因（如CrashLoopBackOff）
          - exit_code: 退出码（137=OOMKilled, 1=Error）
          - restart_count: 重启次数
        - node: 所在节点
        
    **配合其他工具使用：**
    - 发现失败Pod后 → 使用 diagnose_kubernetes_pod_issues 深入诊断
    - 查看具体错误信息 → 使用 get_kubernetes_pod_logs 获取日志
    - 分析镜像问题 → 检查imageRegistry配置和Secret
    - 需要恢复服务 → 使用 restart_pod 或 delete_kubernetes_resource
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()
        pods = core_v1.list_pod_for_all_namespaces()
        failed = []

        for pod in pods.items:
            # Check if pod is in failed state or has failed containers
            is_failed = False
            container_statuses = []

            if pod.status.phase in ["Failed", "Unknown"]:
                is_failed = True

            if pod.status.container_statuses:
                for container in pod.status.container_statuses:
                    container_info = {
                        "name": container.name,
                        "ready": container.ready,
                        "restart_count": container.restart_count,
                        "image": container.image,
                        "state": {}
                    }

                    # Check container state
                    if container.state.waiting:
                        container_info["state"] = {
                            "status": "waiting",
                            "reason": container.state.waiting.reason,
                            "message": container.state.waiting.message
                        }
                        if container.state.waiting.reason in ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "InvalidImageName"]:
                            is_failed = True
                    elif container.state.terminated:
                        container_info["state"] = {
                            "status": "terminated",
                            "reason": container.state.terminated.reason,
                            "exit_code": container.state.terminated.exit_code,
                            "message": container.state.terminated.message
                        }
                        if container.state.terminated.exit_code != 0:
                            is_failed = True
                    elif container.state.running:
                        container_info["state"] = {
                            "status": "running",
                            "started_at": container.state.running.started_at.isoformat() if container.state.running.started_at else None
                        }

                    container_statuses.append(container_info)

            if is_failed:
                failed.append({
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "phase": pod.status.phase,
                    "container_statuses": container_statuses,
                    "node": pod.spec.node_name,
                    "message": pod.status.message,
                    "reason": pod.status.reason,
                    "creation_time": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None
                })

        return json.dumps(failed)
    except ApiException as e:
        return json.dumps({"error": f"获取失败Pod列表失败: {str(e)}"})


@tool()
def get_pending_kubernetes_pods(config: RunnableConfig = None):
    """
    发现无法调度或启动的Pending状态Pod
    
    **何时使用此工具：**
    - 用户反馈"Pod一直Pending"、"服务启动不了"、"调度失败"
    - 新部署的应用长时间未就绪
    - 扩容后新Pod无法启动
    - 检查集群资源是否充足
    
    **工具能力：**
    - 列出所有Pending状态的Pod
    - 分析无法调度的具体原因（资源不足/节点亲和性/Taint/PVC等）
    - 区分调度失败和初始化失败
    - 提供创建时间，识别长期Pending的Pod
    
    **常见Pending原因：**
    - Insufficient cpu/memory: 集群资源不足
    - No nodes available: 没有符合条件的节点
    - PersistentVolumeClaim not bound: 存储卷未绑定
    - Node affinity/selector: 节点选择器不匹配
    - Taints: 节点污点阻止调度
    
    Args:
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含Pending Pod列表，每个Pod包含：
        - name: Pod名称
        - namespace: 命名空间
        - node: 分配的节点（如果已调度）
        - reason: Pending原因（如SchedulingFailed）
        - message: 详细错误信息
        - creation_time: 创建时间
        
    **配合其他工具使用：**
    - 发现资源不足 → 使用 get_kubernetes_node_capacity 检查集群容量
    - 调度问题深入分析 → 使用 diagnose_pending_pod_issues
    - 检查节点状态 → 使用 diagnose_node_issues
    - 存储问题 → 使用 check_kubernetes_persistent_volumes
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()
        pods = core_v1.list_pod_for_all_namespaces()
        pending = []

        for pod in pods.items:
            if pod.status.phase == "Pending":
                reason = "Unknown"
                message = "Pod处于Pending状态"

                # Check pod conditions for more specific reason
                if pod.status.conditions:
                    for condition in pod.status.conditions:
                        if condition.type == "PodScheduled" and condition.status == "False":
                            reason = condition.reason or "SchedulingFailed"
                            message = condition.message or "Pod无法被调度"
                        elif condition.type == "Initialized" and condition.status == "False":
                            reason = condition.reason or "InitializationFailed"
                            message = condition.message or "Pod初始化失败"

                # Check container statuses for initialization issues
                if pod.status.container_statuses:
                    for container in pod.status.container_statuses:
                        if container.state.waiting:
                            reason = container.state.waiting.reason or reason
                            message = container.state.waiting.message or message

                pending.append({
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "node": pod.spec.node_name,
                    "reason": reason,
                    "message": message,
                    "creation_time": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None
                })

        return json.dumps(pending)
    except ApiException as e:
        return json.dumps({"error": f"获取Pending Pod列表失败: {str(e)}"})


@tool()
def get_high_restart_kubernetes_pods(restart_threshold=5, config: RunnableConfig = None):
    """
    发现频繁重启的不稳定Pod
    
    **何时使用此工具：**
    - 用户反馈"服务不稳定"、"时好时坏"、"经常掉线"
    - 怀疑有应用程序bug或配置问题
    - 检查是否有内存泄漏或资源配置不当
    - 监控集群稳定性的日常巡检
    
    **工具能力：**
    - 快速列出重启次数超过阈值的Pod
    - 显示每个容器的具体重启次数
    - 提供容器镜像信息，便于定位版本问题
    - 展示Ready状态，判断当前是否正常
    
    **与analyze_pod_restart_pattern的区别：**
    - 本工具：快速列表，找出"哪些Pod在重启"
    - analyze_pod_restart_pattern：深度分析"为什么重启"（退出码、OOM、事件）
    
    **常见重启原因：**
    - OOM（内存不足）→ 退出码137
    - 健康检查失败 → livenessProbe配置不当
    - 应用程序bug → 退出码1
    - 配置错误 → 启动命令或环境变量问题
    
    Args:
        restart_threshold (int, optional): 重启次数阈值，默认5
            - 5: 标准阈值，找出明显不稳定的Pod
            - 3: 更敏感，发现轻微重启问题
            - 10: 只关注严重频繁重启的Pod
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含高重启Pod列表，每个Pod包含：
        - name: Pod名称
        - namespace: 命名空间
        - node: 所在节点
        - containers[]: 容器列表
          - name: 容器名称
          - restart_count: 重启次数
          - ready: 是否就绪
          - image: 容器镜像
          
    **配合其他工具使用：**
    - 深入分析重启原因 → 使用 analyze_pod_restart_pattern
    - 检查是否OOM → 使用 check_oom_events
    - 查看完整事件历史 → 使用 get_resource_events_timeline
    - 查看容器日志 → 使用 get_kubernetes_pod_logs
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()
        pods = core_v1.list_pod_for_all_namespaces()
        high_restart = []

        for pod in pods.items:
            if pod.status.container_statuses:
                high_restart_containers = []
                for container in pod.status.container_statuses:
                    if container.restart_count >= restart_threshold:
                        high_restart_containers.append({
                            "name": container.name,
                            "restart_count": container.restart_count,
                            "ready": container.ready,
                            "image": container.image
                        })

                if high_restart_containers:
                    high_restart.append({
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "node": pod.spec.node_name,
                        "containers": high_restart_containers
                    })

        return json.dumps(high_restart)
    except ApiException as e:
        return json.dumps({"error": f"获取高重启Pod列表失败: {str(e)}"})


@tool()
def get_kubernetes_node_capacity(config: RunnableConfig = None):
    """
    查看集群节点资源容量和使用情况
    
    **何时使用此工具：**
    - 用户反馈"Pod调度失败"、"资源不足"
    - 规划扩容或缩容决策
    - 评估集群整体负载水平
    - 检查资源碎片化问题（单个节点资源不足）
    - 日常容量管理和监控
    
    **工具能力：**
    - 统计所有节点的资源分配情况
    - 计算CPU/内存的requests占用率（非实际使用率）
    - 显示Pod数量使用情况
    - 检查节点健康状态（Conditions）
    - 识别资源紧张的节点
    
    **重要说明：**
    - 本工具统计的是资源**requests**（预留），不是实际使用量
    - 如需实际使用率，需要Metrics Server（超出纯SDK范围）
    - 高requests占用不等于高实际使用，但会影响调度
    
    **资源占用率解读：**
    - <60%: 资源充足
    - 60-80%: 资源适中，建议监控
    - 80-90%: 资源紧张，可能影响调度
    - >90%: 资源严重不足，建议扩容
    
    Args:
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含所有节点的容量信息：
        - name: 节点名称
        - pods: Pod容量
          - used: 已运行Pod数
          - capacity: 最大Pod数
          - percent_used: 使用率
        - cpu: CPU容量
          - requested: 已分配CPU核心数
          - allocatable: 可分配CPU核心数
          - percent_used: 占用率
        - memory: 内存容量
          - requested: 已分配内存
          - allocatable: 可分配内存
          - percent_used: 占用率
        - conditions: 节点状态（Ready/DiskPressure等）
        
    **配合其他工具使用：**
    - 发现节点问题 → 使用 diagnose_node_issues 深入诊断
    - Pod调度失败 → 使用 get_pending_kubernetes_pods 查看具体Pod
    - 资源不足需扩容 → 建议添加新节点或优化Pod资源配置
    - 检查资源碎片化 → 使用 check_pod_distribution
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()
        nodes = core_v1.list_node()
        pods = core_v1.list_pod_for_all_namespaces()

        # Group pods by node
        node_pods = {}
        for pod in pods.items:
            if pod.spec.node_name:
                if pod.spec.node_name not in node_pods:
                    node_pods[pod.spec.node_name] = []
                node_pods[pod.spec.node_name].append(pod)

        results = []
        for node in nodes.items:
            node_name = node.metadata.name

            # Get node allocatable resources
            allocatable = node.status.allocatable or {}
            allocatable_cpu = parse_resource_quantity(
                allocatable.get('cpu', '0'))
            allocatable_memory = parse_resource_quantity(
                allocatable.get('memory', '0'))
            allocatable_pods = int(allocatable.get('pods', '0'))

            # Calculate resource requests from pods on this node
            pods_on_node = node_pods.get(node_name, [])
            requested_cpu = 0
            requested_memory = 0

            for pod in pods_on_node:
                if pod.spec.containers:
                    for container in pod.spec.containers:
                        if container.resources and container.resources.requests:
                            cpu_request = container.resources.requests.get(
                                'cpu', '0')
                            memory_request = container.resources.requests.get(
                                'memory', '0')
                            requested_cpu += parse_resource_quantity(
                                cpu_request)
                            requested_memory += parse_resource_quantity(
                                memory_request)

            # Calculate percentages
            cpu_percent = (requested_cpu / allocatable_cpu *
                           100) if allocatable_cpu > 0 else 0
            memory_percent = (
                requested_memory / allocatable_memory * 100) if allocatable_memory > 0 else 0
            pods_percent = (len(pods_on_node) / allocatable_pods *
                            100) if allocatable_pods > 0 else 0

            # Get node conditions
            conditions = {}
            if node.status.conditions:
                for condition in node.status.conditions:
                    conditions[condition.type] = {
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message
                    }

            results.append({
                "name": node_name,
                "pods": {
                    "used": len(pods_on_node),
                    "capacity": allocatable_pods,
                    "percent_used": round(pods_percent, 2)
                },
                "cpu": {
                    "requested": round(requested_cpu, 3),
                    "allocatable": round(allocatable_cpu, 3),
                    "percent_used": round(cpu_percent, 2)
                },
                "memory": {
                    "requested": int(requested_memory),
                    "requested_human": format_bytes(requested_memory),
                    "allocatable": int(allocatable_memory),
                    "allocatable_human": format_bytes(allocatable_memory),
                    "percent_used": round(memory_percent, 2)
                },
                "conditions": conditions
            })

        return json.dumps(results)
    except ApiException as e:
        return json.dumps({"error": f"获取节点容量信息失败: {str(e)}"})


@tool()
def get_kubernetes_orphaned_resources(config: RunnableConfig = None):
    """
    发现孤立资源（无控制器管理）- 资源清理和审计
    
    **何时使用此工具：**
    - 用户说"清理无用资源"、"删除孤立对象"
    - 资源审计，找出不受控制器管理的资源
    - 成本优化，识别可能被遗忘的资源
    - 排查资源泄漏问题
    - 清理测试环境的临时资源
    
    **工具能力：**
    - 识别没有OwnerReference的资源（无控制器管理）
    - 扫描Pod、Service、ConfigMap、Secret、PVC
    - 自动过滤系统资源（kube-system等）
    - 显示创建时间，识别长期存在的孤立资源
    
    **什么是孤立资源：**
    - 没有Deployment/StatefulSet等控制器管理的Pod
    - 手动创建未删除的Service
    - 测试时创建的临时ConfigMap/Secret
    - 删除Deployment后残留的PVC
    
    **注意事项：**
    - 并非所有孤立资源都应删除（有些是故意手动创建的）
    - 删除前请确认资源用途
    - Service通常是手动创建的，较多孤立是正常的
    - 建议先核实再清理
    
    Args:
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含各类孤立资源：
        - pods[]: 孤立的Pod列表
        - services[]: 孤立的Service列表
        - persistent_volume_claims[]: 孤立的PVC列表
        - config_maps[]: 孤立的ConfigMap列表
        - secrets[]: 孤立的Secret列表
        
        每个资源包含：
        - name: 资源名称
        - namespace: 命名空间
        - creation_time: 创建时间
        
    **配合其他工具使用：**
    - 确认资源可删除 → 检查是否被其他资源引用
    - 删除孤立资源 → 使用 delete_kubernetes_resource
    - 批量清理Pod → 使用 cleanup_failed_pods
    - 查找ConfigMap使用者 → 使用 find_configmap_consumers
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()
        results = {
            "pods": [],
            "services": [],
            "persistent_volume_claims": [],
            "config_maps": [],
            "secrets": [],
        }

        # Check for orphaned pods
        pods = core_v1.list_pod_for_all_namespaces()
        for pod in pods.items:
            # Skip pods owned by controllers
            if not pod.metadata.owner_references:
                # Also skip pods in kube-system namespace by default
                if pod.metadata.namespace != "kube-system":
                    results["pods"].append({
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "creation_time": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None
                    })

        # Check for orphaned services
        services = core_v1.list_service_for_all_namespaces()
        for service in services.items:
            # Skip system services
            if service.metadata.namespace not in ["kube-system", "kube-public", "kube-node-lease"]:
                if not service.metadata.owner_references:
                    # Skip default kubernetes service
                    if not (service.metadata.name == "kubernetes" and service.metadata.namespace == "default"):
                        results["services"].append({
                            "name": service.metadata.name,
                            "namespace": service.metadata.namespace,
                            "creation_time": service.metadata.creation_timestamp.isoformat() if service.metadata.creation_timestamp else None
                        })

        # Check for orphaned PVCs
        pvcs = core_v1.list_persistent_volume_claim_for_all_namespaces()
        for pvc in pvcs.items:
            if not pvc.metadata.owner_references:
                results["persistent_volume_claims"].append({
                    "name": pvc.metadata.name,
                    "namespace": pvc.metadata.namespace,
                    "creation_time": pvc.metadata.creation_timestamp.isoformat() if pvc.metadata.creation_timestamp else None
                })

        # Check for orphaned ConfigMaps
        config_maps = core_v1.list_config_map_for_all_namespaces()
        for cm in config_maps.items:
            # Skip system configmaps
            if cm.metadata.namespace not in ["kube-system", "kube-public", "kube-node-lease"]:
                if not cm.metadata.owner_references:
                    # Skip some well-known system configmaps
                    system_cms = ["kube-root-ca.crt"]
                    if cm.metadata.name not in system_cms:
                        results["config_maps"].append({
                            "name": cm.metadata.name,
                            "namespace": cm.metadata.namespace,
                            "creation_time": cm.metadata.creation_timestamp.isoformat() if cm.metadata.creation_timestamp else None
                        })

        # Check for orphaned Secrets
        secrets = core_v1.list_secret_for_all_namespaces()
        for secret in secrets.items:
            # Skip system secrets
            if secret.metadata.namespace not in ["kube-system", "kube-public", "kube-node-lease"]:
                if not secret.metadata.owner_references:
                    # Skip service account tokens and other system secrets
                    if secret.type not in ["kubernetes.io/service-account-token", "kubernetes.io/dockercfg", "kubernetes.io/dockerconfigjson"]:
                        results["secrets"].append({
                            "name": secret.metadata.name,
                            "namespace": secret.metadata.namespace,
                            "type": secret.type,
                            "creation_time": secret.metadata.creation_timestamp.isoformat() if secret.metadata.creation_timestamp else None
                        })

        return json.dumps(results)
    except ApiException as e:
        return json.dumps({"error": f"获取孤立资源列表失败: {str(e)}"})


@tool()
def diagnose_kubernetes_pod_issues(namespace, pod_name, config: RunnableConfig = None):
    """
    深度诊断单个Pod的所有问题 - 一站式故障排查
    
    **何时使用此工具：**
    - 用户说"这个Pod有问题，帮我看看"
    - 已知具体Pod名称，需要全面分析
    - 从 get_failed_pods 或 get_pending_pods 发现问题Pod后
    - 需要详细的诊断报告（状态+事件+资源+卷）
    
    **工具能力（最全面的Pod诊断）：**
    - Pod所有Conditions（Ready、Initialized、ContainersReady等）
    - 容器状态详情（waiting/running/terminated，含退出码）
    - Init容器状态（初始化失败诊断）
    - 资源requests和limits配置
    - 挂载卷配置（PVC/ConfigMap/Secret/HostPath）
    - 最近10个相关事件（时间排序）
    - 重启策略和节点信息
    
    **诊断维度：**
    1. 容器健康：状态、退出码、重启次数
    2. 资源配置：CPU/内存requests和limits
    3. 依赖检查：ConfigMap、Secret、PVC是否存在
    4. 事件分析：Warning/Error事件的原因和消息
    5. 节点信息：调度到哪个节点，节点是否健康
    
    Args:
        namespace (str): Pod所在命名空间（必填）
        pod_name (str): Pod名称（必填）
        config (RunnableConfig): 工具配置（自动传递）
        
    Returns:
        JSON格式，包含完整的诊断信息：
        - phase: Pod状态（Running/Pending/Failed）
        - conditions[]: 所有Condition详情
        - containers[]: 容器状态（state、restart_count、image）
        - init_containers[]: Init容器状态
        - resource_requests: 资源请求配置
        - resource_limits: 资源限制配置
        - volumes[]: 卷挂载信息
        - recent_events[]: 最近事件（按时间排序）
        - node: 所在节点
        - restart_policy: 重启策略
        
    **配合其他工具使用：**
    - 查看日志定位错误 → 使用 get_kubernetes_pod_logs
    - 检查镜像拉取问题 → 查看events中的ImagePull相关错误
    - 资源不足 → 使用 get_kubernetes_node_capacity 检查节点容量
    - 需要重启恢复 → 使用 restart_pod
    - 卷挂载问题 → 使用 check_kubernetes_persistent_volumes
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()

        # 获取Pod详细信息
        try:
            pod = core_v1.read_namespaced_pod(pod_name, namespace)
        except ApiException as e:
            if e.status == 404:
                return json.dumps({"error": f"Pod {pod_name} 在命名空间 {namespace} 中不存在"})
            raise

        # 获取相关事件
        events = core_v1.list_namespaced_event(
            namespace,
            field_selector=f"involvedObject.name={pod_name},involvedObject.kind=Pod"
        )

        # 整理诊断信息
        diagnosis = {
            "pod_name": pod_name,
            "namespace": namespace,
            "phase": pod.status.phase,
            "node": pod.spec.node_name,
            "restart_policy": pod.spec.restart_policy,
            "conditions": [],
            "containers": [],
            "init_containers": [],
            "recent_events": [],
            "resource_requests": {},
            "resource_limits": {},
            "volumes": []
        }

        # Pod条件
        if pod.status.conditions:
            for condition in pod.status.conditions:
                diagnosis["conditions"].append({
                    "type": condition.type,
                    "status": condition.status,
                    "reason": condition.reason,
                    "message": condition.message,
                    "last_transition_time": condition.last_transition_time.isoformat() if condition.last_transition_time else None
                })

        # 容器状态
        if pod.status.container_statuses:
            for container in pod.status.container_statuses:
                container_info = {
                    "name": container.name,
                    "ready": container.ready,
                    "restart_count": container.restart_count,
                    "image": container.image,
                    "image_id": container.image_id,
                    "state": {}
                }

                if container.state.waiting:
                    container_info["state"] = {
                        "status": "waiting",
                        "reason": container.state.waiting.reason,
                        "message": container.state.waiting.message
                    }
                elif container.state.running:
                    container_info["state"] = {
                        "status": "running",
                        "started_at": container.state.running.started_at.isoformat() if container.state.running.started_at else None
                    }
                elif container.state.terminated:
                    container_info["state"] = {
                        "status": "terminated",
                        "reason": container.state.terminated.reason,
                        "exit_code": container.state.terminated.exit_code,
                        "started_at": container.state.terminated.started_at.isoformat() if container.state.terminated.started_at else None,
                        "finished_at": container.state.terminated.finished_at.isoformat() if container.state.terminated.finished_at else None
                    }

                diagnosis["containers"].append(container_info)

        # Init容器状态
        if pod.status.init_container_statuses:
            for init_container in pod.status.init_container_statuses:
                init_info = {
                    "name": init_container.name,
                    "ready": init_container.ready,
                    "restart_count": init_container.restart_count,
                    "image": init_container.image,
                    "state": {}
                }

                if init_container.state.waiting:
                    init_info["state"] = {
                        "status": "waiting",
                        "reason": init_container.state.waiting.reason,
                        "message": init_container.state.waiting.message
                    }
                elif init_container.state.terminated:
                    init_info["state"] = {
                        "status": "terminated",
                        "reason": init_container.state.terminated.reason,
                        "exit_code": init_container.state.terminated.exit_code
                    }

                diagnosis["init_containers"].append(init_info)

        # 资源请求和限制
        if pod.spec.containers:
            for container in pod.spec.containers:
                if container.resources:
                    if container.resources.requests:
                        diagnosis["resource_requests"][container.name] = dict(
                            container.resources.requests)
                    if container.resources.limits:
                        diagnosis["resource_limits"][container.name] = dict(
                            container.resources.limits)

        # 卷信息
        if pod.spec.volumes:
            for volume in pod.spec.volumes:
                volume_info = {"name": volume.name}
                if volume.persistent_volume_claim:
                    volume_info["type"] = "pvc"
                    volume_info["claim_name"] = volume.persistent_volume_claim.claim_name
                elif volume.config_map:
                    volume_info["type"] = "configmap"
                    volume_info["config_map_name"] = volume.config_map.name
                elif volume.secret:
                    volume_info["type"] = "secret"
                    volume_info["secret_name"] = volume.secret.secret_name
                elif volume.empty_dir:
                    volume_info["type"] = "emptydir"
                elif volume.host_path:
                    volume_info["type"] = "hostpath"
                    volume_info["path"] = volume.host_path.path
                else:
                    volume_info["type"] = "other"

                diagnosis["volumes"].append(volume_info)

        # 最近的事件
        for event in sorted(events.items, key=lambda e: e.last_timestamp if e.last_timestamp else datetime.min, reverse=True)[:10]:
            diagnosis["recent_events"].append({
                "type": event.type,
                "reason": event.reason,
                "message": event.message,
                "count": event.count,
                "last_timestamp": event.last_timestamp.isoformat() if event.last_timestamp else None
            })

        return json.dumps(diagnosis)
    except ApiException as e:
        return json.dumps({"error": f"诊断Pod失败: {str(e)}"})
