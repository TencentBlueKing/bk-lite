"""隔离测试专用任务，绝不加载业务应用或访问外部主机。"""

import os
import sys
import time

import billiard
import redis
from celery import Celery, current_task

from apps.core.celery_runtime.observation import install_observer
from apps.core.celery_runtime.routing import configure_routes

broker = os.environ["CELERY_TEST_BROKER"]
if not broker.startswith("redis://127.0.0.1:"):
    raise ValueError("架构探针只允许本机临时 Redis")
# macOS 默认 spawn 不等同目标 Linux prefork；仅在不加载业务的专用探针中选 fork。
if sys.platform == "darwin":
    billiard.set_start_method("fork", force=True)
app = Celery("runtime_probe", broker=broker, backend=broker)
configure_routes(app)
app.conf.worker_max_tasks_per_child = 2
observer = install_observer()

NAMES = {
    "critical": "apps.monitor.tasks.monitor_policy.scan_policy_task",
    "notification": "apps.alerts.tasks.tasks.sync_notify",
    "state": "apps.node_mgmt.tasks.action_task.converge_collector_action_task_for_node",
    "background": "apps.cmdb.tasks.celery_tasks.reconcile_instance_auto_association_task",
}


def probe(seconds=0, marker=None):
    client = redis.Redis.from_url(broker)
    started = time.time()
    if marker:
        client.set(marker, "started", ex=60)
    time.sleep(seconds)
    client.close()
    return {"worker": current_task.request.hostname, "pid": os.getpid(), "started": started}


for name in NAMES.values():
    app.task(name=name, shared=False)(probe)


@app.task(bind=True, name="runtime_probe.retry", shared=False, max_retries=1)
def retry_probe(self):
    if not self.request.retries:
        raise self.retry(countdown=1)
    return {"retries": self.request.retries, "worker": self.request.hostname}


@app.task(bind=True, name="runtime_probe.limited", shared=False, time_limit=2, soft_time_limit=1)
def limited_probe(self):
    time.sleep(3)
    return {"declared": [self.time_limit, self.soft_time_limit], "message_limits": self.request.timelimit}


@app.task(name="runtime_probe.hard_limited", shared=False, time_limit=1)
def hard_limited_probe():
    time.sleep(5)
