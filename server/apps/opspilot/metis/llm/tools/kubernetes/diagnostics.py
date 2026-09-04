"""Kubernetes故障诊断和监控工具"""
import json
from datetime import datetime, timezone

from kubernetes import client
from kubernetes.client import ApiException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.kubernetes.instance_scope import prepare_point_instance, run_scan_tool
from apps.opspilot.metis.llm.tools.kubernetes.resources import get_kubernetes_pod_logs, get_kubernetes_previous_pod_logs
from apps.opspilot.metis.llm.tools.kubernetes.utils import coerce_int, format_bytes, parse_resource_quantity, prepare_context

_EVENT_TIME_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _container_last_state(container) -> dict:
    terminated = getattr(getattr(container, "last_state", None), "terminated", None)
    if terminated is None:
        return {}
    finished_at = getattr(terminated, "finished_at", None)
    return {
        "reason": getattr(terminated, "reason", None),
        "exit_code": getattr(terminated, "exit_code", None),
        "finished_at": finished_at.isoformat() if finished_at else None,
        "message": getattr(terminated, "message", None),
    }


def _as_utc_datetime(timestamp):
    if timestamp is None or not isinstance(timestamp, datetime):
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _event_sort_time(event):
    timestamp = getattr(event, "last_timestamp", None)
    if timestamp is None:
        return _EVENT_TIME_MIN
    return _as_utc_datetime(timestamp) or _EVENT_TIME_MIN


def _container_last_restart_at(container):
    """最近一次重启时间：优先当前轮 startedAt，否则上一轮 terminated.finishedAt。"""
    running = getattr(getattr(container, "state", None), "running", None)
    started_at = _as_utc_datetime(getattr(running, "started_at", None) if running is not None else None)
    if started_at is not None:
        return started_at
    terminated = getattr(getattr(container, "last_state", None), "terminated", None)
    return _as_utc_datetime(getattr(terminated, "finished_at", None) if terminated is not None else None)


_RESTART_COUNT_NOTE = "restart_count 是当前 Pod UID 上该容器自创建以来的累计次数，不是时间窗内次数，也不是排序键。"


@tool()
def get_failed_kubernetes_pods(instance_name=None, config: RunnableConfig = None):
    """
    发现集群中所有失败或异常的Pod

    **何时使用此工具：**
    - 用户反馈"有Pod起不来"、"服务异常"、"应用崩溃"
    - 需要快速定位集群中所有问题Pod
    - 排查大面积故障时的第一步
    - 检查是否有镜像拉取、权限、资源等问题

    **工具能力：**
    - 扫描所有命名空间的Pod状态
    - 识别Failed、CrashLoopBackOff、ImagePullBackOff等异常状态
    - 提供容器级别的详细状态（退出码、重启次数、错误原因）
    - 自动过滤已完成的Job Pod（Succeeded状态）

    **典型问题类型：**
    - CrashLoopBackOff: 应用启动后立即崩溃
    - ImagePullBackOff: 镜像拉取失败（地址错误/无权限/网络问题）
    - Failed: Pod运行失败终止
    - Unknown: 节点失联或状态未知

    Args:
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含失败Pod列表，每个Pod包含：
        - name: Pod名称
        - namespace: 命名空间
        - phase: 当前状态
        - container_statuses[]: 容器状态详情
          - state: 状态（waiting/terminated/running）
          - reason: 失败原因（如CrashLoopBackOff）
          - exit_code: 退出码（137=OOMKilled, 1=Error）
          - restart_count: 重启次数
        - node: 所在节点

    **配合其他工具使用：**
    - 发现失败Pod后 → 使用 diagnose_kubernetes_pod_issues 深入诊断
    - 查看具体错误信息 → 使用 get_kubernetes_pod_logs 获取日志
    - 分析镜像问题 → 检查imageRegistry配置和Secret
    - 需要恢复服务 → 使用 restart_pod 或 delete_kubernetes_resource
    """
    return run_scan_tool(config, instance_name, _get_failed_kubernetes_pods_on_instance)


def _get_failed_kubernetes_pods_on_instance(config: RunnableConfig = None):
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
                        "state": {},
                    }

                    # Check container state
                    if container.state.waiting:
                        container_info["state"] = {
                            "status": "waiting",
                            "reason": container.state.waiting.reason,
                            "message": container.state.waiting.message,
                        }
                        if container.state.waiting.reason in ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "InvalidImageName"]:
                            is_failed = True
                    elif container.state.terminated:
                        container_info["state"] = {
                            "status": "terminated",
                            "reason": container.state.terminated.reason,
                            "exit_code": container.state.terminated.exit_code,
                            "message": container.state.terminated.message,
                        }
                        if container.state.terminated.exit_code != 0:
                            is_failed = True
                    elif container.state.running:
                        container_info["state"] = {
                            "status": "running",
                            "started_at": container.state.running.started_at.isoformat() if container.state.running.started_at else None,
                        }

                    container_statuses.append(container_info)

            if is_failed:
                failed.append(
                    {
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "phase": pod.status.phase,
                        "container_statuses": container_statuses,
                        "node": pod.spec.node_name,
                        "message": pod.status.message,
                        "reason": pod.status.reason,
                        "creation_time": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
                    }
                )

        return json.dumps(failed)
    except ApiException as e:
        return json.dumps({"error": f"获取失败Pod列表失败: {str(e)}"})


