"""Kubernetes链路追踪和关联分析工具"""
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from kubernetes import client
from loguru import logger
from neco.llm.tools.kubernetes.utils import prepare_context


@tool()
def trace_service_chain(service_name, namespace, config: RunnableConfig = None):
    """
    追踪Service调用链，从Service → Endpoint → Pod，定位流量异常
    
    **何时使用此工具：**
    - 排查应用访问异常和流量路由问题时
    - 验证Service与后端Pod的关联关系
    - 诊断服务发现或负载均衡层面的故障
    - 分析Endpoint健康状态和流量分发逻辑
    
    **工具能力：**
    - 检查Service配置（type、ClusterIP、selector、ports）
    - 验证Endpoints是否有就绪的后端Pod
    - 检查Pod健康状态（Running、Ready、容器状态）
    - 发现Ingress规则配置（如果有）
    - 识别链路中的断点和配置错误
    - 输出每一跳的健康状态和问题原因
    
    Args:
        service_name (str): Service名称（必填）
        namespace (str): 命名空间（必填）
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含以下关键字段：
        - chain: {service, endpoints, pods, ingress}各组件的详细状态
        - issues: 发现的问题列表，包含severity（critical/high/medium）
        - recommendations: 针对性的修复建议
        - health_status: 整体健康状态（healthy/degraded/critical）
        - summary: 一句话诊断结论
    
    **配合其他工具使用：**
    - 如果发现Pod问题 → 使用 diagnose_kubernetes_pod_issues 深入诊断
    - 如果需要查看Pod日志 → 使用 get_kubernetes_pod_logs 获取日志
    - 如果需要重启Pod → 使用 restart_pod 执行重启操作
    
    **注意事项：**
    - 此工具只检查配置和状态，不检查网络策略和DNS
    - 如需网络诊断，配合 check_network_policies_blocking 使用
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        networking_v1 = client.NetworkingV1Api()
        
        logger.info(f"开始追踪服务链路: {namespace}/{service_name}")
        
        result = {
            "service_name": service_name,
            "namespace": namespace,
            "trace_time": datetime.now(timezone.utc).isoformat(),
            "chain": {},
            "issues": [],
            "recommendations": []
        }
        
        # 1. 检查Service本身
        try:
            service = core_v1.read_namespaced_service(service_name, namespace)
            service_info = {
                "exists": True,
                "type": service.spec.type,
                "cluster_ip": service.spec.cluster_ip,
                "ports": [
                    {
                        "name": port.name,
                        "port": port.port,
                        "target_port": str(port.target_port),
                        "protocol": port.protocol
                    } for port in (service.spec.ports or [])
                ],
                "selector": service.spec.selector or {}
            }
            result["chain"]["service"] = service_info
            
            if not service.spec.selector:
                result["issues"].append({
                    "severity": "high",
                    "component": "service",
                    "message": "Service没有配置selector，无法路由到任何Pod"
                })
        except ApiException as e:
            if e.status == 404:
                result["chain"]["service"] = {"exists": False}
                result["issues"].append({
                    "severity": "critical",
                    "component": "service",
                    "message": f"Service不存在: {service_name}"
                })
                return json.dumps(result)
            raise
        
        # 2. 检查Endpoints
        try:
            endpoints = core_v1.read_namespaced_endpoints(service_name, namespace)
            ready_addresses = []
            not_ready_addresses = []
            
            if endpoints.subsets:
                for subset in endpoints.subsets:
                    if subset.addresses:
                        for addr in subset.addresses:
                            ready_addresses.append({
                                "ip": addr.ip,
                                "target_ref": f"{addr.target_ref.kind}/{addr.target_ref.name}" if addr.target_ref else None
                            })
                    if subset.not_ready_addresses:
                        for addr in subset.not_ready_addresses:
                            not_ready_addresses.append({
                                "ip": addr.ip,
                                "target_ref": f"{addr.target_ref.kind}/{addr.target_ref.name}" if addr.target_ref else None
                            })
            
            endpoints_info = {
                "exists": True,
                "ready_addresses": ready_addresses,
                "not_ready_addresses": not_ready_addresses,
                "ready_count": len(ready_addresses),
                "not_ready_count": len(not_ready_addresses)
            }
            result["chain"]["endpoints"] = endpoints_info
            
            if len(ready_addresses) == 0:
                result["issues"].append({
                    "severity": "critical",
                    "component": "endpoints",
                    "message": "没有就绪的Endpoint，Service无法转发流量"
                })
                if len(not_ready_addresses) > 0:
                    result["recommendations"].append(
                        "有未就绪的Endpoint，请检查Pod的就绪探针配置和Pod健康状态"
                    )
            
        except ApiException as e:
            if e.status == 404:
                result["chain"]["endpoints"] = {"exists": False}
                result["issues"].append({
                    "severity": "critical",
                    "component": "endpoints",
                    "message": "Endpoints不存在，可能是selector不匹配"
                })
        
        # 3. 检查匹配的Pod
        if service.spec.selector:
            label_selector = ",".join([f"{k}={v}" for k, v in service.spec.selector.items()])
            pods = core_v1.list_namespaced_pod(namespace, label_selector=label_selector)
            
            pod_list = []
            for pod in pods.items:
                container_statuses = []
                if pod.status.container_statuses:
                    for container in pod.status.container_statuses:
                        container_statuses.append({
                            "name": container.name,
                            "ready": container.ready,
                            "restart_count": container.restart_count
                        })
                
                pod_info = {
                    "name": pod.metadata.name,
                    "phase": pod.status.phase,
                    "pod_ip": pod.status.pod_ip,
                    "node": pod.spec.node_name,
                    "containers": container_statuses
                }
                pod_list.append(pod_info)
                
                # 检查Pod问题
                if pod.status.phase != "Running":
                    result["issues"].append({
                        "severity": "high",
                        "component": "pod",
                        "message": f"Pod {pod.metadata.name} 状态异常: {pod.status.phase}"
                    })
                
                # 检查容器就绪状态
                if pod.status.container_statuses:
                    for container in pod.status.container_statuses:
                        if not container.ready:
                            result["issues"].append({
                                "severity": "medium",
                                "component": "pod",
                                "message": f"Pod {pod.metadata.name} 的容器 {container.name} 未就绪"
                            })
            
            result["chain"]["pods"] = {
                "count": len(pod_list),
                "pods": pod_list
            }
            
            if len(pod_list) == 0:
                result["issues"].append({
                    "severity": "critical",
                    "component": "pods",
                    "message": f"没有匹配selector的Pod: {service.spec.selector}"
                })
                result["recommendations"].append(
                    "请检查Deployment/StatefulSet的Pod模板标签是否与Service的selector匹配"
                )
        
        # 4. 检查Ingress (如果有)
        try:
            ingresses = networking_v1.list_namespaced_ingress(namespace)
            matching_ingresses = []
            
            for ingress in ingresses.items:
                if ingress.spec.rules:
                    for rule in ingress.spec.rules:
                        if rule.http and rule.http.paths:
                            for path in rule.http.paths:
                                if (path.backend and path.backend.service and 
                                    path.backend.service.name == service_name):
                                    matching_ingresses.append({
                                        "name": ingress.metadata.name,
                                        "host": rule.host or "*",
                                        "path": path.path,
                                        "path_type": path.path_type
                                    })
            
            if matching_ingresses:
                result["chain"]["ingress"] = {
                    "exists": True,
                    "ingresses": matching_ingresses
                }
            else:
                result["chain"]["ingress"] = {
                    "exists": False,
                    "message": "没有Ingress指向此Service"
                }
        except ApiException:
            # Ingress API可能不可用
            result["chain"]["ingress"] = {"exists": False, "message": "无法检查Ingress"}
        
        # 5. 生成总体健康评估
        if len(result["issues"]) == 0:
            result["health_status"] = "healthy"
            result["summary"] = "服务链路完整，所有组件正常"
        else:
            critical_issues = [i for i in result["issues"] if i["severity"] == "critical"]
            if critical_issues:
                result["health_status"] = "critical"
                result["summary"] = "服务链路存在严重问题，服务不可用"
            else:
                result["health_status"] = "degraded"
                result["summary"] = "服务链路存在问题，可能影响服务质量"
        
        logger.info(f"服务链路追踪完成: {namespace}/{service_name}, 状态: {result['health_status']}")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"追踪服务链路失败: {namespace}/{service_name}, 错误: {str(e)}")
        return json.dumps({
            "error": f"追踪服务链路失败: {str(e)}",
            "service_name": service_name,
            "namespace": namespace
        })


@tool()
def get_resource_events_timeline(resource_type, resource_name, namespace, hours=24, config: RunnableConfig = None):
    """
    获取资源的事件时间线，追溯问题演变过程
    
    **何时使用此工具：**
    - 回溯资源的历史状态变化和事件序列
    - 分析间歇性或周期性发生的故障模式
    - 确定问题首次出现的时间点和触发条件
    - 为根因分析提供时间维度的事件上下文
    
    **工具能力：**
    - 按时间顺序展示所有Kubernetes事件
    - 过滤指定时间范围内的事件（默认24小时）
    - 区分事件类型（Normal/Warning/Error）
    - 统计事件发生次数和频率
    - 显示事件的首次和最后发生时间
    
    Args:
        resource_type (str): 资源类型（必填），如 Pod、Deployment、Service、Node
        resource_name (str): 资源名称（必填）
        namespace (str): 命名空间（必填）
        hours (int, optional): 查询时间范围（小时），默认24
            - 24: 查看最近一天的事件（常规故障）
            - 1: 只看最近一小时（快速定位刚发生的问题）
            - 168: 查看一周内的事件（分析长期趋势）
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - timeline[]: 事件列表，按时间排序
          - timestamp: 事件时间
          - type: Normal/Warning/Error
          - reason: 事件原因
          - message: 详细消息
          - count: 发生次数
        - event_summary: 各类型事件的统计
        - total_events: 事件总数
    
    **配合其他工具使用：**
    - 发现大量重启事件 → 使用 analyze_pod_restart_pattern 分析原因
    - 发现OOM事件 → 使用 check_oom_events 专项检查
    - 发现调度失败 → 使用 diagnose_pending_pod_issues 诊断
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        logger.info(f"获取资源事件时间线: {namespace}/{resource_type}/{resource_name}, 时间范围: {hours}小时")
        
        # 获取所有相关事件
        field_selector = f"involvedObject.name={resource_name},involvedObject.kind={resource_type}"
        events = core_v1.list_namespaced_event(
            namespace,
            field_selector=field_selector
        )
        
        # 计算时间过滤
        now = datetime.now(timezone.utc)
        cutoff_time = now.timestamp() - (hours * 3600)
        
        # 整理事件
        timeline = []
        for event in events.items:
            event_time = event.last_timestamp or event.first_timestamp or event.metadata.creation_timestamp
            if event_time and event_time.timestamp() >= cutoff_time:
                timeline.append({
                    "timestamp": event_time.isoformat(),
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "count": event.count or 1,
                    "first_seen": event.first_timestamp.isoformat() if event.first_timestamp else None,
                    "last_seen": event.last_timestamp.isoformat() if event.last_timestamp else None,
                    "source": event.source.component if event.source else None
                })
        
        # 按时间排序
        timeline.sort(key=lambda x: x["timestamp"])
        
        # 统计事件类型
        event_summary = {
            "Normal": 0,
            "Warning": 0,
            "Error": 0
        }
        for event in timeline:
            event_type = event["type"]
            if event_type in event_summary:
                event_summary[event_type] += event["count"]
        
        result = {
            "resource_type": resource_type,
            "resource_name": resource_name,
            "namespace": namespace,
            "time_range_hours": hours,
            "total_events": len(timeline),
            "event_summary": event_summary,
            "timeline": timeline
        }
        
        logger.info(f"事件时间线获取完成: {len(timeline)}个事件")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except ApiException as e:
        logger.error(f"获取事件时间线失败: {str(e)}")
        return json.dumps({
            "error": f"获取事件时间线失败: {str(e)}",
            "resource_type": resource_type,
            "resource_name": resource_name,
            "namespace": namespace
        })


