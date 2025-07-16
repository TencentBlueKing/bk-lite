from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from kubernetes import client, config
import json
from datetime import datetime
import yaml


def prepare_context(cfg):
    if cfg['configurable']['kubeconfig_path']:
        config.load_kube_config(cfg['configurable']['kubeconfig_path'])
    else:
        config.load_incluster_config()


@tool()
def get_kubernetes_namespaces(config: RunnableConfig):
    """
    List all namespaces in the Kubernetes cluster.

    Returns:
        str: JSON string containing an array of namespace objects with fields:
            - name (str): Name of the namespace
            - status (str): Phase of the namespace (Active, Terminating)
            - creation_time (str): Timestamp when namespace was created

    Raises:
        ApiException: If there is an error communicating with the Kubernetes API
    """
    prepare_context(config)

    try:
        core_v1 = client.CoreV1Api()
        namespaces = core_v1.list_namespace()
        result = []
        for ns in namespaces.items:
            result.append(
                {
                    "name": ns.metadata.name,
                    "status": ns.status.phase,
                    "creation_time": ns.metadata.creation_timestamp.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if ns.metadata.creation_timestamp
                    else None,
                }
            )
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)}), 500


@tool()
def list_kubernetes_pods(namespace=None, config: RunnableConfig = None):
    """
    Lists all pods in the specified Kubernetes namespace or across all namespaces.

    Retrieves detailed information about pods including their status, containers,
    and hosting node.

    Args:
        namespace (str, optional): The namespace to filter pods by.
            If None, pods from all namespaces will be returned. Defaults to None.

    Returns:
        str: JSON string containing an array of pod objects with fields:
            - name (str): Name of the pod
            - namespace (str): Namespace where the pod is running
            - phase (str): Current phase of the pod (Running, Pending, etc.)
            - ip (str): Pod IP address
            - node (str): Name of the node running this pod
            - containers (list): List of containers in the pod with their status
            - creation_time (str): Timestamp when pod was created

    Raises:
        ApiException: If there is an error communicating with the Kubernetes API
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
            for container in pod.spec.containers:
                containers.append(
                    {
                        "name": container.name,
                        "image": container.image,
                        "ready": any(
                            s.container_id is not None and s.name == container.name
                            for s in pod.status.container_statuses
                        )
                        if pod.status.container_statuses
                        else False,
                    }
                )

            result.append(
                {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "phase": pod.status.phase,
                    "ip": pod.status.pod_ip,
                    "node": pod.spec.node_name,
                    "containers": containers,
                    "creation_time": pod.metadata.creation_timestamp.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if pod.metadata.creation_timestamp
                    else None,
                }
            )
        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": str(e)}), 500


@tool()
def list_kubernetes_nodes(config: RunnableConfig):
    """List all nodes and their status"""
    try:
        prepare_context(config)
        core_v1 = client.CoreV1Api()
        nodes = core_v1.list_node()
        result = []
        for node in nodes.items:
            conditions = {}
            for condition in node.status.conditions:
                conditions[condition.type] = condition.status

            addresses = {}
            for address in node.status.addresses:
                addresses[address.type] = address.address

            # Get capacity and allocatable resources
            capacity = {
                "cpu": node.status.capacity.get("cpu"),
                "memory": node.status.capacity.get("memory"),
                "pods": node.status.capacity.get("pods"),
            }

            allocatable = {
                "cpu": node.status.allocatable.get("cpu"),
                "memory": node.status.allocatable.get("memory"),
                "pods": node.status.allocatable.get("pods"),
            }

            result.append(
                {
                    "name": node.metadata.name,
                    "conditions": conditions,
                    "addresses": addresses,
                    "capacity": capacity,
                    "allocatable": allocatable,
                    "kubelet_version": node.status.node_info.kubelet_version
                    if node.status.node_info
                    else None,
                }
            )
        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": str(e)}), 500


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
            result.append(
                {
                    "name": deployment.metadata.name,
                    "namespace": deployment.metadata.namespace,
                    "replicas": deployment.spec.replicas,
                    "available_replicas": deployment.status.available_replicas,
                    "ready_replicas": deployment.status.ready_replicas,
                    "strategy": deployment.spec.strategy.type,
                    "creation_time": deployment.metadata.creation_timestamp.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if deployment.metadata.creation_timestamp
                    else None,
                }
            )
        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": str(e)}), 500


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
            for port in service.spec.ports:
                ports.append(
                    {
                        "name": port.name,
                        "port": port.port,
                        "target_port": port.target_port,
                        "protocol": port.protocol,
                        "node_port": port.node_port
                        if hasattr(port, "node_port")
                        else None,
                    }
                )

            result.append(
                {
                    "name": service.metadata.name,
                    "namespace": service.metadata.namespace,
                    "type": service.spec.type,
                    "cluster_ip": service.spec.cluster_ip,
                    "external_ip": service.spec.external_i_ps
                    if hasattr(service.spec, "external_i_ps")
                    else None,
                    "ports": ports,
                    "selector": service.spec.selector,
                    "creation_time": service.metadata.creation_timestamp.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if service.metadata.creation_timestamp
                    else None,
                }
            )
        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": str(e)}), 500


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
            result.append(
                {
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "object": f"{event.involved_object.kind}/{event.involved_object.name}",
                    "namespace": event.metadata.namespace,
                    "count": event.count,
                    "first_time": event.first_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    if event.first_timestamp
                    else None,
                    "last_time": event.last_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    if event.last_timestamp
                    else None,
                }
            )
        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": str(e)}), 500


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
            if pod.status.phase in ["Failed", "Error"] or any(
                    s.state
                    and s.state.waiting
                    and s.state.waiting.reason
                    in ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"]
                    for s in pod.status.container_statuses
                    if s.state and s.state.waiting
            ):
                container_statuses = []
                if pod.status.container_statuses:
                    for s in pod.status.container_statuses:
                        state = {}
                        if s.state.waiting:
                            state = {
                                "status": "waiting",
                                "reason": s.state.waiting.reason,
                                "message": s.state.waiting.message,
                            }
                        elif s.state.terminated:
                            state = {
                                "status": "terminated",
                                "reason": s.state.terminated.reason,
                                "exit_code": s.state.terminated.exit_code,
                                "message": s.state.terminated.message,
                            }
                        container_statuses.append(
                            {
                                "name": s.name,
                                "state": state,
                                "restart_count": s.restart_count,
                            }
                        )

                failed.append(
                    {
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "phase": pod.status.phase,
                        "container_statuses": container_statuses,
                        "node": pod.spec.node_name,
                        "message": pod.status.message if pod.status.message else None,
                        "reason": pod.status.reason if pod.status.reason else None,
                    }
                )

        return json.dumps(failed)
    except ApiException as e:
        return json.dumps({"error": str(e)}), 500


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
                # Check for events related to this pod
                events = core_v1.list_namespaced_event(
                    pod.metadata.namespace,
                    field_selector=f"involvedObject.name={pod.metadata.name},involvedObject.kind=Pod",
                )

                pending_reason = "Unknown"
                pending_message = None

                # Get the latest event that might explain why it's pending
                if events.items:
                    latest_event = max(
                        events.items,
                        key=lambda e: e.last_timestamp
                        if e.last_timestamp
                        else datetime.min,
                    )
                    pending_reason = latest_event.reason
                    pending_message = latest_event.message

                pending.append(
                    {
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "node": pod.spec.node_name,
                        "reason": pending_reason,
                        "message": pending_message,
                        "creation_time": pod.metadata.creation_timestamp.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if pod.metadata.creation_timestamp
                        else None,
                    }
                )

        return json.dumps(pending)
    except ApiException as e:
        return json.dumps({"error": str(e)}), 500


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
            high_restart_containers = []

            if pod.status.container_statuses:
                for status in pod.status.container_statuses:
                    if status.restart_count > restart_threshold:
                        high_restart_containers.append(
                            {
                                "name": status.name,
                                "restart_count": status.restart_count,
                                "ready": status.ready,
                                "image": status.image,
                            }
                        )

            if high_restart_containers:
                high_restart.append(
                    {
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "node": pod.spec.node_name,
                        "containers": high_restart_containers,
                    }
                )

        return json.dumps(high_restart)
    except ApiException as e:
        return json.dumps({"error": str(e)}), 500


# Helper function to format bytes into human-readable format
def format_bytes(size):
    """
    Format bytes to human readable string.

    Converts a byte value to a human-readable string with appropriate
    units (B, KiB, MiB, GiB, TiB).

    Args:
        size (int): Size in bytes

    Returns:
        str: Human-readable string representation of the size
            (e.g., "2.5 MiB")
    """
    power = 2 ** 10
    n = 0
    power_labels = {0: "B", 1: "KiB", 2: "MiB", 3: "GiB", 4: "TiB"}
    while size > power:
        size /= power
        n += 1
    return f"{round(size, 2)} {power_labels[n]}"


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
            # Calculate pod count
            pod_count = len(node_pods.get(node.metadata.name, []))
            max_pods = int(node.status.allocatable.get("pods", 0))

            # Calculate CPU and memory utilization (rough estimate)
            node_pods_list = node_pods.get(node.metadata.name, [])
            cpu_request = 0
            memory_request = 0

            for pod in node_pods_list:
                for container in pod.spec.containers:
                    if container.resources and container.resources.requests:
                        if container.resources.requests.get("cpu"):
                            cpu_str = container.resources.requests.get("cpu")
                            if cpu_str.endswith("m"):
                                cpu_request += int(cpu_str[:-1]) / 1000
                            else:
                                cpu_request += float(cpu_str)

                        if container.resources.requests.get("memory"):
                            mem_str = container.resources.requests.get("memory")
                            # Convert to bytes (rough approximation)
                            if mem_str.endswith("Ki"):
                                memory_request += int(mem_str[:-2]) * 1024
                            elif mem_str.endswith("Mi"):
                                memory_request += int(mem_str[:-2]) * 1024 * 1024
                            elif mem_str.endswith("Gi"):
                                memory_request += int(mem_str[:-2]) * 1024 * 1024 * 1024
                            else:
                                memory_request += int(mem_str)

            # Convert allocatable CPU to cores
            cpu_allocatable = node.status.allocatable.get("cpu", "0")
            if cpu_allocatable.endswith("m"):
                cpu_allocatable = int(cpu_allocatable[:-1]) / 1000
            else:
                cpu_allocatable = float(cpu_allocatable)

            # Convert allocatable memory to bytes
            mem_allocatable = node.status.allocatable.get("memory", "0")
            mem_bytes = 0
            if mem_allocatable.endswith("Ki"):
                mem_bytes = int(mem_allocatable[:-2]) * 1024
            elif mem_allocatable.endswith("Mi"):
                mem_bytes = int(mem_allocatable[:-2]) * 1024 * 1024
            elif mem_allocatable.endswith("Gi"):
                mem_bytes = int(mem_allocatable[:-2]) * 1024 * 1024 * 1024
            else:
                mem_bytes = int(mem_allocatable)

            results.append(
                {
                    "name": node.metadata.name,
                    "pods": {
                        "used": pod_count,
                        "capacity": max_pods,
                        "percent_used": round((pod_count / max_pods) * 100, 2)
                        if max_pods > 0
                        else 0,
                    },
                    "cpu": {
                        "requested": round(cpu_request, 2),
                        "allocatable": round(cpu_allocatable, 2),
                        "percent_used": round((cpu_request / cpu_allocatable) * 100, 2)
                        if cpu_allocatable > 0
                        else 0,
                    },
                    "memory": {
                        "requested": memory_request,
                        "requested_human": format_bytes(memory_request),
                        "allocatable": mem_bytes,
                        "allocatable_human": format_bytes(mem_bytes),
                        "percent_used": round((memory_request / mem_bytes) * 100, 2)
                        if mem_bytes > 0
                        else 0,
                    },
                    "conditions": {
                        cond.type: cond.status for cond in node.status.conditions
                    },
                }
            )

        return json.dumps(results)
    except ApiException as e:
        return json.dumps({"error": str(e)}), 500


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
            if (
                    not pod.metadata.owner_references
                    and not pod.metadata.name.startswith("kube-")
                    and pod.metadata.namespace != "kube-system"
            ):
                results["pods"].append(
                    {
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "creation_time": pod.metadata.creation_timestamp.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if pod.metadata.creation_timestamp
                        else None,
                    }
                )

        # Check for orphaned services
        services = core_v1.list_service_for_all_namespaces()
        for service in services.items:
            if (
                    not service.metadata.owner_references
                    and not service.metadata.name.startswith("kube-")
                    and service.metadata.namespace != "kube-system"
                    and service.metadata.name != "kubernetes"
            ):
                results["services"].append(
                    {
                        "name": service.metadata.name,
                        "namespace": service.metadata.namespace,
                        "creation_time": service.metadata.creation_timestamp.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if service.metadata.creation_timestamp
                        else None,
                    }
                )

        # Check for orphaned PVCs
        pvcs = core_v1.list_persistent_volume_claim_for_all_namespaces()
        for pvc in pvcs.items:
            if not pvc.metadata.owner_references:
                results["persistent_volume_claims"].append(
                    {
                        "name": pvc.metadata.name,
                        "namespace": pvc.metadata.namespace,
                        "creation_time": pvc.metadata.creation_timestamp.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if pvc.metadata.creation_timestamp
                        else None,
                    }
                )

        # Check for orphaned ConfigMaps
        config_maps = core_v1.list_config_map_for_all_namespaces()
        for cm in config_maps.items:
            if (
                    not cm.metadata.owner_references
                    and not cm.metadata.name.startswith("kube-")
                    and cm.metadata.namespace != "kube-system"
            ):
                results["config_maps"].append(
                    {
                        "name": cm.metadata.name,
                        "namespace": cm.metadata.namespace,
                        "creation_time": cm.metadata.creation_timestamp.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if cm.metadata.creation_timestamp
                        else None,
                    }
                )

        # Check for orphaned Secrets
        secrets = core_v1.list_secret_for_all_namespaces()
        for secret in secrets.items:
            if (
                    not secret.metadata.owner_references
                    and not secret.metadata.name.startswith("kube-")
                    and secret.metadata.namespace != "kube-system"
                    and not secret.type.startswith("kubernetes.io/")
            ):
                results["secrets"].append(
                    {
                        "name": secret.metadata.name,
                        "namespace": secret.metadata.namespace,
                        "type": secret.type,
                        "creation_time": secret.metadata.creation_timestamp.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if secret.metadata.creation_timestamp
                        else None,
                    }
                )

        return json.dumps(results)
    except ApiException as e:
        return json.dumps({"error": str(e)}), 500


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
            resource_data = core_v1.read_namespaced_pod(resource_name, namespace)
        elif resource_type == "deployment":
            resource_data = apps_v1.read_namespaced_deployment(resource_name, namespace)
        elif resource_type == "service":
            resource_data = core_v1.read_namespaced_service(resource_name, namespace)
        elif resource_type == "configmap":
            resource_data = core_v1.read_namespaced_config_map(resource_name, namespace)
        elif resource_type == "secret":
            resource_data = core_v1.read_namespaced_secret(resource_name, namespace)
        elif resource_type == "job":
            resource_data = batch_v1.read_namespaced_job(resource_name, namespace)
        else:
            return json.dumps(
                {"error": f"Unsupported resource type: {resource_type}"}
            ), 400

        # Convert to dict and then to YAML
        resource_dict = client.ApiClient().sanitize_for_serialization(resource_data)
        yaml_str = yaml.dump(resource_dict, default_flow_style=False)

        return yaml_str
    except ApiException as e:
        return json.dumps({"error": str(e)}), 500


@tool()
def get_kubernetes_pod_logs(namespace, pod_name, container=None, lines=100, tail=True, config: RunnableConfig = None):
    """
    获取指定 Pod 中容器的日志内容。

    检索特定 Pod 内容器的日志，便于大模型进行故障诊断和异常分析。可以指定容器名称和
    要返回的日志行数，支持获取日志的开头或结尾部分。

    Args:
        namespace (str): Pod 所在的命名空间。
        pod_name (str): Pod 的名称。
        container (str, optional): 容器的名称。如果 Pod 中有多个容器且未指定容器名称，
            将返回 Pod 中第一个容器的日志。默认为 None。
        lines (int, optional): 要返回的日志行数。默认为 100。
        tail (bool, optional): 如果为 True，则返回日志的最后 `lines` 行；
            如果为 False，则返回日志的前 `lines` 行。默认为 True。
        config (RunnableConfig): 工具的配置信息。

    Returns:
        str: Pod 容器的日志内容，或者包含错误信息的 JSON 字符串。

    Raises:
        ApiException: 与 Kubernetes API 通信时出错
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()

        # 先检查 Pod 是否存在，并获取容器信息
        try:
            pod = core_v1.read_namespaced_pod(pod_name, namespace)
        except ApiException as e:
            if e.status == 404:
                return json.dumps({"error": f"Pod '{pod_name}' not found in namespace '{namespace}'"}), 404
            raise

        # 如果未指定容器名称且 Pod 有多个容器，获取容器列表
        if not container and pod.spec.containers and len(pod.spec.containers) > 1:
            containers = [c.name for c in pod.spec.containers]
            container_info = {"containers": containers}
            return json.dumps({
                "warning": f"Pod '{pod_name}' contains multiple containers. Please specify one of the following containers:",
                "containers": containers
            })

        # 如果未指定容器且只有一个容器，使用该容器
        if not container and pod.spec.containers and len(pod.spec.containers) == 1:
            container = pod.spec.containers[0].name

        # 获取日志
        logs = core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container=container,
            tail_lines=lines if tail else None,
            limit_bytes=None if lines else 1024 * 1024  # 如果获取全部日志，限制最大 1MB
        )

        # 如果获取日志的开头部分，需要手动截取
        if not tail and logs:
            logs_lines = logs.splitlines()
            if len(logs_lines) > lines:
                logs = "\n".join(logs_lines[:lines])

        # 返回日志内容或空日志提示
        if not logs:
            return "No logs available for the specified container."
        
        return logs

    except ApiException as e:
        error_message = str(e)
        if "ContainerCreating" in error_message:
            return json.dumps({"error": "Container is still being created. Logs are not available yet."}), 400
        elif "ContainerNotFound" in error_message:
            return json.dumps({"error": f"Container '{container}' not found in pod '{pod_name}'"}), 404
        else:
            return json.dumps({"error": error_message}), 500
    except Exception as e:
        return json.dumps({"error": str(e)}), 500
