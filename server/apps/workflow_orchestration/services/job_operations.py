from __future__ import annotations

import json
from typing import Any

from apps.workflow_orchestration.atom_packages.runtime import actor_snapshot, team_id
from apps.workflow_orchestration.services.job_platform import JobPlatformExecutor

CUSTOM_RESULT_MARKER = "BK_LITE_RESULT="
MAX_CAPTURED_OUTPUT = 16 * 1024
MAX_RESULT_DEPTH = 10
SCRIPT_OPERATING_SYSTEM = {"shell": "linux", "python": "linux", "bat": "windows", "powershell": "windows"}


def _json_depth(value: Any, level: int = 1) -> int:
    if isinstance(value, dict):
        return max((_json_depth(item, level + 1) for item in value.values()), default=level)
    if isinstance(value, list):
        return max((_json_depth(item, level + 1) for item in value), default=level)
    return level


def _target_groups(targets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """按目标来源分组；与作业平台一致，不在提交前按 OS 过滤。"""
    if not 1 <= len(targets) <= 100:
        raise ValueError("作业执行必须选择 1 到 100 台目标主机")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for target in targets:
        source = str(target.get("source") or "")
        if source not in {"node_mgmt", "job_mgmt"}:
            raise ValueError("作业目标缺少受控来源")
        target_source = "manual" if source == "job_mgmt" else source
        grouped.setdefault(target_source, []).append(target)
    return grouped


def _target_identity(target: dict[str, Any], source_id: str) -> dict[str, Any]:
    return {
        "id": str(target.get("id") or source_id),
        "source": target.get("source", ""),
        "source_id": target.get("source_id", source_id),
        "name": target.get("name", ""),
        "ip": target.get("ip", ""),
        "operating_system": target.get("operating_system") or target.get("os_type") or "",
    }


def _parse_optional_data(stdout: str) -> Any:
    bounded = stdout[:MAX_CAPTURED_OUTPUT]

    def marker_payloads(value: Any):
        if isinstance(value, str):
            for line in value.splitlines():
                normalized = line.strip()
                if normalized.startswith(CUSTOM_RESULT_MARKER):
                    yield normalized[len(CUSTOM_RESULT_MARKER) :]
            return
        if isinstance(value, dict):
            for child in value.values():
                yield from marker_payloads(child)
            return
        if isinstance(value, list):
            for child in value:
                yield from marker_payloads(child)

    marker_values = list(marker_payloads(bounded))
    decoder = json.JSONDecoder()
    cursor = 0
    while cursor < len(bounded):
        object_start = bounded.find("{", cursor)
        array_start = bounded.find("[", cursor)
        starts = [index for index in (object_start, array_start) if index >= 0]
        if not starts:
            break
        start = min(starts)
        try:
            decoded, end = decoder.raw_decode(bounded, start)
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        marker_values.extend(marker_payloads(decoded))
        cursor = end

    if not marker_values:
        return None
    try:
        decoded = json.loads(marker_values[-1])
    except json.JSONDecodeError as error:
        raise ValueError("BK_LITE_RESULT 后必须是有效 JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError("BK_LITE_RESULT 必须是 JSON 对象")
    if _json_depth(decoded) > MAX_RESULT_DEPTH:
        raise ValueError("BK_LITE_RESULT 嵌套超过 10 层")
    return decoded


def _execution_results(detail: dict[str, Any], targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target_map = {str(target.get("source_id")): target for target in targets}
    returned: set[str] = set()
    results: list[dict[str, Any]] = []
    for raw in detail.get("execution_results", []) or []:
        source_id = str(raw.get("target_key") or raw.get("node_id") or raw.get("target_id") or "")
        target = target_map.get(source_id, {})
        returned.add(source_id)
        raw_stdout = str(raw.get("stdout") or "")
        stdout = raw_stdout[:MAX_CAPTURED_OUTPUT]
        stderr = str(raw.get("stderr") or raw.get("error_message") or "")[:MAX_CAPTURED_OUTPUT]
        success = str(raw.get("status") or "").lower() == "success"
        exit_code = raw.get("exit_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            exit_code = 0 if success else 1
        error = None if success else (stderr or "脚本执行失败")[:500]
        data = None
        if success:
            data = _parse_optional_data(stdout)
            if data is None:
                data = {}
        results.append(
            {
                "target": _target_identity(target, source_id),
                "status": "SUCCESS" if success else "FAILED",
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "data": data,
                "error": error,
            }
        )
    for source_id, target in target_map.items():
        if source_id in returned:
            continue
        results.append(
            {
                "target": _target_identity(target, source_id),
                "status": "FAILED",
                "exit_code": 1,
                "stdout": "",
                "stderr": "",
                "data": None,
                "error": "作业平台未返回该目标结果",
            }
        )
    return results


def _execution_params(raw: Any) -> list[dict[str, str]]:
    if raw in (None, ""):
        return []
    if isinstance(raw, list):
        if len(raw) > 50 or not all(isinstance(item, (str, int, float)) and not isinstance(item, bool) for item in raw):
            raise ValueError("执行参数非法")
        return [{"value": str(item)} for item in raw]
    text = str(raw).strip()
    if len(text) > 4000:
        raise ValueError("执行参数超过长度限制")
    return [{"value": item} for item in text.split()] if text else []


def execute_custom_script(inputs: dict[str, Any], *, executor=None) -> dict[str, Any]:
    targets = inputs.get("targets")
    if not isinstance(targets, list):
        raise ValueError("作业执行目标非法")
    script_type = str(inputs.get("script_type") or "")
    if script_type not in SCRIPT_OPERATING_SYSTEM:
        raise ValueError("脚本类型非法")
    script_content = str(inputs.get("script_content") or "")
    if not script_content.strip() or len(script_content) > 100000:
        raise ValueError("作业脚本不能为空")
    groups = _target_groups(targets)
    params = _execution_params(inputs.get("execution_params"))
    team = team_id(inputs.get("team"))
    actor = actor_snapshot(inputs)
    timeout = int(inputs.get("timeout_seconds") or 600)
    runner = executor or JobPlatformExecutor()
    submissions: list[tuple[int, list[dict[str, Any]]]] = []
    for source, source_targets in groups.items():
        task_id = runner.submit(
            name="编排中心-脚本执行",
            nodes=source_targets,
            team=team,
            target_source=source,
            script_type=script_type,
            script_content=script_content,
            timeout=timeout,
            actor=actor,
            params=params,
        )
        submissions.append((task_id, source_targets))

    results: list[dict[str, Any]] = []
    for task_id, source_targets in submissions:
        detail = runner.wait(task_id, team=team, timeout=timeout + 60, actor=actor)
        results.extend(_execution_results(detail, source_targets))
    succeeded = sum(item["status"] == "SUCCESS" for item in results)
    failed = len(results) - succeeded
    return {
        "results": results,
        "summary": {"total": len(results), "succeeded": succeeded, "failed": failed},
        "job_task_ids": [task_id for task_id, _targets in submissions],
    }