def _pod_is_not_ready(pod) -> bool:
    statuses = pod.status.container_statuses or []
    if any(not getattr(container, "ready", False) for container in statuses):
        return True
    for condition in pod.status.conditions or []:
        if getattr(condition, "type", None) == "Ready" and str(getattr(condition, "status", "")) == "False":
            return True
    return False


def _not_ready_pod_record(pod) -> dict:
    container_statuses = []
    if pod.status.container_statuses:
        for container in pod.status.container_statuses:
            container_statuses.append(
                {
                    "name": container.name,
                    "ready": container.ready,
                    "restart_count": container.restart_count,
                    "image": container.image,
                }
            )
    return {
        "name": pod.metadata.name,
        "namespace": pod.metadata.namespace,
        "phase": pod.status.phase,
        "ready": False,
        "container_statuses": container_statuses,
        "node": pod.spec.node_name,
        "message": pod.status.message,
        "reason": pod.status.reason,
        "creation_time": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
    }


@tool()
def get_not_ready_kubernetes_pods(namespace=None, instance_name=None, config: RunnableConfig = None):
    """
    发现 Running 但未就绪的 Pod（Readiness 失败入口）

    **何时使用此工具：**
    - Unhealthy / Readiness probe failed 告警
    - 服务已 Running 但流量打不进去、Endpoints 不包含该 Pod
    - get_failed_kubernetes_pods 为空，仍怀疑探针或依赖导致 Not Ready

    **工具能力：**
    - 扫描 Running（非 Succeeded/Failed/Pending）且容器 ready=False 或 Ready 条件为 False 的 Pod
    - 可按 namespace 过滤

    Args:
        namespace (str, optional): 命名空间；省略则扫描全部命名空间
        instance_name (str, optional): 多实例时指定集群；省略则扫描全部已配置实例
        config (RunnableConfig): 工具配置（自动传递）
    """
    return run_scan_tool(config, instance_name, lambda bound: _get_not_ready_kubernetes_pods_on_instance(namespace, bound))


def _get_not_ready_kubernetes_pods_on_instance(namespace, config: RunnableConfig = None):
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()
        if namespace:
            pods = core_v1.list_namespaced_pod(namespace)
        else:
            pods = core_v1.list_pod_for_all_namespaces()
        not_ready = []
        for pod in pods.items:
            if pod.status.phase in ("Succeeded", "Failed", "Pending"):
                continue
            if not _pod_is_not_ready(pod):
                continue
            not_ready.append(_not_ready_pod_record(pod))
        return json.dumps(not_ready)
    except ApiException as e:
        return json.dumps({"error": f"获取未就绪Pod列表失败: {str(e)}"})


@tool()
def get_pending_kubernetes_pods(instance_name=None, config: RunnableConfig = None):
    """
    发现无法调度或启动的Pending状态Pod

    **何时使用此工具：**
    - 用户反馈"Pod一直Pending"、"服务启动不了"、"调度失败"
    - 新部署的应用长时间未就绪
    - 扩容后新Pod无法启动
    - 检查集群资源是否充足

    **工具能力：**
    - 列出所有Pending状态的Pod
    - 分析无法调度的具体原因（资源不足/节点亲和性/Taint/PVC等）
    - 区分调度失败和初始化失败
    - 提供创建时间，识别长期Pending的Pod

    **常见Pending原因：**
    - Insufficient cpu/memory: 集群资源不足
    - No nodes available: 没有符合条件的节点
    - PersistentVolumeClaim not bound: 存储卷未绑定
    - Node affinity/selector: 节点选择器不匹配
    - Taints: 节点污点阻止调度

    Args:
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含Pending Pod列表，每个Pod包含：
        - name: Pod名称
        - namespace: 命名空间
        - node: 分配的节点（如果已调度）
        - reason: Pending原因（如SchedulingFailed）
        - message: 详细错误信息
        - creation_time: 创建时间

    **配合其他工具使用：**
    - 发现资源不足 → 使用 get_kubernetes_node_capacity 检查集群容量
    - 调度问题深入分析 → 使用 diagnose_pending_pod_issues
    - 检查节点状态 → 使用 diagnose_node_issues
    - 存储问题 → 使用 check_kubernetes_persistent_volumes
    """
    return run_scan_tool(config, instance_name, _get_pending_kubernetes_pods_on_instance)


