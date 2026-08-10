from types import SimpleNamespace

import pytest


def test_base_node_params_uses_primary_credential_from_pool_for_node_push():
    from apps.cmdb.node_configs.ssh.host import HostNodeParams

    instance = SimpleNamespace(
        id=91,
        model_id="host",
        driver_type="job",
        decrypt_credentials=[
            {"credential_id": "cred-1", "username": "admin", "password": "first-secret", "port": 22},
            {"credential_id": "cred-2", "username": "ops", "password": "second-secret", "port": 2200},
        ],
        params={},
        timeout=60,
        access_point=[{"id": 3}],
        instances=[{"ip_addr": "10.0.0.8"}],
        ip_range="",
    )

    node = HostNodeParams(instance)

    assert node.credential == {
        "credential_id": "cred-1",
        "username": "admin",
        "password": "first-secret",
        "port": 22,
    }
    assert node.set_credential()["username"] == "admin"
    assert node.set_credential()["port"] == 22
    assert "PASSWORD_password_cmdb_91" not in node.env_config()
    assert node.env_config()["PASSWORD_password_cmdb_91_0"] == "first-secret"


def test_base_node_params_pushes_credentials_pool_to_stargazer_headers():
    from apps.cmdb.node_configs.ssh.host import HostNodeParams

    instance = SimpleNamespace(
        id=92,
        model_id="host",
        driver_type="job",
        decrypt_credentials=[
            {"credential_id": "cred-1", "username": "admin", "password": "first-secret", "port": 22},
            {"credential_id": "cred-2", "username": "ops", "password": "second-secret", "port": 2200},
        ],
        params={},
        timeout=60,
        access_point=[{"id": 3}],
        instances=[{"ip_addr": "10.0.0.8"}],
        ip_range="",
    )

    node = HostNodeParams(instance)
    headers = node.custom_headers()

    assert headers["cmdbcollect_task_id"] == "92"
    assert headers["cmdbcredential_result_subject"] == "receive_collect_credential_result"
    assert "cmdbcredentials_pool" not in headers
    assert headers["cmdbcredential_count"] == "2"
    assert "cmdbpassword" not in headers
    assert "cmdbusername" not in headers
    assert "cmdbport" not in headers
    assert "cmdbcredential_id" not in headers
    assert headers["cmdbcredential_0_credential_id"] == "cred-1"
    assert headers["cmdbcredential_0_password"] == "${PASSWORD_password_cmdb_92_0}"
    assert headers["cmdbcredential_1_credential_id"] == "cred-2"
    assert headers["cmdbcredential_1_password"] == "${PASSWORD_password_cmdb_92_1}"
    assert "PASSWORD_password_cmdb_92" not in node.env_config()
    assert node.env_config()["PASSWORD_password_cmdb_92_1"] == "second-secret"


def test_base_node_params_push_params_renders_template_with_default_filter():
    from apps.cmdb.node_configs.ssh.host import HostNodeParams

    instance = SimpleNamespace(
        id=93,
        model_id="host",
        driver_type="job",
        decrypt_credentials=[
            {"credential_id": "cred-1", "username": "admin", "password": "first-secret", "port": 22},
        ],
        params={},
        timeout=60,
        access_point=[{"id": 3}],
        instances=[{"ip_addr": "10.0.0.9"}],
        ip_range="",
    )

    node = HostNodeParams(instance)
    result = node.push_params()
    rendered_lines = {line.strip() for line in result[0]["content"].splitlines()}

    assert len(result) == 1
    assert node.custom_headers()["cmdbtimeout"] == "60"
    assert 'interval = "300s"' in rendered_lines
    assert 'timeout = "30s"' in rendered_lines
    assert 'response_timeout = "30s"' in rendered_lines
    assert 'http_headers = {' in result[0]["content"]


def test_base_node_params_push_params_uses_task_cycle_interval_when_present():
    from apps.cmdb.node_configs.ssh.host import HostNodeParams

    instance = SimpleNamespace(
        id=94,
        model_id="host",
        driver_type="job",
        decrypt_credentials=[
            {"credential_id": "cred-1", "username": "admin", "password": "first-secret", "port": 22},
        ],
        params={},
        timeout=60,
        access_point=[{"id": 3}],
        instances=[{"ip_addr": "10.0.0.10"}],
        ip_range="",
        cycle_value_type="cycle",
        cycle_value="2",
    )

    node = HostNodeParams(instance)
    result = node.push_params()

    assert 'interval = "120s"' in result[0]["content"]


