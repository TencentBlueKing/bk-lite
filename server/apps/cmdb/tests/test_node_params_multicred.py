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

    assert len(result) == 1
    assert 'interval = "300s"' in result[0]["content"]
    assert 'timeout = "60s"' in result[0]["content"]
    assert 'http_headers = {' in result[0]["content"]


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