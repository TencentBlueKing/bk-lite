"""每个范围内采集插件的 probe 只走连通性函数，不拉完整清单。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from core.collection.contracts import AccessProbeStatus


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_mysql_probe_reads_version_only():
    from plugins.inputs.mysql.mysql_info import MysqlInfo

    info = MysqlInfo.__new__(MysqlInfo)
    called = []

    async def connect():
        called.append("connect")

    async def sql(query):
        called.append(query)
        return [{"Value": "8.0.36"}]

    async def close():
        called.append("close")

    async def inventory():
        called.append("inventory")

    info._connect = connect
    info._exec_sql = sql
    info.close = close
    info.list_all_resources = inventory

    result = await info.probe()

    assert result.status == AccessProbeStatus.READY
    assert called == ["connect", "SHOW GLOBAL VARIABLES LIKE 'version'", "close"]


@pytest.mark.asyncio
async def test_postgresql_probe_reads_server_version_only():
    from plugins.inputs.postgresql.postgresql_info import PostgresqlInfo

    info = PostgresqlInfo.__new__(PostgresqlInfo)
    called = []

    async def connect():
        called.append("connect")

    async def sql(query):
        called.append(query)
        return [{"server_version": "16.1"}]

    async def close():
        called.append("close")

    async def inventory():
        called.append("inventory")

    info._connect = connect
    info._exec_sql = sql
    info.close = close
    info.list_all_resources = inventory

    result = await info.probe()

    assert result.status == AccessProbeStatus.READY
    assert "SHOW server_version" in called
    assert "inventory" not in called


@pytest.mark.asyncio
async def test_mssql_probe_reads_product_version_only():
    from plugins.inputs.mssql.mssql_info import MSSQLInfo

    info = MSSQLInfo.__new__(MSSQLInfo)
    called = []

    async def connect():
        called.append("connect")

    async def sql(query):
        called.append(query)
        return {"version": "15.0.2000.5"}

    async def close():
        called.append("close")

    async def collect():
        called.append("collect")

    info._connect = connect
    info._exec_sql = sql
    info.close = close
    info._collect = collect

    result = await info.probe()

    assert result.status == AccessProbeStatus.READY
    assert "ProductVersion" in called[1]
    assert "collect" not in called


@pytest.mark.asyncio
async def test_influxdb_probe_checks_health_not_buckets():
    from plugins.inputs.influxdb.influxdb_info import InfluxdbInfo

    info = InfluxdbInfo.__new__(InfluxdbInfo)
    info.token = ""
    paths = []

    async def get(_client, path, headers=None):
        paths.append(path)
        return SimpleNamespace(
            status_code=200,
            content=b"{}",
            headers={"X-Influxdb-Version": "2.7.1"},
            json=lambda: {"version": "2.7.1"},
        )

    info._client = lambda: _Client()
    info._get = get

    result = await info.probe()

    assert result.status == AccessProbeStatus.READY
    assert paths == ["/health"]


@pytest.mark.asyncio
async def test_aliyun_probe_calls_connection_result_not_inventory():
    from plugins.inputs.aliyun.aliyun_info import CwAliyun

    info = CwAliyun.__new__(CwAliyun)
    called = []

    def connection():
        called.append("regions")
        return {"result": True}

    async def inventory(**_kwargs):
        called.append("inventory")

    info._probe_connection = connection
    info.list_all_resources = inventory

    result = await info.probe()

    assert result.status == AccessProbeStatus.READY
    assert called == ["regions"]


@pytest.mark.asyncio
async def test_qcloud_probe_calls_test_connection_not_inventory():
    from plugins.inputs.qcloud.qcloud_info import TencentCloudManager

    info = TencentCloudManager.__new__(TencentCloudManager)
    called = []

    def test_connection():
        called.append("regions")
        return True

    def exec_script():
        called.append("inventory")

    info.test_connection = test_connection
    info.exec_script = exec_script

    result = await info.probe()

    assert result.status == AccessProbeStatus.READY
    assert called == ["regions"]


@pytest.mark.asyncio
async def test_hwcloud_probe_calls_connection_result_not_inventory():
    from plugins.inputs.hwcloud.huaweicloud_info import HuaweiCloudManager

    info = HuaweiCloudManager.__new__(HuaweiCloudManager)
    called = []

    def connection():
        called.append("domains")
        return {"result": True}

    def ecs():
        called.append("inventory")

    info._probe_connection = connection
    info.get_ecs = ecs

    result = await info.probe()

    assert result.status == AccessProbeStatus.READY
    assert called == ["domains"]


@pytest.mark.asyncio
async def test_fusioninsight_probe_logs_in_without_listing_clusters():
    from plugins.inputs.fusioninsight.fusioninsight_info import FusionInsightManager

    info = FusionInsightManager.__new__(FusionInsightManager)
    info._client = None
    info._authed = False
    called = []

    async def login():
        called.append("login")

    async def clusters():
        called.append("inventory")

    info.login = login
    info.exec_script = clusters

    result = await info.probe()

    assert result.status == AccessProbeStatus.READY
    assert called == ["login"]


@pytest.mark.asyncio
async def test_vcenter_probe_opens_and_closes_a_session():
    from plugins.inputs.vmware_vc.vmware_info import VmwareManage

    info = VmwareManage.__new__(VmwareManage)
    called = []

    def connect():
        called.append("session")

    def disconnect():
        called.append("disconnect")

    def service():
        called.append("inventory")

    info.connect_vc = connect
    info.disconnect_vc = disconnect
    info.service = service

    result = await info.probe()

    assert result.status == AccessProbeStatus.READY
    assert called == ["session", "disconnect"]


@pytest.mark.asyncio
async def test_hyperv_probe_uses_winrm_login_not_the_discover_script(monkeypatch):
    from plugins.inputs.hyperv_host.hyperv_info import HypervInfo

    async def adhoc(**kwargs):
        assert kwargs["module"] == "win_shell"
        assert kwargs["module_args"] == "Write-Output ok"
        return {"success": True}

    monkeypatch.setattr("plugins.inputs.hyperv_host.hyperv_info.ansible_adhoc", adhoc)
    info = HypervInfo.__new__(HypervInfo)
    info.node_id = "node-1"
    info.host = "10.0.0.8"
    info.username = "ops"
    info.password = "secret-value"
    info.port = 5985
    info.params = {}
    info.execute_timeout = 5

    def read_script():
        raise AssertionError("discover script")

    info._read_script = read_script

    result = await info.probe()

    assert result.status == AccessProbeStatus.READY


@pytest.mark.asyncio
async def test_oceanstor_probe_logs_in_without_fetching_pools(monkeypatch):
    from plugins.inputs.oceanstor.oceanstor_info import OceanStorManager

    info = OceanStorManager.__new__(OceanStorManager)
    info.timeout = 1
    info.verify_tls = False
    info.device_id = None
    called = []

    async def login():
        called.append("login")

    async def logout():
        called.append("logout")

    async def fetch_all(_path):
        called.append("inventory")

    info.login = login
    info.logout = logout
    info._fetch_all = fetch_all

    result = await info.probe()

    assert result.status == AccessProbeStatus.READY
    assert called == ["login", "logout"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "probe_status", "error_code"),
    [
        (401, AccessProbeStatus.AUTH_FAILED, "credential_user_or_password"),
        (403, AccessProbeStatus.CAPABILITY_DENIED, "capability_denied"),
    ],
)
async def test_oceanstor_probe_separates_forbidden_from_credential(monkeypatch, status_code, probe_status, error_code):
    from plugins.inputs.oceanstor import oceanstor_info

    class _Response:
        def __init__(self, code):
            self.status_code = code

        def json(self):
            return {}

    class _Client:
        def __init__(self, *_args, **_kwargs):
            return None

        async def post(self, *_args, **_kwargs):
            return _Response(status_code)

        async def delete(self, *_args, **_kwargs):
            return _Response(200)

        async def aclose(self):
            return None

    monkeypatch.setattr(oceanstor_info.httpx, "AsyncClient", _Client)
    result = await oceanstor_info.OceanStorManager({"host": "10.0.0.8", "username": "collector", "password": "secret-value"}).probe()

    assert result.status == probe_status
    assert result.error_code == error_code
    assert "secret-value" not in result.detail


def test_batch_size_follows_the_row_count():
    from core.collection.access_check import access_check_batch_size, access_row_count
    from core.collection.runtime import CollectionRequest

    assert access_check_batch_size(20) == 20
    assert access_check_batch_size(49) == 49
    assert access_check_batch_size(50) == 20
    assert access_check_batch_size(99) == 20
    assert access_check_batch_size(100) == 20
    assert access_check_batch_size(160) == 20
    assert access_check_batch_size(400) == 50
    assert access_check_batch_size(1000) == 50

    request = CollectionRequest(
        task_id="check-1",
        plugin_ref="mysql.config",
        targets=tuple(f"10.0.0.{index}" for index in range(40)),
        credentials=(
            {"credential_id": "credential-1", "password": "secret"},
            {"credential_id": "credential-2", "password": "secret", "target_host": "10.0.0.1"},
        ),
        params={"run_purpose": "access_check"},
    )
    assert access_row_count(request) == 41


@pytest.mark.asyncio
async def test_small_checks_return_once():
    from core.collection.access_check import emit_access_check_batches

    async def targets():
        for index in range(40):
            yield (SimpleNamespace(target=str(index)),)

    sent = []

    async def publish(status, rows):
        sent.append((status, len(rows)))
        return True

    await emit_access_check_batches(targets(), publish, total=40)

    assert sent == [("finished", 40)]


@pytest.mark.asyncio
async def test_access_check_returns_every_ten_targets():
    from core.collection.access_check import emit_access_check_batches

    async def targets():
        for index in range(25):
            yield (SimpleNamespace(target=f"10.0.0.{index}"),)

    sent = []

    async def publish(status, rows):
        sent.append((status, tuple(row.target for row in rows)))
        return True

    await emit_access_check_batches(targets(), publish, total=25, batch_size=10)

    assert [item[0] for item in sent] == ["running", "running", "finished"]
    assert len(sent[0][1]) == 10
    assert len(sent[1][1]) == 10
    assert sent[2][1] == tuple(f"10.0.0.{index}" for index in range(20, 25))


@pytest.mark.asyncio
async def test_access_check_keeps_a_batch_when_the_callback_is_not_accepted():
    from core.collection.access_check import emit_access_check_batches

    async def targets():
        for index in range(15):
            yield (SimpleNamespace(target=str(index)),)

    sent = []

    async def publish(status, rows):
        sent.append((status, len(rows)))
        return status == "finished"

    await emit_access_check_batches(targets(), publish, total=15, batch_size=10)

    assert sent == [("running", 10), ("finished", 15)]


@pytest.mark.asyncio
async def test_netapp_probe_reads_cluster_not_storage_objects():
    from plugins.inputs.netapp_ontap.netapp_ontap_info import NetAppOntapManager

    info = NetAppOntapManager.__new__(NetAppOntapManager)
    info.timeout = 1
    info.verify_tls = False
    info._client = None
    called = []

    async def get_json(path, params=None, required=False):
        called.append(path)
        return {"name": "cluster"}

    async def fetch_records(*_args, **_kwargs):
        called.append("inventory")

    info._get_json = get_json
    info._fetch_records = fetch_records

    result = await info.probe()

    assert result.status == AccessProbeStatus.READY
    assert called == ["cluster"]


def test_mysql_failure_names_the_field_and_keeps_the_secret_out():
    from plugins.inputs.mysql.mysql_info import classify_mysql_failure
    from pymysql.err import OperationalError

    secret = "secret-do-not-return"
    auth = classify_mysql_failure(
        OperationalError(1045, f"Access denied for user 'root' (using password: YES) {secret}"),
        user_present=True,
        password_present=True,
    )
    assert auth is not None
    assert auth.status == AccessProbeStatus.AUTH_FAILED
    assert auth.error_code == "credential_user_or_password"
    assert secret not in auth.error_code
    assert secret not in auth.detail

    missing_user = classify_mysql_failure(OperationalError(1045, "Access denied"), user_present=False, password_present=True)
    assert missing_user is not None
    assert missing_user.error_code == "credential_user"

    empty_password = classify_mysql_failure(
        OperationalError(1045, "Access denied (using password: NO)"),
        user_present=True,
        password_present=False,
    )
    assert empty_password is not None
    assert empty_password.error_code == "credential_password"

    database = classify_mysql_failure(
        OperationalError(1049, f"Unknown database '{secret}'"),
        user_present=True,
        password_present=True,
    )
    assert database is not None
    assert database.error_code == "credential_database"
    assert secret not in database.error_code
    assert secret not in database.detail

    refused = classify_mysql_failure(
        OperationalError(2003, "Can't connect to MySQL server (Connection refused)"),
        user_present=True,
        password_present=True,
    )
    assert refused is not None
    assert refused.status == AccessProbeStatus.TARGET_UNREACHABLE
    assert refused.error_code == "tcp_connection_refused"

    assert classify_mysql_failure(RuntimeError(f"TypeError {secret}"), user_present=True, password_present=True) is None


@pytest.mark.asyncio
async def test_probe_code_error_becomes_system_error_without_the_message():
    from core.collection.contracts import TargetCollectionContext, TargetExecutorSettings
    from core.collection.credential_attempt import CredentialAttemptRunner
    from core.collection.execution_plan import ExecutionPlan
    from core.collection.metrics import CollectionMetrics
    from core.collection.runtime import CollectionRequest

    secret = "secret-do-not-return"

    class _Boom:
        async def probe(self, target, credential, context, *, timeout_seconds):
            raise RuntimeError(f"password={secret}")

    runner = CredentialAttemptRunner(
        access_probe=_Boom(),
        plugin=object(),
        credential_policy=object(),
        settings=TargetExecutorSettings(),
        plan=ExecutionPlan(
            preflight_timeout_seconds=1,
            probe_timeout_seconds=1,
            collection_timeout_seconds=1,
            publish_timeout_seconds=1,
            execution_mode="sync",
            capacity_group="default",
        ),
        metrics=CollectionMetrics(),
    )
    request = CollectionRequest(
        task_id="check-1",
        plugin_ref="mysql.config",
        targets=("127.0.0.1",),
        params={"run_purpose": "access_check"},
    )
    result = await runner.run(
        request,
        "127.0.0.1",
        ({"credential_id": "credential-1", "name": "凭据 1", "password": secret},),
        TargetCollectionContext(
            task_id="check-1",
            plugin_ref="mysql.config",
            fence=0,
            params={"_log_plugin_call_chain": True},
        ),
        target_started_at=0,
    )

    row = result.access_rows[0]
    assert row.conclusion == "system_error"
    assert row.detail_code == "system_error"
    assert secret not in row.detail_code
    assert secret not in row.conclusion
    assert secret not in row.credential_name
