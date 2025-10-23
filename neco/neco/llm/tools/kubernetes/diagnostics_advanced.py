"""Kubernetes高级诊断工具 - P0高频缺失场景"""
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from kubernetes import client
from loguru import logger
from neco.llm.tools.kubernetes.utils import prepare_context, parse_resource_quantity


@tool()
def diagnose_pending_pod_issues(pod_name, namespace, config: RunnableConfig = None):
    """
    诊断Pod Pending调度失败的根本原因
    
    **何时使用此工具：**
    - 排查Pod长时间处于Pending状态的原因
    - 诊断扩容后新Pod无法成功调度的问题
    - 分析调度失败是由资源、亲和性、污点还是其他因素导致
    - 为调度问题提供具体的根因和解决方案
    
    **工具能力：**
    - 检查节点资源是否充足（CPU/Memory/Pod数）
    - 检查节点亲和性（NodeAffinity）是否过于严格
    - 检查污点（Taint）与容忍度（Toleration）是否匹配
    - 检查PVC绑定状态（PersistentVolume是否可用）
    - 检查镜像拉取状态（ImagePullBackOff、ErrImagePull）
    - 分析调度器事件，识别具体失败原因
    - 提供针对性解决方案
    
    Args:
        pod_name (str): Pod名称（必填）
        namespace (str): 命名空间（必填）
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - pod_name: Pod名称
        - phase: Pod当前状态
        - pending_reason: Pending的主要原因
        - issues[]: 发现的问题列表
          - category: 问题类别（resource/affinity/taint/pvc/image）
          - severity: critical/high/medium
          - message: 问题描述
          - details: 详细信息
        - node_candidates: 符合条件的候选节点信息
        - recommendations[]: 解决建议
        - diagnosis_summary: 一句话诊断结论
    
    **配合其他工具使用：**
    - 如果是资源不足 → 使用 check_scaling_capacity 查看集群容量
    - 如果是PVC问题 → 使用 check_pvc_capacity 检查存储
    - 如果需要查看详细事件 → 使用 get_resource_events_timeline
    
    **常见Pending原因：**
    1. 资源不足：没有节点有足够的CPU/内存
    2. 节点亲和性：NodeSelector或NodeAffinity过于严格
    3. 污点容忍：节点有Taint但Pod没有Toleration
    4. PVC未绑定：PersistentVolumeClaim等待PV
    5. 镜像拉取失败：ImagePullBackOff
    6. 端口冲突：hostPort已被占用
    
    **注意事项：**
    - 此工具只诊断Pending Pod，对于Running/Failed Pod请使用其他工具
    - 诊断结果基于当前集群状态，添加节点后可能变化
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        logger.info(f"开始诊断Pending Pod: {namespace}/{pod_name}")
        
        # 获取Pod详情
        try:
            pod = core_v1.read_namespaced_pod(pod_name, namespace)
        except ApiException as e:
            if e.status == 404:
                return json.dumps({
                    "error": f"Pod不存在: {namespace}/{pod_name}"
                })
            raise
        
        result = {
            "pod_name": pod_name,
            "namespace": namespace,
            "phase": pod.status.phase,
            "pending_reason": None,
            "issues": [],
            "node_candidates": [],
            "recommendations": [],
            "diagnosis_summary": ""
        }
        
        # 检查Pod是否真的是Pending
        if pod.status.phase != "Pending":
            result["diagnosis_summary"] = f"Pod当前状态为{pod.status.phase}，不是Pending"
            return json.dumps(result, ensure_ascii=False, indent=2)
        
        # 1. 分析Pod Conditions
        if pod.status.conditions:
            for condition in pod.status.conditions:
                if condition.type == "PodScheduled" and condition.status == "False":
                    result["pending_reason"] = condition.reason
                    if condition.message:
                        result["issues"].append({
                            "category": "scheduling",
                            "severity": "critical",
                            "message": f"调度失败: {condition.reason}",
                            "details": condition.message
                        })
        
        # 2. 检查资源需求
        resource_requests = {"cpu": 0, "memory": 0}
        if pod.spec.containers:
            for container in pod.spec.containers:
                if container.resources and container.resources.requests:
                    cpu_req = parse_resource_quantity(container.resources.requests.get('cpu', '0'))
                    mem_req = parse_resource_quantity(container.resources.requests.get('memory', '0'))
                    resource_requests["cpu"] += cpu_req
                    resource_requests["memory"] += mem_req
        
        # 3. 检查节点资源可用性
        nodes = core_v1.list_node()
        pods_all = core_v1.list_pod_for_all_namespaces()
        
        # 按节点统计资源使用
        node_resources = {}
        for node in nodes.items:
            if node.spec.unschedulable:
                continue
            
            node_name = node.metadata.name
            allocatable = node.status.allocatable or {}
            allocatable_cpu = parse_resource_quantity(allocatable.get('cpu', '0'))
            allocatable_memory = parse_resource_quantity(allocatable.get('memory', '0'))
            allocatable_pods = int(allocatable.get('pods', '110'))
            
            # 计算已使用
            used_cpu = 0
            used_memory = 0
            used_pods = 0
            
            for p in pods_all.items:
                if p.spec.node_name == node_name and p.status.phase in ["Running", "Pending"]:
                    if p.metadata.uid == pod.metadata.uid:
                        continue  # 排除当前Pod
                    used_pods += 1
                    if p.spec.containers:
                        for c in p.spec.containers:
                            if c.resources and c.resources.requests:
                                used_cpu += parse_resource_quantity(c.resources.requests.get('cpu', '0'))
                                used_memory += parse_resource_quantity(c.resources.requests.get('memory', '0'))
            
            available_cpu = allocatable_cpu - used_cpu
            available_memory = allocatable_memory - used_memory
            available_pods = allocatable_pods - used_pods
            
            node_resources[node_name] = {
                "available_cpu": available_cpu,
                "available_memory": available_memory,
                "available_pods": available_pods,
                "can_fit": (
                    available_cpu >= resource_requests["cpu"] and
                    available_memory >= resource_requests["memory"] and
                    available_pods >= 1
                )
            }
        
        # 检查是否有节点能满足资源需求
        candidates_by_resource = [n for n, r in node_resources.items() if r["can_fit"]]
        
        if not candidates_by_resource:
            result["issues"].append({
                "category": "resource",
                "severity": "critical",
                "message": "没有节点有足够资源",
                "details": f"需要CPU: {resource_requests['cpu']:.2f}核, 内存: {resource_requests['memory']/(1024**3):.2f}Gi"
            })
            result["recommendations"].append("增加集群节点或减少Pod的资源requests")
        
        # 4. 检查节点亲和性
        if pod.spec.node_selector:
            result["issues"].append({
                "category": "affinity",
                "severity": "high",
                "message": "配置了NodeSelector",
                "details": f"NodeSelector: {pod.spec.node_selector}"
            })
            
            # 检查有多少节点匹配selector
            matching_nodes = 0
            for node in nodes.items:
                labels = node.metadata.labels or {}
                if all(labels.get(k) == v for k, v in pod.spec.node_selector.items()):
                    matching_nodes += 1
            
            if matching_nodes == 0:
                result["recommendations"].append("NodeSelector过于严格，没有节点匹配。请检查节点标签或放宽selector")
        
        # 5. 检查污点与容忍度
        taints_blocking = []
        for node in nodes.items:
            if not node.spec.taints:
                continue
            
            node_name = node.metadata.name
            for taint in node.spec.taints:
                # 检查Pod是否有对应的Toleration
                tolerated = False
                if pod.spec.tolerations:
                    for toleration in pod.spec.tolerations:
                        if (toleration.key == taint.key and
                            (not toleration.value or toleration.value == taint.value) and
                            (not toleration.effect or toleration.effect == taint.effect)):
                            tolerated = True
                            break
                
                if not tolerated and taint.effect in ["NoSchedule", "NoExecute"]:
                    taints_blocking.append({
                        "node": node_name,
                        "taint": f"{taint.key}={taint.value}:{taint.effect}"
                    })
        
        if taints_blocking:
            result["issues"].append({
                "category": "taint",
                "severity": "high",
                "message": "节点污点阻止调度",
                "details": f"有{len(taints_blocking)}个节点的污点无法容忍"
            })
            result["recommendations"].append("为Pod添加Toleration或移除节点污点")
        
        # 6. 检查PVC绑定
        if pod.spec.volumes:
            for volume in pod.spec.volumes:
                if volume.persistent_volume_claim:
                    pvc_name = volume.persistent_volume_claim.claim_name
                    try:
                        pvc = core_v1.read_namespaced_persistent_volume_claim(pvc_name, namespace)
                        if pvc.status.phase != "Bound":
                            result["issues"].append({
                                "category": "pvc",
                                "severity": "critical",
                                "message": f"PVC未绑定: {pvc_name}",
                                "details": f"PVC状态: {pvc.status.phase}"
                            })
                            result["recommendations"].append(f"检查PVC {pvc_name} 是否有可用的PV")
                    except ApiException:
                        result["issues"].append({
                            "category": "pvc",
                            "severity": "critical",
                            "message": f"PVC不存在: {pvc_name}",
                            "details": "Pod引用了不存在的PVC"
                        })
        
        # 7. 检查镜像拉取
        if pod.status.container_statuses:
            for container in pod.status.container_statuses:
                if container.state.waiting:
                    reason = container.state.waiting.reason
                    if reason in ["ImagePullBackOff", "ErrImagePull"]:
                        result["issues"].append({
                            "category": "image",
                            "severity": "critical",
                            "message": f"镜像拉取失败: {container.name}",
                            "details": container.state.waiting.message or reason
                        })
                        result["recommendations"].append(
                            f"检查镜像地址是否正确、镜像仓库凭据是否配置、网络是否可达"
                        )
        
        # 8. 生成诊断总结
        if len(result["issues"]) == 0:
            result["diagnosis_summary"] = "Pod Pending但未发现明显问题，可能是调度器延迟"
        else:
            critical_issues = [i for i in result["issues"] if i["severity"] == "critical"]
            if critical_issues:
                result["diagnosis_summary"] = f"发现{len(critical_issues)}个严重问题阻止Pod调度"
            else:
                result["diagnosis_summary"] = f"发现{len(result['issues'])}个问题影响Pod调度"
        
        logger.info(f"Pending Pod诊断完成: {result['diagnosis_summary']}")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"诊断Pending Pod失败: {str(e)}")
        return json.dumps({
            "error": f"诊断失败: {str(e)}",
            "pod_name": pod_name,
            "namespace": namespace
        })


@tool()
def check_network_policies_blocking(source_namespace, source_pod=None, target_namespace=None, target_service=None, config: RunnableConfig = None):
    """
    检查NetworkPolicy是否阻断流量
    
    **何时使用此工具：**
    - 排查服务间网络连通性问题
    - Service和Pod配置正常但仍无法访问时
    - 诊断跨命名空间通信失败的原因
    - 验证网络策略配置的正确性
    
    **工具能力：**
    - 检查源命名空间的Egress策略（出站规则）
    - 检查目标命名空间的Ingress策略（入站规则）
    - 分析Pod标签是否匹配NetworkPolicy选择器
    - 识别是否有默认deny规则
    - 提供网络策略配置建议
    
    Args:
        source_namespace (str): 源命名空间（必填）
        source_pod (str, optional): 源Pod名称，用于精确匹配Pod标签
        target_namespace (str, optional): 目标命名空间
        target_service (str, optional): 目标Service名称
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - source_policies[]: 源命名空间的NetworkPolicy列表
        - target_policies[]: 目标命名空间的NetworkPolicy列表
        - egress_blocked: 出站是否被阻断（bool）
        - ingress_blocked: 入站是否被阻断（bool）
        - blocking_policies[]: 阻断流量的策略列表
        - recommendations[]: 配置建议
        - diagnosis_summary: 诊断结论
    
    **配合其他工具使用：**
    - 先用 trace_service_chain 确认Service/Pod配置正常
    - 再用此工具检查网络策略
    - 如果DNS问题，需要检查CoreDNS状态（超出此工具范围）
    
    **注意事项：**
    - 如果集群未使用NetworkPolicy，此工具返回无阻断
    - NetworkPolicy默认是白名单模式（存在策略后默认deny）
    - 跨命名空间通信需要Egress和Ingress双向放行
    """
    prepare_context(config)
    
    try:
        networking_v1 = client.NetworkingV1Api()
        core_v1 = client.CoreV1Api()
        
        logger.info(f"检查NetworkPolicy阻断: {source_namespace} -> {target_namespace}")
        
        result = {
            "source_namespace": source_namespace,
            "target_namespace": target_namespace,
            "source_policies": [],
            "target_policies": [],
            "egress_blocked": False,
            "ingress_blocked": False,
            "blocking_policies": [],
            "recommendations": [],
            "diagnosis_summary": ""
        }
        
        # 1. 获取源命名空间的NetworkPolicy
        try:
            source_np_list = networking_v1.list_namespaced_network_policy(source_namespace)
            for np in source_np_list.items:
                policy_info = {
                    "name": np.metadata.name,
                    "pod_selector": np.spec.pod_selector.match_labels if np.spec.pod_selector.match_labels else {},
                    "policy_types": np.spec.policy_types or []
                }
                result["source_policies"].append(policy_info)
                
                # 检查Egress规则
                if "Egress" in (np.spec.policy_types or []):
                    if not np.spec.egress:
                        # 没有egress规则 = 默认deny all
                        result["egress_blocked"] = True
                        result["blocking_policies"].append({
                            "policy": np.metadata.name,
                            "namespace": source_namespace,
                            "type": "Egress",
                            "reason": "未定义Egress规则，默认拒绝所有出站流量"
                        })
        except ApiException as e:
            if e.status != 404:
                logger.warning(f"获取源命名空间NetworkPolicy失败: {str(e)}")
        
        # 2. 获取目标命名空间的NetworkPolicy
        if target_namespace:
            try:
                target_np_list = networking_v1.list_namespaced_network_policy(target_namespace)
                for np in target_np_list.items:
                    policy_info = {
                        "name": np.metadata.name,
                        "pod_selector": np.spec.pod_selector.match_labels if np.spec.pod_selector.match_labels else {},
                        "policy_types": np.spec.policy_types or []
                    }
                    result["target_policies"].append(policy_info)
                    
                    # 检查Ingress规则
                    if "Ingress" in (np.spec.policy_types or []):
                        if not np.spec.ingress:
                            # 没有ingress规则 = 默认deny all
                            result["ingress_blocked"] = True
                            result["blocking_policies"].append({
                                "policy": np.metadata.name,
                                "namespace": target_namespace,
                                "type": "Ingress",
                                "reason": "未定义Ingress规则，默认拒绝所有入站流量"
                            })
            except ApiException as e:
                if e.status != 404:
                    logger.warning(f"获取目标命名空间NetworkPolicy失败: {str(e)}")
        
        # 3. 生成诊断结论
        if len(result["source_policies"]) == 0 and (not target_namespace or len(result["target_policies"]) == 0):
            result["diagnosis_summary"] = "未配置NetworkPolicy，网络流量不受限制"
        elif result["egress_blocked"] or result["ingress_blocked"]:
            blocked_types = []
            if result["egress_blocked"]:
                blocked_types.append("出站Egress")
            if result["ingress_blocked"]:
                blocked_types.append("入站Ingress")
            result["diagnosis_summary"] = f"NetworkPolicy阻断了{'/'.join(blocked_types)}流量"
            result["recommendations"].append(
                "检查NetworkPolicy规则，为需要通信的Pod添加相应的Egress/Ingress规则"
            )
        else:
            result["diagnosis_summary"] = "配置了NetworkPolicy但未发现明显阻断（需要详细分析Pod标签匹配）"
            result["recommendations"].append(
                "NetworkPolicy规则较复杂，建议人工检查Pod标签是否匹配policy selector"
            )
        
        logger.info(f"NetworkPolicy检查完成: {result['diagnosis_summary']}")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"检查NetworkPolicy失败: {str(e)}")
        return json.dumps({
            "error": f"检查失败: {str(e)}",
            "source_namespace": source_namespace
        })


@tool()
def check_pvc_capacity(namespace=None, threshold_percent=80, config: RunnableConfig = None):
    """
    检查PVC（持久化存储）使用率，识别磁盘满风险
    
    **何时使用此工具：**
    - 排查存储容量不足导致的应用问题
    - Pod因存储问题无法正常启动时
    - 进行存储容量规划和预警
    - 分析存储资源的使用情况和风险
    
    **工具能力：**
    - 列出所有PVC及其容量配置
    - 识别未绑定（Pending）的PVC
    - 计算PVC使用率（需要Pod挂载信息）
    - 预警接近满的PVC（默认>80%）
    - 识别可扩容的StorageClass
    - 提供扩容和清理建议
    
    Args:
        namespace (str, optional): 命名空间，None=所有命名空间
        threshold_percent (int, optional): 使用率预警阈值，默认80
            - 80: 标准预警阈值
            - 90: 高风险阈值
            - 50: 提前规划容量
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - pvc_list[]: PVC列表
          - name: PVC名称
          - namespace: 命名空间
          - status: Bound/Pending/Lost
          - capacity: 容量大小
          - storage_class: 存储类
          - access_modes: 访问模式
          - mounted_by[]: 挂载此PVC的Pod列表
        - pending_pvcs[]: 未绑定的PVC
        - high_usage_pvcs[]: 使用率高的PVC
        - recommendations[]: 优化建议
        - total_capacity: 总容量
    
    **配合其他工具使用：**
    - 如果Pod因PVC Pending → 使用 diagnose_pending_pod_issues
    - 如果需要扩容 → 根据建议手动扩容PVC或添加PV
    
    **注意事项：**
    - 使用率计算依赖于Pod的volumeMounts信息
    - 某些存储类不支持自动扩容（需要手动操作）
    - emptyDir类型的临时存储不在此工具检查范围
    - 建议结合监控系统获取更准确的使用率数据
    
    **常见存储问题：**
    1. PVC Pending：没有符合条件的PV
    2. PVC满：使用率100%，Pod无法写入
    3. 日志占用：容器日志未rotate，占满磁盘
    4. emptyDir满：超过节点磁盘限制
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        storage_v1 = client.StorageV1Api()
        
        logger.info(f"检查PVC容量, namespace={namespace}, threshold={threshold_percent}%")
        
        # 获取PVC列表
        if namespace:
            pvcs = core_v1.list_namespaced_persistent_volume_claim(namespace)
        else:
            pvcs = core_v1.list_persistent_volume_claim_for_all_namespaces()
        
        # 获取所有Pod（用于查找PVC挂载关系）
        if namespace:
            pods = core_v1.list_namespaced_pod(namespace)
        else:
            pods = core_v1.list_pod_for_all_namespaces()
        
        result = {
            "threshold_percent": threshold_percent,
            "pvc_list": [],
            "pending_pvcs": [],
            "high_usage_pvcs": [],
            "recommendations": [],
            "total_capacity": 0,
            "total_pvcs": 0
        }
        
        # 构建PVC到Pod的映射
        pvc_to_pods = {}
        for pod in pods.items:
            if pod.spec.volumes:
                for volume in pod.spec.volumes:
                    if volume.persistent_volume_claim:
                        pvc_name = volume.persistent_volume_claim.claim_name
                        pvc_key = f"{pod.metadata.namespace}/{pvc_name}"
                        if pvc_key not in pvc_to_pods:
                            pvc_to_pods[pvc_key] = []
                        pvc_to_pods[pvc_key].append(pod.metadata.name)
        
        # 分析每个PVC
        for pvc in pvcs.items:
            pvc_key = f"{pvc.metadata.namespace}/{pvc.metadata.name}"
            
            # 解析容量
            capacity_str = pvc.status.capacity.get('storage', '0') if pvc.status.capacity else '0'
            capacity_bytes = parse_resource_quantity(capacity_str)
            result["total_capacity"] += capacity_bytes
            result["total_pvcs"] += 1
            
            pvc_info = {
                "name": pvc.metadata.name,
                "namespace": pvc.metadata.namespace,
                "status": pvc.status.phase,
                "capacity": capacity_str,
                "capacity_bytes": capacity_bytes,
                "storage_class": pvc.spec.storage_class_name,
                "access_modes": pvc.spec.access_modes or [],
                "mounted_by": pvc_to_pods.get(pvc_key, [])
            }
            
            result["pvc_list"].append(pvc_info)
            
            # 检查未绑定的PVC
            if pvc.status.phase == "Pending":
                result["pending_pvcs"].append({
                    "name": pvc.metadata.name,
                    "namespace": pvc.metadata.namespace,
                    "requested_capacity": capacity_str
                })
                result["recommendations"].append(
                    f"PVC {pvc.metadata.name} 未绑定，检查是否有可用的PV或动态provisioner"
                )
        
        # 生成总结建议
        if len(result["pending_pvcs"]) > 0:
            result["recommendations"].insert(0, 
                f"发现{len(result['pending_pvcs'])}个未绑定的PVC，可能导致Pod无法启动"
            )
        
        if result["total_pvcs"] == 0:
            result["recommendations"].append("集群中没有PVC，如果应用需要持久化存储请创建PVC")
        
        logger.info(f"PVC检查完成: {result['total_pvcs']}个PVC, {len(result['pending_pvcs'])}个Pending")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"检查PVC容量失败: {str(e)}")
        return json.dumps({
            "error": f"检查失败: {str(e)}",
            "namespace": namespace
        })
