"""Kubernetes基础资源查询工具"""
import json
import yaml
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from kubernetes import client
from neco.llm.tools.kubernetes.utils import prepare_context


@tool()
def get_kubernetes_namespaces(config: RunnableConfig):
    """
    列出集群中的所有命名空间
    
    **何时使用此工具：**
    - 用户问"有哪些命名空间"、"项目空间列表"
    - 需要了解集群的租户/项目划分
    - 作为其他查询的前置步骤（先选择namespace）
    - 检查命名空间是否存在或状态异常
    
    **工具能力：**
    - 列出所有命名空间及其状态
    - 显示标签和注解（用于分类和管理）
    - 识别Terminating状态的命名空间（删除中）
    - 提供创建时间
    
    Args:
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含命名空间列表：
        - name: 命名空间名称
        - status: 状态（Active/Terminating）
        - creation_time: 创建时间
        - labels: 标签
        - annotations: 注解
        
    **配合其他工具使用：**
    - 获取namespace后 → 使用 list_kubernetes_pods 查看该空间的Pod
    - 检查资源配额 → 使用 check_kubernetes_resource_quotas
    """
    prepare_context(config)

    try:
        core_v1 = client.CoreV1Api()
        namespaces = core_v1.list_namespace()
        result = []
        for ns in namespaces.items:
            result.append({
                "name": ns.metadata.name,
                "status": ns.status.phase,
                "creation_time": ns.metadata.creation_timestamp.isoformat() if ns.metadata.creation_timestamp else None,
                "labels": ns.metadata.labels if ns.metadata.labels else {},
                "annotations": ns.metadata.annotations if ns.metadata.annotations else {}
            })
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"获取命名空间列表失败: {str(e)}"})


@tool()
def list_kubernetes_pods(namespace=None, config: RunnableConfig = None):
    """
    查看Pod列表和基本状态
    
    **何时使用此工具：**
    - 用户问"有哪些Pod"、"查看运行的应用"
    - 获取特定命名空间的所有Pod概览
    - 查看Pod分布在哪些节点
    - 作为问题诊断的起点（先列表再深入）
    
    **工具能力：**
    - 列出指定命名空间或所有命名空间的Pod
    - 显示Pod状态、IP、所在节点
    - 展示容器列表和就绪状态
    - 提供标签和重启策略信息
    
    **与其他工具的区别：**
    - 本工具：基础列表，显示概览信息
    - get_failed_pods：只看失败的Pod
    - diagnose_pod_issues：深度诊断单个Pod
    
    Args:
        namespace (str, optional): 命名空间，None=所有命名空间
            - None: 查看整个集群的Pod
            - "default": 只看default命名空间
            - "prod": 只看生产环境
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含Pod列表：
        - name: Pod名称
        - namespace: 命名空间
        - phase: 状态（Running/Pending/Failed/Succeeded/Unknown）
        - ip: Pod IP地址
        - node: 所在节点
        - containers[]: 容器列表
          - name: 容器名
          - ready: 是否就绪
          - restart_count: 重启次数
          - image: 镜像
        - creation_time: 创建时间
        - labels: 标签
        
    **配合其他工具使用：**
    - 发现异常Pod → 使用 diagnose_kubernetes_pod_issues 诊断
    - 查看Pod日志 → 使用 get_kubernetes_pod_logs
    - 检查资源使用 → 使用 get_kubernetes_node_capacity
    """
    prepare_context(config)
    core_v1 = client.CoreV1Api()
    try:
        if namespace:
            pods = core_v1.list_namespaced_pod(namespace)
        else:
            pods = core_v1.list_pod_for_all_namespaces()

        result = []
        for pod in pods.items:
            containers = []
            if pod.status.container_statuses:
                for container in pod.status.container_statuses:
                    containers.append({
                        "name": container.name,
                        "ready": container.ready,
                        "restart_count": container.restart_count,
                        "image": container.image,
                        "state": str(container.state)
                    })

            result.append({
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "ip": pod.status.pod_ip,
                "node": pod.spec.node_name,
                "containers": containers,
                "creation_time": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
                "labels": pod.metadata.labels if pod.metadata.labels else {},
                "restart_policy": pod.spec.restart_policy
            })
        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"获取Pod列表失败: {str(e)}"})


