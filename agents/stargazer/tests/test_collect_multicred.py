import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _import_snmp_topo_with_stubbed_sanic_log(monkeypatch):
    sanic_module = types.ModuleType("sanic")
    sanic_module.__path__ = []
    sanic_log_module = types.ModuleType("sanic.log")
    sanic_log_module.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    sanic_module.log = sanic_log_module

    monkeypatch.setitem(sys.modules, "sanic", sanic_module)
    monkeypatch.setitem(sys.modules, "sanic.log", sanic_log_module)
    monkeypatch.delitem(sys.modules, "plugins.inputs.network_topo.snmp_topo", raising=False)

    return importlib.import_module("plugins.inputs.network_topo.snmp_topo")


def _import_snmp_facts_with_stubbed_deps(monkeypatch):
    sanic_module = types.ModuleType("sanic")
    sanic_module.__path__ = []
    sanic_log_module = types.ModuleType("sanic.log")
    sanic_log_module.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    sanic_module.log = sanic_log_module

    cmdgen_module = types.ModuleType("pysnmp.entity.rfc3413.oneliner.cmdgen")
    cmdgen_module.CommunityData = lambda *args, **kwargs: ("community", args, kwargs)
    cmdgen_module.UsmUserData = lambda *args, **kwargs: ("usm", args, kwargs)
    cmdgen_module.CommandGenerator = lambda *args, **kwargs: types.SimpleNamespace()
    cmdgen_module.UdpTransportTarget = lambda *args, **kwargs: ("udp", args, kwargs)
    cmdgen_module.MibVariable = lambda *args, **kwargs: ("mib", args, kwargs)

    pysnmp_module = types.ModuleType("pysnmp")
    entity_module = types.ModuleType("pysnmp.entity")
    rfc3413_module = types.ModuleType("pysnmp.entity.rfc3413")
    oneliner_module = types.ModuleType("pysnmp.entity.rfc3413.oneliner")
    oneliner_module.cmdgen = cmdgen_module

    proto_module = types.ModuleType("pysnmp.proto")
    rfc1905_module = types.ModuleType("pysnmp.proto.rfc1905")
    rfc1905_module.EndOfMibView = type("EndOfMibView", (), {})
    rfc1905_module.endOfMibView = object()

    hlapi_module = types.ModuleType("pysnmp.hlapi")
    hlapi_module.usmHMACSHAAuthProtocol = object()
    hlapi_module.usmHMACMD5AuthProtocol = object()
    hlapi_module.usmAesCfb128Protocol = object()
    hlapi_module.usmDESPrivProtocol = object()

    monkeypatch.setitem(sys.modules, "sanic", sanic_module)
    monkeypatch.setitem(sys.modules, "sanic.log", sanic_log_module)
    monkeypatch.setitem(sys.modules, "pysnmp", pysnmp_module)
    monkeypatch.setitem(sys.modules, "pysnmp.entity", entity_module)
    monkeypatch.setitem(sys.modules, "pysnmp.entity.rfc3413", rfc3413_module)
    monkeypatch.setitem(sys.modules, "pysnmp.entity.rfc3413.oneliner", oneliner_module)
    monkeypatch.setitem(sys.modules, "pysnmp.entity.rfc3413.oneliner.cmdgen", cmdgen_module)
    monkeypatch.setitem(sys.modules, "pysnmp.proto", proto_module)
    monkeypatch.setitem(sys.modules, "pysnmp.proto.rfc1905", rfc1905_module)
    monkeypatch.setitem(sys.modules, "pysnmp.hlapi", hlapi_module)
    monkeypatch.delitem(sys.modules, "plugins.inputs.network.snmp_facts", raising=False)
    monkeypatch.delitem(sys.modules, "plugins.inputs.network_topo.snmp_topo", raising=False)

    return importlib.import_module("plugins.inputs.network.snmp_facts")


def test_generate_task_id_distinguishes_credential_id():
    from core.task_queue import TaskQueue

    queue = TaskQueue()
    base_params = {
        "plugin_name": "mysql_info",
        "host": "10.0.0.1",
        "port": 3306,
        "tags": {"instance_id": "cmdb_1"},
    }

    first_task_id = queue._generate_task_id({**base_params, "credential_id": "cred-1"})
    second_task_id = queue._generate_task_id({**base_params, "credential_id": "cred-2"})

    assert first_task_id != second_task_id


def test_generate_dedupe_key_is_stable_for_host_remote_tasks():
    from core.task_queue import TaskQueue

    queue = TaskQueue()
    params = {
        "monitor_type": "host",
        "host": "10.0.0.8",
        "port": 22,
        "tags": {"instance_id": "cmdb_host_1"},
        "collect_type": "http",
    }

    assert queue._generate_dedupe_key(params) == queue._generate_dedupe_key(params)
    assert queue._generate_dedupe_key(params).startswith("collect_host_")


@pytest.mark.asyncio
async def test_enqueue_collect_task_skips_when_dedupe_job_is_still_queued():
    from core.task_queue import TaskQueue

    class ExistingJobPool:
        def __init__(self):
            self.enqueued = []
            self.values = {}

        async def get(self, key):
            return self.values.get(key)

        async def zscore(self, key, value):
            if key == "arq:queue" and value == "job-existing":
                return 1
            return None

        async def exists(self, key):
            return 0

        async def ttl(self, key):
            return 86399 if key.startswith("task:dedupe:") else -2

        async def delete(self, key):
            self.values.pop(key, None)

        async def enqueue_job(self, *args, **kwargs):
            self.enqueued.append((args, kwargs))
            return types.SimpleNamespace(job_id="job-new")

        async def set(self, key, value, ex=None):
            self.values[key] = value

    queue = TaskQueue()
    queue.pool = ExistingJobPool()
    queue._is_healthy = True
    params = {
        "monitor_type": "windows_wmi",
        "host": "10.0.0.8",
        "tags": {"instance_id": "cmdb_host_1"},
        "collect_type": "http",
    }
    dedupe_key = queue._generate_dedupe_key(params)
    queue.pool.values[f"task:dedupe:{dedupe_key}"] = "job-existing"

    result = await queue.enqueue_collect_task(params)

    assert result["status"] == "skipped"
    assert result["reason"] == "Task already queued or running for dedupe key"
    assert result["job_id"] == "job-existing"
    assert queue.pool.enqueued == []


