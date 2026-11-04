"""临时Redis上的拓扑迁移演练，不加载或执行真实业务任务。"""

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
from celery.exceptions import TimeoutError

from apps.core.celery_runtime.config import RuntimeConfig
from apps.core.celery_runtime.routing import configure_routes
from apps.core.tests.test_celery_runtime_integration import NAMES, eventually

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("CELERY_RUNTIME_INTEGRATION") != "1", reason="需要显式启用临时Redis迁移演练"),
]


class MigrationLab:
    """仅管理自己创建的进程，通过公开Celery接口投递、巡检和等待结果。"""

    def __init__(self, directory, broker):
        self.directory = directory
        self.broker = broker
        self.processes = {}
        self.logs = []
        self.client = redis.Redis.from_url(broker, socket_connect_timeout=1)
        self.old = Celery("legacy_producer", broker=broker, backend=broker, fixups=[], set_as_current=False)
        self.new = Celery("classified_producer", broker=broker, backend=broker, fixups=[], set_as_current=False)
        configure_routes(self.new)

    def start(self, name, pool=None, queues="celery"):
        env = {key: value for key, value in os.environ.items() if not key.startswith("CELERY_")}
        env.pop("DJANGO_SETTINGS_MODULE", None)
        env.update(CELERY_TEST_BROKER=self.broker, AUTOSCALE_KEEPALIVE="2", ENABLE_CELERY="true")
        if pool:
            command = RuntimeConfig.from_env({"ENABLE_CELERY": "true"}).worker_args(pool)
            command[1] = "apps.core.tests.celery_probe_app"
        else:
            env["CELERY_PROBE_LEGACY"] = "1"
            command = [
                "-A",
                "apps.core.tests.celery_probe_app",
                "worker",
                "--pool=prefork",
                "--concurrency=1",
                "--prefetch-multiplier=1",
                "-Q",
                queues,
                "-n",
                f"{name}@%h",
                "--loglevel=info",
            ]
        log = (self.directory / f"{name}.log").open("w")
        self.logs.append(log)
        process = subprocess.Popen(
            [sys.executable, "-m", "celery", *command, "--without-gossip", "--without-mingle"],
            cwd=Path(__file__).resolve().parents[3],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        self.processes[name] = process

        def ready():
            assert process.poll() is None, f"{name}提前退出，请检查{log.name}"
            return any(node.startswith(name + "@") for reply in self.new.control.ping(timeout=0.5) for node in reply)

        eventually(ready, timeout=40)

    def start_new(self):
        for pool in NAMES:
            self.start(pool, pool=pool)

    def stop(self, name, release_key=None):
        process = self.processes[name]
        process.terminate()
        if release_key:
            time.sleep(0.2)
            assert process.poll() is None, "温和退出必须等待在途任务释放"
            self.client.set(release_key, "release", ex=60)
        assert process.wait(timeout=30) == 0, f"{name}未正常温和退出"

    def submit(self, producer, pool, marker, seconds=0, **options):
        return producer.send_task(NAMES[pool], args=[seconds, marker], **options)

    def completed_once(self, results):
        payloads = [result.get(timeout=30) for result in results]
        assert [item["id"] for item in payloads] == [result.id for result in results]
        assert all(item["executions"] == 1 for item in payloads)
        assert all(int(self.client.get(f"executions:{result.id}")) == 1 for result in results)
        return payloads

    def assert_drained(self):
        expected = {f"{name}@{socket.gethostname()}" for name, process in self.processes.items() if process.poll() is None}
        observed = {}

        def drained():
            inspector = self.new.control.inspect(timeout=2, destination=sorted(expected))
            complete = bool(expected)
            for method in ("active", "reserved", "scheduled"):
                response = getattr(inspector, method)() or {}
                observed[method] = {node: len(items) for node, items in response.items()}
                complete &= set(response) == expected and not any(response.values())
            observed["ready"] = {queue: self.client.llen(queue) for queue in (*NAMES, "celery")}
            return complete and not any(observed["ready"].values())

        try:
            eventually(drained)
        except AssertionError as exc:
            raise AssertionError(f"未确认所有存活worker和队列排空：expected={sorted(expected)} observed={observed}") from exc

    def close(self):
        try:
            for name, process in reversed(list(self.processes.items())):
                if process.poll() is None:
                    try:
                        self.stop(name)
                    except (AssertionError, subprocess.TimeoutExpired):
                        process.kill()
                        process.wait(timeout=5)
        finally:
            for app in (self.old, self.new):
                app.backend.result_consumer.stop()
                app.backend.result_consumer._pubsub = None
                app.close()
            self.client.close()
            for log in self.logs:
                log.close()


@pytest.fixture
def migration_lab(tmp_path):
    executable = shutil.which("redis-server")
    if not executable:
        pytest.skip("redis-server不可用")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (tmp_path / "redis.log").open("w") as output:
        process = subprocess.Popen(
            [executable, "--bind", "127.0.0.1", "--port", str(port), "--save", "", "--appendonly", "no"],
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        lab = MigrationLab(tmp_path, f"redis://127.0.0.1:{port}/0")
        try:

            def ready():
                try:
                    return lab.client.ping()
                except redis.ConnectionError:
                    return False

            eventually(ready)
            yield lab
        finally:
            lab.close()
            process.terminate()
            process.wait(timeout=5)


def test_migration_drains_legacy_backlog_and_active_task_with_mixed_producers(migration_lab):
    lab = migration_lab
    lab.start("legacy")
    busy = lab.submit(lab.old, "background", "legacy-active", kwargs={"release_key": "release-legacy"})
    eventually(lambda: lab.client.exists("legacy-active"))
    backlog = [lab.submit(lab.old, "critical", f"legacy-backlog:{i}") for i in range(8)]
    assert lab.client.llen("celery") > 0

    # 新消费者就绪后才允许新生产者投递；迁移期两种生产者并存。
    lab.start_new()
    fresh = [lab.submit(lab.new, pool, f"classified:{pool}") for pool in NAMES]
    mixed = lab.submit(lab.old, "state", "mixed-legacy")
    assert not busy.ready()
    lab.stop("legacy", release_key="release-legacy")
    old_payloads = lab.completed_once([busy, *backlog, mixed])
    assert old_payloads[0]["worker"].startswith("legacy@")
    assert any(item["worker"].startswith("background@") for item in old_payloads[1:])
    for pool, payload in zip(NAMES, lab.completed_once(fresh)):
        assert payload["worker"].startswith(pool + "@")
    lab.assert_drained()


def test_default_only_rollback_leaves_classified_message_pending_until_consumer_added(migration_lab):
    lab = migration_lab
    lab.start("rollback")
    result = lab.submit(lab.new, "critical", "stranded-after-image-rollback")
    with pytest.raises(TimeoutError):
        result.get(timeout=1)
    assert lab.client.llen("critical") == 1
    nodes = lab.new.control.inspect(timeout=1).registered()
    node = next(name for name in nodes if name.startswith("rollback@"))
    assert NAMES["critical"] in nodes[node]
    # 回退worker必须接管新队列；不重投、不改任务ID、不清空消息。
    lab.new.control.add_consumer("critical", destination=[node], reply=True)
    assert lab.completed_once([result])[0]["worker"].startswith("rollback@")
    lab.assert_drained()


def test_rollback_preserves_active_eta_retry_and_all_classified_backlogs(migration_lab):
    lab = migration_lab
    lab.start_new()
    busy = lab.submit(lab.new, "critical", "rollback-active", kwargs={"release_key": "release-critical"})
    eventually(lambda: lab.client.exists("rollback-active"))
    published = time.time()
    eta = lab.submit(lab.new, "critical", "rollback-eta", countdown=20)
    retry = lab.new.send_task("runtime_probe.retry", args=[20, "rollback-retry"], queue="notification")

    def scheduled_ids():
        scheduled = lab.new.control.inspect(timeout=0.5).scheduled() or {}
        return {item["request"]["id"] for items in scheduled.values() for item in items}

    eventually(lambda: {eta.id, retry.id} <= scheduled_ids())
    lab.start("rollback", queues="critical,notification,state,background,celery")
    registered = lab.new.control.inspect(timeout=1).registered()
    old_node = next(name for name in registered if name.startswith("rollback@"))
    assert set(NAMES.values()) | {"runtime_probe.retry"} <= set(registered[old_node])
    assert not busy.ready(), "演练必须在任务仍执行时开始温和退出"
    for pool in NAMES:
        lab.stop(pool, release_key="release-critical" if pool == "critical" else None)
    assert lab.completed_once([busy])[0]["worker"].startswith("critical@")

    # 模拟回退后仍有新版本生产者短暂存活，同时旧生产者恢复默认路由。
    backlog = [lab.submit(lab.new, pool, f"rollback-backlog:{pool}:{i}") for pool in NAMES for i in range(2)]
    legacy = lab.submit(lab.old, "state", "rolled-back-producer")
    payloads = lab.completed_once([eta, *backlog, legacy])
    assert all(item["worker"].startswith("rollback@") for item in payloads)
    assert payloads[0]["started"] >= published + 19
    retried = retry.get(timeout=30)
    assert retried["retries"] == 1
    assert retried["worker"].startswith("rollback@")
    assert retried["id"] == retry.id
    assert retried["executions"] == int(lab.client.get(f"executions:{retry.id}")) == 2
    assert retried["started"] >= published + 19
    lab.assert_drained()
