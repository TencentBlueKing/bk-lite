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
    List all pods in Failed or Error state across all namespaces.

    Identifies pods that are in a failed state, including those in CrashLoopBackOff,
    ImagePullBackOff, or other error states. Provides detailed container status
    information to aid in troubleshooting.

    Args:
        config (RunnableConfig): Configuration for the tool.

    Returns:
        str: JSON string containing an array of failed pod objects with fields:
            - name (str): Name of the pod
            - namespace (str): Namespace where the pod is running
            - phase (str): Current phase of the pod
            - container_statuses (list): Detailed status of each container
              including state, reason, exit codes, and restart counts
            - node (str): Name of the node running this pod
            - message (str): Status message from the pod, if any
            - reason (str): Reason for the current status, if any

    Raises:
        ApiException: If there is an error communicating with the Kubernetes API
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
    List all pods in Pending state and why they're pending

    Args:
        config (RunnableConfig): Configuration for the tool.

    Returns:
        str: JSON string containing an array of pending pod objects with fields:
            - name (str): Name of the pod
            - namespace (str): Namespace where the pod is running
            - node (str): Name of the node assigned to the pod, if any
            - reason (str): Reason why the pod is pending
            - message (str): Detailed message about the pending reason
            - creation_time (str): Timestamp when pod was created
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
    Find pods with high restart counts

    Args:
        restart_threshold (int, optional): The minimum number of restarts
            required to include a pod in the results. Defaults to 5.
        config (RunnableConfig): Configuration for the tool.

    Returns:
        str: JSON string containing an array of high-restart pod objects with fields:
            - name (str): Name of the pod
            - namespace (str): Namespace where the pod is running
            - node (str): Name of the node running this pod
            - containers (list): List of containers with high restart counts,
              including name, restart_count, ready status, and image
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
    Show available capacity and resource utilization on all nodes.

    Calculates the current resource usage across all nodes, including:
    - Pod count vs. maximum pods per node
    - CPU requests vs. allocatable CPU
    - Memory requests vs. allocatable memory

    Args:
        config (RunnableConfig): Configuration for the tool.

    Returns:
        str: JSON string containing an array of node capacity objects with fields:
            - name (str): Name of the node
            - pods (dict): Pod capacity information
              - used (int): Number of pods running on the node
              - capacity (int): Maximum number of pods the node can run
              - percent_used (float): Percentage of pod capacity in use
            - cpu (dict): CPU resource information
              - requested (float): CPU cores requested by pods
              - allocatable (float): CPU cores available on the node
              - percent_used (float): Percentage of CPU capacity in use
            - memory (dict): Memory resource information
              - requested (int): Memory requested by pods in bytes
              - requested_human (str): Human-readable memory requested
              - allocatable (int): Memory available on the node in bytes
              - allocatable_human (str): Human-readable allocatable memory
              - percent_used (float): Percentage of memory capacity in use
            - conditions (dict): Node condition statuses
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
    List resources that might be orphaned (no owner references)

    Args:
        config (RunnableConfig): Configuration for the tool.

    Returns:
        str: JSON string containing categories of potentially orphaned resources:
            - pods (list): Orphaned pod details
            - services (list): Orphaned service details
            - persistent_volume_claims (list): Orphaned PVC details
            - config_maps (list): Orphaned ConfigMap details
            - secrets (list): Orphaned Secret details
            Each resource contains name, namespace and creation time
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
    综合诊断指定Pod的问题，包括事件、状态、资源使用等

    Args:
        namespace (str): Pod所在的命名空间
        pod_name (str): Pod名称
        config (RunnableConfig): 工具配置
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
