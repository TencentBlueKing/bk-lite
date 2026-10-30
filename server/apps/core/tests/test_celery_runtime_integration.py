"""显式启用的真实 Redis / prefork 测试，所有服务均由本测试创建并清理。"""

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import redis
from celery import Celery

from apps.core.celery_runtime.config import POOL_IMPLEMENTATION, RuntimeConfig
from apps.core.celery_runtime.routing import configure_routes

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("CELERY_RUNTIME_INTEGRATION") != "1", reason="需要显式启用临时 Redis 集成测试"),
]
NAMES = {
    "critical": "apps.monitor.tasks.monitor_policy.scan_policy_task",
    "notification": "apps.alerts.tasks.tasks.sync_notify",
    "state": "apps.node_mgmt.tasks.action_task.converge_collector_action_task_for_node",
    "background": "apps.cmdb.tasks.celery_tasks.reconcile_instance_auto_association_task",
}


def eventually(check, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.2)
    raise AssertionError("临时运行环境未在期限内达到预期状态")


@pytest.fixture(scope="module")
def cluster(tmp_path_factory):
    executable = shutil.which("redis-server")
    if not executable:
        pytest.skip("redis-server 不可用")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    directory = tmp_path_factory.mktemp("celery-runtime")
    logs, processes = [], []
    client, app = None, None
    try:
        log = (directory / "redis.log").open("w")
        logs.append(log)
        processes.append(
            subprocess.Popen(
                [executable, "--bind", "127.0.0.1", "--port", str(port), "--save", "", "--appendonly", "no"],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        )
        broker = f"redis://127.0.0.1:{port}/0"
        client = redis.Redis.from_url(broker, socket_connect_timeout=1)

        def ready():
            try:
                return client.ping()
            except redis.ConnectionError:
                return False

        eventually(ready)
        env = dict(os.environ)
        env.pop("DJANGO_SETTINGS_MODULE", None)
        env.update(CELERY_TEST_BROKER=broker, AUTOSCALE_KEEPALIVE="2", ENABLE_CELERY="true", CELERY_TOTAL_CONCURRENCY_LIMIT="12")
        env.pop("CELERY_CONCURRENCY", None)
        for pool in NAMES:
            env[f"CELERY_{pool.upper()}_MIN"] = "1"
            env[f"CELERY_{pool.upper()}_MAX"] = "1" if pool == "background" else "2"
        config = RuntimeConfig.from_env(env)
        root = Path(__file__).resolve().parents[3]
        for pool in NAMES:
            command = config.worker_args(pool)
            command[1] = "apps.core.tests.celery_probe_app"
            log = (directory / f"{pool}.log").open("w")
            logs.append(log)
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-m", "celery", *command, "--without-gossip", "--without-mingle"],
                    cwd=root,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            )
        app = Celery("test_client", broker=broker, backend=broker, set_as_current=False)
        configure_routes(app)
        eventually(lambda: len(app.control.ping(timeout=1)) == 4, timeout=40)
        yield app, client, directory
    finally:
        if app:
            # 临时 broker 即将销毁，释放订阅引用，避免 AsyncResult 析构时重连已关闭服务。
            app.backend.result_consumer.stop()
            app.backend.result_consumer._pubsub = None
        # 只终止本测试创建的进程；生产 worker 不在测试范围内。
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if app:
            app.close()
        if client:
            client.close()
        for log in logs:
            log.close()


def test_other_pools_saturation_does_not_take_critical_slot(cluster):
    app, client, _ = cluster
    blocked = []
    for pool in ("state", "notification", "background"):
        count = 1 if pool == "background" else 2
        for index in range(count):
            marker = f"probe:{pool}:{index}"
            blocked.append(app.send_task(NAMES[pool], args=[8, marker]))
    eventually(
        lambda: all(
            client.exists(f"probe:{pool}:{i}") for pool, count in (("state", 2), ("notification", 2), ("background", 1)) for i in range(count)
        )
    )
    sent = time.time()
    result = app.send_task(NAMES["critical"]).get(timeout=5)
    assert result["worker"].startswith("critical@")
    assert result["started"] - sent < 5
    for item in blocked:
        assert not item.failed()
        item.get(timeout=20)


def test_autoscale_grows_and_shrinks_without_interrupting_busy_children(cluster):
    app, client, _ = cluster
    jobs = [app.send_task(NAMES["critical"], args=[6, f"scale:{i}"]) for i in range(2)]
    eventually(lambda: all(client.exists(f"scale:{i}") for i in range(2)))

    def current_capacity():
        stats = app.control.inspect(timeout=1).stats() or {}
        node = next((data for name, data in stats.items() if name.startswith("critical@")), {})
        if node:
            assert node["pool"]["implementation"] == POOL_IMPLEMENTATION
        return node.get("autoscaler", {}).get("current")

    assert current_capacity() == 2
    assert len({job.get(timeout=15)["pid"] for job in jobs}) == 2
    eventually(lambda: current_capacity() == 1, timeout=20)


def test_eta_retry_and_legacy_queue_have_consumers(cluster):
    app, _, _ = cluster
    sent = time.time()
    delayed = app.send_task(NAMES["critical"], countdown=2)
    legacy = app.send_task(NAMES["background"], queue="celery")
    retried = app.send_task("runtime_probe.retry")
    assert delayed.get(timeout=10)["started"] >= sent + 1.5
    assert legacy.get(timeout=5)["worker"].startswith("background@")
    assert retried.get(timeout=10)["retries"] == 1


def test_upstream_soft_time_limits_remain_effective(cluster):
    from billiard.exceptions import SoftTimeLimitExceeded

    app, _, _ = cluster
    for options in ({}, {"time_limit": 1, "soft_time_limit": 0.5}):
        result = app.send_task("runtime_probe.limited", **options)
        with pytest.raises(SoftTimeLimitExceeded):
            result.get(timeout=15)


def test_upstream_hard_timeout_and_child_recycling_survive_isolation(cluster):
    from billiard.exceptions import TimeLimitExceeded

    app, _, _ = cluster
    with pytest.raises(TimeLimitExceeded):
        app.send_task("runtime_probe.hard_limited").get(timeout=15)
    pids = [app.send_task(NAMES["background"]).get(timeout=15)["pid"] for _ in range(3)]
    assert len(set(pids)) >= 2
