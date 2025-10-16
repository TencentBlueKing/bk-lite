"""Kubernetes高级查询工具 - 类似kubectl get的功能"""
import json
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from kubernetes import client
from neco.llm.tools.kubernetes.utils import prepare_context


@tool()
def kubectl_get_resources(resource_type, namespace=None, label_selector=None, field_selector=None, output_format="json", config: RunnableConfig = None):
    """
    高级资源查询工具，类似于 kubectl get

    支持多种资源类型的查询，可以使用标签选择器和字段选择器进行过滤

    Args:
        resource_type (str): 资源类型 (pods, deployments, services, nodes等)
        namespace (str, optional): 命名空间，对于集群级资源可为None
        label_selector (str, optional): 标签选择器，如 "app=nginx,version=v1"
        field_selector (str, optional): 字段选择器，如 "status.phase=Running"
        output_format (str): 输出格式 (json, table, yaml)
        config (RunnableConfig): 工具配置

    Returns:
        str: 查询结果
    """
    return _query_resources_internal(resource_type, namespace, label_selector, field_selector, output_format, config)


def _query_resources_internal(resource_type, namespace=None, label_selector=None, field_selector=None, output_format="json", config=None):
    """内部资源查询函数，供多个工具复用"""
    try:
        prepare_context(config)

        resource_type = resource_type.lower()

        # 处理资源类型的复数形式和别名
        resource_aliases = {
            "po": "pods",
            "pod": "pods",
            "svc": "services",
            "service": "services",
            "deploy": "deployments",
            "deployment": "deployments",
            "rs": "replicasets",
            "replicaset": "replicasets",
            "ds": "daemonsets",
            "daemonset": "daemonsets",
            "sts": "statefulsets",
            "statefulset": "statefulsets",
            "cm": "configmaps",
            "configmap": "configmaps",
            "ns": "namespaces",
            "namespace": "namespaces",
            "no": "nodes",
            "node": "nodes",
            "pv": "persistentvolumes",
            "pvc": "persistentvolumeclaims",
            "ing": "ingresses",
            "ingress": "ingresses",
            "ep": "endpoints",
            "endpoint": "endpoints",
            "events": "events",
            "event": "events"
        }

        resource_type = resource_aliases.get(resource_type, resource_type)

        # 根据资源类型调用相应的API
        if resource_type == "pods":
            return _get_pods(namespace, label_selector, field_selector, output_format)
        elif resource_type == "deployments":
            return _get_deployments(namespace, label_selector, output_format)
        elif resource_type == "services":
            return _get_services(namespace, label_selector, output_format)
        elif resource_type == "nodes":
            return _get_nodes(label_selector, output_format)
        elif resource_type == "namespaces":
            return _get_namespaces(label_selector, output_format)
        elif resource_type == "configmaps":
            return _get_configmaps(namespace, label_selector, output_format)
        elif resource_type == "secrets":
            return _get_secrets(namespace, label_selector, output_format)
        elif resource_type == "persistentvolumes":
            return _get_persistent_volumes(output_format)
        elif resource_type == "persistentvolumeclaims":
            return _get_persistent_volume_claims(namespace, label_selector, output_format)
        elif resource_type == "events":
            return _get_events(namespace, label_selector, output_format)
        elif resource_type == "replicasets":
            return _get_replicasets(namespace, label_selector, output_format)
        elif resource_type == "daemonsets":
            return _get_daemonsets(namespace, label_selector, output_format)
        elif resource_type == "statefulsets":
            return _get_statefulsets(namespace, label_selector, output_format)
        else:
            return json.dumps({
                "error": f"暂不支持的资源类型: {resource_type}",
                "supported_types": list(set(resource_aliases.values())),
                "aliases": resource_aliases
            })

    except Exception as e:
        return json.dumps({
            "error": f"查询资源失败: {str(e)}",
            "resource_type": resource_type,
            "namespace": namespace
        })


def _get_pods(namespace, label_selector, field_selector, output_format):
    """获取Pod列表"""
    core_v1 = client.CoreV1Api()

    if namespace:
        pods = core_v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector,
            field_selector=field_selector
        )
    else:
        pods = core_v1.list_pod_for_all_namespaces(
            label_selector=label_selector,
            field_selector=field_selector
        )

    if output_format == "table":
        return _format_pods_table(pods.items)
    else:
        pod_list = []
        for pod in pods.items:
            pod_info = {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "ready": _get_pod_ready_status(pod),
                "status": pod.status.phase,
                "restarts": _get_pod_restart_count(pod),
                "age": _calculate_age(pod.metadata.creation_timestamp),
                "ip": pod.status.pod_ip,
                "node": pod.spec.node_name
            }
            pod_list.append(pod_info)

        return json.dumps({"items": pod_list, "total": len(pod_list)})