@pytest.mark.asyncio
async def test_enqueue_collect_task_clears_stale_dedupe_and_requeues():
    from core.task_queue import TaskQueue

    class StaleJobPool:
        def __init__(self):
            self.enqueued = []
            self.values = {}
            self.deleted = []

        async def get(self, key):
            return self.values.get(key)

        async def zscore(self, key, value):
            return None

        async def exists(self, key):
            return 0

        async def ttl(self, key):
            return 86399

        async def delete(self, key):
            self.deleted.append(key)
            self.values.pop(key, None)

        async def enqueue_job(self, *args, **kwargs):
            self.enqueued.append((args, kwargs))
            return types.SimpleNamespace(job_id="job-new")

        async def set(self, key, value, ex=None):
            self.values[key] = value

    queue = TaskQueue()
    queue.pool = StaleJobPool()
    queue._is_healthy = True
    params = {
        "plugin_name": "vmware_info",
        "model_id": "vmware_vc",
        "host": "10.0.0.8",
        "tags": {"instance_id": "cmdb_vc_1"},
        "collect_task_id": "collect-1",
    }
    dedupe_key = queue._generate_dedupe_key(params)
    queue.pool.values[f"task:dedupe:{dedupe_key}"] = "job-missing"

    result = await queue.enqueue_collect_task(params)

    assert result["status"] == "queued"
    assert result["job_id"] == "job-new"
    assert f"task:dedupe:{dedupe_key}" in queue.pool.deleted
    assert queue.pool.values[f"task:dedupe:{dedupe_key}"] == "job-new"
    assert len(queue.pool.enqueued) == 1


def test_expand_collect_tasks_supports_credentials_pool_and_hosts():
    from api.collect import _build_collect_task_candidates, _expand_collect_tasks

    task_params = {
        "collect_task_id": 100,
        "plugin_name": "mysql_info",
        "model_id": "mysql",
        "tags": {"instance_id": "cmdb_1"},
    }
    credentials_pool = [
        {"credential_id": "cred-1", "username": "admin", "password": "first"},
        {"credential_id": "cred-2", "username": "ops", "password": "second"},
    ]

    candidates = _build_collect_task_candidates(task_params, ["10.0.0.1", "10.0.0.2"], credentials_pool)
    assert [candidate["credential_id"] for candidate in candidates["10.0.0.1"]] == ["cred-1", "cred-2"]

    tasks = _expand_collect_tasks(task_params, ["10.0.0.1", "10.0.0.2"], credentials_pool)

    assert len(tasks) == 2
    assert tasks[0]["host"] == "10.0.0.1"
    assert tasks[0]["credential_id"] == "cred-1"
    assert tasks[0]["credential_index"] == 0
    assert tasks[0]["credentials_pool"] == credentials_pool
    assert tasks[1]["host"] == "10.0.0.2"
    assert tasks[1]["credential_id"] == "cred-1"


def test_expand_collect_tasks_prefers_cached_success_and_skips_cooled_credentials():
    from api.collect import _expand_collect_tasks

    task_params = {
        "collect_task_id": 100,
        "plugin_name": "mysql_info",
        "model_id": "mysql",
        "tags": {"instance_id": "cmdb_1"},
    }
    credentials_pool = [
        {"credential_id": "cred-1", "username": "admin", "password": "first"},
        {"credential_id": "cred-2", "username": "ops", "password": "second"},
        {"credential_id": "cred-3", "username": "dba", "password": "third"},
    ]

    cache_state = {
        ("100", "10.0.0.1", "success"): "cred-2",
        ("100", "10.0.0.2", "cred-1"): {"is_cooled": True},
        ("100", "10.0.0.2", "cred-2"): {"is_cooled": True},
    }

    tasks = _expand_collect_tasks(
        task_params,
        ["10.0.0.1", "10.0.0.2"],
        credentials_pool,
        cache_state_getter=lambda collect_task_id, host, credential_id=None: cache_state.get(
            (str(collect_task_id), host, credential_id or "success")
        ),
    )

    assert len(tasks) == 2
    assert tasks[0]["host"] == "10.0.0.1"
    assert tasks[0]["credential_id"] == "cred-2"
    assert tasks[0]["credential_index"] == 1
    assert tasks[1]["host"] == "10.0.0.2"
    assert tasks[1]["credential_id"] == "cred-3"
    assert tasks[1]["credential_index"] == 2


def test_expand_collect_tasks_async_reads_runtime_cache_state():
    from api.collect import _expand_collect_tasks_async

    task_params = {
        "collect_task_id": 100,
        "plugin_name": "mysql_info",
        "model_id": "mysql",
        "tags": {"instance_id": "cmdb_1"},
    }
    credentials_pool = [
        {"credential_id": "cred-1", "username": "admin", "password": "first"},
        {"credential_id": "cred-2", "username": "ops", "password": "second"},
        {"credential_id": "cred-3", "username": "dba", "password": "third"},
    ]

    async def cache_state_getter(collect_task_id, host, credential_id=None):
        cache_state = {
            ("100", "10.0.0.1", "success"): "cred-2",
            ("100", "10.0.0.2", "cred-1"): {"is_cooled": True},
        }
        return cache_state.get((str(collect_task_id), host, credential_id or "success"))

    tasks = asyncio.run(
        _expand_collect_tasks_async(
            task_params,
            ["10.0.0.1", "10.0.0.2"],
            credentials_pool,
            cache_state_getter=cache_state_getter,
        )
    )

    assert [task["credential_id"] for task in tasks] == ["cred-2", "cred-2"]


