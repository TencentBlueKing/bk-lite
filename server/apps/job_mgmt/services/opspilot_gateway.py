"""OpsPilot 作业入口。

身份只来自已校验的签名。请求体中的组织、用户、执行人和脚本正文（脚本库）全部忽略。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from asgiref.sync import async_to_sync
from django.core.files.base import ContentFile
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.core.logger import job_logger as logger
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.job_mgmt.constants import ExecutionStatus, TriggerSource
from apps.job_mgmt.models import DistributionFile, JobExecution, Playbook, Script, Target
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.execution_service import ExecutionAuthorizationError, ExecutionDispatchError, ExecutionService
from apps.job_mgmt.services.param_crypto import MASKED_DEFAULT, ParamCrypto
from apps.job_mgmt.services.target_list_v2 import query_target_list_v2
from apps.job_mgmt.utils.team_authz import is_team_authorized
from apps.node_mgmt.utils.s3 import upload_file_to_s3
from apps.rpc.jetstream import JetStreamService
from apps.rpc.job_opspilot import (
    ACTION_DESCRIBE_SCRIPT,
    ACTION_DISTRIBUTE,
    ACTION_EXECUTE,
    ACTION_LIST_PLAYBOOK_SCRIPTS,
    ACTION_LIST_SCRIPTS,
    ACTION_LIST_TARGETS,
    ACTION_QUERY,
    ACTION_SEARCH_TARGETS,
    is_job_file_key,
    verify_opspilot_job_request,
)

ALLOWED_SCRIPT_TYPES = ("shell", "python", "powershell", "bat")
SCRIPT_OS = {
    "shell": "linux",
    "python": "linux",
    "powershell": "windows",
    "bat": "windows",
}
OS_LABEL = {"linux": "Linux", "windows": "Windows"}
OS_SCRIPT_TYPES = {"linux": "shell、python", "windows": "powershell、bat"}
CUSTOM_TIMEOUT_SECONDS = 600
MAX_PAGE_SIZE = 20
SEARCH_LIMIT = 20


def _int_env(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _max_upload_bytes() -> int:
    return _int_env("JOB_MAX_UPLOAD_FILE_SIZE_MB", 1024) * 1024 * 1024


def _deny():
    return {"result": False, "message": "作业请求签名无效"}


def _verified_actor(action, token, user_info):
    try:
        payload = verify_opspilot_job_request(token, action, user_info)
    except PermissionDenied:
        return None
    return {
        "team": payload["team_id"],
        "user": payload["user"],
        "domain": payload["domain"],
        "include_children": False,
        "is_superuser": False,
    }


def _rule_names(items) -> list[str]:
    names = []
    for item in items or []:
        name = item.get("rule_name") if isinstance(item, dict) else None
        if name and name not in names:
            names.append(name)
    return names


def _danger_gate(check_result, confirmed: bool):
    if check_result.has_forbidden:
        return {"result": False, "code": "forbidden", "rules": _rule_names(check_result.forbidden)}
    if check_result.has_warning and not confirmed:
        return {"result": False, "code": "confirm", "rules": _rule_names(check_result.warnings)}
    return None


def _public_param(param: dict) -> dict:
    default = param.get("default")
    encrypted = bool(param.get("is_encrypted"))
    has_default = default not in (None, "")
    item = {
        "name": param.get("name") or "",
        "required": bool(param.get("is_required")),
        "type": param.get("type") or "text",
        "options": list(param.get("options") or []),
        "has_default": has_default,
        "encrypted": encrypted,
    }
    if has_default:
        item["default"] = MASKED_DEFAULT if encrypted else default
    return item


def _script_queryset(team_id):
    queryset = Script.objects.all()
    return queryset.filter(build_json_membership_query(queryset, "team", [team_id]))


def _playbook_queryset(team_id):
    queryset = Playbook.objects.all()
    return queryset.filter(build_json_membership_query(queryset, "team", [team_id]))


def _script_paths(file_list) -> list[str]:
    """把 Playbook 文件树收成可选的 yml/yaml 路径，不带文件内容。"""

    found = []

    def add(path):
        if path.lower().endswith((".yml", ".yaml")) and path not in found:
            found.append(path)

    def join(prefix, name):
        cleaned = str(name or "").replace("\\", "/").strip("/")
        if not cleaned or any(part in {"", ".", ".."} for part in cleaned.split("/")):
            return ""
        return f"{prefix}/{cleaned}" if prefix else cleaned

    def walk(nodes, prefix):
        if isinstance(nodes, str):
            path = join(prefix, nodes)
            if path:
                add(path)
            return
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if isinstance(node, str):
                walk(node, prefix)
                continue
            if not isinstance(node, dict):
                continue
            path = join(prefix, node.get("name"))
            children = node.get("children")
            if node.get("type") == "directory" or isinstance(children, list):
                walk(children or [], path or prefix)
                continue
            if path:
                add(path)

    walk(file_list, "")
    return found


def _playbook_public_param(param):
    if not isinstance(param, dict) or not str(param.get("name") or "").strip():
        return None
    if "is_required" in param or param.get("type"):
        return _public_param(param)
    default = param.get("default")
    has_default = default not in (None, "") and not isinstance(default, (dict, list))
    item = {
        "name": str(param.get("name")),
        "required": False,
        "type": "text",
        "options": [],
        "has_default": has_default,
        "encrypted": False,
    }
    if has_default:
        item["default"] = default
    return item


def _positive_ids(values) -> list[int] | None:
    if isinstance(values, str):
        values = [item for item in values.split(",") if item.strip()]
    if not isinstance(values, list) or not values:
        return None
    parsed = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            return None
        if isinstance(value, str) and not value.strip().isdecimal():
            return None
        number = int(value)
        if number <= 0 or number in parsed:
            return None
        parsed.append(number)
    return parsed


def _node_permission(actor):
    return {
        "username": actor["user"],
        "domain": actor["domain"],
        "current_team": actor["team"],
        "include_children": False,
        "is_superuser": False,
    }


def _search_nodes(actor, keyword: str) -> list[dict]:
    try:
        from apps.node_mgmt.nats.node import _authorized_node_queryset

        queryset = _authorized_node_queryset(
            {
                "user": actor["user"],
                "domain": actor["domain"],
                "team": actor["team"],
                "include_children": False,
                "is_superuser": False,
            }
        )
        if keyword:
            queryset = queryset.filter(Q(name__icontains=keyword) | Q(ip__icontains=keyword))
        rows = list(queryset.order_by("id").values("id", "name", "ip", "operating_system")[:SEARCH_LIMIT])
    except Exception as exc:
        logger.warning(
            "event=opspilot_job_node_search_failed failed_stage=search_nodes error_type=%s",
            type(exc).__name__,
        )
        return []
    return [
        {
            "source": "node_mgmt",
            "id": str(row["id"]),
            "name": row["name"],
            "ip": str(row["ip"] or ""),
            "os": str(row["operating_system"] or ""),
        }
        for row in rows
    ]


def _list_nodes(actor, cursor: str) -> dict:
    try:
        from apps.node_mgmt.nats.node import _authorized_node_queryset

        queryset = _authorized_node_queryset(
            {
                "user": actor["user"],
                "domain": actor["domain"],
                "team": actor["team"],
                "include_children": False,
                "is_superuser": False,
            }
        )
        if cursor:
            queryset = queryset.filter(id__gt=cursor)
        rows = list(queryset.order_by("id").values("id", "name", "ip", "operating_system")[: MAX_PAGE_SIZE + 1])
    except Exception as exc:
        logger.warning(
            "event=opspilot_job_node_list_failed failed_stage=list_nodes error_type=%s",
            type(exc).__name__,
        )
        return {"items": [], "next_cursor": None, "has_more": False}
    has_more = len(rows) > MAX_PAGE_SIZE
    rows = rows[:MAX_PAGE_SIZE]
    return {
        "items": [
            {
                "source": "node_mgmt",
                "id": str(row["id"]),
                "name": row["name"],
                "ip": str(row["ip"] or ""),
                "os": str(row["operating_system"] or ""),
            }
            for row in rows
        ],
        "next_cursor": str(rows[-1]["id"]) if has_more else None,
        "has_more": has_more,
    }


def _manual_hits(team_id, keyword: str) -> list[dict]:
    found = {}
    for field in ("name", "ip"):
        result = query_target_list_v2({field: keyword, "page_size": SEARCH_LIMIT}, {team_id})
        if not result.get("result"):
            continue
        for item in result["data"]["items"]:
            found[item["target_id"]] = {
                "source": "manual",
                "id": str(item["target_id"]),
                "name": item["name"],
                "ip": item["ip"],
                "os": item.get("os_type") or "",
            }
    return list(found.values())[:SEARCH_LIMIT]


def _resolve_targets(actor, source, raw_ids):
    team_id = actor["team"]
    if source == "manual":
        ids = _positive_ids(raw_ids)
        if not ids:
            return None, "目标不能为空"
        rows = list(Target.objects.filter(id__in=ids))
        if len(rows) != len(ids) or any(not is_team_authorized(row.team, {team_id}) for row in rows):
            return None, "目标不存在或不属于当前组织"
        by_id = {row.id: row for row in rows}
        target_list = [
            {
                "target_id": by_id[item_id].id,
                "name": by_id[item_id].name,
                "ip": str(by_id[item_id].ip),
                "os": by_id[item_id].os_type or "",
            }
            for item_id in ids
        ]
    elif source == "node_mgmt":
        if isinstance(raw_ids, str):
            raw_ids = [item.strip() for item in raw_ids.split(",") if item.strip()]
        if not isinstance(raw_ids, list) or not raw_ids:
            return None, "目标不能为空"
        node_ids = []
        for item in raw_ids:
            text = str(item).strip()
            if not text or text in node_ids:
                return None, "目标不能为空"
            node_ids.append(text)
        from apps.node_mgmt.services.node import NodeService

        found = NodeService.get_authorized_execution_targets_by_ids(node_ids, _node_permission(actor))
        by_id = {str(item["id"]): item for item in found}
        if any(item_id not in by_id for item_id in node_ids):
            return None, "目标不存在或不属于当前组织"
        for item in found:
            organizations = {int(org) for org in item.get("organization_ids") or [] if str(org).isdecimal()}
            if team_id not in organizations:
                return None, "目标不存在或不属于当前组织"
        target_list = [
            {
                "node_id": by_id[item_id]["id"],
                "name": by_id[item_id]["name"],
                "ip": by_id[item_id]["ip"],
                "os": by_id[item_id].get("operating_system") or "",
                "cloud_region_id": by_id[item_id].get("cloud_region_id"),
            }
            for item_id in node_ids
        ]
    else:
        return None, "目标来源只能是作业管理目标或节点管理目标"
    from apps.job_mgmt.nats_api import _validate_openapi_target_scope

    scope_error = _validate_openapi_target_scope(source, target_list, {team_id})
    if scope_error:
        return None, "目标不存在或不属于当前组织"
    return target_list, None


def _library_params(script, choices):
    definitions = [item for item in (script.params or []) if isinstance(item, dict)]
    if not definitions:
        return [], None
    if not isinstance(choices, list) or len(choices) != len(definitions):
        return None, {"result": False, "code": "need_params", "params": [_public_param(item) for item in definitions]}
    by_name = {}
    for choice in choices:
        if not isinstance(choice, dict) or not choice.get("name"):
            return None, {"result": False, "code": "need_params", "params": [_public_param(item) for item in definitions]}
        by_name[choice["name"]] = choice
    params = []
    for definition in definitions:
        name = definition.get("name") or ""
        choice = by_name.get(name)
        if choice is None or type(choice.get("use_default")) is not bool:
            return None, {"result": False, "code": "need_params", "params": [_public_param(item) for item in definitions]}
        params.append(
            {
                "name": name,
                "value": "" if choice["use_default"] else str(choice.get("value") or ""),
                "is_modified": not choice["use_default"],
            }
        )
    return params, None


def _stamp_actor(execution, actor):
    execution.domain = actor["domain"]
    execution.updated_by_domain = actor["domain"]
    execution.trigger_source = TriggerSource.API
    execution.executor_user = actor["user"][:128]
    execution.created_by = actor["user"][:32]
    execution.updated_by = actor["user"][:32]
    execution.save(
        update_fields=[
            "domain",
            "updated_by_domain",
            "trigger_source",
            "executor_user",
            "created_by",
            "updated_by",
            "updated_at",
        ]
    )


def _created(execution):
    return {"result": True, "data": {"task_id": execution.id}}


def list_scripts(actor, body):
    name = str(body.get("name") or "").strip()
    try:
        page = int(body.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    if page < 1:
        page = 1
    queryset = _script_queryset(actor["team"])
    if name:
        queryset = queryset.filter(name__icontains=name)
    total = queryset.count()
    rows = list(queryset.order_by("-updated_at", "-id")[(page - 1) * MAX_PAGE_SIZE : page * MAX_PAGE_SIZE])
    return {
        "result": True,
        "data": {
            "count": total,
            "items": [
                {
                    "id": row.id,
                    "name": row.name,
                    "script_type": row.script_type,
                    "timeout": row.timeout,
                    "params": [_public_param(item) for item in ParamCrypto.mask_encrypted_defaults(list(row.params or [])) if isinstance(item, dict)],
                }
                for row in rows
            ],
        },
    }


def list_playbook_scripts(actor, body):
    name = str(body.get("name") or "").strip()
    path = str(body.get("path") or "").replace("\\", "/").strip().lstrip("/")[:256]
    try:
        page = int(body.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    if page < 1:
        page = 1
    queryset = _playbook_queryset(actor["team"])
    if name:
        queryset = queryset.filter(name__icontains=name)
    matched = []
    for playbook in queryset.order_by("-updated_at", "-id"):
        paths = _script_paths(playbook.file_list)
        if path:
            paths = [item for item in paths if path in item]
        if path and not paths:
            continue
        params = []
        for item in playbook.params or []:
            public = _playbook_public_param(item)
            if public is not None:
                params.append(public)
        matched.append(
            {
                "id": playbook.id,
                "name": playbook.name,
                "version": playbook.version,
                "paths": paths,
                "params": params,
            }
        )
    start = (page - 1) * MAX_PAGE_SIZE
    return {
        "result": True,
        "data": {
            "count": len(matched),
            "items": matched[start : start + MAX_PAGE_SIZE],
        },
    }


def describe_script(actor, body):
    script_id = _positive_ids([body.get("script_id")])
    if not script_id:
        return {"result": False, "message": "脚本不存在或不属于当前组织"}
    script = _script_queryset(actor["team"]).filter(id=script_id[0]).first()
    if script is None:
        return {"result": False, "message": "脚本不存在或不属于当前组织"}
    masked = ParamCrypto.mask_encrypted_defaults(list(script.params or []))
    return {
        "result": True,
        "data": {
            "id": script.id,
            "name": script.name,
            "script_type": script.script_type,
            "timeout": script.timeout,
            "params": [_public_param(item) for item in masked if isinstance(item, dict)],
        },
    }


def search_targets(actor, body):
    keyword = str(body.get("keyword") or "").strip()
    if not keyword:
        return {"result": False, "code": "need_keyword", "message": "需要目标名称或 IP"}
    hits = _manual_hits(actor["team"], keyword) + _search_nodes(actor, keyword)
    hits = hits[:SEARCH_LIMIT]
    return {
        "result": True,
        "data": {
            "count": len(hits),
            "hits": hits,
            "ask_source": len(hits) == 0,
        },
    }


def list_targets(actor, body):
    source = body.get("source")
    cursor = str(body.get("cursor") or "").strip()
    if source == "manual":
        result = query_target_list_v2({"page_size": MAX_PAGE_SIZE, "cursor": cursor or None}, {actor["team"]})
        if not result.get("result"):
            return result
        items = [
            {
                "source": "manual",
                "id": str(item["target_id"]),
                "name": item["name"],
                "ip": item["ip"],
                "os": item.get("os_type") or "",
            }
            for item in result["data"]["items"]
        ]
        return {
            "result": True,
            "data": {"items": items, "next_cursor": result["data"]["next_cursor"], "has_more": result["data"]["has_more"]},
        }
    if source == "node_mgmt":
        return {"result": True, "data": _list_nodes(actor, cursor)}
    return {"result": False, "code": "need_source", "message": "先选择作业管理目标或节点管理目标"}


def _os_mismatch_message(script_type, target_list):
    expected = SCRIPT_OS.get(script_type)
    if not expected:
        return None
    rejected = []
    for item in target_list:
        actual = str(item.get("os") or "").strip().lower()
        if actual == expected:
            continue
        name = item.get("name") or item.get("ip") or ""
        if actual in OS_LABEL:
            rejected.append(f"{name} 是 {OS_LABEL[actual]}，只能执行 {OS_SCRIPT_TYPES[actual]}")
        else:
            rejected.append(f"{name} 的操作系统未知")
    if not rejected:
        return None
    return f"脚本类型 {script_type} 只能在 {OS_LABEL[expected]} 上执行，" f"该系统可执行 {OS_SCRIPT_TYPES[expected]}。不匹配：{'；'.join(rejected)}。没有提交作业。"


def execute_script(actor, body):
    source = body.get("target_source")
    target_list, error = _resolve_targets(actor, source, body.get("target_ids"))
    if error:
        return {"result": False, "message": error}
    confirmed = body.get("danger_confirmed") is True
    team = [actor["team"]]
    mode = body.get("mode")
    if mode == "library":
        script_id = _positive_ids([body.get("script_id")])
        if not script_id:
            return {"result": False, "message": "脚本不存在或不属于当前组织"}
        try:
            script = ExecutionService.fetch_authorized_script(script_id[0], {actor["team"]})
        except ExecutionAuthorizationError:
            return {"result": False, "message": "脚本不存在或不属于当前组织"}
        mismatch = _os_mismatch_message(script.script_type, target_list)
        if mismatch:
            return {"result": False, "message": mismatch}
        gate = _danger_gate(DangerousChecker.check_command(script.content, team), confirmed)
        if gate:
            return gate
        params, param_error = _library_params(script, body.get("params"))
        if param_error:
            return param_error
        data = {
            "name": str(body.get("name") or script.name)[:256],
            "script_id": script.id,
            "target_source": source,
            "target_list": target_list,
            "params": params,
        }
        timeout_explicit = False
    elif mode == "custom":
        script_type = body.get("script_type")
        script_content = body.get("script_content")
        if script_type not in ALLOWED_SCRIPT_TYPES or not isinstance(script_content, str) or not script_content.strip():
            return {"result": False, "message": "自定义脚本只接受 shell、python、powershell、bat，并且要有正文"}
        mismatch = _os_mismatch_message(script_type, target_list)
        if mismatch:
            return {"result": False, "message": mismatch}
        gate = _danger_gate(DangerousChecker.check_command(script_content, team), confirmed)
        if gate:
            return gate
        try:
            timeout = int(body.get("timeout") or CUSTOM_TIMEOUT_SECONDS)
        except (TypeError, ValueError):
            timeout = CUSTOM_TIMEOUT_SECONDS
        if timeout <= 0:
            timeout = CUSTOM_TIMEOUT_SECONDS
        data = {
            "name": str(body.get("name") or "自定义脚本")[:256],
            "script_type": script_type,
            "script_content": script_content,
            "target_source": source,
            "target_list": target_list,
            "params": [],
            "timeout": timeout,
        }
        timeout_explicit = True
    else:
        return {"result": False, "message": "不支持的执行方式"}
    try:
        execution = ExecutionService.create_quick_execution(
            data=data,
            team=team,
            authorized_team_ids={actor["team"]},
            username=actor["user"][:32],
            timeout_explicit=timeout_explicit,
        )
    except ExecutionAuthorizationError as exc:
        return {"result": False, "message": exc.message}
    except serializers.ValidationError:
        return {"result": False, "message": "参数不符合脚本定义"}
    except ExecutionDispatchError:
        logger.warning("event=opspilot_job_dispatch_failed failed_stage=execute mode=%s", mode)
        return {"result": False, "code": "dispatch_failed", "message": "作业调度失败"}
    _stamp_actor(execution, actor)
    return _created(execution)


def _safe_filename(filename: str) -> str:
    return os.path.basename(str(filename or "").replace("\\", "/")).strip() or "file"


def _job_object_size(file_key: str):
    """确认对象已经在 NATS 对象存储里。失败时不返回正文。"""

    async def _info():
        service = JetStreamService()
        await service.connect()
        try:
            info = await service.object_store.get_info(file_key)
            return int(info.size or 0)
        finally:
            await service.close()

    try:
        return async_to_sync(_info)()
    except Exception as exc:
        logger.warning(
            "event=opspilot_job_file_stat_failed failed_stage=distribute error_type=%s",
            type(exc).__name__,
        )
        return None


def _register_uploaded_file(actor, filename: str, file_key: str) -> DistributionFile:
    if not is_job_file_key(file_key):
        raise ExecutionAuthorizationError("文件不在作业通道上")
    size = _job_object_size(file_key)
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ExecutionAuthorizationError("文件写入作业平台失败")
    if size > _max_upload_bytes():
        raise ExecutionAuthorizationError("文件超过作业平台上传上限")
    return DistributionFile.objects.create(
        original_name=_safe_filename(filename)[:255],
        file_key=file_key,
        expire_at=timezone.now() + timedelta(days=7),
        team=actor["team"],
    )


def _store_distribution_file(actor, filename: str, data: bytes) -> DistributionFile:
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise ExecutionAuthorizationError("文件内容为空")
    if len(data) > _max_upload_bytes():
        raise ExecutionAuthorizationError("文件超过作业平台上传上限")
    safe_name = _safe_filename(filename)
    ext = ""
    if "." in safe_name:
        ext = "." + safe_name.rsplit(".", 1)[-1]
    from nanoid import generate

    now = datetime.now()
    file_key = f"job-files/{now.year}/{now.month:02d}/{now.day:02d}/{generate(size=21)}{ext}"
    async_to_sync(upload_file_to_s3)(ContentFile(bytes(data), name=safe_name), file_key)
    return DistributionFile.objects.create(
        original_name=safe_name[:255],
        file_key=file_key,
        expire_at=timezone.now() + timedelta(days=7),
        team=actor["team"],
    )


def _distribution_entries(files):
    if not isinstance(files, list) or not files:
        return None
    entries = []
    for item in files:
        if isinstance(item, (tuple, list)) and len(item) == 2 and isinstance(item[1], (bytes, bytearray)):
            entries.append({"name": item[0], "data": bytes(item[1])})
            continue
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        if item.get("file_key"):
            entries.append({"name": name, "file_key": item.get("file_key")})
        elif "size" in item and "data" not in item:
            entries.append({"name": name, "size": item.get("size")})
        else:
            return None
    return entries


def distribute_files(actor, body, files):
    """确认分发后才登记作业平台文件。字节由调用方先写入 NATS 对象存储，消息里只带文件键。"""

    prepare = body.get("prepare") is True
    entries = _distribution_entries(files)
    if entries is None:
        return {"result": False, "code": "need_file", "message": "没有要分发的文件"}
    target_path = str(body.get("target_path") or "").strip()
    if not target_path:
        return {"result": False, "code": "need_path", "message": "还没有目标路径"}
    strategy = body.get("overwrite_strategy")
    if strategy not in {"overwrite", "skip"}:
        return {"result": False, "code": "need_overwrite", "message": "还没有覆盖策略"}
    target_list, error = _resolve_targets(actor, body.get("target_source"), body.get("target_ids"))
    if error:
        return {"result": False, "message": error}
    gate = _danger_gate(DangerousChecker.check_path(target_path, [actor["team"]]), body.get("danger_confirmed") is True)
    if gate:
        return gate
    if prepare:
        for entry in entries:
            size = entry.get("size")
            if type(size) is not int or size <= 0:
                return {"result": False, "code": "need_file", "message": "文件内容为空"}
            if size > _max_upload_bytes():
                return {"result": False, "message": "文件超过作业平台上传上限"}
            if not _safe_filename(entry.get("name")):
                return {"result": False, "code": "need_file", "message": "没有要分发的文件"}
        return {"result": True, "code": "ready"}
    stored = []
    try:
        for entry in entries:
            if entry.get("data") is not None:
                stored.append(_store_distribution_file(actor, entry["name"], entry["data"]))
            elif entry.get("file_key"):
                stored.append(_register_uploaded_file(actor, entry["name"], entry["file_key"]))
            else:
                return {"result": False, "code": "need_file", "message": "没有要分发的文件"}
        names = [item.original_name for item in stored]
        execution = ExecutionService.create_file_distribution(
            data={
                "name": str(body.get("name") or (names[0] if len(names) == 1 else names[0]))[:256],
                "file_ids": [item.id for item in stored],
                "target_source": body.get("target_source"),
                "target_list": target_list,
                "target_path": target_path,
                "overwrite_strategy": strategy,
                "timeout": CUSTOM_TIMEOUT_SECONDS,
            },
            team=[actor["team"]],
            authorized_team_ids={actor["team"]},
            username=actor["user"][:32],
        )
    except ExecutionAuthorizationError as exc:
        return {"result": False, "message": exc.message}
    except ExecutionDispatchError:
        logger.warning("event=opspilot_job_dispatch_failed failed_stage=distribute")
        return {"result": False, "code": "dispatch_failed", "message": "作业调度失败"}
    except Exception as exc:
        logger.warning(
            "event=opspilot_job_upload_failed failed_stage=distribute error_type=%s",
            type(exc).__name__,
        )
        return {"result": False, "message": "文件写入作业平台失败"}
    _stamp_actor(execution, actor)
    return _created(execution)


def query_execution(actor, body):
    task_id = _positive_ids([body.get("task_id")])
    if not task_id:
        return {"result": False, "message": "作业不存在或不属于当前组织"}
    execution = JobExecution.objects.filter(id=task_id[0]).first()
    if execution is None or not is_team_authorized(execution.team, {actor["team"]}):
        return {"result": False, "message": "作业不存在或不属于当前组织"}
    results = []
    for item in execution.execution_results or []:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "name": item.get("name") or "",
                "ip": item.get("ip") or "",
                "status": item.get("status") or "",
                "stdout": item.get("stdout") or "",
                "stderr": item.get("stderr") or "",
                "exit_code": item.get("exit_code"),
            }
        )
    return {
        "result": True,
        "data": {
            "task_id": execution.id,
            "status": execution.status,
            "terminal_source": execution.terminal_source or "",
            "job_type": execution.job_type,
            "success_count": execution.success_count,
            "failed_count": execution.failed_count,
            "results": results,
        },
    }


def run_opspilot_action(action, token, user_info, body=None):
    """签名通过后才执行。调用方传来的 team、user 会被丢掉。"""

    actor = _verified_actor(action, token, user_info)
    if actor is None:
        return _deny()
    payload = dict(body or {})
    payload.pop("team", None)
    payload.pop("user", None)
    payload.pop("user_info", None)
    payload.pop("executor", None)
    handlers = {
        ACTION_LIST_SCRIPTS: list_scripts,
        ACTION_LIST_PLAYBOOK_SCRIPTS: list_playbook_scripts,
        ACTION_DESCRIBE_SCRIPT: describe_script,
        ACTION_SEARCH_TARGETS: search_targets,
        ACTION_LIST_TARGETS: list_targets,
        ACTION_EXECUTE: execute_script,
        ACTION_QUERY: query_execution,
    }
    handler = handlers.get(action)
    if handler is None:
        return {"result": False, "message": "不支持的作业操作"}
    return handler(actor, payload)


def run_opspilot_distribute(token, user_info, body, files):
    actor = _verified_actor(ACTION_DISTRIBUTE, token, user_info)
    if actor is None:
        return _deny()
    payload = dict(body or {})
    payload.pop("team", None)
    payload.pop("user", None)
    payload.pop("user_info", None)
    return distribute_files(actor, payload, files)


# 终态常量供 OpsPilot 轮询使用，避免工具再依赖一组散落字符串。
TERMINAL_STATUSES = set(ExecutionStatus.TERMINAL_STATES)