def test_base_node_params_push_params_uses_minute_one_as_60_seconds():
    from apps.cmdb.node_configs.ssh.host import HostNodeParams

    instance = SimpleNamespace(
        id=95,
        model_id="host",
        driver_type="job",
        decrypt_credentials=[
            {"credential_id": "cred-1", "username": "admin", "password": "first-secret", "port": 22},
        ],
        params={},
        timeout=60,
        access_point=[{"id": 3}],
        instances=[{"ip_addr": "10.0.0.11"}],
        ip_range="",
        cycle_value_type="cycle",
        cycle_value="1",
    )

    node = HostNodeParams(instance)
    result = node.push_params()

    assert 'interval = "60s"' in result[0]["content"]


@pytest.mark.parametrize(
    ("node_params_class", "model_id", "primary_credential", "secondary_credential", "expected_extra_headers"),
    [
        (
            "apps.cmdb.node_configs.databases.mysql.MysqlNodeParams",
            "mysql",
            {"credential_id": "cred-1", "user": "root", "password": "first-secret", "port": 3306},
            {"credential_id": "cred-2", "user": "ops", "password": "second-secret", "port": 3307},
            {},
        ),
        (
            "apps.cmdb.node_configs.databases.oracle.OracleNodeParams",
            "oracle",
            {
                "credential_id": "cred-1",
                "user": "system",
                "password": "first-secret",
                "port": 1521,
                "service_name": "orcl",
            },
            {
                "credential_id": "cred-2",
                "user": "ops",
                "password": "second-secret",
                "port": 1522,
                "service_name": "orcl2",
            },
            {"cmdbcredential_1_service_name": "orcl2"},
        ),
        (
            "apps.cmdb.node_configs.databases.mssql.MssqlNodeParams",
            "mssql",
            {"credential_id": "cred-1", "user": "sa", "password": "first-secret", "port": 1433, "database": "master"},
            {"credential_id": "cred-2", "user": "ops", "password": "second-secret", "port": 1434, "database": "cmdb"},
            {"cmdbcredential_1_database": "cmdb"},
        ),
        (
            "apps.cmdb.node_configs.databases.postgresql.PostgresqlNodeParams",
            "postgresql",
            {"credential_id": "cred-1", "user": "postgres", "password": "first-secret", "port": 5432},
            {"credential_id": "cred-2", "user": "ops", "password": "second-secret", "port": 5433},
            {},
        ),
    ],
)
def test_direct_database_node_params_push_multicred_headers(
    node_params_class,
    model_id,
    primary_credential,
    secondary_credential,
    expected_extra_headers,
):
    from django.utils.module_loading import import_string

    node_cls = import_string(node_params_class)
    instance = SimpleNamespace(
        id=120,
        model_id=model_id,
        driver_type="protocol",
        decrypt_credentials=[primary_credential, secondary_credential],
        params={},
        timeout=60,
        access_point=[{"id": 3}],
        instances=[{"ip_addr": "10.0.0.8"}],
        ip_range="",
    )

    node = node_cls(instance)
    headers = node.custom_headers()

    assert headers["cmdbcredential_count"] == "2"
    assert "cmdbpassword" not in headers
    assert "cmdbcredential_id" not in headers
    assert headers["cmdbcredential_0_credential_id"] == "cred-1"
    assert headers["cmdbcredential_0_password"] == "${PASSWORD_password_cmdb_120_0}"
    assert headers["cmdbcredential_1_credential_id"] == "cred-2"
    assert headers["cmdbcredential_1_password"] == "${PASSWORD_password_cmdb_120_1}"
    assert f"PASSWORD_password_cmdb_{instance.id}" not in node.env_config()
    assert node.env_config()["PASSWORD_password_cmdb_120_1"] == "second-secret"
    for header_key, expected_value in expected_extra_headers.items():
        assert headers[header_key] == expected_value


def test_base_node_params_single_credential_keeps_legacy_headers():
    from apps.cmdb.node_configs.ssh.host import HostNodeParams

    instance = SimpleNamespace(
        id=94,
        model_id="host",
        driver_type="job",
        decrypt_credentials=[
            {"credential_id": "cred-1", "username": "admin", "password": "first-secret", "port": 22},
        ],
        params={},
        timeout=60,
        access_point=[{"id": 3}],
        instances=[{"ip_addr": "10.0.0.10"}],
        ip_range="",
    )

    node = HostNodeParams(instance)
    headers = node.custom_headers()

    assert "cmdbcredential_count" not in headers
    assert headers["cmdbpassword"] == "${PASSWORD_password_cmdb_94}"
    assert headers["cmdbcredential_id"] == "cred-1"
    assert node.env_config()["PASSWORD_password_cmdb_94"] == "first-secret"


