from __future__ import annotations

from typing import Any

from apps.workflow_orchestration.services.job_operations import execute_custom_script
from apps.workflow_orchestration.services.target_resolver import RpcTargetGateway, TargetGateway, resolve_target_fields


def _target_reference(target: Any) -> str:
    if isinstance(target, str):
        return target
    if not isinstance(target, dict):
        raise ValueError("作业执行目标非法")
    source = str(target.get("source") or "")
    source_id = str(target.get("source_id") or "")
    if source == "node_mgmt" and source_id:
        return f"node:{source_id}"
    if source in {"job_mgmt", "manual"} and source_id.isdigit():
        return f"manual:{source_id}"
    raise ValueError("作业目标缺少受控来源")


def _trusted_execution_context(inputs: dict[str, Any]) -> tuple[int, dict[str, str]]:
    context = inputs.get("__bklite_context")
    if not isinstance(context, dict):
        raise ValueError("作业执行缺少可信流程上下文")
    organization_id = context.get("organization_id")
    actor = context.get("actor")
    if isinstance(organization_id, bool) or not isinstance(organization_id, int) or organization_id <= 0:
        raise ValueError("作业执行缺少可信组织上下文")
    if not isinstance(actor, dict) or not str(actor.get("username") or "").strip():
        raise ValueError("作业执行缺少可信执行人上下文")
    return organization_id, {
        "username": str(actor["username"]).strip()[:150],
        "domain": str(actor.get("domain") or "domain.com")[:255],
    }


def execute(inputs: dict[str, Any], *, gateway: TargetGateway | None = None, executor=None) -> dict[str, Any]:
    team, actor = _trusted_execution_context(inputs)
    targets = inputs.get("targets")
    if not isinstance(targets, list):
        raise ValueError("作业执行目标非法")
    script_type = str(inputs.get("script_type") or "")
    if script_type not in {"shell", "python", "bat", "powershell"}:
        raise ValueError("脚本类型非法")
    references = [_target_reference(target) for target in targets]
    authoritative_gateway = gateway or RpcTargetGateway(
        team=team,
        permission_data={
            "username": actor["username"],
            "domain": actor["domain"],
            "current_team": team,
            "include_children": False,
            "is_superuser": False,
        },
    )
    # 与作业平台对齐：Linux/Windows 均可同批提交；不兼容主机由作业层按目标失败。
    resolution = resolve_target_fields(
        {"targets": references},
        [
            {
                "key": "targets",
                "required": True,
                "allowed_sources": ["node_mgmt", "job_mgmt"],
                "allowed_operating_systems": ["linux", "windows"],
                "min_count": 1,
                "max_count": 100,
            }
        ],
        gateway=authoritative_gateway,
    )
    return execute_custom_script(
        {**inputs, "targets": resolution.inputs["targets"], "team": team, "actor": actor},
        executor=executor,
    )
