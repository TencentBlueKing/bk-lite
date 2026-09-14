"""CMDB ↔ 监控对象映射：同步名单与 ingest 共用一张表。"""

from apps.cmdb.constants.monitor_link import CMDB_MODEL_TO_MONITOR_OBJECT, CMDB_MONITOR_SYNC_MODEL_IDS


def test_cmdb_monitor_sync_model_ids_match_mapping_keys():
    assert CMDB_MONITOR_SYNC_MODEL_IDS == frozenset(CMDB_MODEL_TO_MONITOR_OBJECT)