def test_expand_collect_tasks_async_does_not_reuse_cached_success_when_it_is_cooled():
    from api.collect import _expand_collect_tasks_async

    task_params = {
        "collect_task_id": 100,
        "plugin_name": "mysql_info",
        "model_id": "mysql",
        "tags": {"instance_id": "cmdb_1"},
    }
    credentials_pool = [
        {"credential_id": "cred-1", "username": "admin", "password": "first"},
        {"credential_id": "cred-2", "username": "ops", "password": "second"},
        {"credential_id": "cred-3", "username": "dba", "password": "third"},
    ]

    async def cache_state_getter(collect_task_id, host, credential_id=None):
        cache_state = {
            ("100", "10.0.0.1", "success"): "cred-2",
            ("100", "10.0.0.1", "cred-2"): {"is_cooled": True},
        }
        return cache_state.get((str(collect_task_id), host, credential_id or "success"))

    tasks = asyncio.run(
        _expand_collect_tasks_async(
            task_params,
            ["10.0.0.1"],
            credentials_pool,
            cache_state_getter=cache_state_getter,
        )
    )

    assert [task["credential_id"] for task in tasks] == ["cred-1"]


def test_cooldown_hours_escalates_by_failure_count():
    from tasks.handlers.plugin_handler import _cooldown_hours_for_failure

    assert _cooldown_hours_for_failure(1) == 1
    assert _cooldown_hours_for_failure(2) == 4
    assert _cooldown_hours_for_failure(3) == 24
    assert _cooldown_hours_for_failure(7) == 24


def test_classify_failure_kind_cools_connection_unreachable_only():
    from tasks.handlers.plugin_handler import _classify_failure_kind

    # 连接不可达（假 IP / 拨号失败 / 拒绝 / 路由不可达）→ 冷却
    assert _classify_failure_kind("TCP connect timed out after 5s") == "unreachable"
    assert _classify_failure_kind("TCP connect failed: connection refused") == "unreachable"
    assert _classify_failure_kind("SSH dial timed out after 15s") == "unreachable"
    assert _classify_failure_kind("TCP connect failed: dial tcp 10.0.0.5:22: no route to host") == "unreachable"
    assert _classify_failure_kind("network is unreachable") == "unreachable"
    # 刻意排除：executor 无响应 / 已连上但执行超时 → 仍归 task，不冷却
    assert _classify_failure_kind("nats: timeout") == "task"
    assert _classify_failure_kind("no responders available for request") == "task"
    assert _classify_failure_kind("SSH execution timed out after 9.8s (timeout: 10s)") == "task"
    # 认证类失败仍归为 credential（优先级高于不可达）
    assert _classify_failure_kind("SSH authentication failed: ...") == "credential"
    assert _classify_failure_kind("permission denied (publickey,password)") == "credential"
    # 其它任务类失败仍归为 task，不冷却
    assert _classify_failure_kind("docker command not found") == "task"
    assert _classify_failure_kind("") == "task"


def test_failed_metrics_payload_detected_and_classified():
    from tasks.handlers.plugin_handler import _build_credential_execution_result

    prom_unreachable = (
        "# HELP docker_info Auto-generated help for docker_info\n# TYPE docker_info gauge\n"
        'docker_info{bk_obj_id="docker",collect_error="TCP connect timed out after 2.999995535s",'
        'collect_status="failed",host="10.11.27.115",model_id="docker"} 1 1749470000000\n'
    )
    res = _build_credential_execution_result({"host": "10.11.27.115", "credential_id": "cred-1", "model_id": "docker"}, prom_unreachable)
    assert res["success"] is False
    assert res["failure_kind"] == "unreachable"
    assert "timed out" in res["error_message"].lower()

    prom_auth = (
        'docker_info{bk_obj_id="docker",collect_error="SSH authentication failed: ssh: handshake failed: '
        'ssh: unable to authenticate",collect_status="failed",host="10.11.27.113",model_id="docker"} 1 1749470000000\n'
    )
    res2 = _build_credential_execution_result({"host": "10.11.27.113", "credential_id": "cred-1", "model_id": "docker"}, prom_auth)
    assert res2["success"] is False
    assert res2["failure_kind"] == "credential"

    prom_ok = (
        'docker_info{bk_obj_id="docker",collect_status="success",host="10.11.27.120",'
        'inst_name="10.11.27.120_abc",model_id="docker"} 1 1749470000000\n'
    )
    res3 = _build_credential_execution_result({"host": "10.11.27.120", "credential_id": "cred-1", "model_id": "docker"}, prom_ok)
    assert res3["success"] is True


class _RecordingCache:
    def __init__(self):
        self.mark_failure_calls = []
        self.mark_success_calls = []

    async def append_result_event(self, event):
        pass

    async def mark_success(self, collect_task_id, host, credential_id):
        self.mark_success_calls.append((host, credential_id))

    async def clear_success(self, collect_task_id, host):
        pass

    async def mark_failure(self, collect_task_id, host, credential_id, error_message, cooldown_level, consecutive_failures, next_retry_at):
        self.mark_failure_calls.append((host, credential_id, cooldown_level))

    async def get_failure_state(self, collect_task_id, host, credential_id):
        return {"is_cooled": True}


def test_handle_multicred_post_execute_cools_unreachable_failure():
    from tasks.handlers.plugin_handler import _handle_multicred_post_execute

    cache = _RecordingCache()
    params = {
        "collect_task_id": "task-1",
        "host": "10.0.0.99",
        "credential_id": "cred-1",
        "credential_index": 0,
        "credentials_pool": [
            {"credential_id": "cred-1"},
            {"credential_id": "cred-2"},
        ],
    }
    execution_result = {
        "success": False,
        "failure_kind": "unreachable",
        "error_message": "TCP connect timed out after 5s",
    }
    asyncio.run(_handle_multicred_post_execute(params, "tid", execution_result, cache, lambda: None))
    assert cache.mark_failure_calls == [("10.0.0.99", "cred-1", 1)]


