"""Kubernetes配置分析和策略检查工具"""
import json
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from kubernetes import client
from neco.llm.tools.kubernetes.utils import prepare_context, parse_resource_quantity


@tool()
def check_kubernetes_resource_quotas(namespace=None, config: RunnableConfig = None):
    """
    检查资源配额使用情况

    Args:
        namespace (str, optional): 要检查的命名空间，如果为None则检查所有命名空间
        config (RunnableConfig): 工具配置

    Returns:
        str: JSON格式的资源配额信息，包括配额限制和当前使用量
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()

        if namespace:
            quotas = core_v1.list_namespaced_resource_quota(namespace)
        else:
            quotas = core_v1.list_resource_quota_for_all_namespaces()

        result = []
        for quota in quotas.items:
            quota_info = {
                "name": quota.metadata.name,
                "namespace": quota.metadata.namespace,
                "hard": dict(quota.status.hard) if quota.status.hard else {},
                "used": dict(quota.status.used) if quota.status.used else {},
                "usage_percentage": {}
            }

            # Calculate usage percentages
            if quota.status.hard and quota.status.used:
                for resource, hard_limit in quota.status.hard.items():
                    used_amount = quota.status.used.get(resource, "0")
                    try:
                        hard_value = parse_resource_quantity(hard_limit)
                        used_value = parse_resource_quantity(used_amount)
                        if hard_value > 0:
                            quota_info["usage_percentage"][resource] = round(
                                (used_value / hard_value) * 100, 2)
                    except:
                        # For non-numeric resources like count/integer
                        try:
                            hard_int = int(hard_limit)
                            used_int = int(used_amount)
                            if hard_int > 0:
                                quota_info["usage_percentage"][resource] = round(
                                    (used_int / hard_int) * 100, 2)
                        except:
                            quota_info["usage_percentage"][resource] = "无法计算"

            result.append(quota_info)

        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"检查资源配额失败: {str(e)}"})


@tool()
def check_kubernetes_network_policies(namespace=None, config: RunnableConfig = None):
    """
    检查网络策略配置

    Args:
        namespace (str, optional): 要检查的命名空间
        config (RunnableConfig): 工具配置

    Returns:
        str: JSON格式的网络策略信息
    """
    prepare_context(config)
    try:
        networking_v1 = client.NetworkingV1Api()

        if namespace:
            policies = networking_v1.list_namespaced_network_policy(namespace)
        else:
            policies = networking_v1.list_network_policy_for_all_namespaces()

        result = []
        for policy in policies.items:
            result.append({
                "name": policy.metadata.name,
                "namespace": policy.metadata.namespace,
                "pod_selector": policy.spec.pod_selector.match_labels if policy.spec.pod_selector and policy.spec.pod_selector.match_labels else {},
                "policy_types": policy.spec.policy_types if policy.spec.policy_types else [],
                "ingress_rules": len(policy.spec.ingress) if policy.spec.ingress else 0,
                "egress_rules": len(policy.spec.egress) if policy.spec.egress else 0
            })

        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"检查网络策略失败: {str(e)}"})


@tool()
def check_kubernetes_persistent_volumes(config: RunnableConfig = None):
    """
    检查持久化卷状态和使用情况

    Returns:
        str: JSON格式的PV信息，包括状态、容量、回收策略等
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()
        pvs = core_v1.list_persistent_volume()
        pvcs = core_v1.list_persistent_volume_claim_for_all_namespaces()

        # 构建PVC映射
        pvc_map = {}
        for pvc in pvcs.items:
            if pvc.spec.volume_name:
                pvc_map[pvc.spec.volume_name] = {
                    "name": pvc.metadata.name,
                    "namespace": pvc.metadata.namespace,
                    "status": pvc.status.phase
                }

        result = []
        for pv in pvs.items:
            pv_info = {
                "name": pv.metadata.name,
                "capacity": dict(pv.spec.capacity) if pv.spec.capacity else {},
                "access_modes": pv.spec.access_modes if pv.spec.access_modes else [],
                "reclaim_policy": pv.spec.persistent_volume_reclaim_policy,
                "status": pv.status.phase,
                "storage_class": pv.spec.storage_class_name,
                "claim": pvc_map.get(pv.metadata.name, None)
            }
            result.append(pv_info)

        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"检查持久化卷失败: {str(e)}"})


