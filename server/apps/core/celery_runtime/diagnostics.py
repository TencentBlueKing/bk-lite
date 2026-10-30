"""只读诊断：白名单输出，避免 inspect 原始载荷泄露任务参数。"""

from pathlib import Path

from apps.core.celery_runtime.config import POOL_IMPLEMENTATION
from apps.core.celery_runtime.manifest import TASK_ROUTES
from apps.core.celery_runtime.routing import QUEUE_NAMES


def prefork_issues(app):
    if app.conf.worker_pool != POOL_IMPLEMENTATION:
        return [{"setting": "worker_pool", "required": POOL_IMPLEMENTATION}]
    return []


def inactive_limit_declarations(app):
    issues = []
    for name, task in sorted(app.tasks.items()):
        if task.time_limit or task.soft_time_limit:
            issues.append({"task": name, "time_limit": task.time_limit, "soft_time_limit": task.soft_time_limit})
    for key in ("task_time_limit", "task_soft_time_limit", "worker_max_tasks_per_child", "worker_max_memory_per_child"):
        value = getattr(app.conf, key, None)
        if value:
            issues.append({"setting": key, "value": value})
    return issues


def periodic_report(app, rows, registered):
    report = []
    for row in rows:
        options = {key: getattr(row, key) for key in ("queue", "exchange", "routing_key") if getattr(row, key)}
        issues = []
        expected = TASK_ROUTES.get(row.task)
        if row.task not in registered:
            issues.append("unregistered")
        if expected is None:
            issues.append("unmapped")
        try:
            route = app.amqp.router.route(options, row.task)
            queue = route["queue"]
            effective = {
                "queue": queue.name,
                "exchange": route.get("exchange", queue.exchange.name),
                "routing_key": route.get("routing_key", queue.routing_key),
            }
            if expected and any(value != expected for value in effective.values()):
                issues.append("route_conflict")
        except Exception:
            effective = None
            issues.append("route_unavailable")
        report.append({"id": row.pk, "task": row.task, "expected_queue": expected, "effective": effective, "issues": issues})
    return report


def worker_report(inspector):
    responses, unavailable = {}, []
    for method in ("active", "reserved", "scheduled", "active_queues", "stats", "registered"):
        try:
            response = getattr(inspector, method)()
        except Exception:
            response = None
        if not response:
            unavailable.append(method)
        responses[method] = response or {}
    workers = {}
    consumers = {queue: 0 for queue in QUEUE_NAMES}
    for node in set().union(*(response.keys() for response in responses.values())):
        unavailable.extend(f"{node}:{method}" for method, response in responses.items() if node not in response)
        queues = [item["name"] for item in responses["active_queues"].get(node, [])]
        for queue in set(queues) & set(QUEUE_NAMES):
            consumers[queue] += 1
        stats = responses["stats"].get(node, {})
        autoscaler = stats.get("autoscaler", {})
        workers[node] = {
            "queues": queues,
            "registered": [name.split(" ", 1)[0] for name in responses["registered"][node]] if node in responses["registered"] else None,
            **{method: len(responses[method][node]) if node in responses[method] else None for method in ("active", "reserved", "scheduled")},
            "capacity": {key: autoscaler.get(key) for key in ("min", "max", "current", "qty")},
            "child_processes": len(stats.get("pool", {}).get("processes", [])) if "pool" in stats else None,
            "maxrss_platform_units": stats.get("rusage", {}).get("maxrss"),
            "pool_implementation": stats.get("pool", {}).get("implementation"),
        }
    return {"workers": workers, "queue_consumers": consumers, "unavailable": unavailable}


def ready_report(app):
    """Redis 的 _size 聚合优先级子列表；不消费、不声明或创建队列。"""
    result = {queue: None for queue in QUEUE_NAMES}
    try:
        with app.connection_for_read(connect_timeout=3) as connection:
            if connection.transport.driver_type != "redis":
                return {"ready": result, "scope": "非 Redis，请使用 broker 自带只读监控"}
            with connection.channel() as channel:
                for queue in QUEUE_NAMES:
                    result[queue] = channel._size(queue)
    except Exception:
        return {"ready": result, "scope": "broker 读取不可用；未知值不是零"}
    return {"ready": result, "scope": "Redis 优先级列表之和，不含 unacked、active、reserved、scheduled；各计数不保证互斥"}


def memory_report():
    result = {}
    for key, path in (
        ("cgroup_current_bytes", "/sys/fs/cgroup/memory.current"),
        ("cgroup_limit_bytes", "/sys/fs/cgroup/memory.max"),
        ("host_mem_available_kib", "/proc/meminfo"),
    ):
        try:
            content = Path(path).read_text()
            if key == "host_mem_available_kib":
                value = next(line.split()[1] for line in content.splitlines() if line.startswith("MemAvailable:"))
            else:
                value = content.strip()
            result[key] = int(value) if value.isdigit() else None
        except (OSError, StopIteration, ValueError):
            result[key] = None
    return result
