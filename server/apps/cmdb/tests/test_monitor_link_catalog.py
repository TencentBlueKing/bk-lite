"""CMDB ↔ 监控对象映射：同步名单与 ingest 共用一张表。"""

from apps.cmdb.constants.monitor_link import CMDB_MODEL_TO_MONITOR_OBJECT, CMDB_MONITOR_SYNC_MODEL_IDS, builtin_model_id


def test_cmdb_monitor_sync_model_ids_match_mapping_keys():
    assert CMDB_MONITOR_SYNC_MODEL_IDS == frozenset(CMDB_MODEL_TO_MONITOR_OBJECT)


def test_builtin_model_id_inverts_mapping_without_default_host():
    assert builtin_model_id("Host") == "host"
    assert builtin_model_id("Switch") == "switch"
    assert builtin_model_id("Docker Container") == "docker"
    assert builtin_model_id("Weblogic") is None
    assert builtin_model_id("主机") is None
    assert builtin_model_id("") is None
    assert builtin_model_id(None) is None
    assert CMDB_MODEL_TO_MONITOR_OBJECT["host"] == "Host"