@tool()
def check_kubernetes_ingress(namespace=None, config: RunnableConfig = None):
    """
    检查Ingress配置和状态

    Args:
        namespace (str, optional): 要检查的命名空间
        config (RunnableConfig): 工具配置
    """
    prepare_context(config)
    try:
        networking_v1 = client.NetworkingV1Api()

        if namespace:
            ingresses = networking_v1.list_namespaced_ingress(namespace)
        else:
            ingresses = networking_v1.list_ingress_for_all_namespaces()

        result = []
        for ingress in ingresses.items:
            hosts = []
            if ingress.spec.rules:
                for rule in ingress.spec.rules:
                    if rule.host:
                        hosts.append(rule.host)

            # Get load balancer status
            load_balancers = []
            if ingress.status.load_balancer and ingress.status.load_balancer.ingress:
                for lb in ingress.status.load_balancer.ingress:
                    if lb.ip:
                        load_balancers.append({"type": "ip", "value": lb.ip})
                    elif lb.hostname:
                        load_balancers.append(
                            {"type": "hostname", "value": lb.hostname})

            # Extract backend services
            backends = []
            if ingress.spec.rules:
                for rule in ingress.spec.rules:
                    if rule.http and rule.http.paths:
                        for path in rule.http.paths:
                            if path.backend and path.backend.service:
                                backends.append({
                                    "service_name": path.backend.service.name,
                                    "service_port": path.backend.service.port.number if path.backend.service.port else None,
                                    "path": path.path,
                                    "path_type": path.path_type
                                })

            result.append({
                "name": ingress.metadata.name,
                "namespace": ingress.metadata.namespace,
                "hosts": hosts,
                "load_balancers": load_balancers,
                "backends": backends,
                "ingress_class": ingress.spec.ingress_class_name,
                "tls": len(ingress.spec.tls) if ingress.spec.tls else 0
            })

        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"检查Ingress失败: {str(e)}"})


@tool()
def check_kubernetes_daemonsets(namespace=None, config: RunnableConfig = None):
    """
    检查DaemonSet状态

    Args:
        namespace (str, optional): 要检查的命名空间
        config (RunnableConfig): 工具配置
    """
    prepare_context(config)
    try:
        apps_v1 = client.AppsV1Api()

        if namespace:
            daemonsets = apps_v1.list_namespaced_daemon_set(namespace)
        else:
            daemonsets = apps_v1.list_daemon_set_for_all_namespaces()

        result = []
        for ds in daemonsets.items:
            result.append({
                "name": ds.metadata.name,
                "namespace": ds.metadata.namespace,
                "desired": ds.status.desired_number_scheduled or 0,
                "current": ds.status.current_number_scheduled or 0,
                "ready": ds.status.number_ready or 0,
                "up_to_date": ds.status.updated_number_scheduled or 0,
                "available": ds.status.number_available or 0,
                "node_selector": ds.spec.template.spec.node_selector if ds.spec.template.spec.node_selector else {}
            })

        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"检查DaemonSet失败: {str(e)}"})


@tool()
def check_kubernetes_statefulsets(namespace=None, config: RunnableConfig = None):
    """
    检查StatefulSet状态

    Args:
        namespace (str, optional): 要检查的命名空间
        config (RunnableConfig): 工具配置
    """
    prepare_context(config)
    try:
        apps_v1 = client.AppsV1Api()

        if namespace:
            statefulsets = apps_v1.list_namespaced_stateful_set(namespace)
        else:
            statefulsets = apps_v1.list_stateful_set_for_all_namespaces()

        result = []
        for sts in statefulsets.items:
            result.append({
                "name": sts.metadata.name,
                "namespace": sts.metadata.namespace,
                "replicas": sts.spec.replicas,
                "ready_replicas": sts.status.ready_replicas or 0,
                "current_replicas": sts.status.current_replicas or 0,
                "updated_replicas": sts.status.updated_replicas or 0,
                "service_name": sts.spec.service_name,
                "volume_claim_templates": len(sts.spec.volume_claim_templates) if sts.spec.volume_claim_templates else 0
            })

        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"检查StatefulSet失败: {str(e)}"})


