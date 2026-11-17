COMPLETE_RUN_STATUSES = {"success", "partial"}


def plan_account_associations(channels: list[dict], runs: list[dict], mapping_ids_by_channel: dict[int, list[int]]) -> list[dict]:
    """每条渠道单独生成一个账号关联。不访问数据库，不调用外部接口。"""
    complete_channel_ids: set[int] = set()
    runs_by_channel: dict[int, list[dict]] = {}
    for run in runs:
        runs_by_channel.setdefault(run["channel_id"], []).append(run)
        if run.get("status") in COMPLETE_RUN_STATUSES and run.get("finished_at") is not None:
            complete_channel_ids.add(run["channel_id"])

    planned = []
    for channel in sorted(channels, key=lambda item: item["id"]):
        if channel["id"] in complete_channel_ids:
            kept_mapping_ids = list(mapping_ids_by_channel.get(channel["id"]) or [])
            status = "ready" if kept_mapping_ids else "needs_resync"
        else:
            kept_mapping_ids = []
            status = "pending_sync"
        schedule = channel.get("schedule_config") or {}
        if _is_daily(schedule):
            schedule_config = {"enabled": True, "sync_time": schedule["sync_time"]}
        else:
            schedule_config = {"enabled": False}
        planned.append(
            {
                "integration_instance_id": channel["integration_instance_id"],
                "name": channel["name"],
                "platform_match_field": channel["platform_match_field"],
                "external_match_field": channel["external_match_field"],
                "external_receive_field": channel["external_receive_field"],
                "schedule_config": schedule_config,
                "status": status,
                "source_channel_ids": [channel["id"]],
                "kept_mapping_ids": kept_mapping_ids,
                "run_ids": [run["id"] for run in runs_by_channel.get(channel["id"], [])],
            }
        )
    return planned


def _is_daily(schedule_config) -> bool:
    schedule = schedule_config or {}
    return bool(schedule.get("enabled")) and bool(schedule.get("sync_time"))
