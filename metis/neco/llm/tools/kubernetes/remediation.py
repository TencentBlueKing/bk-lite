"""Kubernetes故障自愈工具 - 操作类工具"""
import json
import time
from datetime import datetime, timezone
from typing import Optional
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from kubernetes import client
from loguru import logger
from neco.llm.tools.kubernetes.utils import prepare_context


def _log_operation(operation: str, namespace: str, resource_type: str, resource_name: str):
    """记录操作到审计日志"""
    logger.warning(
        f"K8S操作执行",
        extra={
            "operation": operation,
            "namespace": namespace,
            "resource_type": resource_type,
            "resource_name": resource_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


@tool()
def restart_pod(pod_name, namespace, wait_for_ready=True, timeout=60, config: RunnableConfig = None):
    """
    重启Pod，用于故障恢复或重新加载配置
    
    **何时使用此工具：**
    - 需要强制恢复处于异常状态的Pod
    - 配置更新后需要重新加载生效
    - 应用出现僵死、泄漏等需要通过重启恢复
    - 排查时需要重新触发Pod的初始化流程
    
    **工具能力：**
    - 删除当前Pod，由控制器自动重建
    - 记录旧Pod的UID，便于追踪
    - 可选等待新Pod就绪（避免操作不生效）
    - 返回新旧Pod的对比信息
    - 审计日志记录，可追溯操作
    
    Args:
        pod_name (str): Pod名称（必填）
        namespace (str): 命名空间（必填）
        wait_for_ready (bool, optional): 是否等待新Pod就绪，默认True
            - True: 等待新Pod Running且容器Ready（推荐）
            - False: 仅删除Pod，不等待重建
        timeout (int, optional): 等待超时时间（秒），默认60
            - 仅在wait_for_ready=True时生效
            - 超时不代表失败，只是不再等待
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - success (bool): 是否成功
        - old_pod_uid: 旧Pod的UID
        - owner_controller: Pod的控制器信息
        - new_pod_status: "ready" 或 "not_ready"（wait_for_ready=True时）
        - new_pod_uid: 新Pod的UID（就绪后）
        - wait_time_seconds: 等待耗时
        - restart_time: 重启时间戳
    
    **配合其他工具使用：**
    - 重启后检查日志 → 使用 get_pod_logs 查看启动日志
    - 批量重启 → 多次调用此工具（建议逐个重启）
    - 重启失败诊断 → 使用 diagnose_kubernetes_pod_issues
    
    **注意事项：**
    - 重启会短暂中断服务（除非配置了多副本）
    - 无状态Pod可安全重启，有状态Pod需谨慎
    - 如果控制器不存在（孤儿Pod），删除后不会重建
    - 新Pod会被调度到可能不同的节点
    
    **最佳实践：**
    - 生产环境建议逐个重启，避免服务完全中断
    - 重启前确认是由控制器管理的Pod
    - 建议使用wait_for_ready=True，确保新Pod启动成功
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        _log_operation("restart_pod", namespace, "Pod", pod_name)
        
        logger.info(f"开始重启Pod: {namespace}/{pod_name}")
        
        # 1. 检查Pod是否存在
        try:
            pod = core_v1.read_namespaced_pod(pod_name, namespace)
        except ApiException as e:
            if e.status == 404:
                return json.dumps({
                    "success": False,
                    "error": f"Pod不存在: {namespace}/{pod_name}"
                })
            raise
        
        # 2. 记录Pod的控制器信息
        owner_info = None
        if pod.metadata.owner_references:
            owner_ref = pod.metadata.owner_references[0]
            owner_info = {
                "kind": owner_ref.kind,
                "name": owner_ref.name,
                "uid": owner_ref.uid
            }
        
        old_pod_uid = pod.metadata.uid
        
        # 3. 删除Pod
        try:
            core_v1.delete_namespaced_pod(
                name=pod_name,
                namespace=namespace,
                grace_period_seconds=30  # 优雅删除
            )
            logger.info(f"Pod已删除: {namespace}/{pod_name}")
        except ApiException as e:
            return json.dumps({
                "success": False,
                "error": f"删除Pod失败: {str(e)}"
            })
        
        result = {
            "success": True,
            "pod_name": pod_name,
            "namespace": namespace,
            "old_pod_uid": old_pod_uid,
            "owner_controller": owner_info,
            "restart_time": datetime.now(timezone.utc).isoformat()
        }
        
        # 4. 等待新Pod就绪
        if wait_for_ready:
            logger.info(f"等待新Pod就绪: {namespace}/{pod_name}, 超时{timeout}秒")
            
            start_time = time.time()
            new_pod_ready = False
            new_pod_uid = None
            
            while time.time() - start_time < timeout:
                try:
                    new_pod = core_v1.read_namespaced_pod(pod_name, namespace)
                    new_pod_uid = new_pod.metadata.uid
                    
                    # 确保是新的Pod
                    if new_pod_uid != old_pod_uid:
                        # 检查Pod是否就绪
                        if new_pod.status.phase == "Running":
                            # 检查所有容器是否就绪
                            if new_pod.status.container_statuses:
                                all_ready = all(c.ready for c in new_pod.status.container_statuses)
                                if all_ready:
                                    new_pod_ready = True
                                    break
                    
                    time.sleep(2)
                except ApiException as e:
                    if e.status != 404:
                        raise
                    # Pod还在删除中
                    time.sleep(2)
            
            if new_pod_ready:
                result["new_pod_status"] = "ready"
                result["new_pod_uid"] = new_pod_uid
                result["wait_time_seconds"] = int(time.time() - start_time)
                logger.info(f"新Pod已就绪: {namespace}/{pod_name}")
            else:
                result["new_pod_status"] = "not_ready"
                result["warning"] = f"新Pod在{timeout}秒内未就绪"
                logger.warning(f"新Pod未就绪: {namespace}/{pod_name}")
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"重启Pod失败: {namespace}/{pod_name}, 错误: {str(e)}")
        return json.dumps({
            "success": False,
            "error": f"重启Pod失败: {str(e)}",
            "pod_name": pod_name,
            "namespace": namespace
        })


@tool()
def scale_deployment(deployment_name, namespace, replicas, config: RunnableConfig = None):
    """
    扩缩容Deployment或StatefulSet - 应对流量变化
    
    **何时使用此工具：**
    - 根据流量变化动态调整应用容量
    - 通过缩容降低资源消耗或成本
    - 快速恢复服务（如缩容到0再扩容触发重建）
    - 匹配业务需求调整服务规模
    
    **工具能力：**
    - 支持Deployment和StatefulSet两种资源类型
    - 自动识别资源类型（无需指定）
    - 记录操作前后的副本数变化
    - 记录审计日志，包含操作者和时间
    - 区分扩容（scale_up）和缩容（scale_down）操作
    
    Args:
        deployment_name (str): Deployment或StatefulSet名称（必填）
        namespace (str): 命名空间（必填）
        replicas (int): 目标副本数（必填）
            - >当前副本数: 扩容操作
            - <当前副本数: 缩容操作
            - 0: 完全停止服务（谨慎使用）
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - success (bool): 是否成功
        - resource_type: "Deployment" 或 "StatefulSet"
        - previous_replicas: 操作前的副本数
        - target_replicas: 目标副本数
        - operation: "scale_up" 或 "scale_down"
        - scale_time: 操作时间戳
    
    **配合其他工具使用：**
    - 扩容前检查容量 → 使用 check_scaling_capacity 确保有足够资源
    - 扩容后等待就绪 → 使用 wait_for_pod_ready 验证新Pod
    - 扩容后检查分布 → 使用 check_pod_distribution 验证高可用
    
    **注意事项：**
    - 扩容前建议先检查集群资源是否充足
    - 缩容会删除Pod，可能导致服务短暂不可用
    - 对于StatefulSet，缩容会从高序号Pod开始删除
    - 如果配置了HPA，手动扩缩容可能被HPA覆盖
    
    **最佳实践：**
    - 扩容：先调用 check_scaling_capacity 确认资源充足
    - 缩容：建议逐步缩容，观察服务影响
    - 生产环境：谨慎缩容到0副本（会导致服务完全下线）
    """
    prepare_context(config)
    
    try:
        apps_v1 = client.AppsV1Api()
        _log_operation("scale", namespace, "Deployment", deployment_name)
        
        logger.info(f"开始扩缩容: {namespace}/{deployment_name} -> {replicas}副本")
        
        # 1. 尝试作为Deployment处理
        try:
            deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
            resource_type = "Deployment"
            current_replicas = deployment.spec.replicas
            
            # 更新副本数
            deployment.spec.replicas = replicas
            apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=deployment
            )
            
        except ApiException as e:
            if e.status == 404:
                # 尝试作为StatefulSet处理
                try:
                    statefulset = apps_v1.read_namespaced_stateful_set(deployment_name, namespace)
                    resource_type = "StatefulSet"
                    current_replicas = statefulset.spec.replicas
                    
                    # 更新副本数
                    statefulset.spec.replicas = replicas
                    apps_v1.patch_namespaced_stateful_set(
                        name=deployment_name,
                        namespace=namespace,
                        body=statefulset
                    )
                except ApiException as e2:
                    if e2.status == 404:
                        return json.dumps({
                            "success": False,
                            "error": f"未找到Deployment或StatefulSet: {namespace}/{deployment_name}"
                        })
                    raise e2
            else:
                raise
        
        result = {
            "success": True,
            "resource_type": resource_type,
            "resource_name": deployment_name,
            "namespace": namespace,
            "previous_replicas": current_replicas,
            "target_replicas": replicas,
            "operation": "scale_up" if replicas > current_replicas else "scale_down",
            "scale_time": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"扩缩容成功: {namespace}/{deployment_name}, {current_replicas} -> {replicas}")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"扩缩容失败: {namespace}/{deployment_name}, 错误: {str(e)}")
        return json.dumps({
            "success": False,
            "error": f"扩缩容失败: {str(e)}",
            "resource_name": deployment_name,
            "namespace": namespace
        })


@tool()
def get_deployment_revision_history(deployment_name, namespace, config: RunnableConfig = None):
    """
    获取Deployment的版本历史，用于回滚决策
    
    **何时使用此工具：**
    - 新版本发布出现问题需要回滚时
    - 查看Deployment的版本演进历史
    - 确定可回滚的目标版本
    - 为版本对比分析提供基础数据
    
    **工具能力：**
    - 列出所有历史版本（revision）
    - 展示每个版本的ReplicaSet、镜像、创建时间
    - 标识当前运行的版本
    - 按版本号倒序排列（最新版本在前）
    - 提供版本选择建议，支持回滚决策
    
    Args:
        deployment_name (str): Deployment名称（必填）
        namespace (str): 命名空间（必填）
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - current_revision: 当前版本号
        - revisions[]: 历史版本列表
          - revision: 版本号
          - replica_set_name: ReplicaSet名称
          - creation_time: 创建时间
          - image: 容器镜像
          - is_current: 是否当前版本
        - total_revisions: 版本总数
        - rollback_limit: 保留的历史版本数
    
    **配合其他工具使用：**
    - 对比版本差异 → 使用 compare_deployment_revisions
    - 确定回滚目标 → 使用此工具查看历史，然后 rollback_deployment
    
    **注意事项：**
    - 历史版本数由 spec.revisionHistoryLimit 控制（默认10）
    - 过旧的版本会被自动清理
    - revision 编号是递增的，不会重复使用
    """
    prepare_context(config)
    
    try:
        apps_v1 = client.AppsV1Api()
        logger.info(f"获取Deployment发布历史: {namespace}/{deployment_name}")
        
        # 获取Deployment
        deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
        
        # 获取关联的ReplicaSet
        label_selector = ",".join([f"{k}={v}" for k, v in deployment.spec.selector.match_labels.items()])
        replica_sets = apps_v1.list_namespaced_replica_set(
            namespace,
            label_selector=label_selector
        )
        
        # 整理历史版本
        revisions = []
        for rs in replica_sets.items:
            # 获取revision注解
            revision = rs.metadata.annotations.get("deployment.kubernetes.io/revision")
            if revision:
                revision_info = {
                    "revision": int(revision),
                    "replica_set_name": rs.metadata.name,
                    "creation_time": rs.metadata.creation_timestamp.isoformat() if rs.metadata.creation_timestamp else None,
                    "replicas": rs.spec.replicas,
                    "ready_replicas": rs.status.ready_replicas or 0,
                    "is_current": (rs.metadata.name == deployment.status.conditions[0].message.split()[-1] if deployment.status.conditions else False),
                    "image": rs.spec.template.spec.containers[0].image if rs.spec.template.spec.containers else None
                }
                revisions.append(revision_info)
        
        # 按revision排序
        revisions.sort(key=lambda x: x["revision"], reverse=True)
        
        # 当前revision
        current_revision = deployment.metadata.annotations.get("deployment.kubernetes.io/revision")
        
        result = {
            "deployment_name": deployment_name,
            "namespace": namespace,
            "current_revision": int(current_revision) if current_revision else None,
            "total_revisions": len(revisions),
            "revisions": revisions,
            "rollback_limit": deployment.spec.revision_history_limit or 10
        }
        
        logger.info(f"获取发布历史成功: {len(revisions)}个版本")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except ApiException as e:
        logger.error(f"获取发布历史失败: {str(e)}")
        if e.status == 404:
            return json.dumps({
                "error": f"Deployment不存在: {namespace}/{deployment_name}"
            })
        return json.dumps({
            "error": f"获取发布历史失败: {str(e)}"
        })


@tool()
def rollback_deployment(deployment_name, namespace, revision=None, config: RunnableConfig = None):
    """
    回滚Deployment到指定版本，快速恢复服务
    
    **何时使用此工具：**
    - 用户反馈"新版本有问题，回滚"、"恢复到上个版本"
    - 发布后出现严重bug或性能问题
    - 需要紧急恢复到稳定版本
    - 灰度发布失败，需要回退
    
    **工具能力：**
    - 支持回滚到上一个版本（revision=None）
    - 支持回滚到任意历史版本（指定revision）
    - 自动复制目标版本的Pod模板
    - 添加回滚注解，记录变更原因
    - 触发滚动更新，逐步替换Pod
    - 记录审计日志
    
    Args:
        deployment_name (str): Deployment名称（必填）
        namespace (str): 命名空间（必填）
        revision (int, optional): 目标版本号，None=回滚到上一个版本
            - None: 自动回滚到前一个版本（最常用）
            - 2: 回滚到revision 2
            - 使用 get_deployment_revision_history 查看可用版本
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - success (bool): 是否成功
        - previous_revision: 回滚前的版本号
        - target_revision: 目标版本号
        - target_image: 目标版本的镜像
        - rollback_time: 回滚时间戳
    
    **配合其他工具使用：**
    - 回滚前查看历史 → 使用 get_deployment_revision_history
    - 回滚前对比差异 → 使用 compare_deployment_revisions
    - 回滚后验证Pod → 使用 wait_for_pod_ready 或 check_pod_distribution
    
    **注意事项：**
    - 回滚是滚动更新，会逐步替换Pod（不是瞬时完成）
    - 回滚不会恢复ConfigMap/Secret等配置资源
    - 如果目标revision已被清理，回滚会失败
    - 回滚操作本身也会生成新的revision
    
    **最佳实践：**
    - 回滚前先用 get_deployment_revision_history 确认目标版本存在
    - 生产环境回滚建议先在测试环境验证
    - 回滚后观察服务状态，确认问题已解决
    """
    prepare_context(config)
    
    try:
        apps_v1 = client.AppsV1Api()
        _log_operation("rollback", namespace, "Deployment", deployment_name)
        
        logger.info(f"开始回滚Deployment: {namespace}/{deployment_name}, revision={revision}")
        
        # 获取当前Deployment
        deployment = apps_v1.read_namespaced_deployment(deployment_name, namespace)
        current_revision = deployment.metadata.annotations.get("deployment.kubernetes.io/revision")
        
        # 如果未指定版本，回滚到上一个版本
        if revision is None:
            # 获取历史版本
            label_selector = ",".join([f"{k}={v}" for k, v in deployment.spec.selector.match_labels.items()])
            replica_sets = apps_v1.list_namespaced_replica_set(
                namespace,
                label_selector=label_selector
            )
            
            revisions_list = []
            for rs in replica_sets.items:
                rs_revision = rs.metadata.annotations.get("deployment.kubernetes.io/revision")
                if rs_revision:
                    revisions_list.append(int(rs_revision))
            
            revisions_list.sort(reverse=True)
            if len(revisions_list) < 2:
                return json.dumps({
                    "success": False,
                    "error": "没有可回滚的历史版本"
                })
            
            # 回滚到前一个版本
            revision = revisions_list[1]
        
        # 执行回滚
        # 使用 DeploymentRollback API (如果可用) 或者通过更新annotations触发回滚
        try:
            # 方式1: 使用kubectl rollback等效的API
            # 注意: 某些K8S版本可能不支持DeploymentRollback API
            rollback_body = {
                "name": deployment_name,
                "rollbackTo": {
                    "revision": revision
                }
            }
            
            # 直接更新deployment的template到目标revision的template
            # 找到目标revision的ReplicaSet
            target_rs = None
            for rs in replica_sets.items:
                rs_revision = rs.metadata.annotations.get("deployment.kubernetes.io/revision")
                if rs_revision and int(rs_revision) == revision:
                    target_rs = rs
                    break
            
            if not target_rs:
                return json.dumps({
                    "success": False,
                    "error": f"未找到revision {revision}对应的ReplicaSet"
                })
            
            # 更新Deployment的template为目标版本的template
            deployment.spec.template = target_rs.spec.template
            
            # 添加回滚注解
            if not deployment.metadata.annotations:
                deployment.metadata.annotations = {}
            deployment.metadata.annotations["kubernetes.io/change-cause"] = f"Rollback to revision {revision}"
            
            apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=deployment
            )
            
            result = {
                "success": True,
                "deployment_name": deployment_name,
                "namespace": namespace,
                "previous_revision": int(current_revision) if current_revision else None,
                "target_revision": revision,
                "rollback_time": datetime.now(timezone.utc).isoformat(),
                "target_image": target_rs.spec.template.spec.containers[0].image if target_rs.spec.template.spec.containers else None
            }
            
            logger.info(f"回滚成功: {namespace}/{deployment_name}, revision {current_revision} -> {revision}")
            return json.dumps(result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"回滚失败: {str(e)}"
            })
        
    except ApiException as e:
        logger.error(f"回滚Deployment失败: {str(e)}")
        if e.status == 404:
            return json.dumps({
                "success": False,
                "error": f"Deployment不存在: {namespace}/{deployment_name}"
            })
        return json.dumps({
            "success": False,
            "error": f"回滚失败: {str(e)}"
        })


@tool()
def delete_kubernetes_resource(resource_type, resource_name, namespace, grace_period=30, config: RunnableConfig = None):
    """
    删除Kubernetes资源，支持优雅终止
    
    **何时使用此工具：**
    - 用户要求"删除这个资源"、"清理Pod"
    - 清理测试资源或临时资源
    - 删除失败的Pod（Failed/Evicted）
    - 清理不再使用的ConfigMap/Secret
    
    **支持的资源类型：**
    - pod: 删除Pod（会触发控制器重建）
    - deployment: 删除Deployment及其管理的所有Pod
    - service: 删除Service（不影响Pod）
    - configmap: 删除ConfigMap
    - secret: 删除Secret
    
    Args:
        resource_type (str): 资源类型（必填），支持pod/deployment/service/configmap/secret
        resource_name (str): 资源名称（必填）
        namespace (str): 命名空间（必填）
        grace_period (int, optional): 优雅删除等待时间（秒），默认30
            - 30: 给Pod足够时间清理资源（推荐）
            - 0: 立即强制删除（谨慎使用）
            - 60: 对于需要长时间清理的应用
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - success (bool): 是否成功
        - resource_type: 资源类型
        - resource_name: 资源名称
        - grace_period_seconds: 优雅删除时长
        - delete_time: 删除时间戳
    
    **注意事项：**
    - ⚠️ 删除操作不可逆，请谨慎使用
    - 删除Pod：如果有控制器，会自动重建
    - 删除Deployment：会删除所有关联的ReplicaSet和Pod
    - 删除Service：不会删除后端Pod
    - 删除ConfigMap/Secret：不会影响已挂载的Pod（直到Pod重启）
    - grace_period=0会强制删除，可能导致数据丢失
    
    **配合其他工具使用：**
    - 批量删除 → 使用 cleanup_failed_pods
    - 删除前检查依赖 → 使用 find_configmap_consumers
    """
    prepare_context(config)
    
    try:
        _log_operation("delete", namespace, resource_type, resource_name)
        
        core_v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()
        
        resource_type = resource_type.lower()
        logger.warning(f"删除资源: {namespace}/{resource_type}/{resource_name}")
        
        # 根据资源类型调用相应的删除API
        if resource_type == "pod":
            core_v1.delete_namespaced_pod(
                name=resource_name,
                namespace=namespace,
                grace_period_seconds=grace_period
            )
        elif resource_type == "deployment":
            apps_v1.delete_namespaced_deployment(
                name=resource_name,
                namespace=namespace,
                grace_period_seconds=grace_period
            )
        elif resource_type == "service":
            core_v1.delete_namespaced_service(
                name=resource_name,
                namespace=namespace
            )
        elif resource_type == "configmap":
            core_v1.delete_namespaced_config_map(
                name=resource_name,
                namespace=namespace
            )
        elif resource_type == "secret":
            core_v1.delete_namespaced_secret(
                name=resource_name,
                namespace=namespace
            )
        else:
            return json.dumps({
                "success": False,
                "error": f"不支持的资源类型: {resource_type}",
                "supported_types": ["pod", "deployment", "service", "configmap", "secret"]
            })
        
        result = {
            "success": True,
            "resource_type": resource_type,
            "resource_name": resource_name,
            "namespace": namespace,
            "grace_period_seconds": grace_period,
            "delete_time": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"资源删除成功: {namespace}/{resource_type}/{resource_name}")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except ApiException as e:
        logger.error(f"删除资源失败: {str(e)}")
        if e.status == 404:
            return json.dumps({
                "success": False,
                "error": f"资源不存在: {namespace}/{resource_type}/{resource_name}"
            })
        return json.dumps({
            "success": False,
            "error": f"删除失败: {str(e)}"
        })


@tool()
def wait_for_pod_ready(pod_name, namespace, timeout=60, config: RunnableConfig = None):
    """
    等待Pod就绪，验证操作成功
    
    **何时使用此工具：**
    - 重启/扩容后，等待新Pod就绪
    - 发布后，验证Pod是否成功启动
    - 确认操作生效，避免过早返回
    
    **工具能力：**
    - 轮询检查Pod状态（每2秒检查一次）
    - 验证Pod phase为Running
    - 验证所有容器Ready
    - 检测Pod失败状态（Failed/Unknown）
    - 返回Pod IP和节点信息
    
    Args:
        pod_name (str): Pod名称（必填）
        namespace (str): 命名空间（必填）
        timeout (int, optional): 超时时间（秒），默认60
            - 60: 适用于大部分应用
            - 120: 对于启动慢的应用（如Java）
            - 30: 对于快速启动的应用
        config (RunnableConfig): 工具配置（自动传递）
    
    Returns:
        JSON格式，包含：
        - success (bool): 是否就绪
        - status: "ready"、"timeout"、"failed"
        - pod_ip: Pod IP地址（就绪时）
        - node: 所在节点（就绪时）
        - wait_time_seconds: 等待耗时
        - error: 错误信息（失败时）
    
    **配合其他工具使用：**
    - 通常在 restart_pod、scale_deployment 之后自动调用
    - 如果超时，使用 diagnose_kubernetes_pod_issues 诊断
    
    **注意事项：**
    - 如果Pod不存在，会返回错误
    - 如果Pod处于Failed状态，会立即返回失败
    - 超时不代表Pod永远不会就绪，只是超过等待时间
    """
    prepare_context(config)
    
    try:
        core_v1 = client.CoreV1Api()
        logger.info(f"等待Pod就绪: {namespace}/{pod_name}, 超时{timeout}秒")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                pod = core_v1.read_namespaced_pod(pod_name, namespace)
                
                if pod.status.phase == "Running":
                    # 检查所有容器是否就绪
                    if pod.status.container_statuses:
                        all_ready = all(c.ready for c in pod.status.container_statuses)
                        if all_ready:
                            wait_time = int(time.time() - start_time)
                            result = {
                                "success": True,
                                "pod_name": pod_name,
                                "namespace": namespace,
                                "status": "ready",
                                "wait_time_seconds": wait_time,
                                "pod_ip": pod.status.pod_ip,
                                "node": pod.spec.node_name
                            }
                            logger.info(f"Pod已就绪: {namespace}/{pod_name}, 等待时间: {wait_time}秒")
                            return json.dumps(result, ensure_ascii=False, indent=2)
                
                elif pod.status.phase in ["Failed", "Unknown"]:
                    return json.dumps({
                        "success": False,
                        "pod_name": pod_name,
                        "namespace": namespace,
                        "status": pod.status.phase,
                        "error": f"Pod处于失败状态: {pod.status.phase}"
                    })
                
                time.sleep(2)
                
            except ApiException as e:
                if e.status == 404:
                    return json.dumps({
                        "success": False,
                        "error": f"Pod不存在: {namespace}/{pod_name}"
                    })
                raise
        
        # 超时
        logger.warning(f"等待Pod就绪超时: {namespace}/{pod_name}")
        return json.dumps({
            "success": False,
            "pod_name": pod_name,
            "namespace": namespace,
            "status": "timeout",
            "error": f"Pod在{timeout}秒内未就绪"
        })
        
    except Exception as e:
        logger.error(f"等待Pod就绪失败: {str(e)}")
        return json.dumps({
            "success": False,
            "error": f"等待Pod就绪失败: {str(e)}",
            "pod_name": pod_name,
            "namespace": namespace
        })