@tool()
def check_kubernetes_jobs(namespace=None, config: RunnableConfig = None):
    """
    检查Job和CronJob状态

    Args:
        namespace (str, optional): 要检查的命名空间
        config (RunnableConfig): 工具配置
    """
    prepare_context(config)
    try:
        batch_v1 = client.BatchV1Api()

        result = {"jobs": [], "cronjobs": []}

        # 检查Jobs
        if namespace:
            jobs = batch_v1.list_namespaced_job(namespace)
        else:
            jobs = batch_v1.list_job_for_all_namespaces()

        for job in jobs.items:
            result["jobs"].append({
                "name": job.metadata.name,
                "namespace": job.metadata.namespace,
                "completions": job.spec.completions,
                "parallelism": job.spec.parallelism,
                "succeeded": job.status.succeeded or 0,
                "failed": job.status.failed or 0,
                "active": job.status.active or 0,
                "start_time": job.status.start_time.isoformat() if job.status.start_time else None,
                "completion_time": job.status.completion_time.isoformat() if job.status.completion_time else None
            })

        # 检查CronJobs - 尝试多个API版本以兼容不同的Kubernetes版本
        try:
            # 首先尝试v1 API (Kubernetes 1.21+)
            if namespace:
                cronjobs = batch_v1.list_namespaced_cron_job(namespace)
            else:
                cronjobs = batch_v1.list_cron_job_for_all_namespaces()

            for cronjob in cronjobs.items:
                result["cronjobs"].append({
                    "name": cronjob.metadata.name,
                    "namespace": cronjob.metadata.namespace,
                    "schedule": cronjob.spec.schedule,
                    "suspend": cronjob.spec.suspend or False,
                    "active_jobs": len(cronjob.status.active) if cronjob.status.active else 0,
                    "last_schedule_time": cronjob.status.last_schedule_time.isoformat() if cronjob.status.last_schedule_time else None
                })
        except AttributeError:
            # 如果v1 API不支持CronJob，尝试使用v1beta1 API
            try:
                # 动态导入以避免在不支持的版本中出错
                from kubernetes.client.apis import batch_v1beta1_api
                batch_v1beta1 = batch_v1beta1_api.BatchV1beta1Api()

                if namespace:
                    cronjobs = batch_v1beta1.list_namespaced_cron_job(
                        namespace)
                else:
                    cronjobs = batch_v1beta1.list_cron_job_for_all_namespaces()

                for cronjob in cronjobs.items:
                    result["cronjobs"].append({
                        "name": cronjob.metadata.name,
                        "namespace": cronjob.metadata.namespace,
                        "schedule": cronjob.spec.schedule,
                        "suspend": cronjob.spec.suspend or False,
                        "active_jobs": len(cronjob.status.active) if cronjob.status.active else 0,
                        "last_schedule_time": cronjob.status.last_schedule_time.isoformat() if cronjob.status.last_schedule_time else None
                    })
            except (ImportError, AttributeError, ApiException):
                # 如果都不支持，添加说明信息
                result["cronjobs_note"] = "CronJob API不可用于当前Kubernetes版本"

        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"检查Job失败: {str(e)}"})