def test_handle_multicred_post_execute_logs_cooldown_write():
    from tasks.handlers import plugin_handler

    records = []

    class _FakeLogger:
        def info(self, msg, *a, **k):
            records.append(str(msg))

        def warning(self, *a, **k):
            pass

        def error(self, *a, **k):
            pass

        def debug(self, *a, **k):
            pass

    original_logger = plugin_handler.logger
    plugin_handler.logger = _FakeLogger()
    try:
        cache = _RecordingCache()
        params = {
            "collect_task_id": "task-1",
            "host": "10.0.0.7",
            "credential_id": "cred-1",
            "credential_index": 0,
            "credentials_pool": [{"credential_id": "cred-1"}],
        }
        asyncio.run(
            plugin_handler._handle_multicred_post_execute(
                params,
                "tid",
                {"success": False, "failure_kind": "unreachable", "error_message": "connection refused"},
                cache,
                lambda: None,
            )
        )
    finally:
        plugin_handler.logger = original_logger

    cooldown_logs = [m for m in records if "[Cooldown]" in m]
    assert cooldown_logs, "应打出冷却日志"
    assert any("10.0.0.7" in m and "unreachable" in m for m in cooldown_logs)


def test_handle_multicred_post_execute_cools_single_credential_without_pool():
    from tasks.handlers.plugin_handler import _handle_multicred_post_execute

    enqueued = []

    class _FakeQueue:
        async def enqueue_collect_task(self, task):
            enqueued.append(task)

    # 单凭据：params 不含 credentials_pool
    params = {
        "collect_task_id": "task-1",
        "host": "10.0.0.50",
        "credential_id": "cred-1",
    }

    # 失败 → 写冷却，且不链式入队（无凭据可换）
    cache = _RecordingCache()
    asyncio.run(
        _handle_multicred_post_execute(
            params,
            "tid",
            {"success": False, "failure_kind": "unreachable", "error_message": "TCP connect timed out after 5s"},
            cache,
            lambda: _FakeQueue(),
        )
    )
    assert cache.mark_failure_calls == [("10.0.0.50", "cred-1", 1)]
    assert enqueued == []

    # 成功 → 记录成功凭据
    cache2 = _RecordingCache()
    asyncio.run(
        _handle_multicred_post_execute(
            params,
            "tid",
            {"success": True, "failure_kind": "", "error_message": ""},
            cache2,
            lambda: _FakeQueue(),
        )
    )
    assert cache2.mark_success_calls == [("10.0.0.50", "cred-1")]


def test_parse_credentials_pool_supports_flattened_params():
    from api.collect import _parse_credentials_pool

    params = {
        "credential_count": "2",
        "credential_0_credential_id": "cred-1",
        "credential_0_username": "admin",
        "credential_0_password": "${PASSWORD_password_cmdb_92_0}",
        "credential_0_port": "22",
        "credential_1_credential_id": "cred-2",
        "credential_1_username": "ops",
        "credential_1_password": "${PASSWORD_password_cmdb_92_1}",
        "credential_1_port": "2200",
    }

    parsed = _parse_credentials_pool(params=params)

    assert parsed == [
        {"credential_id": "cred-1", "username": "admin", "password": "${PASSWORD_password_cmdb_92_0}", "port": "22"},
        {"credential_id": "cred-2", "username": "ops", "password": "${PASSWORD_password_cmdb_92_1}", "port": "2200"},
    ]


def test_collect_endpoint_accepts_legacy_single_credential_headers(monkeypatch):
    from types import SimpleNamespace

    from api.collect import collect

    enqueued_tasks = []

    class FakeTaskQueue:
        async def enqueue_collect_task(self, params):
            enqueued_tasks.append(params)
            return {
                "task_id": f"task-{len(enqueued_tasks)}",
                "job_id": f"job-{len(enqueued_tasks)}",
                "status": "queued",
            }

    headers = {
        "cmdbnode_id": "9e0353a3-9aac-4fed-9cae-6734b40f6fc7",
        "cmdbexecute_timeout": "5",
        "cmdbpassword": "",
        "cmdbport": "",
        "cmdbusername": "",
        "cmdbplugin_name": "host_info",
        "cmdbhosts": "172.30.112.1",
        "cmdbexecutor_type": "job",
        "cmdbmodel_id": "host",
        "cmdbtimeout": "5",
        "instance_id": "cmdb_588",
        "instance_type": "cmdb_host",
        "collect_type": "http",
        "config_type": "host",
    }

    async def fake_receive_body():
        return None

    request = SimpleNamespace(headers=headers, query_args=[], receive_body=fake_receive_body)

    monkeypatch.setattr("api.collect.get_task_queue", lambda: FakeTaskQueue())

    response = asyncio.run(collect(request))

    assert response.status == 200
    assert response.headers["X-Task-Count"] == "1"
    assert response.headers["X-Success-Count"] == "1"
    assert len(enqueued_tasks) == 1

    queued_task = enqueued_tasks[0]
    assert queued_task["plugin_name"] == "host_info"
    assert queued_task["model_id"] == "host"
    assert queued_task["executor_type"] == "job"
    assert queued_task["host"] == "172.30.112.1"
    assert queued_task["node_id"] == "9e0353a3-9aac-4fed-9cae-6734b40f6fc7"
    assert queued_task["execute_timeout"] == "5"
    assert queued_task["timeout"] == "5"
    assert queued_task["username"] == ""
    assert queued_task["password"] == ""
    assert queued_task["port"] == ""
    assert "credential_count" not in queued_task
    assert "credentials_pool" not in queued_task
    assert "collect_task_id" not in queued_task


