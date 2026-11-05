"""编排文件分发节点关联的作业平台文件续期。"""

from __future__ import annotations

from typing import Any, Iterable

from apps.job_mgmt.services.distribution_file_service import WORKFLOW_FILE_RENEW_DAYS, renew_distribution_files


def _walk_definition_tasks(tasks: Iterable[Any]):
    for task in tasks:
        if not isinstance(task, dict):
            continue
        yield task
        for key in ("loopOver", "defaultCase"):
            nested = task.get(key)
            if isinstance(nested, list):
                yield from _walk_definition_tasks(nested)
        for branch in (task.get("decisionCases") or {}).values():
            if isinstance(branch, list):
                yield from _walk_definition_tasks(branch)
        for branch in task.get("forkTasks", []) or []:
            if isinstance(branch, list):
                yield from _walk_definition_tasks(branch)


def collect_file_distribute_keys(definition: dict[str, Any] | None) -> list[str]:
    if not isinstance(definition, dict):
        return []
    keys: list[str] = []
    seen: set[str] = set()
    for task in _walk_definition_tasks(definition.get("tasks") or []):
        if task.get("name") != "bklite_file_distribute":
            continue
        params = task.get("inputParameters") if isinstance(task.get("inputParameters"), dict) else {}
        files = params.get("files")
        if not isinstance(files, list):
            continue
        for item in files:
            if not isinstance(item, dict):
                continue
            file_key = str(item.get("file_key") or "").strip()
            if not file_key or file_key in seen:
                continue
            seen.add(file_key)
            keys.append(file_key)
    return keys


def renew_workflow_file_distribute_assets(*, definition: dict[str, Any] | None, team: list[int] | int | None) -> int:
    file_keys = collect_file_distribute_keys(definition)
    if not file_keys:
        return 0
    if isinstance(team, list):
        team_ids = [int(item) for item in team if str(item).lstrip("-").isdigit() and int(item) > 0]
    elif isinstance(team, bool) or not isinstance(team, int) or team <= 0:
        team_ids = []
    else:
        team_ids = [team]
    return renew_distribution_files(file_keys=file_keys, team_ids=team_ids, days=WORKFLOW_FILE_RENEW_DAYS)