def _get_deployments(namespace, label_selector, output_format):
    """获取Deployment列表"""
    apps_v1 = client.AppsV1Api()

    if namespace:
        deployments = apps_v1.list_namespaced_deployment(
            namespace=namespace,
            label_selector=label_selector
        )
    else:
        deployments = apps_v1.list_deployment_for_all_namespaces(
            label_selector=label_selector
        )

    if output_format == "table":
        return _format_deployments_table(deployments.items)
    else:
        deployment_list = []
        for deployment in deployments.items:
            deployment_info = {
                "name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "ready": f"{deployment.status.ready_replicas or 0}/{deployment.spec.replicas or 0}",
                "up_to_date": deployment.status.updated_replicas or 0,
                "available": deployment.status.available_replicas or 0,
                "age": _calculate_age(deployment.metadata.creation_timestamp)
            }
            deployment_list.append(deployment_info)

        return json.dumps({"items": deployment_list, "total": len(deployment_list)})


def _get_services(namespace, label_selector, output_format):
    """获取Service列表"""
    core_v1 = client.CoreV1Api()

    if namespace:
        services = core_v1.list_namespaced_service(
            namespace=namespace,
            label_selector=label_selector
        )
    else:
        services = core_v1.list_service_for_all_namespaces(
            label_selector=label_selector
        )

    if output_format == "table":
        return _format_services_table(services.items)
    else:
        service_list = []
        for service in services.items:
            ports = []
            if service.spec.ports:
                for port in service.spec.ports:
                    port_str = f"{port.port}"
                    if port.target_port:
                        port_str += f":{port.target_port}"
                    if port.protocol != "TCP":
                        port_str += f"/{port.protocol}"
                    ports.append(port_str)

            service_info = {
                "name": service.metadata.name,
                "namespace": service.metadata.namespace,
                "type": service.spec.type,
                "cluster_ip": service.spec.cluster_ip,
                "external_ip": _get_external_ip(service),
                "ports": ports,
                "age": _calculate_age(service.metadata.creation_timestamp)
            }
            service_list.append(service_info)

        return json.dumps({"items": service_list, "total": len(service_list)})


def _get_nodes(label_selector, output_format):
    """获取Node列表"""
    core_v1 = client.CoreV1Api()
    nodes = core_v1.list_node(label_selector=label_selector)

    if output_format == "table":
        return _format_nodes_table(nodes.items)
    else:
        node_list = []
        for node in nodes.items:
            # 获取节点状态
            status = "Unknown"
            for condition in node.status.conditions or []:
                if condition.type == "Ready":
                    status = "Ready" if condition.status == "True" else "NotReady"
                    break

            # 获取节点角色
            roles = []
            if node.metadata.labels:
                for label, value in node.metadata.labels.items():
                    if label.startswith("node-role.kubernetes.io/"):
                        role = label.split("/", 1)[1]
                        if role:
                            roles.append(role)

            node_info = {
                "name": node.metadata.name,
                "status": status,
                "roles": roles or ["<none>"],
                "age": _calculate_age(node.metadata.creation_timestamp),
                "version": node.status.node_info.kubelet_version if node.status.node_info else "",
                "internal_ip": _get_node_internal_ip(node),
                "external_ip": _get_node_external_ip(node)
            }
            node_list.append(node_info)

        return json.dumps({"items": node_list, "total": len(node_list)})


def _get_namespaces(label_selector, output_format):
    """获取Namespace列表"""
    core_v1 = client.CoreV1Api()
    namespaces = core_v1.list_namespace(label_selector=label_selector)

    namespace_list = []
    for ns in namespaces.items:
        ns_info = {
            "name": ns.metadata.name,
            "status": ns.status.phase,
            "age": _calculate_age(ns.metadata.creation_timestamp)
        }
        namespace_list.append(ns_info)

    return json.dumps({"items": namespace_list, "total": len(namespace_list)})