@pytest.mark.parametrize(
    "identity_headers",
    [
        {"cmdbprotocol_version": "1", "cmdbtarget_instance_uuid": "123e4567-e89b-42d3-a456-426614174000"},
        {"cmdbprotocol_version": "2", "cmdbtarget_instance_id": "101"},
        {"cmdbprotocol_version": "2", "cmdbtarget_instance_uuid": "101"},
    ],
)
def test_config_collection_endpoint_rejects_old_identity_protocol(monkeypatch, identity_headers):
    from types import SimpleNamespace

    from api.collect import collect

    async def fake_receive_body():
        return None

    headers = {
        "cmdbplugin_name": "config_file_info",
        "cmdbmodel_id": "config_file",
        "cmdbhosts": "10.0.0.1",
        **identity_headers,
    }
    request = SimpleNamespace(headers=headers, query_args=[], receive_body=fake_receive_body)

    response = asyncio.run(collect(request))

    assert response.status == 400


def test_config_collection_endpoint_preserves_uuid_identity_when_splitting(monkeypatch):
    from types import SimpleNamespace

    from api.collect import collect

    target_uuid = "123e4567-e89b-42d3-a456-426614174000"
    enqueued_tasks = []

    async def fake_receive_body():
        return None

    request = SimpleNamespace(
        headers={
            "cmdbplugin_name": "config_file_info",
            "cmdbmodel_id": "config_file",
            "cmdbhosts": "10.0.0.1",
            "cmdbprotocol_version": "2",
            "cmdbtarget_instance_uuid": target_uuid,
        },
        query_args=[],
        receive_body=fake_receive_body,
    )

    async def fake_submit(request, task_params, model_id):
        enqueued_tasks.append(task_params)
        from sanic import response as sanic_response

        return sanic_response.json({"ok": True}, status=200)

    monkeypatch.setattr("api.collect._submit_collection_run", fake_submit)

    response = asyncio.run(collect(request))

    assert response.status == 200
    assert enqueued_tasks[0]["target_instance_uuid"] == target_uuid
    assert "target_instance_id" not in enqueued_tasks[0]


def test_network_topology_protocol_registry_contains_expected_groups():
    from plugins.inputs.network_topo.protocol_oids import PROTOCOL_OID_GROUPS

    assert {"arp", "lldp", "cdp", "fdb"}.issubset(PROTOCOL_OID_GROUPS)


def test_network_topology_root_oid_lookup_prefers_matching_prefix():
    from plugins.inputs.network_topo.protocol_oids import get_root_oid

    assert get_root_oid("1.3.6.1.2.1.17.4.3.1.2.10.20.30.40.50.60") == "1.3.6.1.2.1.17.4.3.1.2"
    assert get_root_oid("1.3.6.1.2.1.17.4.3.99") is None


def test_build_topology_fact_uses_protocol_default_confidence_for_lldp_and_fdb():
    from plugins.inputs.network_topo.topology_facts import build_topology_fact

    lldp_fact = build_topology_fact(
        "lldp",
        {
            "local_device_id": "sw-1",
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "sw-2",
            "remote_port_id": "202",
            "remote_port_name": "GigabitEthernet1/0/2",
        },
        raw_evidence={"oid": "1.0.8802.1.1.2.1.4.1.1.7.0.1.1"},
    )
    fdb_fact = build_topology_fact(
        "fdb",
        {
            "local_device_id": "sw-1",
            "local_port_id": "301",
            "local_port_name": "Vlan10",
            "remote_device_id": "00:11:22:33:44:55",
            "remote_port_id": "10",
            "remote_port_name": "dynamic-mac",
        },
        raw_evidence={"oid": "1.3.6.1.2.1.17.4.3.1.2.0.17.34.51.68.85"},
    )

    assert lldp_fact["source_protocol"] == "lldp"
    assert lldp_fact["confidence"] == 0.95
    assert fdb_fact["source_protocol"] == "fdb"
    assert fdb_fact["confidence"] == 0.7


def test_merge_topology_facts_prefers_fdb_over_arp_when_no_stronger_fact_exists():
    from plugins.inputs.network_topo.topology_facts import build_topology_fact, merge_topology_facts

    arp_fact = build_topology_fact(
        "arp",
        {
            "local_device_id": None,
            "local_port_id": "7",
            "local_port_name": "Vlan7",
            "remote_device_id": "10.0.0.8",
            "remote_port_id": None,
            "remote_port_name": None,
        },
        raw_evidence={"source": "arp"},
    )
    fdb_fact = build_topology_fact(
        "fdb",
        {
            "local_device_id": None,
            "local_port_id": "7",
            "local_port_name": "GigabitEthernet1/0/7",
            "remote_device_id": "10.0.0.8",
            "remote_port_id": None,
            "remote_port_name": None,
        },
        raw_evidence={"source": "fdb"},
    )

    assert merge_topology_facts([arp_fact, fdb_fact]) == [fdb_fact]


def test_merge_topology_facts_keeps_arp_as_last_fallback_when_no_stronger_fact_exists():
    from plugins.inputs.network_topo.topology_facts import build_topology_fact, merge_topology_facts

    arp_fact = build_topology_fact(
        "arp",
        {
            "local_device_id": None,
            "local_port_id": "9",
            "local_port_name": "Vlan9",
            "remote_device_id": "10.0.0.9",
            "remote_port_id": None,
            "remote_port_name": None,
        },
        raw_evidence={"source": "arp"},
    )

    assert merge_topology_facts([arp_fact]) == [arp_fact]