def _get_pending_kubernetes_pods_on_instance(config: RunnableConfig = None):
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

                pending.append(
                    {
                        "name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "node": pod.spec.node_name,
                        "reason": reason,
                        "message": message,
                        "creation_time": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
                    }
                )

        return json.dumps(pending)
    except ApiException as e:
        return json.dumps({"error": f"获取Pending Pod列表失败: {str(e)}"})


@tool()
def get_high_restart_kubernetes_pods(restart_threshold: int = 5, instance_name=None, config: RunnableConfig = None):
    """
    发现频繁重启的不稳定Pod

    **何时使用此工具：**
    - 用户反馈"服务不稳定"、"时好时坏"、"经常掉线"
    - 怀疑有应用程序bug或配置问题
    - 检查是否有内存泄漏或资源配置不当
    - 监控集群稳定性的日常巡检

    **工具能力：**
    - 快速列出重启次数超过阈值的Pod
    - 显示每个容器的具体重启次数
    - 提供容器镜像信息，便于定位版本问题
    - 展示Ready状态，判断当前是否正常

    **注意：** restart_count 是容器自创建以来的累计次数，不是今天或指定时间窗内的次数。
    用户问「今天重启了几次」时，本工具不能当作时间窗答案；必须再用
    get_resource_events_timeline 等按时间过滤，且不要把累计次数写成「今天重启了 N 次」。
    用户要按重启时间排序、列出最近重启的 Pod 时，使用 get_recently_restarted_kubernetes_pods，
    不要用本工具：这里没有重启时间，也不能按累计次数冒充「最近重启」。

    **与analyze_pod_restart_pattern的区别：**
    - 本工具：快速列表，找出"哪些Pod在重启"
    - analyze_pod_restart_pattern：深度分析"为什么重启"（退出码、OOM、事件）

    **常见重启原因：**
    - OOM（内存不足）→ 退出码137
    - 健康检查失败 → livenessProbe配置不当
    - 应用程序bug → 退出码1
    - 配置错误 → 启动命令或环境变量问题

    Args:
        restart_threshold (int, optional): 重启次数阈值，默认5
            - 5: 标准阈值，找出明显不稳定的Pod
            - 3: 更敏感，发现轻微重启问题
            - 10: 只关注严重频繁重启的Pod
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含高重启Pod列表，每个Pod包含：
        - name: Pod名称
        - namespace: 命名空间
        - node: 所在节点
        - containers[]: 容器列表
          - name: 容器名称
          - restart_count: 重启次数
          - ready: 是否就绪
          - image: 容器镜像

    **配合其他工具使用：**
    - 深入分析重启原因 → 使用 analyze_pod_restart_pattern
    - 检查是否OOM → 使用 check_oom_events
    - 查看完整事件历史 → 使用 get_resource_events_timeline
    - 查看容器日志 → 使用 get_kubernetes_pod_logs
    """
    restart_threshold = coerce_int(restart_threshold, 5, lo=0, hi=10000)
    return run_scan_tool(config, instance_name, lambda bound: _get_high_restart_kubernetes_pods_on_instance(restart_threshold, bound))


