from __future__ import annotations

import copy
import hashlib
import uuid
from typing import Any

from django.core import signing

LAUNCH_TOKEN_SALT = "workflow-orchestration.launch-plan.v1"
LAUNCH_TOKEN_TTL_SECONDS = 15 * 60
SUPPORTED_TARGET_SOURCES = {"node_mgmt", "job_mgmt"}
SUPPORTED_TARGET_OPERATING_SYSTEMS = {"linux", "windows"}


class LaunchPlanTokenError(ValueError):
    pass


def extract_target_fields(canvas_metadata: Any) -> list[dict[str, Any]]:
    if not isinstance(canvas_metadata, dict):
        return []
    contract = canvas_metadata.get("data_contract")
    if not isinstance(contract, dict):
        return []
    fields: list[dict[str, Any]] = []
    for item in contract.get("inputs") or []:
        if not isinstance(item, dict):
            continue
        schema = item.get("schema") if isinstance(item.get("schema"), dict) else {}
        ui = item.get("ui")
        binding = ui.get("targetBinding") if isinstance(ui, dict) else None
        if not isinstance(binding, dict):
            binding = schema.get("x-target-binding")
        if not isinstance(binding, dict):
            continue
        mode = binding.get("mode")
        if mode != "runtime":
            continue
        item_schema = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        if schema.get("type") != "array" or item_schema.get("type") != "string":
            raise ValueError(f"目标字段 {item.get('key') or '--'} 必须是字符串数组")
        if item.get("sensitive") or schema.get("sensitive"):
            raise ValueError(f"目标字段 {item.get('key') or '--'} 不能标记为敏感")
        allowed_sources = binding.get("allowedSources")
        if not isinstance(allowed_sources, list) or not allowed_sources:
            raise ValueError(f"目标字段 {item.get('key') or '--'} 缺少允许来源")
        normalized_sources = list(dict.fromkeys(str(source) for source in allowed_sources))
        if any(source not in SUPPORTED_TARGET_SOURCES for source in normalized_sources):
            raise ValueError(f"目标字段 {item.get('key') or '--'} 包含不支持的来源")
        allowed_operating_systems = binding.get("allowedOperatingSystems", [])
        if not isinstance(allowed_operating_systems, list):
            raise ValueError(f"目标字段 {item.get('key') or '--'} 的操作系统约束非法")
        normalized_operating_systems = list(dict.fromkeys(str(value).strip().lower() for value in allowed_operating_systems))
        if any(value not in SUPPORTED_TARGET_OPERATING_SYSTEMS for value in normalized_operating_systems):
            raise ValueError(f"目标字段 {item.get('key') or '--'} 包含不支持的操作系统")
        min_count = int(binding.get("minCount", 1))
        max_count = int(binding.get("maxCount", 100))
        if not 0 <= min_count <= max_count <= 100:
            raise ValueError(f"目标字段 {item.get('key') or '--'} 的数量约束非法")
        if schema.get("minItems", min_count) != min_count or schema.get("maxItems", max_count) != max_count:
            raise ValueError(f"目标字段 {item.get('key') or '--'} 的 Schema 与选择器数量约束不一致")
        fields.append(
            {
                "key": item["key"],
                "name": item.get("name") or item["key"],
                "required": bool(item.get("required")),
                "binding_mode": "runtime",
                "allowed_sources": normalized_sources,
                "allowed_operating_systems": normalized_operating_systems,
                "min_count": min_count,
                "max_count": max_count,
            }
        )
    return fields


def build_launch_plan(
    *,
    workflow_id: int,
    workflow_name: str,
    workflow_version: int,
    canvas_metadata: dict[str, Any],
    team: int,
    username: str,
    domain: str,
    target_fields: list[dict[str, Any]] | None = None,
    parent_execution_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "nonce": uuid.uuid4().hex,
        "workflow_id": int(workflow_id),
        "workflow_version": int(workflow_version),
        "team": int(team),
        "username": username,
        "domain": domain,
        "parent_execution_id": parent_execution_id,
    }
    token = signing.dumps(payload, salt=LAUNCH_TOKEN_SALT, compress=True)
    metadata = canvas_metadata if isinstance(canvas_metadata, dict) else {}
    fields = copy.deepcopy(target_fields) if target_fields is not None else extract_target_fields(metadata)
    input_schema = copy.deepcopy(metadata.get("input_schema") or {})
    schema_ui = {
        key: {"ui:widget": schema["x-widget"]}
        for key, schema in (input_schema.get("properties") or {}).items()
        if isinstance(schema, dict) and isinstance(schema.get("x-widget"), str)
    }
    explicit_ui = copy.deepcopy(metadata.get("input_ui_schema") or {})
    return {
        "workflow_id": int(workflow_id),
        "workflow_name": workflow_name,
        "workflow_version": int(workflow_version),
        "input_schema": input_schema,
        "ui_schema": {**schema_ui, **explicit_ui},
        "target_fields": fields,
        "risk_summary": copy.deepcopy(metadata.get("risk_summary") or {}),
        "parent_execution_id": parent_execution_id,
        "launch_token": token,
        "expires_in_seconds": LAUNCH_TOKEN_TTL_SECONDS,
    }


def verify_launch_token(
    token: str,
    *,
    workflow_id: int,
    team: int,
    username: str,
    domain: str,
) -> dict[str, Any]:
    if not isinstance(token, str) or not token:
        raise LaunchPlanTokenError("缺少启动凭证，请重新打开执行窗口")
    try:
        payload = signing.loads(
            token,
            salt=LAUNCH_TOKEN_SALT,
            max_age=LAUNCH_TOKEN_TTL_SECONDS,
        )
    except signing.SignatureExpired as error:
        raise LaunchPlanTokenError("启动凭证已过期，请重新打开执行窗口") from error
    except signing.BadSignature as error:
        raise LaunchPlanTokenError("启动凭证无效，请重新打开执行窗口") from error
    if not isinstance(payload, dict):
        raise LaunchPlanTokenError("启动凭证内容非法")
    if payload.get("workflow_id") != int(workflow_id):
        raise LaunchPlanTokenError("启动凭证与流程不匹配")
    if payload.get("team") != int(team):
        raise LaunchPlanTokenError("启动凭证与当前组织不匹配")
    if payload.get("username") != username or payload.get("domain") != domain:
        raise LaunchPlanTokenError("启动凭证与当前操作者不匹配")
    if not isinstance(payload.get("workflow_version"), int) or not payload.get("nonce"):
        raise LaunchPlanTokenError("启动凭证内容非法")
    return payload


def launch_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
