"""采集清理的共同判定；调用方提供完整快照和已限定来源的资源。"""
from datetime import datetime, timedelta

from apps.cmdb.constants.constants import DataCleanupStrategy


def parse_collect_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # 无时区的历史数据不能推断属于哪个时区，保留并允许其余资源继续清理。
    return parsed if parsed.utcoffset() is not None else None


def snapshot_allows_cleanup(plugin, model_id):
    complete = getattr(plugin, "snapshot_complete", None)
    authoritative = getattr(plugin, "is_authoritative_snapshot", None)
    if complete is False:
        return False
    if callable(authoritative):
        return bool(authoritative(model_id))
    return complete is True


def cleanup_due(strategy, collect_time, observed_at, expire_days=0):
    if strategy == DataCleanupStrategy.NO_CLEANUP:
        return False
    last_seen = parse_collect_time(collect_time)
    observed = parse_collect_time(observed_at)
    if observed and last_seen and last_seen > observed:
        return False
    if strategy == DataCleanupStrategy.IMMEDIATELY:
        return True
    return bool(
        strategy == DataCleanupStrategy.AFTER_EXPIRATION
        and expire_days > 0
        and last_seen
        and observed
        and last_seen < observed - timedelta(days=expire_days)
    )


def is_collection_target(instance, targets):
    for target in targets:
        if instance.get("inst_uuid") and target.get("inst_uuid") == instance["inst_uuid"]:
            return True
        if target.get("model_id") == instance.get("model_id") and target.get("inst_name") == instance.get("inst_name"):
            return True
    return False
