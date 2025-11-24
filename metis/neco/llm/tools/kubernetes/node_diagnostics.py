"""Kubernetes Node深度诊断工具"""
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from kubernetes import client
from loguru import logger
from neco.llm.tools.kubernetes.utils import prepare_context, parse_resource_quantity, format_bytes


@tool()
def diagnose_node_issues(node_name, config: RunnableConfig = None):
    """
    深度诊断Node健康状态、压力和调度能力
    
    **何时使用此工具：**
    - 排查节点不可用或调度失败问题
    - 检查节点压力状态（磁盘、内存、PID）
    - 分析节点资源碎片化导致的调度问题
    - 验证节点Taint配置和影响范围
    - 诊断节点被Cordon导致的Pod无法调度
    
    **工具能力：**
    - 检查节点所有Conditions状态（Ready、DiskPressure、MemoryPressure、PIDPressure、NetworkUnavailable）
    - 分析Taints配置及其阻止的Pod数量
    - 检测Cordoned状态（手动标记不可调度）
    - 计算资源碎片化程度（总资源充足但大Pod无法调度）
    - 统计节点上Pod分布和资源占用
    - 检查节点标签和角色配置
    - 提供详细的诊断结论和修复建议
    
    Args:
        node_name (str): 节点名称（必填）
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - node_name: 节点名称
        - health_status: healthy/warning/critical
        - conditions[]: 所有Condition详情
          - type: Ready/DiskPressure/MemoryPressure/PIDPressure/NetworkUnavailable
          - status: True/False/Unknown
          - reason: 原因
          - message: 详细消息
          - last_transition: 最后变化时间
        - taints[]: Taint列表和影响分析
        - is_cordoned: 是否被标记为不可调度
        - resource_analysis: 资源分析
          - allocatable: 可分配资源
          - allocated: 已分配资源
          - available: 可用资源
          - utilization_percent: 利用率百分比
          - fragmentation_risk: 碎片化风险（low/medium/high）
        - pod_summary: Pod统计
          - total_pods: 总Pod数
          - by_phase: 按状态分组的Pod数
          - largest_pod: 最大Pod的资源需求
        - issues[]: 发现的问题列表
        - recommendations[]: 修复建议
        - diagnosis_summary: 一句话诊断结论
    
    **配合其他工具使用：**
    - 如果发现资源不足 → 使用 get_kubernetes_node_capacity 查看集群整体容量
    - 如果发现Taint问题 → 建议用户为Pod添加Toleration
    - 如果节点有问题Pod → 使用 diagnose_kubernetes_pod_issues 诊断具体Pod
    
    **常见Node问题：**
    1. DiskPressure: 磁盘空间不足，无法调度新Pod
    2. MemoryPressure: 内存压力，可能触发OOM
    3. PIDPressure: 进程数超限
    4. NotReady: 节点不健康，所有Pod会被驱逐
    5. Cordoned: 手动标记不可调度，用于维护
    6. 资源碎片化: 总资源够但大Pod调度失败
    
    **注意事项：**
    - 此工具只检查配置和状态，不检查实际资源使用率（需要Metrics Server）
    - Taint分析基于当前Pod配置，实际调度还受其他因素影响
    - 资源碎片化分析基于requests，不考虑实际使用
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        logger.info(f"开始诊断Node: {node_name}")
        
        # 获取Node详情
        try:
            node = core_v1.read_node(node_name)
        except ApiException as e:
            if e.status == 404:
                return json.dumps({
                    "error": f"Node不存在: {node_name}"
                })
            raise
        
        result = {
            "node_name": node_name,
            "health_status": "unknown",
            "conditions": [],
            "taints": [],
            "is_cordoned": node.spec.unschedulable or False,
            "resource_analysis": {},
            "pod_summary": {},
            "node_info": {},
            "issues": [],
            "recommendations": [],
            "diagnosis_summary": "",
            "check_time": datetime.now(timezone.utc).isoformat()
        }
        
        # 1. 分析Node Conditions
        is_ready = False
        critical_conditions = []
        warning_conditions = []
        
        if node.status.conditions:
            for condition in node.status.conditions:
                condition_info = {
                    "type": condition.type,
                    "status": condition.status,
                    "reason": condition.reason,
                    "message": condition.message,
                    "last_transition": condition.last_transition_time.isoformat() if condition.last_transition_time else None
                }
                result["conditions"].append(condition_info)
                
                # 检查关键Condition
                if condition.type == "Ready":
                    if condition.status == "True":
                        is_ready = True
                    else:
                        critical_conditions.append(f"节点NotReady: {condition.reason or condition.message}")
                        result["issues"].append({
                            "severity": "critical",
                            "category": "node_health",
                            "message": f"节点NotReady: {condition.reason}",
                            "details": condition.message
                        })
                
                # 检查压力Condition
                pressure_types = ["DiskPressure", "MemoryPressure", "PIDPressure"]
                if condition.type in pressure_types and condition.status == "True":
                    critical_conditions.append(f"{condition.type}: {condition.message}")
                    result["issues"].append({
                        "severity": "critical",
                        "category": "resource_pressure",
                        "message": f"节点{condition.type}",
                        "details": condition.message
                    })
                    
                    # 针对性建议
                    if condition.type == "DiskPressure":
                        result["recommendations"].append("清理节点磁盘空间：删除未使用的镜像、清理日志文件")
                    elif condition.type == "MemoryPressure":
                        result["recommendations"].append("降低节点内存压力：减少Pod数量或优化Pod内存配置")
                    elif condition.type == "PIDPressure":
                        result["recommendations"].append("减少节点上的进程数：检查是否有进程泄漏")
                
                # NetworkUnavailable
                if condition.type == "NetworkUnavailable" and condition.status == "True":
                    critical_conditions.append("网络不可用")
                    result["issues"].append({
                        "severity": "critical",
                        "category": "network",
                        "message": "节点网络不可用",
                        "details": condition.message
                    })
        
        # 2. 检查Taints
        if node.spec.taints:
            for taint in node.spec.taints:
                taint_info = {
                    "key": taint.key,
                    "value": taint.value,
                    "effect": taint.effect,
                    "description": f"{taint.key}={taint.value}:{taint.effect}"
                }
                result["taints"].append(taint_info)
                
                if taint.effect in ["NoSchedule", "NoExecute"]:
                    result["issues"].append({
                        "severity": "medium",
                        "category": "scheduling",
                        "message": f"Taint阻止Pod调度: {taint.key}={taint.value}:{taint.effect}",
                        "details": "只有带有对应Toleration的Pod才能调度到此节点"
                    })
            
            result["recommendations"].append(
                f"节点有{len(node.spec.taints)}个Taint，确保Pod配置了正确的Toleration"
            )
        
        # 3. 检查Cordoned状态
        if result["is_cordoned"]:
            result["issues"].append({
                "severity": "high",
                "category": "scheduling",
                "message": "节点已被Cordon（标记为不可调度）",
                "details": "新Pod无法调度到此节点，通常用于节点维护"
            })
            result["recommendations"].append("如果维护完成，使用 kubectl uncordon 恢复调度")
        
        # 4. 资源分析
        allocatable = node.status.allocatable or {}
        allocatable_cpu = parse_resource_quantity(allocatable.get('cpu', '0'))
        allocatable_memory = parse_resource_quantity(allocatable.get('memory', '0'))
        allocatable_pods = int(allocatable.get('pods', '110'))
        
        # 获取节点上的Pod
        pods = core_v1.list_pod_for_all_namespaces(
            field_selector=f"spec.nodeName={node_name}"
        )
        
        # 计算已分配资源
        allocated_cpu = 0
        allocated_memory = 0
        pod_count = 0
        pods_by_phase = {"Running": 0, "Pending": 0, "Failed": 0, "Succeeded": 0, "Unknown": 0}
        largest_pod = {"cpu": 0, "memory": 0, "name": ""}
        
        for pod in pods.items:
            if pod.status.phase not in ["Succeeded", "Failed"]:  # 不计算已完成的Pod
                pod_count += 1
                pods_by_phase[pod.status.phase] = pods_by_phase.get(pod.status.phase, 0) + 1
                
                pod_cpu = 0
                pod_memory = 0
                
                if pod.spec.containers:
                    for container in pod.spec.containers:
                        if container.resources and container.resources.requests:
                            cpu_req = parse_resource_quantity(container.resources.requests.get('cpu', '0'))
                            mem_req = parse_resource_quantity(container.resources.requests.get('memory', '0'))
                            allocated_cpu += cpu_req
                            allocated_memory += mem_req
                            pod_cpu += cpu_req
                            pod_memory += mem_req
                
                # 记录最大Pod
                if pod_cpu > largest_pod["cpu"]:
                    largest_pod = {
                        "name": f"{pod.metadata.namespace}/{pod.metadata.name}",
                        "cpu": pod_cpu,
                        "memory": pod_memory
                    }
        
        # 计算可用资源和利用率
        available_cpu = allocatable_cpu - allocated_cpu
        available_memory = allocatable_memory - allocated_memory
        available_pods = allocatable_pods - pod_count
        
        cpu_utilization = (allocated_cpu / allocatable_cpu * 100) if allocatable_cpu > 0 else 0
        memory_utilization = (allocated_memory / allocatable_memory * 100) if allocatable_memory > 0 else 0
        pods_utilization = (pod_count / allocatable_pods * 100) if allocatable_pods > 0 else 0
        
        result["resource_analysis"] = {
            "allocatable": {
                "cpu": round(allocatable_cpu, 3),
                "memory": allocatable_memory,
                "memory_human": format_bytes(allocatable_memory),
                "pods": allocatable_pods
            },
            "allocated": {
                "cpu": round(allocated_cpu, 3),
                "memory": allocated_memory,
                "memory_human": format_bytes(allocated_memory),
                "pods": pod_count
            },
            "available": {
                "cpu": round(available_cpu, 3),
                "memory": available_memory,
                "memory_human": format_bytes(available_memory),
                "pods": available_pods
            },
            "utilization_percent": {
                "cpu": round(cpu_utilization, 2),
                "memory": round(memory_utilization, 2),
                "pods": round(pods_utilization, 2)
            }
        }
        
        # 5. 资源碎片化分析
        fragmentation_risk = "low"
        if available_cpu > 0 and available_memory > 0:
            # 检查是否能容纳一个与最大Pod同等大小的Pod
            if largest_pod["cpu"] > 0:
                can_fit_largest = (
                    available_cpu >= largest_pod["cpu"] and
                    available_memory >= largest_pod["memory"]
                )
                
                if not can_fit_largest and cpu_utilization < 80:
                    fragmentation_risk = "high"
                    result["issues"].append({
                        "severity": "medium",
                        "category": "fragmentation",
                        "message": "资源碎片化：总资源充足但无法调度大Pod",
                        "details": f"可用CPU {available_cpu:.2f}核，但最大Pod需要{largest_pod['cpu']:.2f}核"
                    })
                    result["recommendations"].append("考虑重新调度Pod以减少资源碎片化")
                elif cpu_utilization > 60 and available_cpu < largest_pod["cpu"] * 0.5:
                    fragmentation_risk = "medium"
        
        result["resource_analysis"]["fragmentation_risk"] = fragmentation_risk
        
        # 6. Pod统计
        result["pod_summary"] = {
            "total_pods": pod_count,
            "by_phase": pods_by_phase,
            "largest_pod": largest_pod if largest_pod["cpu"] > 0 else None
        }
        
        # 7. Node信息
        if node.status.node_info:
            node_info = node.status.node_info
            result["node_info"] = {
                "os_image": node_info.os_image,
                "kernel_version": node_info.kernel_version,
                "container_runtime": node_info.container_runtime_version,
                "kubelet_version": node_info.kubelet_version,
                "kube_proxy_version": node_info.kube_proxy_version,
                "architecture": node_info.architecture
            }
        
        # 获取节点角色
        roles = []
        if node.metadata.labels:
            for label in node.metadata.labels:
                if label.startswith("node-role.kubernetes.io/"):
                    role = label.split("/", 1)[1]
                    if role:
                        roles.append(role)
        result["node_info"]["roles"] = roles or ["worker"]
        
        # 8. 资源使用预警
        if cpu_utilization > 90:
            result["issues"].append({
                "severity": "high",
                "category": "capacity",
                "message": f"CPU利用率过高: {cpu_utilization:.1f}%",
                "details": "节点接近CPU容量上限，可能影响调度"
            })
            result["recommendations"].append("考虑将部分Pod迁移到其他节点或添加新节点")
        elif cpu_utilization > 80:
            result["issues"].append({
                "severity": "medium",
                "category": "capacity",
                "message": f"CPU利用率较高: {cpu_utilization:.1f}%",
                "details": "建议监控节点负载"
            })
        
        if memory_utilization > 90:
            result["issues"].append({
                "severity": "high",
                "category": "capacity",
                "message": f"内存利用率过高: {memory_utilization:.1f}%",
                "details": "节点接近内存容量上限，可能触发OOM"
            })
            result["recommendations"].append("考虑将部分Pod迁移到其他节点或添加新节点")
        elif memory_utilization > 80:
            result["issues"].append({
                "severity": "medium",
                "category": "capacity",
                "message": f"内存利用率较高: {memory_utilization:.1f}%",
                "details": "建议监控节点内存使用"
            })
        
        if available_pods < 10:
            result["issues"].append({
                "severity": "medium",
                "category": "capacity",
                "message": f"Pod容量即将耗尽: 剩余{available_pods}个",
                "details": "节点即将达到最大Pod数量限制"
            })
        
        # 9. 确定整体健康状态
        if len(critical_conditions) > 0 or not is_ready:
            result["health_status"] = "critical"
            result["diagnosis_summary"] = f"节点处于Critical状态: {'; '.join(critical_conditions)}"
        elif len([i for i in result["issues"] if i["severity"] in ["high", "critical"]]) > 0:
            result["health_status"] = "warning"
            high_issues = [i["message"] for i in result["issues"] if i["severity"] == "high"]
            result["diagnosis_summary"] = f"节点有{len(high_issues)}个高优先级问题: {'; '.join(high_issues[:2])}"
        else:
            result["health_status"] = "healthy"
            result["diagnosis_summary"] = f"节点健康，CPU利用率{cpu_utilization:.1f}%，内存利用率{memory_utilization:.1f}%"
        
        # 10. 默认建议
        if len(result["recommendations"]) == 0:
            result["recommendations"].append("节点运行正常，继续监控资源使用情况")
        
        logger.info(f"Node诊断完成: {node_name}, 状态: {result['health_status']}")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"诊断Node失败: {node_name}, 错误: {str(e)}")
        return json.dumps({
            "error": f"诊断Node失败: {str(e)}",
            "node_name": node_name
        })