@tool()
def list_kubernetes_nodes(config: RunnableConfig):
    """List all nodes and their status"""
    try:
        prepare_context(config)
        core_v1 = client.CoreV1Api()
        nodes = core_v1.list_node()
        result = []
        for node in nodes.items:
            conditions = []
            if node.status.conditions:
                for condition in node.status.conditions:
                    conditions.append({
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message
                    })

            allocatable = {}
            if node.status.allocatable:
                allocatable = {
                    "cpu": node.status.allocatable.get('cpu', ''),
                    "memory": node.status.allocatable.get('memory', ''),
                    "pods": node.status.allocatable.get('pods', '')
                }

            result.append({
                "name": node.metadata.name,
                "status": "Ready" if any(c.type == "Ready" and c.status == "True" for c in node.status.conditions) else "NotReady",
                "roles": list(node.metadata.labels.keys()) if node.metadata.labels else [],
                "age": node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else None,
                "version": node.status.node_info.kubelet_version if node.status.node_info else "",
                "conditions": conditions,
                "allocatable": allocatable,
                "addresses": [{"type": addr.type, "address": addr.address} for addr in (node.status.addresses or [])]
            })
        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"获取节点列表失败: {str(e)}"})


@tool()
def list_kubernetes_deployments(namespace=None, config: RunnableConfig = None):
    """
    List deployments with optional namespace filter

    Args:
        namespaces (list, optional): A list of namespace names to filter pods by.
            If None, pods from all namespaces will be returned. Defaults to None.
    """
    prepare_context(config)
    apps_v1 = client.AppsV1Api()
    try:
        if namespace:
            deployments = apps_v1.list_namespaced_deployment(namespace)
        else:
            deployments = apps_v1.list_deployment_for_all_namespaces()

        result = []
        for deployment in deployments.items:
            result.append({
                "name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "replicas": deployment.spec.replicas,
                "ready_replicas": deployment.status.ready_replicas or 0,
                "available_replicas": deployment.status.available_replicas or 0,
                "updated_replicas": deployment.status.updated_replicas or 0,
                "creation_time": deployment.metadata.creation_timestamp.isoformat() if deployment.metadata.creation_timestamp else None,
                "labels": deployment.metadata.labels if deployment.metadata.labels else {},
                "selector": deployment.spec.selector.match_labels if deployment.spec.selector else {}
            })
        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"获取Deployment列表失败: {str(e)}"})