@tool()
def check_kubernetes_endpoints(namespace=None, config: RunnableConfig = None):
    """
    检查Service的Endpoints状态，帮助诊断服务发现问题

    Args:
        namespace (str, optional): 要检查的命名空间
        config (RunnableConfig): 工具配置
    """
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()

        if namespace:
            endpoints = core_v1.list_namespaced_endpoints(namespace)
        else:
            endpoints = core_v1.list_endpoints_for_all_namespaces()

        result = []
        for endpoint in endpoints.items:
            addresses = []
            not_ready_addresses = []

            if endpoint.subsets:
                for subset in endpoint.subsets:
                    # Ready addresses
                    if subset.addresses:
                        for addr in subset.addresses:
                            port_info = []
                            if subset.ports:
                                for port in subset.ports:
                                    port_info.append({
                                        "name": port.name,
                                        "port": port.port,
                                        "protocol": port.protocol
                                    })
                            addresses.append({
                                "ip": addr.ip,
                                "hostname": addr.hostname,
                                "target_ref": f"{addr.target_ref.kind}/{addr.target_ref.name}" if addr.target_ref else None,
                                "ports": port_info
                            })

                    # Not ready addresses
                    if subset.not_ready_addresses:
                        for addr in subset.not_ready_addresses:
                            not_ready_addresses.append({
                                "ip": addr.ip,
                                "hostname": addr.hostname,
                                "target_ref": f"{addr.target_ref.kind}/{addr.target_ref.name}" if addr.target_ref else None
                            })

            result.append({
                "name": endpoint.metadata.name,
                "namespace": endpoint.metadata.namespace,
                "ready_addresses": addresses,
                "not_ready_addresses": not_ready_addresses,
                "ready_count": len(addresses),
                "not_ready_count": len(not_ready_addresses)
            })

        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"检查Endpoints失败: {str(e)}"})


@tool()
def analyze_deployment_configurations(namespace=None, config: RunnableConfig = None):
    """
    分析 Deployment 配置的合理性

    检查每个 Deployment 的资源配置、探针设置、副本策略等，
    评估配置是否合理并识别潜在问题。

    Args:
        namespace (str, optional): 要分析的命名空间
        config (RunnableConfig): 工具配置

    Returns:
        str: JSON格式的分析结果，包含每个Deployment的配置评估
    """
    prepare_context(config)
    try:
        apps_v1 = client.AppsV1Api()
        core_v1 = client.CoreV1Api()

        if namespace:
            deployments = apps_v1.list_namespaced_deployment(namespace)
        else:
            deployments = apps_v1.list_deployment_for_all_namespaces()

        analysis_results = []

        for deployment in deployments.items:
            analysis = {
                "name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "issues": [],
                "recommendations": [],
                "config_analysis": {
                    "replicas": deployment.spec.replicas,
                    "strategy": deployment.spec.strategy.type if deployment.spec.strategy else "RollingUpdate",
                    "containers": []
                }
            }

            # 分析副本数
            if deployment.spec.replicas == 1:
                analysis["issues"].append("单副本部署，存在单点故障风险")
                analysis["recommendations"].append("考虑增加副本数以提高可用性")

            # 分析容器配置
            if deployment.spec.template.spec.containers:
                for container in deployment.spec.template.spec.containers:
                    container_analysis = {
                        "name": container.name,
                        "image": container.image,
                        "issues": [],
                        "recommendations": []
                    }

                    # 检查资源限制
                    has_requests = False
                    has_limits = False
                    if container.resources:
                        if container.resources.requests:
                            has_requests = True
                        if container.resources.limits:
                            has_limits = True

                    if not has_requests:
                        container_analysis["issues"].append("未设置资源请求")
                        container_analysis["recommendations"].append(
                            "设置CPU和内存请求以确保调度")

                    if not has_limits:
                        container_analysis["issues"].append("未设置资源限制")
                        container_analysis["recommendations"].append(
                            "设置CPU和内存限制以防止资源耗尽")

                    # 检查健康检查
                    if not container.liveness_probe:
                        container_analysis["issues"].append("未配置存活探针")
                        container_analysis["recommendations"].append(
                            "配置存活探针以自动重启失败的容器")

                    if not container.readiness_probe:
                        container_analysis["issues"].append("未配置就绪探针")
                        container_analysis["recommendations"].append(
                            "配置就绪探针以确保流量只路由到就绪的Pod")

                    # 检查镜像标签
                    if container.image.endswith(":latest"):
                        container_analysis["issues"].append("使用latest标签")
                        container_analysis["recommendations"].append(
                            "使用具体的版本标签以确保部署的一致性")

                    # 检查安全上下文
                    if not container.security_context or not container.security_context.run_as_non_root:
                        container_analysis["issues"].append("可能以root用户运行")
                        container_analysis["recommendations"].append(
                            "配置非root用户运行以提高安全性")

                    analysis["config_analysis"]["containers"].append(
                        container_analysis)

            # 检查Pod反亲和性
            if not deployment.spec.template.spec.affinity:
                analysis["recommendations"].append("考虑配置Pod反亲和性以在不同节点上分布副本")

            # 检查中断预算
            try:
                pdbs = core_v1.list_namespaced_pod_disruption_budget(
                    deployment.metadata.namespace)
                has_pdb = any(pdb.spec.selector and
                              pdb.spec.selector.match_labels and
                              all(deployment.spec.selector.match_labels.get(k) == v
                                  for k, v in pdb.spec.selector.match_labels.items())
                              for pdb in pdbs.items)
                if not has_pdb:
                    analysis["recommendations"].append(
                        "考虑配置PodDisruptionBudget以控制自愿中断")
            except:
                pass  # PDB API可能不可用

            analysis_results.append(analysis)

        return json.dumps(analysis_results)

    except ApiException as e:
        return json.dumps({"error": f"分析Deployment配置失败: {str(e)}"})