def _get_configmaps(namespace, label_selector, output_format):
    """获取ConfigMap列表"""
    core_v1 = client.CoreV1Api()

    if namespace:
        configmaps = core_v1.list_namespaced_config_map(
            namespace=namespace,
            label_selector=label_selector
        )
    else:
        configmaps = core_v1.list_config_map_for_all_namespaces(
            label_selector=label_selector
        )

    cm_list = []
    for cm in configmaps.items:
        data_count = len(cm.data) if cm.data else 0
        cm_info = {
            "name": cm.metadata.name,
            "namespace": cm.metadata.namespace,
            "data_keys": data_count,
            "age": _calculate_age(cm.metadata.creation_timestamp)
        }
        cm_list.append(cm_info)

    return json.dumps({"items": cm_list, "total": len(cm_list)})


def _get_secrets(namespace, label_selector, output_format):
    """获取Secret列表（隐藏敏感数据）"""
    core_v1 = client.CoreV1Api()

    if namespace:
        secrets = core_v1.list_namespaced_secret(
            namespace=namespace,
            label_selector=label_selector
        )
    else:
        secrets = core_v1.list_secret_for_all_namespaces(
            label_selector=label_selector
        )

    secret_list = []
    for secret in secrets.items:
        data_count = len(secret.data) if secret.data else 0
        secret_info = {
            "name": secret.metadata.name,
            "namespace": secret.metadata.namespace,
            "type": secret.type,
            "data_keys": data_count,
            "age": _calculate_age(secret.metadata.creation_timestamp)
        }
        secret_list.append(secret_info)

    return json.dumps({"items": secret_list, "total": len(secret_list)})


def _get_persistent_volumes(output_format):
    """获取PV列表"""
    core_v1 = client.CoreV1Api()
    pvs = core_v1.list_persistent_volume()

    pv_list = []
    for pv in pvs.items:
        capacity = ""
        if pv.spec.capacity and "storage" in pv.spec.capacity:
            capacity = pv.spec.capacity["storage"]

        pv_info = {
            "name": pv.metadata.name,
            "capacity": capacity,
            "access_modes": pv.spec.access_modes or [],
            "reclaim_policy": pv.spec.persistent_volume_reclaim_policy,
            "status": pv.status.phase,
            "claim": _get_pv_claim(pv),
            "storage_class": pv.spec.storage_class_name or "",
            "age": _calculate_age(pv.metadata.creation_timestamp)
        }
        pv_list.append(pv_info)

    return json.dumps({"items": pv_list, "total": len(pv_list)})


def _get_persistent_volume_claims(namespace, label_selector, output_format):
    """获取PVC列表"""
    core_v1 = client.CoreV1Api()

    if namespace:
        pvcs = core_v1.list_namespaced_persistent_volume_claim(
            namespace=namespace,
            label_selector=label_selector
        )
    else:
        pvcs = core_v1.list_persistent_volume_claim_for_all_namespaces(
            label_selector=label_selector
        )

    pvc_list = []
    for pvc in pvcs.items:
        capacity = ""
        if pvc.status.capacity and "storage" in pvc.status.capacity:
            capacity = pvc.status.capacity["storage"]

        pvc_info = {
            "name": pvc.metadata.name,
            "namespace": pvc.metadata.namespace,
            "status": pvc.status.phase,
            "volume": pvc.spec.volume_name or "",
            "capacity": capacity,
            "access_modes": pvc.spec.access_modes or [],
            "storage_class": pvc.spec.storage_class_name or "",
            "age": _calculate_age(pvc.metadata.creation_timestamp)
        }
        pvc_list.append(pvc_info)

    return json.dumps({"items": pvc_list, "total": len(pvc_list)})


def _get_events(namespace, label_selector, output_format):
    """获取Event列表"""
    core_v1 = client.CoreV1Api()

    if namespace:
        events = core_v1.list_namespaced_event(
            namespace=namespace,
            label_selector=label_selector
        )
    else:
        events = core_v1.list_event_for_all_namespaces(
            label_selector=label_selector
        )

    event_list = []
    for event in events.items:
        event_info = {
            "name": event.metadata.name,
            "namespace": event.metadata.namespace,
            "type": event.type,
            "reason": event.reason,
            "message": event.message,
            "source": event.source.component if event.source else "",
            "first_timestamp": event.first_timestamp.isoformat() if event.first_timestamp else "",
            "last_timestamp": event.last_timestamp.isoformat() if event.last_timestamp else "",
            "count": event.count or 1,
            "age": _calculate_age(event.metadata.creation_timestamp)
        }
        event_list.append(event_info)

    return json.dumps({"items": event_list, "total": len(event_list)})