def _get_high_restart_kubernetes_pods_on_instance(restart_threshold, config: RunnableConfig = None):
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
                        high_restart_containers.append(
                            {"name": container.name, "restart_count": container.restart_count, "ready": container.ready, "image": container.image}
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
        return json.dumps({"error": f"获取高重启Pod列表失败: {str(e)}"})


@tool()
def get_recently_restarted_kubernetes_pods(namespace=None, top_n: int = 10, instance_name=None, config: RunnableConfig = None):
    """
    按最近一次重启时间列出最近重启过的 Pod（默认 Top 10）

    **何时使用此工具：**
    - 用户要按重启时间排序、列出最近重启的 Pod
    - 「最近 10 个重启的 Pod」「按照重启时间排序」
    - 需要看谁最近刚重启过，而不是谁累计 restartCount 最高

    **不要用此工具：**
    - 已知具体 Pod 问重启原因 → collect_pod_restart_evidence（目录没有则用 diagnose_kubernetes_pod_issues）
    - 只想按累计次数找长期不稳定 Pod → get_high_restart_kubernetes_pods
    - 问今天/近 N 小时重启了几次 → 本工具给不出时间窗次数

    **工具能力：**
    - 一次 list pods，按每个 Pod 最近一次重启时间降序取 Top-N
    - 重启时间优先取当前轮 startedAt，否则上一轮 finishedAt；没有时间戳则跳过
    - restart_count 只展示累计值，不是排序键，也不是窗口次数

    Args:
        namespace (str, optional): 命名空间；省略则扫描全部命名空间
        top_n (int, optional): 返回条数，默认 10，最大 50
        instance_name (str, optional): 多实例时指定集群；省略则扫描全部已配置实例
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON 对象：
        - sort: last_restart_time_desc
        - restart_count_note: 累计次数口径说明
        - items[]: pod、namespace、container、last_restart_time、restart_count、ready、node
    """
    namespace = str(namespace).strip() if namespace else None
    top_n = coerce_int(top_n, 10, lo=1, hi=50)
    return run_scan_tool(config, instance_name, lambda bound: _get_recently_restarted_kubernetes_pods_on_instance(namespace, top_n, bound))


def _iter_pod_container_statuses(pod):
    for attr in ("container_statuses", "init_container_statuses"):
        statuses = getattr(getattr(pod, "status", None), attr, None) or []
        for container in statuses:
            yield container


def _recent_restart_row(pod, container, restarted_at):
    return {
        "pod": pod.metadata.name,
        "namespace": pod.metadata.namespace,
        "container": getattr(container, "name", None),
        "last_restart_time": restarted_at.isoformat(),
        "restart_count": int(getattr(container, "restart_count", 0) or 0),
        "ready": bool(getattr(container, "ready", False)),
        "node": getattr(getattr(pod, "spec", None), "node_name", None),
        "_sort": restarted_at,
    }


def _best_recent_restart_row(pod):
    best = None
    for container in _iter_pod_container_statuses(pod):
        restart_count = int(getattr(container, "restart_count", 0) or 0)
        if restart_count < 1:
            continue
        restarted_at = _container_last_restart_at(container)
        if restarted_at is None:
            continue
        row = _recent_restart_row(pod, container, restarted_at)
        if best is None or (restarted_at, restart_count) > (best["_sort"], best["restart_count"]):
            best = row
    return best


def _get_recently_restarted_kubernetes_pods_on_instance(namespace, top_n, config: RunnableConfig = None):
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()
        if namespace:
            pods = core_v1.list_namespaced_pod(namespace)
        else:
            pods = core_v1.list_pod_for_all_namespaces()
        rows = []
        for pod in pods.items:
            row = _best_recent_restart_row(pod)
            if row is not None:
                rows.append(row)
        rows.sort(key=lambda item: item["_sort"], reverse=True)
        items = [{key: value for key, value in row.items() if key != "_sort"} for row in rows[:top_n]]
        return json.dumps(
            {
                "sort": "last_restart_time_desc",
                "restart_count_note": _RESTART_COUNT_NOTE,
                "items": items,
            }
        )
    except ApiException as e:
        return json.dumps({"error": f"获取最近重启Pod列表失败: {str(e)}"})


@tool()
def get_kubernetes_node_capacity(config: RunnableConfig = None):
    """
    查看集群节点资源容量和使用情况

    **何时使用此工具：**
    - 用户反馈"Pod调度失败"、"资源不足"
    - 规划扩容或缩容决策
    - 评估集群整体负载水平
    - 检查资源碎片化问题（单个节点资源不足）
    - 日常容量管理和监控

    **工具能力：**
    - 统计所有节点的资源分配情况
    - 计算CPU/内存的requests占用率（非实际使用率）
    - 显示Pod数量使用情况
    - 检查节点健康状态（Conditions）
    - 识别资源紧张的节点

    **重要说明：**
    - 本工具统计的是资源**requests**（预留），不是实际使用量
    - 如需实际使用率，需要Metrics Server（超出纯SDK范围）
    - 高requests占用不等于高实际使用，但会影响调度

    **资源占用率解读：**
    - <60%: 资源充足
    - 60-80%: 资源适中，建议监控
    - 80-90%: 资源紧张，可能影响调度
    - >90%: 资源严重不足，建议扩容

    Args:
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含所有节点的容量信息：
        - name: 节点名称
        - pods: Pod容量
          - used: 已运行Pod数
          - capacity: 最大Pod数
          - percent_used: 使用率
        - cpu: CPU容量
          - requested: 已分配CPU核心数
          - allocatable: 可分配CPU核心数
          - percent_used: 占用率
        - memory: 内存容量
          - requested: 已分配内存
          - allocatable: 可分配内存
          - percent_used: 占用率
        - conditions: 节点状态（Ready/DiskPressure等）

    **配合其他工具使用：**
    - 发现节点问题 → 使用 diagnose_node_issues 深入诊断
    - Pod调度失败 → 使用 get_pending_kubernetes_pods 查看具体Pod
    - 资源不足需扩容 → 建议添加新节点或优化Pod资源配置
    - 检查资源碎片化 → 使用 check_pod_distribution
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
            allocatable_cpu = parse_resource_quantity(allocatable.get("cpu", "0"))
            allocatable_memory = parse_resource_quantity(allocatable.get("memory", "0"))
            allocatable_pods = int(allocatable.get("pods", "0"))

            # Calculate resource requests from pods on this node
            pods_on_node = node_pods.get(node_name, [])
            requested_cpu = 0
            requested_memory = 0

            for pod in pods_on_node:
                if pod.spec.containers:
                    for container in pod.spec.containers:
                        if container.resources and container.resources.requests:
                            cpu_request = container.resources.requests.get("cpu", "0")
                            memory_request = container.resources.requests.get("memory", "0")
                            requested_cpu += parse_resource_quantity(cpu_request)
                            requested_memory += parse_resource_quantity(memory_request)

            # Calculate percentages
            cpu_percent = (requested_cpu / allocatable_cpu * 100) if allocatable_cpu > 0 else 0
            memory_percent = (requested_memory / allocatable_memory * 100) if allocatable_memory > 0 else 0
            pods_percent = (len(pods_on_node) / allocatable_pods * 100) if allocatable_pods > 0 else 0

            # Get node conditions
            conditions = {}
            if node.status.conditions:
                for condition in node.status.conditions:
                    conditions[condition.type] = {"status": condition.status, "reason": condition.reason, "message": condition.message}

            results.append(
                {
                    "name": node_name,
                    "pods": {"used": len(pods_on_node), "capacity": allocatable_pods, "percent_used": round(pods_percent, 2)},
                    "cpu": {"requested": round(requested_cpu, 3), "allocatable": round(allocatable_cpu, 3), "percent_used": round(cpu_percent, 2)},
                    "memory": {
                        "requested": int(requested_memory),
                        "requested_human": format_bytes(requested_memory),
                        "allocatable": int(allocatable_memory),
                        "allocatable_human": format_bytes(allocatable_memory),
                        "percent_used": round(memory_percent, 2),
                    },
                    "conditions": conditions,
                }
            )

        return json.dumps(results)
    except ApiException as e:
        return json.dumps({"error": f"获取节点容量信息失败: {str(e)}"})


@tool()
def get_kubernetes_orphaned_resources(config: RunnableConfig = None):
    """
    发现孤立资源（无控制器管理）- 资源清理和审计

    **何时使用此工具：**
    - 用户说"清理无用资源"、"删除孤立对象"
    - 资源审计，找出不受控制器管理的资源
    - 成本优化，识别可能被遗忘的资源
    - 排查资源泄漏问题
    - 清理测试环境的临时资源

    **工具能力：**
    - 识别没有OwnerReference的资源（无控制器管理）
    - 扫描Pod、Service、ConfigMap、Secret、PVC
    - 自动过滤系统资源（kube-system等）
    - 显示创建时间，识别长期存在的孤立资源

    **什么是孤立资源：**
    - 没有Deployment/StatefulSet等控制器管理的Pod
    - 手动创建未删除的Service
    - 测试时创建的临时ConfigMap/Secret
    - 删除Deployment后残留的PVC

    **注意事项：**
    - 并非所有孤立资源都应删除（有些是故意手动创建的）
    - 删除前请确认资源用途
    - Service通常是手动创建的，较多孤立是正常的
    - 建议先核实再清理

    Args:
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含各类孤立资源：
        - pods[]: 孤立的Pod列表
        - services[]: 孤立的Service列表
        - persistent_volume_claims[]: 孤立的PVC列表
        - config_maps[]: 孤立的ConfigMap列表
        - secrets[]: 孤立的Secret列表

        每个资源包含：
        - name: 资源名称
        - namespace: 命名空间
        - creation_time: 创建时间

    **配合其他工具使用：**
    - 确认资源可删除 → 检查是否被其他资源引用
    - 删除孤立资源 → 使用 delete_kubernetes_resource
    - 批量清理Pod → 使用 cleanup_failed_pods
    - 查找ConfigMap使用者 → 使用 find_configmap_consumers
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
                    results["pods"].append(
                        {
                            "name": pod.metadata.name,
                            "namespace": pod.metadata.namespace,
                            "creation_time": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
                        }
                    )

        # Check for orphaned services
        services = core_v1.list_service_for_all_namespaces()
        for service in services.items:
            # Skip system services
            if service.metadata.namespace not in ["kube-system", "kube-public", "kube-node-lease"]:
                if not service.metadata.owner_references:
                    # Skip default kubernetes service
                    if not (service.metadata.name == "kubernetes" and service.metadata.namespace == "default"):
                        results["services"].append(
                            {
                                "name": service.metadata.name,
                                "namespace": service.metadata.namespace,
                                "creation_time": service.metadata.creation_timestamp.isoformat() if service.metadata.creation_timestamp else None,
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
                        "creation_time": pvc.metadata.creation_timestamp.isoformat() if pvc.metadata.creation_timestamp else None,
                    }
                )

        # Check for orphaned ConfigMaps
        config_maps = core_v1.list_config_map_for_all_namespaces()
        for cm in config_maps.items:
            # Skip system configmaps
            if cm.metadata.namespace not in ["kube-system", "kube-public", "kube-node-lease"]:
                if not cm.metadata.owner_references:
                    # Skip some well-known system configmaps
                    system_cms = ["kube-root-ca.crt"]
                    if cm.metadata.name not in system_cms:
                        results["config_maps"].append(
                            {
                                "name": cm.metadata.name,
                                "namespace": cm.metadata.namespace,
                                "creation_time": cm.metadata.creation_timestamp.isoformat() if cm.metadata.creation_timestamp else None,
                            }
                        )

        # Check for orphaned Secrets
        secrets = core_v1.list_secret_for_all_namespaces()
        for secret in secrets.items:
            # Skip system secrets
            if secret.metadata.namespace not in ["kube-system", "kube-public", "kube-node-lease"]:
                if not secret.metadata.owner_references:
                    # Skip service account tokens and other system secrets
                    if secret.type not in ["kubernetes.io/service-account-token", "kubernetes.io/dockercfg", "kubernetes.io/dockerconfigjson"]:
                        results["secrets"].append(
                            {
                                "name": secret.metadata.name,
                                "namespace": secret.metadata.namespace,
                                "type": secret.type,
                                "creation_time": secret.metadata.creation_timestamp.isoformat() if secret.metadata.creation_timestamp else None,
                            }
                        )

        return json.dumps(results)
    except ApiException as e:
        return json.dumps({"error": f"获取孤立资源列表失败: {str(e)}"})


@tool()
def diagnose_kubernetes_pod_issues(namespace, pod_name, instance_name=None, config: RunnableConfig = None):  # noqa: C901
    """
    深度诊断单个Pod的所有问题 - 一站式故障排查

    **何时使用此工具：**
    - 用户说"这个Pod有问题，帮我看看"
    - 已知具体Pod名称，需要全面分析
    - 从 get_failed_pods 或 get_pending_pods 发现问题Pod后
    - 需要详细的诊断报告（状态+事件+资源+卷）

    **工具能力（最全面的Pod诊断）：**
    - Pod所有Conditions（Ready、Initialized、ContainersReady等）
    - 容器状态详情（waiting/running/terminated，含退出码）
    - 每个容器的 last_state（上一轮终止 reason、exit_code、finished_at、message）
    - Init容器状态（初始化失败诊断）
    - 资源requests和limits配置
    - 挂载卷配置（PVC/ConfigMap/Secret/HostPath）
    - 最近10个相关事件（时间排序）
    - 重启策略和节点信息

    **诊断维度：**
    1. 容器健康：状态、退出码、重启次数
    2. 资源配置：CPU/内存requests和limits
    3. 依赖检查：ConfigMap、Secret、PVC是否存在
    4. 事件分析：Warning/Error事件的原因和消息
    5. 节点信息：调度到哪个节点，节点是否健康

    Args:
        namespace (str): Pod所在命名空间（必填）
        pod_name (str): Pod名称（必填）
        config (RunnableConfig): 工具配置（自动传递）

    Returns:
        JSON格式，包含完整的诊断信息：
        - phase: Pod状态（Running/Pending/Failed）
        - conditions[]: 所有Condition详情
        - containers[]: 容器状态（state、restart_count、last_state、image）
        - init_containers[]: Init容器状态（含 last_state）
        - resource_requests: 资源请求配置
        - resource_limits: 资源限制配置
        - volumes[]: 卷挂载信息
        - recent_events[]: 最近事件（按时间排序）
        - node: 所在节点
        - restart_policy: 重启策略

    **配合其他工具使用：**
    - 容器已重启、需要上一轮日志 → 使用 get_kubernetes_previous_pod_logs
    - 查看当前轮日志 → 使用 get_kubernetes_pod_logs
    - 检查镜像拉取问题 → 查看events中的ImagePull相关错误
    - 资源不足 → 使用 get_kubernetes_node_capacity 检查节点容量
    - 怀疑探针误杀 → 使用 validate_probe_configuration
    - 需要重启恢复 → 使用 restart_pod
    - 卷挂载问题 → 使用 check_kubernetes_persistent_volumes
    """
    config, instance_error = prepare_point_instance(config, instance_name)
    if instance_error:
        return instance_error
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
        events = core_v1.list_namespaced_event(namespace, field_selector=f"involvedObject.name={pod_name},involvedObject.kind=Pod")

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
            "volumes": [],
        }

        # Pod条件
        if pod.status.conditions:
            for condition in pod.status.conditions:
                diagnosis["conditions"].append(
                    {
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message,
                        "last_transition_time": condition.last_transition_time.isoformat() if condition.last_transition_time else None,
                    }
                )

        # 容器状态
        if pod.status.container_statuses:
            for container in pod.status.container_statuses:
                container_info = {
                    "name": container.name,
                    "ready": container.ready,
                    "restart_count": container.restart_count,
                    "image": container.image,
                    "image_id": container.image_id,
                    "state": {},
                }

                if container.state.waiting:
                    container_info["state"] = {
                        "status": "waiting",
                        "reason": container.state.waiting.reason,
                        "message": container.state.waiting.message,
                    }
                elif container.state.running:
                    container_info["state"] = {
                        "status": "running",
                        "started_at": container.state.running.started_at.isoformat() if container.state.running.started_at else None,
                    }
                elif container.state.terminated:
                    container_info["state"] = {
                        "status": "terminated",
                        "reason": container.state.terminated.reason,
                        "exit_code": container.state.terminated.exit_code,
                        "started_at": container.state.terminated.started_at.isoformat() if container.state.terminated.started_at else None,
                        "finished_at": container.state.terminated.finished_at.isoformat() if container.state.terminated.finished_at else None,
                    }

                container_info["last_state"] = _container_last_state(container)
                diagnosis["containers"].append(container_info)

        # Init容器状态
        if pod.status.init_container_statuses:
            for init_container in pod.status.init_container_statuses:
                init_info = {
                    "name": init_container.name,
                    "ready": init_container.ready,
                    "restart_count": init_container.restart_count,
                    "image": init_container.image,
                    "state": {},
                }

                if init_container.state.waiting:
                    init_info["state"] = {
                        "status": "waiting",
                        "reason": init_container.state.waiting.reason,
                        "message": init_container.state.waiting.message,
                    }
                elif init_container.state.terminated:
                    init_info["state"] = {
                        "status": "terminated",
                        "reason": init_container.state.terminated.reason,
                        "exit_code": init_container.state.terminated.exit_code,
                    }

                init_info["last_state"] = _container_last_state(init_container)
                diagnosis["init_containers"].append(init_info)

        # 资源请求和限制
        if pod.spec.containers:
            for container in pod.spec.containers:
                if container.resources:
                    if container.resources.requests:
                        diagnosis["resource_requests"][container.name] = dict(container.resources.requests)
                    if container.resources.limits:
                        diagnosis["resource_limits"][container.name] = dict(container.resources.limits)

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
        for event in sorted(events.items, key=_event_sort_time, reverse=True)[:10]:
            diagnosis["recent_events"].append(
                {
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "count": event.count,
                    "last_timestamp": event.last_timestamp.isoformat() if event.last_timestamp else None,
                }
            )

        return json.dumps(diagnosis)
    except ApiException as e:
        return json.dumps({"error": f"诊断Pod失败: {str(e)}"})