@tool()
def check_kubernetes_hpa_status(namespace=None, config: RunnableConfig = None):
    """
    检查 HPA (Horizontal Pod Autoscaler) 状态

    Args:
        namespace (str, optional): 要检查的命名空间
        config (RunnableConfig): 工具配置

    Returns:
        str: JSON格式的HPA状态信息
    """
    prepare_context(config)
    try:
        autoscaling_v2 = client.AutoscalingV2Api()

        if namespace:
            hpas = autoscaling_v2.list_namespaced_horizontal_pod_autoscaler(
                namespace)
        else:
            hpas = autoscaling_v2.list_horizontal_pod_autoscaler_for_all_namespaces()

        result = []
        for hpa in hpas.items:
            # 获取当前指标
            current_metrics = []
            if hpa.status.current_metrics:
                for metric in hpa.status.current_metrics:
                    metric_info = {"type": metric.type}
                    if metric.resource:
                        metric_info["resource_name"] = metric.resource.name
                        metric_info["current_value"] = metric.resource.current.average_value or metric.resource.current.average_utilization
                    current_metrics.append(metric_info)

            # 获取目标指标
            target_metrics = []
            if hpa.spec.metrics:
                for metric in hpa.spec.metrics:
                    metric_info = {"type": metric.type}
                    if metric.resource:
                        metric_info["resource_name"] = metric.resource.name
                        metric_info["target_value"] = metric.resource.target.average_value or metric.resource.target.average_utilization
                    target_metrics.append(metric_info)

            result.append({
                "name": hpa.metadata.name,
                "namespace": hpa.metadata.namespace,
                "target_ref": f"{hpa.spec.scale_target_ref.kind}/{hpa.spec.scale_target_ref.name}",
                "min_replicas": hpa.spec.min_replicas,
                "max_replicas": hpa.spec.max_replicas,
                "current_replicas": hpa.status.current_replicas,
                "desired_replicas": hpa.status.desired_replicas,
                "target_metrics": target_metrics,
                "current_metrics": current_metrics,
                "conditions": [
                    {
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message
                    } for condition in (hpa.status.conditions or [])
                ]
            })

        return json.dumps(result)
    except ApiException as e:
        return json.dumps({"error": f"检查HPA状态失败: {str(e)}"})