@tool()
def list_kubernetes_services(namespace=None, config: RunnableConfig = None):
    """
    List services with optional namespace filter

    Args:
        namespace (str, optional): The namespace to filter services by.
            If None, services from all namespaces will be returned. Defaults to None.
        config (RunnableConfig): Configuration for the tool.

    Returns:
        str: JSON string containing an array of service objects with fields:
            - name (str): Name of the service
            - namespace (str): Namespace where the service is running
            - type (str): Type of the service (ClusterIP, NodePort, LoadBalancer)
            - cluster_ip (str): The cluster IP address assigned to the service
            - external_ip (str): External IP address, if available
            - ports (list): List of ports exposed by the service
            - selector (dict): Label selector used by the service
            - creation_time (str): Timestamp when service was created
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()
        if namespace:
            services = core_v1.list_namespaced_service(namespace)
        else:
            services = core_v1.list_service_for_all_namespaces()

        result = []
        for service in services.items:
            ports = []
            if service.spec.ports:
                for port in service.spec.ports:
                    ports.append({
                        "name": port.name,
                        "port": port.port,
                        "target_port": str(port.target_port) if port.target_port else None,
                        "protocol": port.protocol,
                        "node_port": port.node_port if hasattr(port, 'node_port') else None
                    })

            external_ips = []
            if service.status.load_balancer and service.status.load_balancer.ingress:
                for ingress in service.status.load_balancer.ingress:
                    if ingress.ip:
                        external_ips.append(ingress.ip)
                    elif ingress.hostname:
                        external_ips.append(ingress.hostname)

            result.append({
                "name": service.metadata.name,
                "namespace": service.metadata.namespace,
                "type": service.spec.type,
                "cluster_ip": service.spec.cluster_ip,
                "external_ips": external_ips,
                "ports": ports,
                "selector": service.spec.selector if service.spec.selector else {},
                "creation_time": service.metadata.creation_timestamp.isoformat() if service.metadata.creation_timestamp else None
            })
        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"获取Service列表失败: {str(e)}"})


@tool()
def list_kubernetes_events(namespace=None, config: RunnableConfig = None):
    """
    List events with optional namespace filter

    Args:
        namespace (str, optional): The namespace to filter events by.
            If None, events from all namespaces will be returned. Defaults to None.
        config (RunnableConfig): Configuration for the tool.

    Returns:
        str: JSON string containing an array of event objects with fields:
            - type (str): Type of event (Normal, Warning)
            - reason (str): Short reason for the event
            - message (str): Detailed message about the event
            - object (str): Object involved in the event
            - namespace (str): Namespace where the event occurred
            - count (int): Number of times this event has occurred
            - first_time (str): Timestamp when event first occurred
            - last_time (str): Timestamp when event last occurred
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()
        if namespace:
            events = core_v1.list_namespaced_event(namespace)
        else:
            events = core_v1.list_event_for_all_namespaces()

        result = []
        for event in events.items:
            result.append({
                "type": event.type,
                "reason": event.reason,
                "message": event.message,
                "object": f"{event.involved_object.kind}/{event.involved_object.name}",
                "namespace": event.namespace,
                "count": event.count,
                "first_time": event.first_timestamp.isoformat() if event.first_timestamp else None,
                "last_time": event.last_timestamp.isoformat() if event.last_timestamp else None
            })
        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"获取事件列表失败: {str(e)}"})