def _pod_log_text(*, previous: bool, namespace, pod_name, container, lines, tail, config) -> str:
    """读取当前/上一轮日志正文。抽成模块函数便于测试替身，避免 patch StructuredTool.invoke。"""
    tool = get_kubernetes_previous_pod_logs if previous else get_kubernetes_pod_logs
    return tool.func(
        namespace=namespace,
        pod_name=pod_name,
        container=container,
        lines=lines,
        tail=tail,
        config=config,
    )


def _restart_log_slice(content: str, *, role: str) -> dict:
    text = str(content or "").strip()
    unavailable = (not text) or any(
        marker in text
        for marker in (
            "没有可用的 previous",
            "没有上一次实例的日志",
            "没有 previous 日志",
            "没有日志输出",
        )
    )
    return {
        "role": role,
        "available": not unavailable,
        "content": text,
    }


def _container_needs_current_tail(container, phase: str) -> bool:
    if str(phase or "") in {"Failed"}:
        return True
    if not getattr(container, "ready", True):
        return True
    state = getattr(container, "state", None)
    waiting = getattr(state, "waiting", None) if state is not None else None
    reason = str(getattr(waiting, "reason", "") or "")
    if reason in {"CrashLoopBackOff", "Error", "CreateContainerError"}:
        return True
    if getattr(state, "terminated", None) is not None:
        return True
    return False