def _get_replicasets(namespace, label_selector, output_format):
    """获取ReplicaSet列表"""
    apps_v1 = client.AppsV1Api()

    if namespace:
        replicasets = apps_v1.list_namespaced_replica_set(
            namespace=namespace,
            label_selector=label_selector
        )
    else:
        replicasets = apps_v1.list_replica_set_for_all_namespaces(
            label_selector=label_selector
        )

    rs_list = []
    for rs in replicasets.items:
        rs_info = {
            "name": rs.metadata.name,
            "namespace": rs.metadata.namespace,
            "desired": rs.spec.replicas or 0,
            "current": rs.status.replicas or 0,
            "ready": rs.status.ready_replicas or 0,
            "age": _calculate_age(rs.metadata.creation_timestamp)
        }
        rs_list.append(rs_info)

    return json.dumps({"items": rs_list, "total": len(rs_list)})


def _get_daemonsets(namespace, label_selector, output_format):
    """获取DaemonSet列表"""
    apps_v1 = client.AppsV1Api()

    if namespace:
        daemonsets = apps_v1.list_namespaced_daemon_set(
            namespace=namespace,
            label_selector=label_selector
        )
    else:
        daemonsets = apps_v1.list_daemon_set_for_all_namespaces(
            label_selector=label_selector
        )

    ds_list = []
    for ds in daemonsets.items:
        ds_info = {
            "name": ds.metadata.name,
            "namespace": ds.metadata.namespace,
            "desired": ds.status.desired_number_scheduled or 0,
            "current": ds.status.current_number_scheduled or 0,
            "ready": ds.status.number_ready or 0,
            "up_to_date": ds.status.updated_number_scheduled or 0,
            "available": ds.status.number_available or 0,
            "age": _calculate_age(ds.metadata.creation_timestamp)
        }
        ds_list.append(ds_info)

    return json.dumps({"items": ds_list, "total": len(ds_list)})


def _get_statefulsets(namespace, label_selector, output_format):
    """获取StatefulSet列表"""
    apps_v1 = client.AppsV1Api()

    if namespace:
        statefulsets = apps_v1.list_namespaced_stateful_set(
            namespace=namespace,
            label_selector=label_selector
        )
    else:
        statefulsets = apps_v1.list_stateful_set_for_all_namespaces(
            label_selector=label_selector
        )

    sts_list = []
    for sts in statefulsets.items:
        sts_info = {
            "name": sts.metadata.name,
            "namespace": sts.metadata.namespace,
            "ready": f"{sts.status.ready_replicas or 0}/{sts.spec.replicas or 0}",
            "age": _calculate_age(sts.metadata.creation_timestamp)
        }
        sts_list.append(sts_info)

    return json.dumps({"items": sts_list, "total": len(sts_list)})


# 辅助函数
def _get_pod_ready_status(pod):
    """获取Pod的就绪状态"""
    if not pod.status.container_statuses:
        return "0/0"

    total = len(pod.status.container_statuses)
    ready = sum(
        1 for container in pod.status.container_statuses if container.ready)
    return f"{ready}/{total}"


def _get_pod_restart_count(pod):
    """获取Pod的重启次数"""
    if not pod.status.container_statuses:
        return 0

    return sum(container.restart_count for container in pod.status.container_statuses)


def _get_external_ip(service):
    """获取Service的外部IP"""
    if service.spec.type == "LoadBalancer" and service.status.load_balancer:
        if service.status.load_balancer.ingress:
            for ingress in service.status.load_balancer.ingress:
                if ingress.ip:
                    return ingress.ip
                elif ingress.hostname:
                    return ingress.hostname
    elif service.spec.type == "NodePort":
        return "<nodes>"
    elif service.spec.external_i_ps:
        return ",".join(service.spec.external_i_ps)
    return "<none>"


def _get_node_internal_ip(node):
    """获取节点内部IP"""
    if node.status.addresses:
        for address in node.status.addresses:
            if address.type == "InternalIP":
                return address.address
    return "<none>"


def _get_node_external_ip(node):
    """获取节点外部IP"""
    if node.status.addresses:
        for address in node.status.addresses:
            if address.type == "ExternalIP":
                return address.address
    return "<none>"


def _get_pv_claim(pv):
    """获取PV的绑定Claim"""
    if pv.spec.claim_ref:
        return f"{pv.spec.claim_ref.namespace}/{pv.spec.claim_ref.name}"
    return ""