def test_merge_topology_facts_preserves_stronger_fact_on_exact_full_edge_duplicate():
    from plugins.inputs.network_topo.topology_facts import build_topology_fact, merge_topology_facts

    cdp_fact = build_topology_fact(
        "cdp",
        {
            "local_device_id": None,
            "local_port_id": "7",
            "local_port_name": "GigabitEthernet1/0/7",
            "remote_device_id": "core-sw-1",
            "remote_port_id": "Gi1/0/48",
            "remote_port_name": "GigabitEthernet1/0/48",
        },
        raw_evidence={"source": "cdp"},
        confidence=0.95,
    )
    lldp_fact = build_topology_fact(
        "lldp",
        {
            "local_device_id": None,
            "local_port_id": "7",
            "local_port_name": "Ethernet7",
            "remote_device_id": "core-sw-1",
            "remote_port_id": "Gi1/0/48",
            "remote_port_name": "uplink-to-core",
        },
        raw_evidence={"source": "lldp"},
        confidence=0.95,
    )

    assert merge_topology_facts([cdp_fact, lldp_fact]) == [lldp_fact]


def test_merge_topology_facts_prefers_higher_confidence_across_protocols_for_same_full_edge():
    from plugins.inputs.network_topo.topology_facts import build_topology_fact, merge_topology_facts

    default_lldp_fact = build_topology_fact(
        "lldp",
        {
            "local_device_id": "access-sw-1",
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "dist-sw-1",
            "remote_port_id": "GigabitEthernet1/0/24",
            "remote_port_name": "GigabitEthernet1/0/24",
        },
        raw_evidence={"source": "lldp-default"},
    )
    higher_confidence_fdb_fact = build_topology_fact(
        "fdb",
        {
            "local_device_id": "access-sw-1",
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "dist-sw-1",
            "remote_port_id": "GigabitEthernet1/0/24",
            "remote_port_name": "dynamic-mac",
        },
        raw_evidence={"source": "fdb-override"},
        confidence=0.99,
    )

    assert merge_topology_facts([default_lldp_fact, higher_confidence_fdb_fact]) == [higher_confidence_fdb_fact]


def test_merge_topology_facts_prefers_higher_confidence_for_same_edge_key():
    from plugins.inputs.network_topo.topology_facts import build_topology_fact, merge_topology_facts

    weaker_lldp_fact = build_topology_fact(
        "lldp",
        {
            "local_device_id": None,
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "dist-sw-1",
            "remote_port_id": "GigabitEthernet1/0/24",
            "remote_port_name": "GigabitEthernet1/0/24",
        },
        raw_evidence={"source": "lldp-weak"},
        confidence=0.82,
    )
    stronger_lldp_fact = build_topology_fact(
        "lldp",
        {
            "local_device_id": None,
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "dist-sw-1",
            "remote_port_id": "GigabitEthernet1/0/24",
            "remote_port_name": "GigabitEthernet1/0/24",
        },
        raw_evidence={"source": "lldp-strong"},
        confidence=0.97,
    )

    assert merge_topology_facts([weaker_lldp_fact, stronger_lldp_fact]) == [stronger_lldp_fact]


def test_snmp_topo_format_result_preserves_raw_row_shape_after_registry_refactor(monkeypatch):
    from plugins.inputs.network_topo.protocol_oids import NETWORK_TOPO_OIDS

    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo

    class FakeValue:
        def __init__(self, value):
            self.value = value

        def prettyPrint(self):
            return self.value

    varbinds = [
        [
            (
                FakeValue("1.3.6.1.2.1.4.22.1.1.192.168.1.10"),
                FakeValue("7"),
            ),
            (
                FakeValue("1.3.6.1.2.1.2.2.1.2.7"),
                FakeValue("GigabitEthernet1/0/7"),
            ),
        ]
    ]

    result = SnmpTopo._format_result(varbinds, eval_oids=NETWORK_TOPO_OIDS)

    assert result == [
        {
            "root": "1.3.6.1.2.1.4.22.1.1",
            "key": "1.3.6.1.2.1.4.22.1.1.192.168.1.10",
            "tag": "ARP-IfIndex",
            "ifindex": "192.168.1.10",
            "ifindex_type": "ipaddr",
            "val": "7",
            "group": "arp",
        },
        {
            "root": "1.3.6.1.2.1.2.2.1.2",
            "key": "1.3.6.1.2.1.2.2.1.2.7",
            "tag": "IFTable-IfDescr",
            "ifindex": "7",
            "ifindex_type": "default",
            "val": "GigabitEthernet1/0/7",
            "group": "interfaces",
        },
    ]


def test_snmp_topo_format_result_prefers_longest_matching_eval_oid(monkeypatch):
    snmp_topo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch)

    class FakeValue:
        def __init__(self, value):
            self.value = value

        def prettyPrint(self):
            return self.value

    def parse_suffix(oid, root_oid):
        return oid[len(root_oid) + 1 :] if oid != root_oid else None

    fake_oid_meta = {
        "1.2.3": {
            "tag": "short-root",
            "ifindex_type": "suffix",
            "index_parser": parse_suffix,
        },
        "1.2.3.4": {
            "tag": "long-root",
            "ifindex_type": "suffix",
            "index_parser": parse_suffix,
        },
    }

    monkeypatch.setattr(snmp_topo, "get_oid_meta", lambda root_oid: fake_oid_meta[root_oid])

    result = snmp_topo.SnmpTopo._format_result(
        [[(FakeValue("1.2.3.4.5"), FakeValue("value"))]],
        eval_oids=["1.2.3", "1.2.3.4"],
    )

    assert result == [
        {
            "root": "1.2.3.4",
            "key": "1.2.3.4.5",
            "tag": "long-root",
            "ifindex": "5",
            "ifindex_type": "suffix",
            "val": "value",
            "group": "interfaces",
        }
    ]


