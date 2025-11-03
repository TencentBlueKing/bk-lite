"""Kubernetes配置优化建议工具"""
import json
from datetime import datetime, timezone
from typing import Dict, List
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from kubernetes import client
from loguru import logger
from neco.llm.tools.kubernetes.utils import prepare_context, parse_resource_quantity


@tool()
def check_scaling_capacity(namespace, replicas, resource_requirements=None, config: RunnableConfig = None):
    """
    扩容前的容量校验，避免资源不足导致Pending
    
    **何时使用此工具：**
    - 执行扩容操作前的容量预检查
    - 评估集群是否有足够资源满足扩容需求
    - 排查扩容后Pod持续Pending的原因
    - 进行容量规划和资源使用率评估
    
    **工具能力：**
    - 检查所有Ready节点的可用资源（CPU/Memory/Pod数）
    - 计算是否满足扩容需求
    - 预警资源紧张情况（利用率>80%）
    - 考虑节点分布和调度约束
    - 提供详细的每节点资源使用情况
    
    Args:
        namespace (str): 命名空间（必填）
        replicas (int): 目标副本数（必填）
        resource_requirements (dict, optional): 单个Pod资源需求
            格式: {"cpu": "100m", "memory": "128Mi"}
            - 如果提供：精确计算CPU和内存是否满足
            - 如果不提供：只检查Pod数量容量，强烈建议补充
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - can_scale (bool): 是否可以扩容（关键字段）
        - node_capacity[]: 每个节点的详细容量信息
          - allocatable: 节点总资源
          - available: 当前可用资源
          - utilization: 资源利用率百分比
        - total_nodes: Ready节点总数
        - recommendations[]: 建议列表
          - 资源不足时会说明缺口（缺多少CPU/内存）
          - 资源紧张时会预警利用率
    
    **配合其他工具使用：**
    - 扩容前必须调用此工具 → 然后 scale_deployment
    - 如果 can_scale=false → 考虑添加节点或优化资源配置
    - 扩容后验证分布 → 使用 check_pod_distribution
    
    **最佳实践：**
    - 扩容前务必调用此工具，避免创建大量Pending Pod
    - 建议提供 resource_requirements，获得更准确的评估
    - 如果资源利用率>80%，考虑先添加节点
    
    **注意事项：**
    - 只检查Ready状态的节点
    - 不考虑节点亲和性、污点等高级调度策略
    - 实际调度结果可能因调度器策略而异
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        logger.info(f"检查扩容容量: namespace={namespace}, replicas={replicas}")
        
        # 获取所有节点
        nodes = core_v1.list_node()
        pods = core_v1.list_pod_for_all_namespaces()
        
        # 计算每个节点的可用资源
        node_capacity = []
        for node in nodes.items:
            # 跳过不可调度的节点
            if node.spec.unschedulable:
                continue
            
            # 检查节点是否Ready
            is_ready = False
            for condition in (node.status.conditions or []):
                if condition.type == "Ready" and condition.status == "True":
                    is_ready = True
                    break
            
            if not is_ready:
                continue
            
            node_name = node.metadata.name
            allocatable = node.status.allocatable or {}
            allocatable_cpu = parse_resource_quantity(allocatable.get('cpu', '0'))
            allocatable_memory = parse_resource_quantity(allocatable.get('memory', '0'))
            allocatable_pods = int(allocatable.get('pods', '110'))
            
            # 计算已使用的资源
            used_cpu = 0
            used_memory = 0
            used_pods = 0
            
            for pod in pods.items:
                if pod.spec.node_name == node_name and pod.status.phase in ["Running", "Pending"]:
                    used_pods += 1
                    if pod.spec.containers:
                        for container in pod.spec.containers:
                            if container.resources and container.resources.requests:
                                cpu_request = container.resources.requests.get('cpu', '0')
                                memory_request = container.resources.requests.get('memory', '0')
                                used_cpu += parse_resource_quantity(cpu_request)
                                used_memory += parse_resource_quantity(memory_request)
            
            # 计算可用资源
            available_cpu = allocatable_cpu - used_cpu
            available_memory = allocatable_memory - used_memory
            available_pods = allocatable_pods - used_pods
            
            node_capacity.append({
                "node_name": node_name,
                "allocatable": {
                    "cpu": allocatable_cpu,
                    "memory": allocatable_memory,
                    "pods": allocatable_pods
                },
                "available": {
                    "cpu": available_cpu,
                    "memory": available_memory,
                    "pods": available_pods
                },
                "utilization": {
                    "cpu_percent": round((used_cpu / allocatable_cpu * 100) if allocatable_cpu > 0 else 0, 2),
                    "memory_percent": round((used_memory / allocatable_memory * 100) if allocatable_memory > 0 else 0, 2),
                    "pods_percent": round((used_pods / allocatable_pods * 100) if allocatable_pods > 0 else 0, 2)
                }
            })
        
        # 如果提供了资源需求，计算是否可以满足
        can_scale = True
        recommendations = []
        
        if resource_requirements:
            required_cpu = parse_resource_quantity(resource_requirements.get('cpu', '0'))
            required_memory = parse_resource_quantity(resource_requirements.get('memory', '0'))
            
            total_required_cpu = required_cpu * replicas
            total_required_memory = required_memory * replicas
            
            # 计算集群总可用资源
            total_available_cpu = sum(n["available"]["cpu"] for n in node_capacity)
            total_available_memory = sum(n["available"]["memory"] for n in node_capacity)
            total_available_pods = sum(n["available"]["pods"] for n in node_capacity)
            
            if total_required_cpu > total_available_cpu:
                can_scale = False
                recommendations.append(f"CPU资源不足：需要{total_required_cpu:.2f}核，可用{total_available_cpu:.2f}核")
            
            if total_required_memory > total_available_memory:
                can_scale = False
                recommendations.append(f"内存资源不足：需要{total_required_memory / (1024**3):.2f}Gi，可用{total_available_memory / (1024**3):.2f}Gi")
            
            if replicas > total_available_pods:
                can_scale = False
                recommendations.append(f"Pod容量不足：需要{replicas}个Pod，可用{total_available_pods}个")
            
            if can_scale:
                recommendations.append("集群有足够资源进行扩容")
                # 检查是否资源紧张
                if total_required_cpu / total_available_cpu > 0.8:
                    recommendations.append("警告：扩容后CPU利用率将超过80%")
                if total_required_memory / total_available_memory > 0.8:
                    recommendations.append("警告：扩容后内存利用率将超过80%")
        else:
            # 只检查Pod容量
            total_available_pods = sum(n["available"]["pods"] for n in node_capacity)
            if replicas > total_available_pods:
                can_scale = False
                recommendations.append(f"Pod容量不足：需要{replicas}个Pod，可用{total_available_pods}个")
            else:
                recommendations.append("集群有足够Pod容量，但需要确认资源requests配置")
        
        result = {
            "namespace": namespace,
            "requested_replicas": replicas,
            "resource_requirements_per_pod": resource_requirements,
            "can_scale": can_scale,
            "node_capacity": node_capacity,
            "total_nodes": len(node_capacity),
            "recommendations": recommendations,
            "check_time": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"容量检查完成: can_scale={can_scale}")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"检查扩容容量失败: {str(e)}")
        return json.dumps({
            "error": f"检查扩容容量失败: {str(e)}",
            "namespace": namespace
        })


@tool()
def check_pod_distribution(deployment_name, namespace, config: RunnableConfig = None):
    """
    检查Pod分布情况，评估高可用性和单点故障风险
    
    **何时使用此工具：**
    - 评估应用的高可用性和容灾能力
    - 识别单点故障风险和分布不均问题
    - 扩容后验证Pod分布的合理性
    - 分析Pod在节点和可用区的分布模式
    
    **工具能力：**
    - 分析Pod在节点上的分布情况
    - 识别单点故障风险（所有Pod在一个节点）
    - 检查可用区（Zone）分布，评估区域容灾能力
    - 计算分布均匀性（最多vs最少Pod数差异）
    - 提供Pod反亲和性配置建议
    
    Args:
        deployment_name (str): Deployment或StatefulSet名称（必填）
        namespace (str): 命名空间（必填）
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - node_distribution: 每个节点上的Pod列表
          - pod_count: 节点上的Pod数量
          - pods[]: Pod详情（name、status）
        - zone_distribution: 每个可用区的Pod数量
        - total_pods: Pod总数
        - running_pods: Running状态的Pod数
        - issues[]: 发现的问题
          - severity: high/medium/low
          - message: 问题描述
        - recommendations[]: 改进建议
        - distribution_score: "good" 或 "needs_improvement"
    
    **配合其他工具使用：**
    - 扩容前检查容量 → 使用 check_scaling_capacity
    - 扩容后检查分布 → 使用此工具验证
    - 发现配置问题 → 根据 recommendations 调整 Pod 配置
    
    **高可用评分标准：**
    - 单节点部署：high severity（单点故障）
    - 分布不均（差异>2）：medium severity
    - 单可用区：medium severity（无区域容灾）
    - 分布均匀 + 多可用区：good
    
    **注意事项：**
    - 如果未配置Pod反亲和性，Kubernetes默认可能将Pod调度到同一节点
    - 单副本应用无需关注分布问题
    - StatefulSet的Pod分布受Volume Zone影响
    """
    prepare_context(config)
    
    try:
        apps_v1 = client.AppsV1Api()
        core_v1 = client.CoreV1Api()
        
        logger.info(f"检查Pod分布: {namespace}/{deployment_name}")
        
        # 获取Deployment
        try:
            deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
            resource_type = "Deployment"
            selector = deployment.spec.selector.match_labels
        except ApiException:
            # 尝试StatefulSet
            try:
                statefulset = apps_v1.read_namespaced_stateful_set(deployment_name, namespace)
                resource_type = "StatefulSet"
                selector = statefulset.spec.selector.match_labels
            except ApiException:
                return json.dumps({
                    "error": f"未找到Deployment或StatefulSet: {namespace}/{deployment_name}"
                })
        
        # 获取匹配的Pod
        label_selector = ",".join([f"{k}={v}" for k, v in selector.items()])
        pods = core_v1.list_namespaced_pod(namespace, label_selector=label_selector)
        
        # 按节点分组
        node_distribution = {}
        total_pods = 0
        running_pods = 0
        
        for pod in pods.items:
            total_pods += 1
            if pod.status.phase == "Running":
                running_pods += 1
            
            node_name = pod.spec.node_name or "未调度"
            if node_name not in node_distribution:
                node_distribution[node_name] = []
            
            node_distribution[node_name].append({
                "pod_name": pod.metadata.name,
                "status": pod.status.phase
            })
        
        # 分析分布均匀性
        issues = []
        recommendations = []
        
        node_count = len([n for n in node_distribution.keys() if n != "未调度"])
        
        if node_count == 0:
            issues.append({
                "severity": "critical",
                "message": "所有Pod都未被调度"
            })
        elif node_count == 1 and total_pods > 1:
            issues.append({
                "severity": "high",
                "message": f"所有{total_pods}个Pod都运行在同一个节点上，存在单点故障风险"
            })
            recommendations.append("配置Pod反亲和性（podAntiAffinity）将Pod分散到不同节点")
        else:
            # 计算分布均匀性
            pods_per_node = [len(pods) for node, pods in node_distribution.items() if node != "未调度"]
            if pods_per_node:
                max_pods = max(pods_per_node)
                min_pods = min(pods_per_node)
                
                if max_pods - min_pods > 2:
                    issues.append({
                        "severity": "medium",
                        "message": f"Pod分布不均匀：最多{max_pods}个/节点，最少{min_pods}个/节点"
                    })
                    recommendations.append("考虑使用topologySpreadConstraints实现更均匀的分布")
        
        # 检查可用区分布
        nodes = core_v1.list_node()
        zone_distribution = {}
        
        for pod in pods.items:
            if pod.spec.node_name:
                for node in nodes.items:
                    if node.metadata.name == pod.spec.node_name:
                        zone = node.metadata.labels.get("topology.kubernetes.io/zone", "unknown")
                        if zone not in zone_distribution:
                            zone_distribution[zone] = 0
                        zone_distribution[zone] += 1
                        break
        
        if len(zone_distribution) == 1 and total_pods > 1:
            issues.append({
                "severity": "medium",
                "message": "所有Pod都在同一个可用区，缺乏区域容灾能力"
            })
            recommendations.append("配置跨可用区的Pod拓扑分布约束")
        
        result = {
            "resource_type": resource_type,
            "resource_name": deployment_name,
            "namespace": namespace,
            "total_pods": total_pods,
            "running_pods": running_pods,
            "node_distribution": {
                node: {
                    "pod_count": len(pods_list),
                    "pods": pods_list
                } for node, pods_list in node_distribution.items()
            },
            "zone_distribution": zone_distribution,
            "issues": issues,
            "recommendations": recommendations,
            "distribution_score": "good" if len(issues) == 0 else "needs_improvement"
        }
        
        logger.info(f"Pod分布检查完成: {total_pods}个Pod分布在{node_count}个节点")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"检查Pod分布失败: {str(e)}")
        return json.dumps({
            "error": f"检查Pod分布失败: {str(e)}",
            "deployment_name": deployment_name,
            "namespace": namespace
        })


@tool()
def validate_probe_configuration(deployment_name, namespace, config: RunnableConfig = None):
    """
    验证健康检查探针配置，确保服务可靠性
    
    **何时使用此工具：**
    - 评估健康检查探针的配置合理性和完整性
    - 排查因探针配置不当导致的频繁重启问题
    - 诊断Pod一直无法达到Ready状态的原因
    - 检查探针参数设置是否符合最佳实践
    
    **工具能力：**
    - 检查Liveness探针配置（存活探针）
    - 检查Readiness探针配置（就绪探针）
    - 检查Startup探针配置（启动探针，K8S 1.16+）
    - 验证探针参数合理性（超时、延迟、阈值）
    - 识别常见配置错误（延迟为0、超时太短等）
    - 计算探针覆盖率评分
    
    **探针类型说明：**
    - Liveness: 检测容器是否存活，失败会重启容器
    - Readiness: 检测容器是否就绪，失败会从Service移除
    - Startup: 检测容器是否启动完成，用于慢启动应用
    
    Args:
        deployment_name (str): Deployment名称（必填）
        namespace (str): 命名空间（必填）
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - containers_analysis[]: 每个容器的探针分析
          - liveness_probe: 存活探针配置（type、delay、timeout等）
          - readiness_probe: 就绪探针配置
          - startup_probe: 启动探针配置
          - issues[]: 发现的配置问题
          - recommendations[]: 改进建议
        - probe_score: 探针配置评分（如"4/6"表示3个容器中2个配置完整）
        - probe_coverage_percent: 探针覆盖率百分比
        - overall_status: "good" 或 "needs_improvement"
    
    **配合其他工具使用：**
    - 如果发现探针问题导致重启 → 使用 analyze_pod_restart_pattern
    - 如果需要修改探针配置 → 建议用户更新Deployment YAML
    
    **常见问题识别：**
    - initialDelaySeconds=0: 容器启动时就开始检查，可能过早失败
    - timeoutSeconds<1: 超时太短，网络抖动就会失败
    - 未配置Readiness: 容器未就绪也会接收流量
    - 未配置Liveness: 容器僵死无法自动恢复
    
    **最佳实践建议：**
    - 必须配置Readiness探针，避免未就绪Pod接收流量
    - Liveness探针建议配置，但要谨慎设置（避免误杀）
    - initialDelaySeconds应大于应用启动时间
    - 对于慢启动应用（如Java），建议配置Startup探针
    """
    prepare_context(config)
    
    try:
        apps_v1 = client.AppsV1Api()
        logger.info(f"验证探针配置: {namespace}/{deployment_name}")
        
        # 获取Deployment
        deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
        
        containers_analysis = []
        issues = []
        recommendations = []
        
        for container in (deployment.spec.template.spec.containers or []):
            container_analysis = {
                "container_name": container.name,
                "liveness_probe": None,
                "readiness_probe": None,
                "startup_probe": None,
                "issues": [],
                "recommendations": []
            }
            
            # 分析Liveness Probe
            if container.liveness_probe:
                liveness = container.liveness_probe
                container_analysis["liveness_probe"] = {
                    "configured": True,
                    "type": _get_probe_type(liveness),
                    "initial_delay_seconds": liveness.initial_delay_seconds or 0,
                    "period_seconds": liveness.period_seconds or 10,
                    "timeout_seconds": liveness.timeout_seconds or 1,
                    "failure_threshold": liveness.failure_threshold or 3
                }
                
                # 检查配置合理性
                if liveness.initial_delay_seconds == 0:
                    container_analysis["issues"].append("Liveness探针initialDelaySeconds为0，可能导致容器启动时就被杀死")
                    container_analysis["recommendations"].append("设置合理的initialDelaySeconds，给容器足够的启动时间")
                
                if liveness.timeout_seconds < 1:
                    container_analysis["issues"].append("Liveness探针timeout太短")
                
            else:
                container_analysis["liveness_probe"] = {"configured": False}
                container_analysis["issues"].append("未配置Liveness探针")
                container_analysis["recommendations"].append("配置Liveness探针以自动重启失败的容器")
            
            # 分析Readiness Probe
            if container.readiness_probe:
                readiness = container.readiness_probe
                container_analysis["readiness_probe"] = {
                    "configured": True,
                    "type": _get_probe_type(readiness),
                    "initial_delay_seconds": readiness.initial_delay_seconds or 0,
                    "period_seconds": readiness.period_seconds or 10,
                    "timeout_seconds": readiness.timeout_seconds or 1,
                    "failure_threshold": readiness.failure_threshold or 3
                }
            else:
                container_analysis["readiness_probe"] = {"configured": False}
                container_analysis["issues"].append("未配置Readiness探针")
                container_analysis["recommendations"].append("配置Readiness探针确保只有就绪的Pod接收流量")
            
            # 分析Startup Probe (K8S 1.16+)
            if hasattr(container, 'startup_probe') and container.startup_probe:
                startup = container.startup_probe
                container_analysis["startup_probe"] = {
                    "configured": True,
                    "type": _get_probe_type(startup),
                    "initial_delay_seconds": startup.initial_delay_seconds or 0,
                    "period_seconds": startup.period_seconds or 10,
                    "failure_threshold": startup.failure_threshold or 3
                }
            else:
                container_analysis["startup_probe"] = {"configured": False}
            
            containers_analysis.append(container_analysis)
            
            # 汇总问题和建议
            if container_analysis["issues"]:
                issues.extend([f"{container.name}: {issue}" for issue in container_analysis["issues"]])
            if container_analysis["recommendations"]:
                recommendations.extend([f"{container.name}: {rec}" for rec in container_analysis["recommendations"]])
        
        # 总体评分
        probe_score = 0
        total_score = len(containers_analysis) * 2  # 每个容器2分（liveness + readiness）
        
        for analysis in containers_analysis:
            if analysis["liveness_probe"]["configured"]:
                probe_score += 1
            if analysis["readiness_probe"]["configured"]:
                probe_score += 1
        
        result = {
            "deployment_name": deployment_name,
            "namespace": namespace,
            "total_containers": len(containers_analysis),
            "containers_analysis": containers_analysis,
            "probe_score": f"{probe_score}/{total_score}",
            "probe_coverage_percent": round((probe_score / total_score * 100) if total_score > 0 else 0, 2),
            "issues": issues,
            "recommendations": recommendations,
            "overall_status": "good" if len(issues) == 0 else "needs_improvement"
        }
        
        logger.info(f"探针配置验证完成: {probe_score}/{total_score}")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except ApiException as e:
        logger.error(f"验证探针配置失败: {str(e)}")
        if e.status == 404:
            return json.dumps({
                "error": f"Deployment不存在: {namespace}/{deployment_name}"
            })
        return json.dumps({
            "error": f"验证探针配置失败: {str(e)}"
        })


def _get_probe_type(probe):
    """获取探针类型"""
    if probe.http_get:
        return "httpGet"
    elif probe.tcp_socket:
        return "tcpSocket"
    elif probe._exec:
        return "exec"
    elif probe.grpc:
        return "grpc"
    else:
        return "unknown"


@tool()
def compare_deployment_revisions(deployment_name, namespace, revision1, revision2, config: RunnableConfig = None):
    """
    对比Deployment版本差异，理解变更内容
    
    **何时使用此工具：**
    - 分析不同版本之间的配置差异
    - 回滚前确认目标版本的具体变更
    - 排查变更与故障之间的因果关系
    - 理解版本演进过程中的配置变化
    
    **工具能力：**
    - 对比两个revision的Pod模板
    - 识别镜像变更（版本升级）
    - 识别环境变量变更（新增/删除/修改）
    - 识别副本数变更
    - 识别资源配置变更（requests/limits）
    - 展示每个revision的基本信息（创建时间、ReplicaSet）
    
    Args:
        deployment_name (str): Deployment名称（必填）
        namespace (str): 命名空间（必填）
        revision1 (int): 第一个版本号（必填）
        revision2 (int): 第二个版本号（必填）
            提示：使用 get_deployment_revision_history 查看可用版本
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - comparison: 两个版本的基本信息
          - revision1/revision2: 版本号、ReplicaSet名称、创建时间
        - differences[]: 差异列表
          - field: 变更字段（container_images、env、replicas等）
          - revision1_value: 版本1的值
          - revision2_value: 版本2的值
          - change_type: modified/added/removed
          - added_vars/removed_vars/modified_vars: 环境变量变更详情
        - differences_count: 差异总数
        - has_changes: 是否有变更（bool）
    
    **配合其他工具使用：**
    - 先查看历史 → 使用 get_deployment_revision_history
    - 对比后决定回滚 → 使用 rollback_deployment
    
    **注意事项：**
    - 如果版本号不存在，会返回错误
    - 只对比Pod模板，不对比Deployment级别的配置
    - 只显示主要差异，不包含所有字段
    
    **典型使用场景：**
    ```
    场景：用户说"新版本有问题，看看改了什么"
    步骤1: get_deployment_revision_history 查看历史（发现当前是rev3，上一个是rev2）
    步骤2: compare_deployment_revisions(rev2, rev3) 对比差异
    步骤3: 发现镜像从v1.0升级到v1.1，环境变量新增了DEBUG=true
    步骤4: 建议回滚到rev2
    ```
    """
    prepare_context(config)
    
    try:
        apps_v1 = client.AppsV1Api()
        logger.info(f"对比Deployment版本: {namespace}/{deployment_name}, rev{revision1} vs rev{revision2}")
        
        # 获取Deployment的所有ReplicaSet
        deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
        label_selector = ",".join([f"{k}={v}" for k, v in deployment.spec.selector.match_labels.items()])
        replica_sets = apps_v1.list_namespaced_replica_set(namespace, label_selector=label_selector)
        
        # 找到对应revision的ReplicaSet
        rs1 = None
        rs2 = None
        
        for rs in replica_sets.items:
            rs_revision = rs.metadata.annotations.get("deployment.kubernetes.io/revision")
            if rs_revision:
                if int(rs_revision) == revision1:
                    rs1 = rs
                elif int(rs_revision) == revision2:
                    rs2 = rs
        
        if not rs1:
            return json.dumps({"error": f"未找到revision {revision1}"})
        if not rs2:
            return json.dumps({"error": f"未找到revision {revision2}"})
        
        # 对比配置
        differences = []
        
        # 对比镜像
        images1 = [c.image for c in (rs1.spec.template.spec.containers or [])]
        images2 = [c.image for c in (rs2.spec.template.spec.containers or [])]
        
        if images1 != images2:
            differences.append({
                "field": "container_images",
                "revision1_value": images1,
                "revision2_value": images2,
                "change_type": "modified"
            })
        
        # 对比环境变量
        for i, container1 in enumerate(rs1.spec.template.spec.containers or []):
            if i < len(rs2.spec.template.spec.containers or []):
                container2 = rs2.spec.template.spec.containers[i]
                
                env1 = {e.name: e.value for e in (container1.env or []) if e.value}
                env2 = {e.name: e.value for e in (container2.env or []) if e.value}
                
                if env1 != env2:
                    differences.append({
                        "field": f"container[{i}].env",
                        "container_name": container1.name,
                        "added_vars": list(set(env2.keys()) - set(env1.keys())),
                        "removed_vars": list(set(env1.keys()) - set(env2.keys())),
                        "modified_vars": [k for k in env1.keys() if k in env2 and env1[k] != env2[k]]
                    })
        
        # 对比副本数
        if rs1.spec.replicas != rs2.spec.replicas:
            differences.append({
                "field": "replicas",
                "revision1_value": rs1.spec.replicas,
                "revision2_value": rs2.spec.replicas,
                "change_type": "modified"
            })
        
        result = {
            "deployment_name": deployment_name,
            "namespace": namespace,
            "comparison": {
                "revision1": {
                    "revision": revision1,
                    "replica_set_name": rs1.metadata.name,
                    "creation_time": rs1.metadata.creation_timestamp.isoformat() if rs1.metadata.creation_timestamp else None
                },
                "revision2": {
                    "revision": revision2,
                    "replica_set_name": rs2.metadata.name,
                    "creation_time": rs2.metadata.creation_timestamp.isoformat() if rs2.metadata.creation_timestamp else None
                }
            },
            "differences_count": len(differences),
            "differences": differences,
            "has_changes": len(differences) > 0
        }
        
        logger.info(f"版本对比完成: {len(differences)}个差异")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"对比Deployment版本失败: {str(e)}")
        return json.dumps({
            "error": f"对比Deployment版本失败: {str(e)}",
            "deployment_name": deployment_name,
            "namespace": namespace
        })