def _pick_restart_container(statuses, container_name: str | None):
    items = list(statuses or [])
    if not items:
        return None
    if container_name:
        for item in items:
            if getattr(item, "name", None) == container_name:
                return item
        return None
    return max(items, key=lambda item: int(getattr(item, "restart_count", 0) or 0))


def _container_started_at(container) -> str | None:
    running = getattr(getattr(container, "state", None), "running", None)
    started = getattr(running, "started_at", None) if running is not None else None
    if started is None:
        terminated = getattr(getattr(container, "state", None), "terminated", None)
        started = getattr(terminated, "started_at", None) if terminated is not None else None
    return started.isoformat() if started else None


@tool()
def collect_pod_restart_evidence(
    namespace,
    pod_name,
    container=None,
    instance_name=None,
    config: RunnableConfig = None,
):
    """
    已知具体 Pod 时，采集重启原因取证包（时钟 + lastState + 事件 + 死前日志）。

    **何时使用此工具：**
    - 用户指定 namespace/pod，问为什么重启、频繁重启、重启原因
    - 不要用于告警 RCA、查看当前日志、按重启时间列 Top-N、配置巡检

    **工具能力：**
    - 区分 finishedAt（上一轮死亡/开始重启）与 startedAt（这一轮起来）
    - 默认取 previous 日志末尾（死前现场），不取当前轮「现在往前」的尾巴
    - 仅当容器当前未 Ready / CrashLoop 时才附加 current_tail
    - previous 不存在或为空是终态，不要再降 lines 或改拉当前尾巴

    Args:
        namespace (str): Pod 所在命名空间
        pod_name (str): Pod 名称
        container (str, optional): 多容器时指定；省略则取重启次数最高的容器
        instance_name (str, optional): 多实例时指定集群
        config (RunnableConfig): 工具配置
    """
    config, instance_error = prepare_point_instance(config, instance_name)
    if instance_error:
        return instance_error
    prepare_context(config)
    try:
        core_v1 = client.CoreV1Api()
        try:
            pod = core_v1.read_namespaced_pod(pod_name, namespace)
        except ApiException as e:
            if e.status == 404:
                return json.dumps({"error": f"Pod {pod_name} 在命名空间 {namespace} 中不存在"})
            raise

        statuses = list(getattr(pod.status, "container_statuses", None) or [])
        chosen = _pick_restart_container(statuses, container)
        if chosen is None and statuses:
            return json.dumps({"error": f"在 Pod {pod_name} 中找不到容器 {container}"})
        if chosen is None:
            return json.dumps(
                {
                    "pod_name": pod_name,
                    "namespace": namespace,
                    "phase": pod.status.phase,
                    "missing": ["container_status"],
                    "logs": {
                        "previous_tail": {"role": "previous_tail", "available": False, "content": "", "skipped": True, "why": "无容器状态"},
                        "current_tail": {"role": "current_tail", "available": False, "content": "", "skipped": True, "why": "无容器状态"},
                        "current_head": {"role": "current_head", "available": False, "content": "", "skipped": True, "why": "重启取证默认不取当前轮开头"},
                    },
                }
            )

        last_state = _container_last_state(chosen)
        restart_count = int(getattr(chosen, "restart_count", 0) or 0)
        clock = {
            "finished_at": last_state.get("finished_at"),
            "started_at": _container_started_at(chosen),
            "start_time_note": "pod.status.startTime 是首次上节点时间，容器重启通常不变，不当重启时间",
        }
        events = core_v1.list_namespaced_event(namespace, field_selector=f"involvedObject.name={pod_name},involvedObject.kind=Pod")
        recent_events = []
        for event in sorted(events.items, key=_event_sort_time, reverse=True)[:10]:
            recent_events.append(
                {
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "count": event.count,
                    "last_timestamp": event.last_timestamp.isoformat() if event.last_timestamp else None,
                }
            )

        container_name = chosen.name
        log_kwargs = {
            "namespace": namespace,
            "pod_name": pod_name,
            "container": container_name,
            "lines": 80,
            "tail": True,
            "config": config,
        }
        previous_tail = {
            "role": "previous_tail",
            "available": False,
            "content": "",
            "skipped": True,
            "why": "restart_count=0 且无 lastState，没有上一轮",
        }
        if restart_count > 0 or last_state:
            previous_tail = _restart_log_slice(
                _pod_log_text(previous=True, **log_kwargs),
                role="previous_tail",
            )
            previous_tail["skipped"] = False
            if not previous_tail["available"]:
                previous_tail["why"] = "kubelet 未保留 previous 日志，这是终态，不要改拉当前尾巴或降低 lines"

        current_tail = {
            "role": "current_tail",
            "available": False,
            "content": "",
            "skipped": True,
            "why": "当前已 Ready，尾巴是此刻日志，不是上一轮死因",
        }
        if _container_needs_current_tail(chosen, pod.status.phase):
            current_tail = _restart_log_slice(
                _pod_log_text(previous=False, **log_kwargs),
                role="current_tail",
            )
            current_tail["skipped"] = False
            current_tail["why"] = "当前未就绪或仍在 CrashLoop，附加此刻尾巴作对照，不是 finishedAt 现场"

        return json.dumps(
            {
                "pod_name": pod_name,
                "namespace": namespace,
                "container": container_name,
                "phase": pod.status.phase,
                "ready": bool(getattr(chosen, "ready", False)),
                "restart_count": restart_count,
                "restart_count_note": _RESTART_COUNT_NOTE,
                "clock": clock,
                "last_state": last_state,
                "events": recent_events,
                "logs": {
                    "previous_tail": previous_tail,
                    "current_tail": current_tail,
                    "current_head": {
                        "role": "current_head",
                        "available": False,
                        "content": "",
                        "skipped": True,
                        "why": "重启取证默认不取当前轮开头；问启动过程再调 get_kubernetes_pod_logs 且 tail=false",
                    },
                },
                "missing": [] if previous_tail.get("available") or previous_tail.get("skipped") else ["previous_container_logs"],
            }
        )
    except ApiException as e:
        return json.dumps({"error": f"采集 Pod 重启取证失败: {str(e)}"})