def test_snmp_topo_build_topology_facts_builds_lldp_neighbor_evidence(monkeypatch):
    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo

    snmp_rows = [
        {"tag": "LLDP-LocPortId", "ifindex": "101", "val": "GigabitEthernet1/0/1"},
        {"tag": "LLDP-RemSysName", "ifindex": "8457.101.1", "val": "dist-sw-1"},
        {"tag": "LLDP-RemPortId", "ifindex": "8457.101.1", "val": "GigabitEthernet1/0/24"},
    ]

    facts = SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=("lldp",))

    assert facts == [
        {
            "source_protocol": "lldp",
            "confidence": 0.95,
            "local_device_id": None,
            "local_port_id": "101",
            "local_port_name": "GigabitEthernet1/0/1",
            "remote_device_id": "dist-sw-1",
            "remote_port_id": "GigabitEthernet1/0/24",
            "remote_port_name": "GigabitEthernet1/0/24",
            "raw_evidence": {
                "local_port": snmp_rows[0],
                "remote_system": snmp_rows[1],
                "remote_port": snmp_rows[2],
            },
        }
    ]


def test_snmp_topo_extract_lldp_local_ifindex_uses_local_port_component(monkeypatch):
    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo

    assert SnmpTopo._extract_lldp_local_ifindex("8457.101.1") == "101"


def test_snmp_topo_build_topology_facts_builds_cdp_neighbor_evidence(monkeypatch):
    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo

    snmp_rows = [
        {"tag": "IFTable-IfDescr", "ifindex": "7", "val": "GigabitEthernet1/0/7"},
        {"tag": "CDP-DeviceId", "ifindex": "7.1", "val": "core-sw-1"},
        {"tag": "CDP-DevicePort", "ifindex": "7.1", "val": "GigabitEthernet1/0/48"},
    ]

    facts = SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=("cdp",))

    assert facts == [
        {
            "source_protocol": "cdp",
            "confidence": 0.9,
            "local_device_id": None,
            "local_port_id": "7",
            "local_port_name": "GigabitEthernet1/0/7",
            "remote_device_id": "core-sw-1",
            "remote_port_id": "GigabitEthernet1/0/48",
            "remote_port_name": "GigabitEthernet1/0/48",
            "raw_evidence": {
                "local_port": snmp_rows[0],
                "remote_device": snmp_rows[1],
                "remote_port": snmp_rows[2],
            },
        }
    ]


def test_snmp_topo_build_topology_facts_returns_no_neighbor_facts_for_explicit_empty_or_unsupported_protocols(monkeypatch):
    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo

    snmp_rows = [
        {"tag": "LLDP-LocPortId", "ifindex": "101", "val": "GigabitEthernet1/0/1"},
        {"tag": "LLDP-RemSysName", "ifindex": "8457.101.1", "val": "dist-sw-1"},
        {"tag": "LLDP-RemPortId", "ifindex": "8457.101.1", "val": "GigabitEthernet1/0/24"},
        {"tag": "IFTable-IfDescr", "ifindex": "7", "val": "GigabitEthernet1/0/7"},
        {"tag": "CDP-DeviceId", "ifindex": "7.1", "val": "core-sw-1"},
        {"tag": "CDP-DevicePort", "ifindex": "7.1", "val": "GigabitEthernet1/0/48"},
    ]

    assert SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=()) == []
    assert SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=("ospf",)) == []


def test_snmp_topo_build_topology_facts_skips_fdb_when_bridge_port_mapping_missing(monkeypatch):
    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo
    snmp_rows = [
        {"tag": "FDB-MacAddress", "ifindex": "0.17.34.51.68.85", "val": "00:11:22:33:44:55"},
        {"tag": "FDB-Port", "ifindex": "0.17.34.51.68.85", "val": "10"},
        {"tag": "IFTable-IfDescr", "ifindex": "15", "val": "GigabitEthernet1/0/15"},
        {"tag": "IFTable-IfAlias", "ifindex": "15", "val": "server-uplink"},
    ]

    assert SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=("fdb",)) == []


def test_snmp_topo_build_topology_facts_builds_fdb_neighbor_when_bridge_port_mapping_exists(monkeypatch):
    SnmpTopo = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch).SnmpTopo

    snmp_rows = [
        {"tag": "FDB-MacAddress", "ifindex": "0.17.34.51.68.85", "val": "00:11:22:33:44:55"},
        {"tag": "FDB-Port", "ifindex": "0.17.34.51.68.85", "val": "10"},
        {"tag": "BRIDGE-BasePortIfIndex", "ifindex": "10", "val": "15"},
        {"tag": "IFTable-IfDescr", "ifindex": "15", "val": "GigabitEthernet1/0/15"},
        {"tag": "IFTable-IfAlias", "ifindex": "15", "val": "server-uplink"},
    ]

    assert SnmpTopo.build_topology_facts(snmp_rows, enabled_protocols=("fdb", "arp")) == [
        {
            "source_protocol": "fdb",
            "confidence": 0.7,
            "local_device_id": None,
            "local_port_id": "15",
            "local_port_name": "server-uplink",
            "remote_device_id": "00:11:22:33:44:55",
            "remote_port_id": None,
            "remote_port_name": None,
            "raw_evidence": {
                "local_port": snmp_rows[3],
                "local_port_alias": snmp_rows[4],
                "bridge_port": snmp_rows[2],
                "fdb_mac": snmp_rows[0],
                "fdb_port": snmp_rows[1],
            },
        }
    ]


def test_snmp_topo_default_oid_collection_includes_fdb_fallback_without_duplicates(monkeypatch):
    snmp_topo_module = _import_snmp_topo_with_stubbed_sanic_log(monkeypatch)
    SnmpTopo = snmp_topo_module.SnmpTopo

    default_oids = SnmpTopo._build_oids()
    expected_fdb_oids = [entry["key"] for entry in snmp_topo_module.flatten_oid_registry(("fdb",))]

    assert set(expected_fdb_oids).issubset(default_oids)
    assert len(default_oids) == len(set(default_oids))


