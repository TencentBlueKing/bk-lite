"""采集结果快照写入前补齐 inst_uuid，避免游标清洗后再次写入遗留图 ID。"""

from apps.core.logger import cmdb_logger as logger


def normalize_collect_result_payloads(*payloads):
    try:
        from apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs import Command

        command = Command()
        command._dry_run = False
        command._graph_uuid_by_id = {}
        numeric_ids = []
        for payload in payloads:
            Command._collect_graph_ids(payload, numeric_ids)
        if not numeric_ids:
            return payloads
        uuid_map = command._graph_uuid_map(numeric_ids)
        rewritten = []
        for payload in payloads:
            value, _changed = Command._rewrite_json_uuids(payload, uuid_map)
            rewritten.append(value)
        return tuple(rewritten)
    except Exception as exc:
        logger.warning(
            "event=collect_snapshot_uuid_skipped failed_stage=%s error_type=%s",
            "graph_uuid_lookup",
            type(exc).__name__,
        )
        return payloads
