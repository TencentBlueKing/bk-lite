"""采集结果快照写入前补齐 inst_uuid。

查图抛错时不返回原载荷，调用方不得把仍含数字图 ID 的快照落库。
图中已经不存在的数字 ID 补不出 UUID，保留原字段。
"""

from apps.core.logger import cmdb_logger as logger


class CollectSnapshotUuidLookupError(RuntimeError):
    """查图失败，调用方应放弃本次快照写入。"""


def normalize_collect_result_payloads(*payloads):
    from apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs import Command

    command = Command()
    command._dry_run = False
    command._graph_uuid_by_id = {}
    numeric_ids = []
    for payload in payloads:
        Command._collect_graph_ids(payload, numeric_ids)
    if not numeric_ids:
        return payloads
    try:
        uuid_map = command._graph_uuid_map(numeric_ids)
    except Exception as exc:
        logger.warning(
            "event=collect_snapshot_uuid_skipped failed_stage=%s error_type=%s",
            "graph_uuid_lookup",
            type(exc).__name__,
        )
        raise CollectSnapshotUuidLookupError("graph_uuid_lookup") from None
    rewritten = []
    for payload in payloads:
        value, _changed = Command._rewrite_json_uuids(payload, uuid_map)
        rewritten.append(value)
    return tuple(rewritten)