def test_snmp_facts_hardcodes_timeout_10_retries_1():
    from plugins.inputs.network.snmp_facts import SnmpFacts

    facts = SnmpFacts(
        {
            "host": "127.0.0.1",
            "version": "v2c",
            "community": "public",
            "timeout": 99,
            "retries": 9,
        }
    )
    assert (facts.timeout, facts.retries) == (10, 1)


# ============================================================================
# 多凭据池轮询：任何失败都换下一个凭据（修复 SNMP v3 设备卡在 v2c 不前进）
# ============================================================================
class _FakeCredCache:
    """记录 mark_failure/mark_success/clear_success/enqueue 调用的假缓存。"""

    def __init__(self, cooled=None):
        self.events = []
        self.failures = []  # mark_failure 调用
        self.successes = []
        self.cleared = []
        self._cooled = set(cooled or set())  # 已冷却的 (task,host,cred_id)

    async def append_result_event(self, ev):
        self.events.append(ev)

    async def mark_success(self, t, h, c):
        self.successes.append((str(t), h, c))

    async def clear_success(self, t, h):
        self.cleared.append((str(t), h))

    async def mark_failure(self, t, h, c, err, level, consecutive, next_retry):
        self.failures.append({"host": h, "cred": c, "level": level, "consecutive": consecutive})
        self._cooled.add((str(t), h, c))

    async def get_failure_state(self, t, h, c):
        return {"is_cooled": True} if (str(t), h, c) in self._cooled else {}


class _FakeQueue:
    def __init__(self):
        self.enqueued = []

    async def enqueue_collect_task(self, task):
        self.enqueued.append(task)
        return {"task_id": "t", "status": "queued"}


def _exec_result(failure_kind, error_message, success=False):
    return {
        "collect_task_id": 293,
        "host": "10.10.69.246",
        "credential_id": "cred-v2c",
        "credential_index": 0,
        "model_id": "network",
        "plugin_name": "snmp_facts",
        "success": success,
        "failure_kind": failure_kind,
        "error_message": error_message,
        "finished_at": "2026-06-12T00:00:00Z",
        "snapshot": {},
    }


def _mc_params(pool):
    return {
        "collect_task_id": 293,
        "host": "10.10.69.246",
        "credential_id": "cred-v2c",
        "credential_index": 0,
        "credentials_pool": pool,
        "model_id": "network",
        "plugin_name": "snmp_facts",
    }


_POOL = [
    {"credential_id": "cred-v2c", "version": "v2c", "community": "x"},
    {"credential_id": "cred-v3", "version": "v3", "username": "u"},
]


@pytest.mark.asyncio
async def test_multicred_snmp_timeout_cools_and_rotates_to_v3():
    """246 场景：v2c 在 v3 设备上静默超时（failure_kind=task）→ 多凭据池下应冷却 v2c 并换到 v3。"""
    from tasks.handlers.plugin_handler import _handle_multicred_post_execute

    cache = _FakeCredCache()
    queue = _FakeQueue()
    er = _exec_result("task", "No SNMP response received before timeout")
    await _handle_multicred_post_execute(_mc_params(_POOL), "t", er, cache, lambda: queue)
    assert [f["cred"] for f in cache.failures] == ["cred-v2c"]  # v2c 被冷却
    assert len(queue.enqueued) == 1  # 换下一个
    assert queue.enqueued[0]["credential_id"] == "cred-v3"


@pytest.mark.asyncio
async def test_multicred_generic_task_failure_rotates_without_cooldown():
    """非 SNMP 的瞬时 task 失败：多凭据池下仍换下一个，但不冷却当前凭据（下一轮仍可重试）。"""
    from tasks.handlers.plugin_handler import _handle_multicred_post_execute

    cache = _FakeCredCache()
    queue = _FakeQueue()
    er = _exec_result("task", "docker command not found")
    await _handle_multicred_post_execute(_mc_params(_POOL), "t", er, cache, lambda: queue)
    assert cache.failures == []  # 不冷却
    assert len(queue.enqueued) == 1  # 仍换下一个
    assert queue.enqueued[0]["credential_id"] == "cred-v3"


@pytest.mark.asyncio
async def test_single_credential_snmp_timeout_unchanged():
    """单凭据 SNMP 超时：保持原行为——不冷却、不换（下一轮重试），零回归。"""
    from tasks.handlers.plugin_handler import _handle_multicred_post_execute

    cache = _FakeCredCache()
    queue = _FakeQueue()
    er = _exec_result("task", "No SNMP response received before timeout")
    await _handle_multicred_post_execute(_mc_params([]), "t", er, cache, lambda: queue)
    assert cache.failures == []  # 单凭据不冷却
    assert queue.enqueued == []  # 无可换


@pytest.mark.asyncio
async def test_multicred_credential_failure_still_cools_and_rotates():
    """既有行为：明确 credential 失败仍冷却 + 换下一个（不回归）。"""
    from tasks.handlers.plugin_handler import _handle_multicred_post_execute

    cache = _FakeCredCache()
    queue = _FakeQueue()
    er = _exec_result("credential", "SSH authentication failed")
    await _handle_multicred_post_execute(_mc_params(_POOL), "t", er, cache, lambda: queue)
    assert [f["cred"] for f in cache.failures] == ["cred-v2c"]
    assert queue.enqueued[0]["credential_id"] == "cred-v3"


@pytest.mark.asyncio
async def test_multicred_no_next_when_remaining_cooled():
    """下一个凭据已冷却 → 不再 enqueue（避免空转）。"""
    from tasks.handlers.plugin_handler import _handle_multicred_post_execute

    cache = _FakeCredCache(cooled={("293", "10.10.69.246", "cred-v3")})
    queue = _FakeQueue()
    er = _exec_result("task", "No SNMP response received before timeout")
    await _handle_multicred_post_execute(_mc_params(_POOL), "t", er, cache, lambda: queue)
    assert queue.enqueued == []  # v3 已冷却，无可换
