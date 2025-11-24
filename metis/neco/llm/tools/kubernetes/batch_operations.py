"""Kubernetes批量操作工具 - P1效率提升"""
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from kubernetes import client
from loguru import logger
from neco.llm.tools.kubernetes.utils import prepare_context


def _log_operation(operation: str, namespace: str, resource_type: str, count: int):
    """记录批量操作到审计日志"""
    logger.warning(
        f"K8S批量操作",
        extra={
            "operation": operation,
            "namespace": namespace,
            "resource_type": resource_type,
            "count": count,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


@tool()
def batch_restart_pods(namespace, label_selector=None, pod_names=None, wait_for_ready=False, config: RunnableConfig = None):
    """
    批量重启Pod，提升运维效率
    
    **何时使用此工具：**
    - 用户要求"重启所有app=nginx的Pod"、"重启这几个Pod"
    - 配置更新后需要批量重启生效
    - 批量清理异常Pod
    - 滚动重启应用（逐个重启避免服务中断）
    
    **工具能力：**
    - 支持按label selector批量选择Pod
    - 支持指定Pod名称列表
    - 自动检查Pod是否有控制器（避免误删孤立Pod）
    - 支持等待所有Pod就绪（可选）
    - 记录每个Pod的重启结果
    - 记录审计日志
    
    Args:
        namespace (str): 命名空间（必填）
        label_selector (str, optional): 标签选择器，如 "app=nginx,env=prod"
        pod_names (list, optional): Pod名称列表
            注意：label_selector 和 pod_names 至少提供一个
        wait_for_ready (bool, optional): 是否等待所有Pod就绪，默认False
            - False: 异步重启，立即返回（推荐批量操作）
            - True: 等待所有Pod就绪再返回（耗时长）
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - namespace: 命名空间
        - total_pods: 找到的Pod总数
        - restarted_pods[]: 成功重启的Pod列表
        - failed_pods[]: 重启失败的Pod列表
          - pod_name: Pod名称
          - error: 失败原因
        - skipped_pods[]: 跳过的Pod列表（如孤立Pod）
        - wait_for_ready: 是否等待就绪
        - all_ready: 所有Pod是否就绪（如果wait_for_ready=True）
    
    **配合其他工具使用：**
    - 重启前检查Pod状态 → 使用 list_kubernetes_pods
    - 重启后验证 → 使用 check_pod_distribution
    
    **注意事项：**
    - ⚠️ 批量重启会导致服务短暂不可用
    - 建议逐步重启，避免一次重启太多Pod
    - 对于关键服务，建议设置PodDisruptionBudget
    - 重启会丢失emptyDir中的临时数据
    
    **最佳实践：**
    - 生产环境：分批重启，每批重启后观察服务状态
    - 使用label精确匹配，避免误重启其他Pod
    - 对于大规模重启，建议wait_for_ready=False，然后单独验证
    
    **示例场景：**
    ```
    场景1：重启所有nginx Pod
    → batch_restart_pods(namespace="prod", label_selector="app=nginx")
    
    场景2：重启指定的3个Pod
    → batch_restart_pods(namespace="prod", pod_names=["pod-1", "pod-2", "pod-3"])
    ```
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        
        logger.info(f"开始批量重启Pod: namespace={namespace}, label_selector={label_selector}, pod_names={pod_names}")
        
        # 参数验证
        if not label_selector and not pod_names:
            return json.dumps({
                "error": "必须提供 label_selector 或 pod_names 之一"
            })
        
        # 获取要重启的Pod列表
        pods_to_restart = []
        
        if label_selector:
            pods = core_v1.list_namespaced_pod(namespace, label_selector=label_selector)
            pods_to_restart = pods.items
        elif pod_names:
            for pod_name in pod_names:
                try:
                    pod = core_v1.read_namespaced_pod(pod_name, namespace)
                    pods_to_restart.append(pod)
                except ApiException as e:
                    if e.status != 404:
                        raise
        
        result = {
            "namespace": namespace,
            "label_selector": label_selector,
            "total_pods": len(pods_to_restart),
            "restarted_pods": [],
            "failed_pods": [],
            "skipped_pods": [],
            "wait_for_ready": wait_for_ready,
            "restart_time": datetime.now(timezone.utc).isoformat()
        }
        
        if len(pods_to_restart) == 0:
            result["message"] = "没有找到匹配的Pod"
            return json.dumps(result, ensure_ascii=False, indent=2)
        
        _log_operation("batch_restart", namespace, "Pod", len(pods_to_restart))
        
        # 逐个重启Pod
        for pod in pods_to_restart:
            pod_name = pod.metadata.name
            
            # 检查是否有控制器
            has_controller = pod.metadata.owner_references and len(pod.metadata.owner_references) > 0
            
            if not has_controller:
                result["skipped_pods"].append({
                    "pod_name": pod_name,
                    "reason": "孤立Pod（无控制器），跳过重启"
                })
                logger.warning(f"跳过孤立Pod: {pod_name}")
                continue
            
            # 删除Pod触发重启
            try:
                core_v1.delete_namespaced_pod(
                    name=pod_name,
                    namespace=namespace,
                    grace_period_seconds=30
                )
                
                result["restarted_pods"].append({
                    "pod_name": pod_name,
                    "old_uid": pod.metadata.uid,
                    "status": "deleted"
                })
                
                logger.info(f"已重启Pod: {namespace}/{pod_name}")
                
            except ApiException as e:
                result["failed_pods"].append({
                    "pod_name": pod_name,
                    "error": str(e)
                })
                logger.error(f"重启Pod失败: {namespace}/{pod_name}, 错误: {str(e)}")
        
        # 如果需要等待就绪
        if wait_for_ready and len(result["restarted_pods"]) > 0:
            logger.info(f"等待{len(result['restarted_pods'])}个Pod就绪...")
            time.sleep(5)  # 等待Pod开始创建
            
            ready_count = 0
            timeout = 120  # 总超时2分钟
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                ready_count = 0
                
                for restart_info in result["restarted_pods"]:
                    pod_name = restart_info["pod_name"]
                    try:
                        new_pod = core_v1.read_namespaced_pod(pod_name, namespace)
                        
                        # 确保是新Pod
                        if new_pod.metadata.uid != restart_info["old_uid"]:
                            if new_pod.status.phase == "Running":
                                if new_pod.status.container_statuses:
                                    all_ready = all(c.ready for c in new_pod.status.container_statuses)
                                    if all_ready:
                                        ready_count += 1
                                        restart_info["status"] = "ready"
                                        restart_info["new_uid"] = new_pod.metadata.uid
                    except ApiException:
                        pass
                
                if ready_count == len(result["restarted_pods"]):
                    break
                
                time.sleep(3)
            
            result["all_ready"] = (ready_count == len(result["restarted_pods"]))
            result["ready_count"] = ready_count
        
        logger.info(f"批量重启完成: 成功{len(result['restarted_pods'])}个, 失败{len(result['failed_pods'])}个, 跳过{len(result['skipped_pods'])}个")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"批量重启Pod失败: {str(e)}")
        return json.dumps({
            "error": f"批量重启失败: {str(e)}",
            "namespace": namespace
        })


@tool()
def find_configmap_consumers(configmap_name, namespace, config: RunnableConfig = None):
    """
    查找ConfigMap的消费者，评估变更影响范围
    
    **何时使用此工具：**
    - 用户询问"这个ConfigMap被哪些Pod用了"、"改这个配置影响谁"
    - 更新ConfigMap前，评估影响范围
    - 删除ConfigMap前，确认是否还在使用
    - 排查配置未生效问题
    
    **工具能力：**
    - 列出所有挂载此ConfigMap的Pod
    - 区分挂载方式（volume挂载 vs 环境变量引用）
    - 检测是否使用subPath（subPath不会自动更新）
    - 统计影响的Deployment/StatefulSet
    - 提供重启建议（哪些Pod需要重启）
    
    Args:
        configmap_name (str): ConfigMap名称（必填）
        namespace (str): 命名空间（必填）
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - configmap_name: ConfigMap名称
        - namespace: 命名空间
        - configmap_exists: ConfigMap是否存在
        - consumers[]: 消费者Pod列表
          - pod_name: Pod名称
          - mount_type: "volume" 或 "env"
          - uses_subpath: 是否使用subPath（bool）
          - controller: 所属控制器（Deployment/StatefulSet）
          - needs_restart: 是否需要重启生效（bool）
        - affected_controllers[]: 受影响的控制器列表
        - total_consumers: 消费者总数
        - recommendations[]: 建议
    
    **配合其他工具使用：**
    - 发现需要重启的Pod → 使用 batch_restart_pods 批量重启
    - 查看控制器详情 → 使用 describe_kubernetes_resource
    
    **ConfigMap更新机制：**
    1. Volume挂载：自动更新（几秒到几分钟延迟）
    2. Volume + subPath：不会自动更新，必须重启Pod
    3. 环境变量：不会自动更新，必须重启Pod
    
    **注意事项：**
    - 只检查当前命名空间的Pod
    - 不检查其他命名空间的ConfigMap引用
    - 不检查Secret的消费者（需要单独工具）
    
    **典型使用场景：**
    ```
    场景：用户要更新nginx-config ConfigMap
    步骤1: find_configmap_consumers("nginx-config", "prod")
    步骤2: 查看结果，发现3个Pod使用，其中2个用了subPath
    步骤3: 提醒用户：修改ConfigMap后，需要重启使用subPath的Pod
    步骤4: 用户确认后，调用 batch_restart_pods 重启
    ```
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        
        logger.info(f"查找ConfigMap消费者: {namespace}/{configmap_name}")
        
        # 检查ConfigMap是否存在
        configmap_exists = False
        try:
            core_v1.read_namespaced_config_map(configmap_name, namespace)
            configmap_exists = True
        except ApiException as e:
            if e.status != 404:
                raise
        
        result = {
            "configmap_name": configmap_name,
            "namespace": namespace,
            "configmap_exists": configmap_exists,
            "consumers": [],
            "affected_controllers": [],
            "total_consumers": 0,
            "recommendations": []
        }
        
        if not configmap_exists:
            result["message"] = f"ConfigMap不存在: {namespace}/{configmap_name}"
            return json.dumps(result, ensure_ascii=False, indent=2)
        
        # 获取所有Pod
        pods = core_v1.list_namespaced_pod(namespace)
        
        controllers_set = set()
        
        for pod in pods.items:
            pod_name = pod.metadata.name
            uses_configmap = False
            mount_types = []
            uses_subpath = False
            
            # 检查Volume挂载
            if pod.spec.volumes:
                for volume in pod.spec.volumes:
                    if volume.config_map and volume.config_map.name == configmap_name:
                        uses_configmap = True
                        mount_types.append("volume")
                        
                        # 检查是否使用了subPath
                        if pod.spec.containers:
                            for container in pod.spec.containers:
                                if container.volume_mounts:
                                    for vm in container.volume_mounts:
                                        if vm.name == volume.name and vm.sub_path:
                                            uses_subpath = True
            
            # 检查环境变量引用
            if pod.spec.containers:
                for container in pod.spec.containers:
                    if container.env:
                        for env in container.env:
                            if env.value_from and env.value_from.config_map_key_ref:
                                if env.value_from.config_map_key_ref.name == configmap_name:
                                    uses_configmap = True
                                    if "env" not in mount_types:
                                        mount_types.append("env")
            
            if uses_configmap:
                # 获取控制器信息
                controller_info = None
                if pod.metadata.owner_references:
                    owner_ref = pod.metadata.owner_references[0]
                    controller_info = f"{owner_ref.kind}/{owner_ref.name}"
                    controllers_set.add(controller_info)
                
                # 判断是否需要重启
                needs_restart = uses_subpath or ("env" in mount_types)
                
                consumer_info = {
                    "pod_name": pod_name,
                    "mount_types": mount_types,
                    "uses_subpath": uses_subpath,
                    "controller": controller_info,
                    "needs_restart": needs_restart
                }
                
                result["consumers"].append(consumer_info)
                result["total_consumers"] += 1
        
        result["affected_controllers"] = list(controllers_set)
        
        # 生成建议
        if result["total_consumers"] == 0:
            result["recommendations"].append(
                f"ConfigMap {configmap_name} 当前没有被任何Pod使用，可以安全修改或删除"
            )
        else:
            pods_need_restart = [c for c in result["consumers"] if c["needs_restart"]]
            if len(pods_need_restart) > 0:
                result["recommendations"].append(
                    f"有{len(pods_need_restart)}个Pod使用了subPath或环境变量，修改ConfigMap后需要重启这些Pod"
                )
                result["recommendations"].append(
                    f"建议使用 batch_restart_pods 批量重启：{[p['pod_name'] for p in pods_need_restart]}"
                )
            else:
                result["recommendations"].append(
                    f"所有Pod都是Volume挂载（无subPath），ConfigMap更新会自动生效（有延迟）"
                )
        
        logger.info(f"ConfigMap消费者查找完成: {result['total_consumers']}个消费者")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"查找ConfigMap消费者失败: {str(e)}")
        return json.dumps({
            "error": f"查找失败: {str(e)}",
            "configmap_name": configmap_name,
            "namespace": namespace
        })


@tool()
def cleanup_failed_pods(namespace=None, include_evicted=True, config: RunnableConfig = None):
    """
    批量清理失败的Pod，释放资源
    
    **何时使用此工具：**
    - 用户要求"清理失败的Pod"、"删除Evicted Pod"
    - 集群中积累了大量Failed/Evicted Pod
    - 释放资源配额（Failed Pod仍占用配额）
    - 清理测试遗留的Pod
    
    **工具能力：**
    - 自动识别Failed状态的Pod
    - 可选清理Evicted Pod（节点资源不足被驱逐）
    - 可选清理Completed状态的Job Pod
    - 记录清理的Pod列表
    - 记录审计日志
    
    Args:
        namespace (str, optional): 命名空间，None=所有命名空间
        include_evicted (bool, optional): 是否清理Evicted Pod，默认True
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - namespace: 命名空间
        - cleaned_pods[]: 已清理的Pod列表
          - pod_name: Pod名称
          - namespace: 命名空间
          - status: Failed/Evicted/Completed
          - reason: 失败原因
        - failed_cleanups[]: 清理失败的Pod
        - total_cleaned: 清理总数
        - total_failed: 清理失败数
    
    **配合其他工具使用：**
    - 清理前查看失败Pod → 使用 get_failed_kubernetes_pods
    - 清理前分析失败原因 → 使用 diagnose_kubernetes_pod_issues
    
    **Pod状态说明：**
    - Failed: Pod中所有容器都已终止，至少一个容器非0退出
    - Evicted: 节点资源不足，Pod被驱逐
    - Completed: Job Pod成功完成（exitCode=0）
    
    **注意事项：**
    - ⚠️ 清理操作不可逆，请谨慎使用
    - Failed Pod可能包含重要的故障信息（日志、退出码）
    - 建议清理前先用 get_kubernetes_pod_logs 保存日志
    - Evicted Pod通常是资源不足导致，清理后要解决根本问题
    
    **最佳实践：**
    - 生产环境：清理前先分析失败原因，保存日志
    - 测试环境：可以直接清理
    - 定期清理：避免Failed Pod积累过多
    
    **典型使用场景：**
    ```
    场景1：清理所有Failed Pod
    → cleanup_failed_pods(namespace="prod", include_evicted=True)
    
    场景2：清理前先查看
    → get_failed_kubernetes_pods()
    → 确认无重要信息后
    → cleanup_failed_pods()
    ```
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        
        logger.info(f"开始清理失败Pod: namespace={namespace}, include_evicted={include_evicted}")
        
        # 获取Pod列表
        if namespace:
            pods = core_v1.list_namespaced_pod(namespace)
        else:
            pods = core_v1.list_pod_for_all_namespaces()
        
        result = {
            "namespace": namespace or "all",
            "include_evicted": include_evicted,
            "cleaned_pods": [],
            "failed_cleanups": [],
            "total_cleaned": 0,
            "total_failed": 0,
            "cleanup_time": datetime.now(timezone.utc).isoformat()
        }
        
        pods_to_clean = []
        
        for pod in pods.items:
            pod_name = pod.metadata.name
            pod_namespace = pod.metadata.namespace
            pod_phase = pod.status.phase
            
            # 识别需要清理的Pod
            should_clean = False
            reason = None
            
            if pod_phase == "Failed":
                should_clean = True
                reason = "Failed"
            elif pod_phase == "Succeeded":
                # Completed Job Pod
                should_clean = True
                reason = "Completed"
            elif include_evicted and pod_phase == "Failed":
                # 检查是否是Evicted
                if pod.status.reason == "Evicted":
                    should_clean = True
                    reason = "Evicted"
            
            if should_clean:
                pods_to_clean.append({
                    "name": pod_name,
                    "namespace": pod_namespace,
                    "reason": reason,
                    "phase": pod_phase
                })
        
        if len(pods_to_clean) == 0:
            result["message"] = "没有需要清理的Pod"
            return json.dumps(result, ensure_ascii=False, indent=2)
        
        _log_operation("cleanup_failed_pods", namespace or "all", "Pod", len(pods_to_clean))
        
        # 批量清理
        for pod_info in pods_to_clean:
            try:
                core_v1.delete_namespaced_pod(
                    name=pod_info["name"],
                    namespace=pod_info["namespace"],
                    grace_period_seconds=0  # 立即删除
                )
                
                result["cleaned_pods"].append(pod_info)
                result["total_cleaned"] += 1
                
                logger.info(f"已清理Pod: {pod_info['namespace']}/{pod_info['name']} ({pod_info['reason']})")
                
            except ApiException as e:
                result["failed_cleanups"].append({
                    "pod_name": pod_info["name"],
                    "namespace": pod_info["namespace"],
                    "error": str(e)
                })
                result["total_failed"] += 1
                logger.error(f"清理Pod失败: {pod_info['namespace']}/{pod_info['name']}, 错误: {str(e)}")
        
        logger.info(f"清理完成: 成功{result['total_cleaned']}个, 失败{result['total_failed']}个")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"批量清理失败: {str(e)}")
        return json.dumps({
            "error": f"批量清理失败: {str(e)}",
            "namespace": namespace
        })
