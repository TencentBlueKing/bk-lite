from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.scan_shot import ScanShot, build_scan_collect_headers, join_ip_ranges


def _mysql_shot(**overrides):
    values = {
        "id": 99,
        "model_id": "mysql",
        "driver_type": CollectDriverTypes.PROTOCOL,
        "ip_range": "10.0.1.1-10.0.1.3",
        "instances": [],
        "credential": CollectCredentialPoolService.normalize_pool([{"username": "monitor", "password": "db-secret", "port": 3306}]),
        "timeout": 30,
        "params": {"has_network_topo": False},
        "access_point": [{"id": "node-1"}],
    }
    values.update(overrides)
    return ScanShot(**values)


def test_join_ip_ranges_matches_collect_ip_range_shape():
    assert join_ip_ranges([{"begin": "10.0.1.1", "end": "10.0.1.10"}]) == "10.0.1.1-10.0.1.10"
    assert (
        join_ip_ranges(
            [
                {"begin": "10.0.1.1", "end": "10.0.1.10"},
                {"begin": "10.0.2.1", "end": "10.0.2.5"},
            ]
        )
        == "10.0.1.1-10.0.1.10,10.0.2.1-10.0.2.5"
    )


def test_scan_shot_mysql_headers_reuse_node_params():
    headers = build_scan_collect_headers(_mysql_shot())
    assert headers["cmdbplugin_name"] == "mysql_info"
    assert headers["cmdbhosts"] == "10.0.1.1-10.0.1.3"
    assert headers["cmdbcollect_task_id"] == "99"
    assert headers["cmdbcredential_result_subject"] == "receive_scan_credential_result"
    assert headers["instance_id"] == "cmdb_99"


def test_scan_shot_allows_more_than_three_credentials():
    pool = CollectCredentialPoolService.normalize_pool(
        [
            {"username": "u1", "password": "p1", "port": 3306},
            {"username": "u2", "password": "p2", "port": 3306},
            {"username": "u3", "password": "p3", "port": 3306},
            {"username": "u4", "password": "p4", "port": 3306},
        ]
    )
    headers = build_scan_collect_headers(_mysql_shot(credential=pool))
    assert headers["cmdbcredential_count"] == "4"
    assert "cmdbcredential_0_password" in headers
    assert "cmdbcredential_3_password" in headers
    assert headers["cmdbcredential_0_password"] == "p1"