@tool()
def analyze_pod_restart_pattern(namespace=None, min_restarts=3, config: RunnableConfig = None):
    """
    深度分析Pod重启模式，定位根本原因
    
    **何时使用此工具：**
    - 分析Pod重启的根本原因和触发模式
    - 区分不同退出码对应的故障类型（OOM、信号终止、异常退出等）
    - 识别重启的时间规律和集中性特征
    - 评估重启对服务稳定性的影响范围
    
    **工具能力：**
    - 分析容器退出码含义（137=OOMKilled、143=SIGTERM、1=Error等）
    - 识别CrashLoopBackOff重启模式
    - 关联最近的事件（BackOff、Killing、Unhealthy）
    - 区分OOM、应用错误、健康检查失败等不同原因
    - 提供针对性修复建议（增加内存、检查启动命令、调整探针等）
    - 按重启次数排序，优先展示最严重的问题
    
    **与get_high_restart_kubernetes_pods的区别：**
    - get_high_restart_pods: 只列出重启次数高的Pod
    - analyze_pod_restart_pattern: 深度分析每个容器的重启原因和退出码
    
    Args:
        namespace (str, optional): 命名空间，None=所有命名空间
            - None: 全局扫描，发现所有问题Pod
            - "prod": 只检查生产环境
        min_restarts (int, optional): 最小重启阈值，默认3
            - 3: 找出所有有重启迹象的Pod（推荐）
            - 5: 只关注重启较多的Pod
            - 10: 只看严重频繁重启的Pod
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - analysis[]: 每个问题容器的详细分析
          - restart_count: 重启次数
          - restart_reasons[]: 推断的原因列表
          - last_state: 上次终止状态（exit_code、reason、message）
          - current_state: 当前状态
          - severity: critical/high/medium
          - recommendations[]: 修复建议
          - recent_events[]: 最近相关事件
        - total_problematic_containers: 问题容器总数
    
    **配合其他工具使用：**
    - 发现OOM原因 → 使用 check_oom_events 获取集群级OOM概况
    - 查看完整时间线 → 使用 get_resource_events_timeline
    - 查看容器日志 → 使用 get_kubernetes_pod_logs
    - 需要重启Pod → 使用 restart_pod
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        logger.info(f"开始分析Pod重启模式, namespace={namespace}, min_restarts={min_restarts}")
        
        # 获取Pod列表
        if namespace:
            pods = core_v1.list_namespaced_pod(namespace)
        else:
            pods = core_v1.list_pod_for_all_namespaces()
        
        restart_analysis = []
        
        for pod in pods.items:
            if not pod.status.container_statuses:
                continue
            
            # 分析每个容器的重启情况
            for container in pod.status.container_statuses:
                if container.restart_count >= min_restarts:
                    analysis = {
                        "pod_name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "container_name": container.name,
                        "restart_count": container.restart_count,
                        "current_state": {},
                        "last_state": {},
                        "restart_reasons": [],
                        "severity": "unknown"
                    }
                    
                    # 分析当前状态
                    if container.state.waiting:
                        analysis["current_state"] = {
                            "status": "waiting",
                            "reason": container.state.waiting.reason,
                            "message": container.state.waiting.message
                        }
                        if container.state.waiting.reason == "CrashLoopBackOff":
                            analysis["severity"] = "critical"
                            analysis["restart_reasons"].append("容器持续崩溃")
                    elif container.state.running:
                        analysis["current_state"] = {
                            "status": "running",
                            "started_at": container.state.running.started_at.isoformat() if container.state.running.started_at else None
                        }
                    elif container.state.terminated:
                        analysis["current_state"] = {
                            "status": "terminated",
                            "reason": container.state.terminated.reason,
                            "exit_code": container.state.terminated.exit_code,
                            "message": container.state.terminated.message
                        }
                    
                    # 分析上一次状态（重启原因）
                    if container.last_state and container.last_state.terminated:
                        last_term = container.last_state.terminated
                        analysis["last_state"] = {
                            "reason": last_term.reason,
                            "exit_code": last_term.exit_code,
                            "started_at": last_term.started_at.isoformat() if last_term.started_at else None,
                            "finished_at": last_term.finished_at.isoformat() if last_term.finished_at else None,
                            "message": last_term.message
                        }
                        
                        # 根据退出码判断原因
                        exit_code = last_term.exit_code
                        if exit_code == 137:
                            analysis["restart_reasons"].append("OOMKilled - 内存超限被杀死")
                            analysis["severity"] = "high"
                        elif exit_code == 143:
                            analysis["restart_reasons"].append("SIGTERM - 被正常终止信号杀死")
                            analysis["severity"] = "medium"
                        elif exit_code == 1:
                            analysis["restart_reasons"].append("应用程序错误退出")
                            analysis["severity"] = "high"
                        elif exit_code != 0:
                            analysis["restart_reasons"].append(f"异常退出码: {exit_code}")
                            analysis["severity"] = "high"
                        
                        if last_term.reason == "OOMKilled":
                            analysis["restart_reasons"].append("内存不足（OOM）")
                            analysis["severity"] = "high"
                        elif last_term.reason == "Error":
                            analysis["restart_reasons"].append("容器运行错误")
                            analysis["severity"] = "high"
                    
                    # 获取相关事件
                    try:
                        events = core_v1.list_namespaced_event(
                            pod.metadata.namespace,
                            field_selector=f"involvedObject.name={pod.metadata.name},involvedObject.kind=Pod"
                        )
                        
                        recent_events = []
                        for event in events.items:
                            if event.reason in ["BackOff", "Failed", "Killing", "Unhealthy"]:
                                recent_events.append({
                                    "reason": event.reason,
                                    "message": event.message,
                                    "count": event.count
                                })
                        
                        if recent_events:
                            analysis["recent_events"] = recent_events[:5]  # 最近5个相关事件
                    except Exception:
                        pass
                    
                    # 生成建议
                    recommendations = []
                    if "OOMKilled" in str(analysis.get("last_state", {})):
                        recommendations.append("增加容器的memory limits和requests")
                        recommendations.append("检查应用是否存在内存泄漏")
                    if analysis["current_state"].get("reason") == "CrashLoopBackOff":
                        recommendations.append("检查容器启动命令和参数")
                        recommendations.append("查看Pod日志分析崩溃原因")
                    if container.restart_count > 10:
                        recommendations.append("重启次数过多，建议深入排查根本原因")
                    
                    analysis["recommendations"] = recommendations
                    restart_analysis.append(analysis)
        
        # 按重启次数排序
        restart_analysis.sort(key=lambda x: x["restart_count"], reverse=True)
        
        result = {
            "analysis_time": datetime.now(timezone.utc).isoformat(),
            "namespace": namespace or "all",
            "min_restarts_threshold": min_restarts,
            "total_problematic_containers": len(restart_analysis),
            "analysis": restart_analysis
        }
        
        logger.info(f"Pod重启分析完成: 发现{len(restart_analysis)}个问题容器")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"分析Pod重启模式失败: {str(e)}")
        return json.dumps({
            "error": f"分析Pod重启模式失败: {str(e)}",
            "namespace": namespace
        })


@tool()
def check_oom_events(namespace=None, hours=24, config: RunnableConfig = None):
    """
    检查OOM（Out of Memory）事件，识别内存配置问题
    
    **何时使用此工具：**
    - 诊断容器因内存不足被终止的问题
    - 评估内存配置（requests/limits）的合理性
    - 分析内存使用模式和泄漏风险
    - 识别OOM事件的发生频率和规律
    
    **工具能力：**
    - 检测所有OOM相关事件（OOMKilling、FailedKillPod）
    - 列出当前有OOM历史的Pod
    - 展示每个Pod的内存limits和requests配置
    - 统计OOM事件发生频率和时间
    - 提供内存优化建议（增加limits、检查泄漏、使用VPA等）
    
    Args:
        namespace (str, optional): 命名空间，None=所有命名空间
            - None: 全局扫描，发现所有OOM问题
            - "prod": 只检查生产环境的OOM
        hours (int, optional): 查询时间范围（小时），默认24
            - 24: 查看最近一天的OOM（常规检查）
            - 1: 只看最近一小时（快速定位刚发生的OOM）
            - 168: 查看一周内的OOM（分析长期趋势）
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - oom_events[]: OOM事件列表（按时间倒序）
          - timestamp: 发生时间
          - pod_name: Pod名称
          - namespace: 命名空间
          - reason: 事件原因
          - count: 发生次数
        - oom_pods[]: 有OOM历史的Pod
          - memory_limit: 内存限制
          - memory_request: 内存请求
          - restart_count: 重启次数
          - last_oom_time: 最后OOM时间
        - recommendations[]: 优化建议
        - total_oom_events: OOM事件总数
        - total_oom_pods: OOM Pod总数
    
    **配合其他工具使用：**
    - 分析具体Pod的重启原因 → 使用 analyze_pod_restart_pattern
    - 查看Pod资源使用详情 → 使用 diagnose_kubernetes_pod_issues
    - 查看容器日志分析内存泄漏 → 使用 get_kubernetes_pod_logs
    
    **注意事项：**
    - OOM通常表示内存配置不足，但也可能是应用内存泄漏
    - 建议结合日志分析，排查是否真实需要这么多内存
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        logger.info(f"检查OOM事件, namespace={namespace}, hours={hours}")
        
        # 获取事件
        if namespace:
            events = core_v1.list_namespaced_event(namespace)
        else:
            events = core_v1.list_event_for_all_namespaces()
        
        # 过滤OOM相关事件
        now = datetime.now(timezone.utc)
        cutoff_time = now.timestamp() - (hours * 3600)
        
        oom_events = []
        for event in events.items:
            # 检查OOM相关的reason
            if event.reason in ["OOMKilling", "FailedKillPod"] or "OOM" in (event.message or ""):
                event_time = event.last_timestamp or event.first_timestamp or event.metadata.creation_timestamp
                if event_time and event_time.timestamp() >= cutoff_time:
                    oom_events.append({
                        "timestamp": event_time.isoformat(),
                        "namespace": event.metadata.namespace,
                        "pod_name": event.involved_object.name if event.involved_object else None,
                        "reason": event.reason,
                        "message": event.message,
                        "count": event.count or 1
                    })
        
        # 获取当前有OOM历史的Pod
        oom_pods = []
        if namespace:
            pods = core_v1.list_namespaced_pod(namespace)
        else:
            pods = core_v1.list_pod_for_all_namespaces()
        
        for pod in pods.items:
            if pod.status.container_statuses:
                for container in pod.status.container_statuses:
                    # 检查上次终止状态
                    if (container.last_state and 
                        container.last_state.terminated and 
                        container.last_state.terminated.reason == "OOMKilled"):
                        
                        # 获取资源配置
                        container_spec = None
                        for c in pod.spec.containers:
                            if c.name == container.name:
                                container_spec = c
                                break
                        
                        memory_limit = "未设置"
                        memory_request = "未设置"
                        if container_spec and container_spec.resources:
                            if container_spec.resources.limits:
                                memory_limit = container_spec.resources.limits.get("memory", "未设置")
                            if container_spec.resources.requests:
                                memory_request = container_spec.resources.requests.get("memory", "未设置")
                        
                        oom_pods.append({
                            "pod_name": pod.metadata.name,
                            "namespace": pod.metadata.namespace,
                            "container_name": container.name,
                            "restart_count": container.restart_count,
                            "memory_limit": memory_limit,
                            "memory_request": memory_request,
                            "last_oom_time": container.last_state.terminated.finished_at.isoformat() if container.last_state.terminated.finished_at else None,
                            "exit_code": container.last_state.terminated.exit_code
                        })
        
        # 生成建议
        recommendations = []
        if len(oom_pods) > 0:
            recommendations.append("发现OOM事件，建议检查以下方面：")
            recommendations.append("1. 增加容器的memory limits配置")
            recommendations.append("2. 检查应用是否存在内存泄漏")
            recommendations.append("3. 优化应用的内存使用")
            recommendations.append("4. 考虑使用VPA（Vertical Pod Autoscaler）自动调整资源")
        
        result = {
            "check_time": datetime.now(timezone.utc).isoformat(),
            "time_range_hours": hours,
            "namespace": namespace or "all",
            "total_oom_events": len(oom_events),
            "total_oom_pods": len(oom_pods),
            "oom_events": sorted(oom_events, key=lambda x: x["timestamp"], reverse=True),
            "oom_pods": oom_pods,
            "recommendations": recommendations
        }
        
        logger.info(f"OOM检查完成: {len(oom_events)}个事件, {len(oom_pods)}个Pod")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"检查OOM事件失败: {str(e)}")
        return json.dumps({
            "error": f"检查OOM事件失败: {str(e)}",
            "namespace": namespace
        })