@tool()
def get_kubernetes_resource_yaml(namespace, resource_type, resource_name, config: RunnableConfig = None):
    """
    Retrieves the YAML configuration for a specified Kubernetes resource.

    Fetches the complete configuration of a resource, which can be useful for
    debugging, documentation, or backup purposes.

    Args:
        namespace (str): The Kubernetes namespace containing the resource.
        resource_type (str): The type of resource to retrieve.
            Supported types: 'pod', 'deployment', 'service', 'configmap',
            'secret', 'job'
        resource_name (str): The name of the specific resource to retrieve.
        config (RunnableConfig): Configuration for the tool.

    Returns:
        str: YAML string representation of the resource configuration.

    Raises:
        ApiException: If there is an error communicating with the Kubernetes API
        ValueError: If an unsupported resource type is specified
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()
        batch_v1 = client.BatchV1Api()

        resource_data = None

        if resource_type == "pod":
            resource_data = core_v1.read_namespaced_pod(
                resource_name, namespace)
        elif resource_type == "deployment":
            resource_data = apps_v1.read_namespaced_deployment(
                resource_name, namespace)
        elif resource_type == "service":
            resource_data = core_v1.read_namespaced_service(
                resource_name, namespace)
        elif resource_type == "configmap":
            resource_data = core_v1.read_namespaced_config_map(
                resource_name, namespace)
        elif resource_type == "secret":
            resource_data = core_v1.read_namespaced_secret(
                resource_name, namespace)
        elif resource_type == "job":
            resource_data = batch_v1.read_namespaced_job(
                resource_name, namespace)
        else:
            return f"不支持的资源类型: {resource_type}。支持的类型: pod, deployment, service, configmap, secret, job"

        # Convert to dict and then to YAML
        resource_dict = client.ApiClient().sanitize_for_serialization(resource_data)
        yaml_str = yaml.dump(resource_dict, default_flow_style=False)

        return yaml_str
    except ApiException as e:
        return f"获取资源YAML失败: {str(e)}"


@tool()
def get_kubernetes_pod_logs(namespace, pod_name, container=None, lines=100, tail=True, config: RunnableConfig = None):
    """
    获取Pod容器日志 - 定位应用程序错误
    
    **何时使用此工具：**
    - 用户说"查看日志"、"看看报什么错"
    - Pod启动失败需要查看启动日志
    - 应用程序行为异常需要查看运行日志
    - 从 diagnose_pod_issues 发现问题后查看详细错误
    - 分析应用崩溃、异常退出的具体原因
    
    **工具能力：**
    - 获取容器的标准输出日志（stdout/stderr）
    - 支持多容器Pod（可指定容器名）
    - 可获取最近N行或开头N行
    - 自动处理单容器Pod（无需指定容器名）
    
    **日志分析场景：**
    - CrashLoopBackOff → 查看最后100行，找panic/error
    - ImagePullBackOff → 日志为空，检查镜像地址
    - OOMKilled → 查看崩溃前日志，分析内存占用
    - 应用错误 → 搜索Exception、Error、Failed关键词
    
    **重要提示：**
    - 本工具只能获取当前运行容器的日志
    - 如果容器已重启，无法获取上一次的日志（需要--previous参数，暂不支持）
    - 日志默认最多1MB，超大日志会被截断
    
    Args:
        namespace (str): Pod所在命名空间（必填）
        pod_name (str): Pod名称（必填）
        container (str, optional): 容器名称，多容器Pod必须指定
            - None: 自动选择第一个容器（仅适用于单容器Pod）
            - "app": 指定名为app的容器
        lines (int, optional): 日志行数，默认100
            - 100: 适合快速查看最近日志
            - 500: 查看更多上下文
            - 50: 只看最关键的错误
        tail (bool, optional): True=最后N行，False=开头N行，默认True
            - True: 查看最新日志（推荐）
            - False: 查看启动初期日志
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        日志文本内容，或错误信息：
        - 成功: 容器的实际日志输出
        - 失败: 错误原因（Pod不存在、容器不存在、容器创建中等）
        
    **配合其他工具使用：**
    - 发现Pod问题 → 使用 diagnose_kubernetes_pod_issues 确定需要查看哪个Pod
    - 日志显示OOM → 使用 check_oom_events 分析内存配置
    - 日志显示网络错误 → 使用 trace_service_chain 检查服务链路
    - 需要重启恢复 → 使用 restart_pod
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()

        # 先检查 Pod 是否存在，并获取容器信息
        try:
            pod = core_v1.read_namespaced_pod(pod_name, namespace)
        except ApiException as e:
            if e.status == 404:
                return f"Pod {pod_name} 在命名空间 {namespace} 中不存在"
            raise

        # 如果未指定容器名称且 Pod 有多个容器，获取容器列表
        if not container and pod.spec.containers and len(pod.spec.containers) > 1:
            container_names = [c.name for c in pod.spec.containers]
            return f"Pod {pod_name} 包含多个容器: {container_names}。请指定容器名称。"

        # 如果未指定容器且只有一个容器，使用该容器
        if not container and pod.spec.containers and len(pod.spec.containers) == 1:
            container = pod.spec.containers[0].name

        # 获取日志
        logs = core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container=container,
            tail_lines=lines if tail else None,
            limit_bytes=None if lines else 1024 * 1024  # 1MB limit if no line limit
        )

        # 如果获取日志的开头部分，需要手动截取
        if not tail and logs:
            log_lines = logs.split('\n')
            logs = '\n'.join(log_lines[:lines])

        # 返回日志内容或空日志提示
        if not logs:
            return f"Pod {pod_name} 容器 {container} 没有日志输出"

        return logs

    except ApiException as e:
        error_message = str(e)
        if "ContainerCreating" in error_message:
            return f"容器 {container} 正在创建中，日志暂不可用"
        elif "ContainerNotFound" in error_message:
            return f"在 Pod {pod_name} 中找不到容器 {container}"
        else:
            return f"获取Pod日志失败: {error_message}"
    except Exception as e:
        return f"获取Pod日志时发生未知错误: {str(e)}"