def test_network_node_params_single_credential_carries_topology_contract():
    from apps.cmdb.node_configs.network.network import NetworkNodeParams

    instance = SimpleNamespace(
        id=95,
        model_id="network",
        driver_type="protocol",
        decrypt_credentials=[
            {"credential_id": "cred-1", "version": "v2c", "community": "public", "snmp_port": 161},
        ],
        params={
            "has_network_topo": True,
            "topology_protocols": ["lldp", "fdb"],
            "topology_fallback_strategy": "strict_neighbors_only",
            "min_confidence": 0.75,
        },
        timeout=60,
        access_point=[{"id": 3}],
        instances=[{"ip_addr": "10.0.0.11"}],
        ip_range="",
    )

    node = NetworkNodeParams(instance)
    credential = node.set_credential()

    assert credential["has_network_topo"] is True
    # 下发给 agent 的拓扑协议必须是逗号串（agent 按逗号 split 解析），
    # 不能是 Python 列表 repr（会被 custom_headers 的 str() 破坏成 "['lldp', 'fdb']"）
    assert credential["topology_protocols"] == "lldp,fdb"
    assert credential["topology_fallback_strategy"] == "strict_neighbors_only"
    assert credential["min_confidence"] == 0.75


def test_config_file_node_params_carries_execution_id():
    from apps.cmdb.node_configs.ssh.config_file import ConfigFileNodeParams

    instance = SimpleNamespace(
        id=96,
        task_id="execution-current",
        model_id="config_file",
        driver_type="job",
        decrypt_credentials=[
            {"credential_id": "cred-1", "username": "admin", "password": "secret", "port": 22},
        ],
        params={"config_file_path": "/etc/app.conf"},
        timeout=60,
        access_point=[{"id": 3}],
        instances=[{"_id": "inst-1", "model_id": "host", "ip_addr": "10.0.0.10"}],
        ip_range="",
    )

    credential = ConfigFileNodeParams(instance).set_credential()

    assert credential["execution_id"] == "execution-current"


def test_network_node_params_topology_protocols_header_is_agent_parseable():
    """复现并防回归：topology_protocols 下发到 header 后必须能被 agent 的 split(',') 正确解析。
    旧实现把列表 str() 成 "['lldp', 'cdp', 'fdb', 'arp']"，agent 解析为空 → 不采 LLDP/CDP/FDB。"""
    from apps.cmdb.node_configs.network.network import NetworkNodeParams

    instance = SimpleNamespace(
        id=97,
        model_id="network",
        driver_type="protocol",
        decrypt_credentials=[{"credential_id": "cred-1", "version": "v2c", "community": "public", "snmp_port": 161}],
        params={"has_network_topo": True, "topology_protocols": ["lldp", "cdp", "fdb", "arp"]},
        timeout=60,
        access_point=[{"id": 3}],
        instances=[{"ip_addr": "10.0.0.11"}],
        ip_range="",
    )

    node = NetworkNodeParams(instance)
    headers = node.custom_headers()

    raw = headers["cmdbtopology_protocols"]
    # 不能含列表 repr 的方括号/引号
    assert "[" not in raw and "'" not in raw, f"topology_protocols 下发被破坏: {raw!r}"
    # agent 解析（split 逗号）应还原出协议集合
    parsed = [p.strip() for p in raw.split(",") if p.strip()]
    assert parsed == ["lldp", "cdp", "fdb", "arp"]


def test_network_node_params_multicred_pool_carries_topology_contract_defaults():
    from apps.cmdb.node_configs.network.network import NetworkNodeParams

    instance = SimpleNamespace(
        id=96,
        model_id="network",
        driver_type="protocol",
        decrypt_credentials=[
            {"credential_id": "cred-1", "version": "v2c", "community": "public", "snmp_port": 161},
            {"credential_id": "cred-2", "version": "v3", "username": "ops", "authkey": "a", "privkey": "b"},
        ],
        params={"has_network_topo": True},
        timeout=60,
        access_point=[{"id": 3}],
        instances=[{"ip_addr": "10.0.0.12"}],
        ip_range="",
    )

    node = NetworkNodeParams(instance)
    credentials_pool = node.build_credentials_pool()

    assert len(credentials_pool) == 2
    assert credentials_pool[0]["has_network_topo"] is True
    assert credentials_pool[0]["topology_protocols"] == "lldp,cdp,fdb,arp"
    assert credentials_pool[0]["topology_fallback_strategy"] == "prefer_neighbors_then_fdb_then_arp"
    assert credentials_pool[0]["min_confidence"] == 0.0
    assert credentials_pool[1]["topology_protocols"] == "lldp,cdp,fdb,arp"
    assert credentials_pool[1]["topology_fallback_strategy"] == "prefer_neighbors_then_fdb_then_arp"
    assert credentials_pool[1]["min_confidence"] == 0.0
