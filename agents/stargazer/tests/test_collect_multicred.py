import sys
import asyncio
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))


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


def test_build_credential_results_payload_returns_next_since():
    from api.collect import _build_credential_results_payload

    events = [
        {"host": "10.0.0.1", "finished_at": "2026-06-03T12:00:00+00:00"},
        {"host": "10.0.0.2", "finished_at": "2026-06-03T12:05:00+00:00"},
    ]

    payload = _build_credential_results_payload(events)

    assert payload["results"] == events
    assert payload["next_since"] == "2026-06-03T12:05:00+00:00"


def test_collect_endpoint_enqueues_selected_tasks_from_flattened_multicred_headers(monkeypatch):
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

    async def fake_get_success_credential(collect_task_id, host):
        return ""

    async def fake_get_failure_state(collect_task_id, host, credential_id):
        return {}

    headers = {
        "cmdbnode_id": "47e14286b3ea11f0ae1f0242ac12000e",
        "cmdbexecute_timeout": "500",
        "cmdbpassword": "password1",
        "cmdbport": "22",
        "cmdbusername": "admin",
        "cmdbcredential_id": "cred_ce9ce17b8eb9",
        "cmdbcredential_count": "2",
        "cmdbcredential_0_node_id": "47e14286b3ea11f0ae1f0242ac12000e",
        "cmdbcredential_0_execute_timeout": "600",
        "cmdbcredential_0_password": "sasas",
        "cmdbcredential_0_username": "admin",
        "cmdbcredential_0_credential_id": "cred_ce9ce17b8eb9",
        "cmdbcredential_1_node_id": "47e14286b3ea11f0ae1f0242ac12000e",
        "cmdbcredential_1_execute_timeout": "600",
        "cmdbcredential_1_password": "sasas1111",
        "cmdbcredential_1_username": "admin111",
        "cmdbcredential_1_credential_id": "cred_439e46a6b9d2",
        "cmdbplugin_name": "host_info",
        "cmdbhosts": "127.0.0.5-127.0.0.9",
        "cmdbexecutor_type": "job",
        "cmdbmodel_id": "host",
        "cmdbtimeout": "50",
        "instance_id": "cmdb_588",
        "instance_type": "cmdb_host",
        "collect_type": "http",
        "config_type": "host",
        "cmdbcollect_task_id": "131",
        "cmdbcredential_result_subject": "receive_collect_credential_result",
    }
    async def fake_receive_body():
        return None

    request = SimpleNamespace(headers=headers, query_args=[], receive_body=fake_receive_body)

    monkeypatch.setattr("api.collect.get_task_queue", lambda: FakeTaskQueue())
    monkeypatch.setattr("api.collect.CredentialStateCache.get_success_credential", fake_get_success_credential)
    monkeypatch.setattr("api.collect.CredentialStateCache.get_failure_state", fake_get_failure_state)

    response = asyncio.run(collect(request))

    assert response.status == 200
    assert response.headers["X-Task-Count"] == "5"
    assert response.headers["X-Success-Count"] == "5"
    assert len(enqueued_tasks) == 5
    assert [task["host"] for task in enqueued_tasks] == [
        "127.0.0.5",
        "127.0.0.6",
        "127.0.0.7",
        "127.0.0.8",
        "127.0.0.9",
    ]
    assert all(task["credential_id"] == "cred_ce9ce17b8eb9" for task in enqueued_tasks)
    assert all(task["credential_index"] == 0 for task in enqueued_tasks)
    assert all(task["password"] == "sasas" for task in enqueued_tasks)
    assert all(task["username"] == "admin" for task in enqueued_tasks)
    assert all(task["execute_timeout"] == "600" for task in enqueued_tasks)
    assert all(task["timeout"] == "50" for task in enqueued_tasks)
    assert all(len(task["credentials_pool"]) == 2 for task in enqueued_tasks)


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