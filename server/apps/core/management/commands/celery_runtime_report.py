import json
import os
from dataclasses import asdict

import celery
import kombu
from celery import current_app
from django.core.management.base import BaseCommand, CommandError
from django_celery_beat.models import PeriodicTask

from apps.core.celery_runtime import inspect_registry
from apps.core.celery_runtime.config import POOL_IMPLEMENTATION, POOL_QUEUES, RuntimeConfig
from apps.core.celery_runtime.diagnostics import (
    inactive_limit_declarations,
    memory_report,
    periodic_report,
    prefork_issues,
    ready_report,
    worker_report,
)
from apps.core.celery_runtime.manifest import TASK_ROUTES


class Command(BaseCommand):
    help = "只读检查任务注册、Beat 有效路由、消费池与资源；不输出参数或 broker 凭据"

    def add_arguments(self, parser):
        parser.add_argument("--workers", action="store_true", help="同时查询 worker 摘要与 Redis ready 数量")
        parser.add_argument("--timeout", type=float, default=3)
        parser.add_argument("--strict", action="store_true", help="路由/配置/消费者异常时退出非零，需配合 --workers")

    def handle(self, *args, **options):
        if not 0 < options["timeout"] <= 30 or (options["strict"] and not options["workers"]):
            raise CommandError("timeout 必须为 (0,30]；strict 需要 --workers")
        errors = []
        try:
            config = RuntimeConfig.from_env()
            config_report = asdict(config)
        except ValueError as exc:
            config = None
            config_report = None
            errors.append(str(exc))
        # 命令入口在 core.celery 中排除自动同步周期表；此处仅注册定义。
        registered = {name for name in inspect_registry(current_app) if not name.startswith("celery.")}
        periodic = periodic_report(
            current_app, PeriodicTask.objects.filter(enabled=True).only("id", "task", "queue", "exchange", "routing_key"), registered
        )
        unmapped = sorted(registered - TASK_ROUTES.keys())
        if unmapped:
            errors.append("存在未分类的已注册任务")
        if any(row["issues"] for row in periodic):
            errors.append("周期任务存在注册/路由冲突")
        limits = prefork_issues(current_app)
        if limits:
            errors.append("执行池缺少 threads 行为兼容层")
        report = {
            "versions": {"celery": celery.__version__, "kombu": kombu.__version__},
            "install_apps": os.getenv("INSTALL_APPS", ""),
            "config": config_report,
            "memory": memory_report(),
            "registered": sorted(registered),
            "unmapped": unmapped,
            "periodic": periodic,
            "prefork_semantics_review": limits,
            "inactive_limit_declarations": inactive_limit_declarations(current_app),
            "limitations": [
                "任务声明保留；兼容池保持 threads 行为，不启用执行池超时/按任务数或内存回收",
                "本报告不证明生产容量或任务 fork 兼容性",
                "最老等待年龄、时延分位数及速率需关联生命周期日志；未采集时未知",
            ],
        }
        if options["workers"]:
            workers = worker_report(current_app.control.inspect(timeout=options["timeout"]))
            report["runtime"] = workers
            report["broker"] = ready_report(current_app)
            expected = config.replicas if config and config.pools else 0
            if workers["unavailable"] or any(count != expected for count in workers["queue_consumers"].values()):
                errors.append("worker 回复缺失或消费者数量不符合部署声明")
            for node, worker in workers["workers"].items():
                expected_pool = next((pool for pool in config.pools if node.startswith(pool.name + "@")), None) if config else None
                if expected_pool is None or worker["capacity"]["max"] != expected_pool.maximum or worker["capacity"]["min"] != expected_pool.minimum:
                    errors.append("worker 身份或实际伸缩范围不符合配置")
                elif set(worker["queues"]) != set(POOL_QUEUES[expected_pool.name]):
                    errors.append("worker 消费队列越过了执行池边界")
                elif worker.get("pool_implementation") != POOL_IMPLEMENTATION:
                    errors.append("worker 未使用受控执行池，可能隐式启用超时行为")
                else:
                    required = {name for name in registered if TASK_ROUTES.get(name, "celery") in POOL_QUEUES[expected_pool.name]}
                    if worker["registered"] is None or required - set(worker["registered"]):
                        errors.append("worker 注册集缺少该池目标任务，不能切换生产者路由")
        report["errors"] = errors
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        if options["strict"] and errors:
            raise CommandError("Celery 运行检查未通过，详见 JSON 摘要")