def _calculate_age(creation_timestamp):
    """计算资源的年龄"""
    if not creation_timestamp:
        return "unknown"

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    age = now - creation_timestamp

    days = age.days
    hours, remainder = divmod(age.seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    if days > 0:
        return f"{days}d"
    elif hours > 0:
        return f"{hours}h"
    else:
        return f"{minutes}m"


def _format_pods_table(pods):
    """格式化Pod表格输出"""
    table = "NAME                    READY   STATUS    RESTARTS   AGE   IP           NODE\n"
    for pod in pods:
        ready = _get_pod_ready_status(pod)
        restarts = _get_pod_restart_count(pod)
        age = _calculate_age(pod.metadata.creation_timestamp)
        ip = pod.status.pod_ip or "<none>"
        node = pod.spec.node_name or "<none>"

        table += f"{pod.metadata.name:<23} {ready:<7} {pod.status.phase:<9} {restarts:<10} {age:<5} {ip:<12} {node}\n"

    return table


def _format_deployments_table(deployments):
    """格式化Deployment表格输出"""
    table = "NAME                    READY   UP-TO-DATE   AVAILABLE   AGE\n"
    for deployment in deployments:
        ready_replicas = deployment.status.ready_replicas or 0
        total_replicas = deployment.spec.replicas or 0
        updated = deployment.status.updated_replicas or 0
        available = deployment.status.available_replicas or 0
        age = _calculate_age(deployment.metadata.creation_timestamp)

        table += f"{deployment.metadata.name:<23} {ready_replicas}/{total_replicas:<7} {updated:<12} {available:<11} {age}\n"

    return table


def _format_services_table(services):
    """格式化Service表格输出"""
    table = "NAME                    TYPE           CLUSTER-IP      EXTERNAL-IP   PORT(S)                  AGE\n"
    for service in services:
        external_ip = _get_external_ip(service)
        ports = []
        if service.spec.ports:
            for port in service.spec.ports:
                port_str = f"{port.port}"
                if port.node_port and service.spec.type == "NodePort":
                    port_str += f":{port.node_port}"
                if port.protocol != "TCP":
                    port_str += f"/{port.protocol}"
                ports.append(port_str)
        ports_str = ",".join(ports) if ports else "<none>"
        age = _calculate_age(service.metadata.creation_timestamp)

        table += f"{service.metadata.name:<23} {service.spec.type:<14} {service.spec.cluster_ip:<15} {external_ip:<13} {ports_str:<24} {age}\n"

    return table


def _format_nodes_table(nodes):
    """格式化Node表格输出"""
    table = "NAME                    STATUS   ROLES    AGE     VERSION\n"
    for node in nodes:
        # 获取节点状态
        status = "Unknown"
        for condition in node.status.conditions or []:
            if condition.type == "Ready":
                status = "Ready" if condition.status == "True" else "NotReady"
                break

        # 获取节点角色
        roles = []
        if node.metadata.labels:
            for label in node.metadata.labels:
                if label.startswith("node-role.kubernetes.io/"):
                    role = label.split("/", 1)[1]
                    if role:
                        roles.append(role)
        roles_str = ",".join(roles) if roles else "<none>"

        age = _calculate_age(node.metadata.creation_timestamp)
        version = node.status.node_info.kubelet_version if node.status.node_info else ""

        table += f"{node.metadata.name:<23} {status:<8} {roles_str:<8} {age:<7} {version}\n"

    return table


@tool()
def kubectl_get_all_resources(namespace=None, config: RunnableConfig = None):
    """
    获取指定命名空间中的所有主要资源，类似于 kubectl get all

    Args:
        namespace (str, optional): 命名空间，如果为None则查看所有命名空间
        config (RunnableConfig): 工具配置

    Returns:
        str: JSON格式的所有资源概览
    """
    try:
        prepare_context(config)

        result = {
            "namespace": namespace or "所有命名空间",
            "timestamp": "查询时间",
            "resources": {}
        }

        # 查询各种资源类型 - 按照kubectl get all的标准顺序
        resource_types = ["pods", "services", "deployments", "replicasets",
                          "daemonsets", "statefulsets", "configmaps", "secrets"]

        for resource_type in resource_types:
            try:
                resource_data = _query_resources_internal(
                    resource_type, namespace, config=config)
                if resource_data and not resource_data.startswith('{"error"'):
                    resource_json = json.loads(resource_data)
                    result["resources"][resource_type] = {
                        "count": resource_json.get("total", 0),
                        "items": resource_json.get("items", [])
                    }
                else:
                    result["resources"][resource_type] = {
                        "count": 0,
                        "error": "查询失败"
                    }
            except Exception as e:
                result["resources"][resource_type] = {
                    "count": 0,
                    "error": str(e)
                }

        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"获取资源概览失败: {str(e)}",
            "namespace": namespace
        })
