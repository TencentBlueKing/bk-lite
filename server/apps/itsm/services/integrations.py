"""集成只负责配置和编排，执行复用平台网关及隔离 Runner。"""

import ast
import json
import re
import time

from apps.core.openapi.dispatcher import dispatch
from apps.core.openapi.identity import CallerIdentity
from apps.core.openapi.registry import default_registry
from apps.core.utils.ssrf_validator import SSRFValidator
from apps.itsm.models.integration import Integration, IntegrationRun
from apps.operation_analysis.services.transform.errors import TransformError
from apps.operation_analysis.services.transform.executor import get_transform_executor

MAX_BYTES = 100000


def validate_config(kind, config):
    if not isinstance(config, dict):
        raise ValueError("配置必须为对象")
    if kind == "api":
        if config.get("transport") == "external":
            from apps.itsm.services.external_api import validate_external

            return validate_external(config)
        path = str(config.get("path") or "").strip("/")
        service, _, subpath = path.partition("/")
        method = str(config.get("method") or "GET").upper()
        if not default_registry.find(service, subpath, method):
            raise ValueError("请从平台 API 目录选择接口")
        return {"path": path, "method": method}
    if kind == "python":
        script = config.get("script")
        if not isinstance(script, str) or not script.strip() or len(script.encode("utf-8")) > MAX_BYTES:
            raise ValueError("脚本不能为空且不能超过 100KB")
        try:
            tree = ast.parse(script)
        except (SyntaxError, ValueError, RecursionError) as exc:
            raise ValueError("Python 语法错误") from exc
        if not any(isinstance(node, ast.FunctionDef) and node.name == "transform" for node in tree.body):
            raise ValueError("脚本须定义 transform(rows, params) 函数")
        return {"script": script, "filename": str(config.get("filename") or "transform.py")[:128]}
    if kind == "todo":
        url = str(config.get("url") or "")
        try:
            SSRFValidator.validate(url)
        except Exception as exc:
            raise ValueError("待办地址必须为允许访问的 HTTP(S) 地址") from exc
        token = str(config.get("token") or "")
        if len(token) > 4096:
            raise ValueError("认证令牌过长")
        return {"url": url, "token": token}
    raise ValueError("不支持的集成类型")


def request_identity(request):
    """已认证会话身份，不接受请求体中传入的用户/组织/权限。"""
    user = request.user
    groups = getattr(user, "group_list", []) or []
    token_id = getattr(user, "_api_secret_id", None)
    teams = [int(g["id"] if isinstance(g, dict) else g) for g in groups]
    if token_id is not None:
        teams = [int(user._api_secret_team)]
    return CallerIdentity(
        user=user.username,
        domain=user.domain,
        credential_type="api_token" if token_id is not None else "jwt",
        team_ids=teams,
        token_id=token_id,
        token_scope=getattr(user, "_api_secret_scope", None),
        is_superuser=bool(getattr(user, "is_superuser", False)),
        permission=getattr(user, "permission", {}) or {},
        roles=getattr(user, "roles", []) or [],
    )


def live_identity(item, actor=None, *, permission=None):
    """异步执行恢复操作者实时权限，不借用集成维护人的身份。"""
    from apps.base.models.user import User
    from apps.core.backends import APISecretAuthBackend, _normalize_group_ids
    from apps.system_mgmt.models import User as SystemUser
    from apps.system_mgmt.services.user_access import is_account_expired

    name = actor if actor is not None else item.updated_by or item.created_by
    account = SystemUser.objects.filter(username=name, domain=item.domain, disabled=False).first()
    if account is None or is_account_expired(account):
        raise PermissionError("集成维护人已停用")
    user = User.objects.filter(username=name, domain=item.domain, is_active=True).first()
    if user is None:
        raise PermissionError("集成维护人不存在")
    teams = sorted(_normalize_group_ids(account.group_list))
    APISecretAuthBackend()._populate_user_permissions(user, teams[0] if teams else 0)
    permission = permission or ("workflow-Edit" if actor is not None else "data-Edit")
    if not user.is_superuser and permission not in (user.permission or {}).get("itsm", []):
        raise PermissionError("集成维护人权限已收回")
    return CallerIdentity(
        user=name,
        domain=item.domain,
        credential_type="jwt",
        team_ids=teams,
        is_superuser=user.is_superuser,
        permission=user.permission,
        roles=user.roles,
    )


def resolve_inputs(value, ticket):
    if isinstance(value, dict):
        return {key: resolve_inputs(item, ticket) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_inputs(item, ticket) for item in value]
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r"\$\{(form|ticket)\.([\w]+)\}", value)
    if not match:
        return value
    source = ticket.form_data if match[1] == "form" else {"id": ticket.id, "sn": ticket.sn, "title": ticket.title, "creator": ticket.creator}
    if match[2] not in source:
        raise ValueError(f"未找到变量 {value}")
    return source[match[2]]


def execute(item, inputs, identity):
    if item.domain != identity.domain:
        raise PermissionError()
    if not item.is_enabled:
        raise ValueError("集成已停用")
    if not isinstance(inputs, dict) or len(json.dumps(inputs, ensure_ascii=False).encode()) > 1024 * 1024:
        raise ValueError("输入必须是对象且不能超过 1MB")
    run = IntegrationRun.objects.create(integration=item, domain=item.domain, created_by=identity.user, updated_by=identity.user)
    started = time.monotonic()
    status, code, output = "failed", "", None
    try:
        if item.kind == "api" and item.config.get("transport") == "external":
            from apps.itsm.services.external_api import execute_external

            output = execute_external(item.config, inputs)
            status = "done"
        elif item.kind == "api":
            service, _, subpath = item.config["path"].partition("/")
            endpoint = default_registry.find(service, subpath, item.config["method"])
            if endpoint is None:
                raise ValueError("平台接口已移除")
            response = dispatch(identity, endpoint, inputs)
            result = json.loads(response.content)
            status = "done" if result.get("result") else "failed"
            code = result.get("code", "")
            output = result.get("data") if status == "done" else result.get("message")
        elif item.kind == "python":
            rows = inputs.get("rows", [])
            params = inputs.get("params", {})
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows) or not isinstance(params, dict):
                raise ValueError("rows 须为对象数组，params 须为对象")
            output = get_transform_executor().execute(rows, params, item.config["script"], org_id=item.domain, request_id=f"itsm-{run.id}")
            status = "done"
        elif item.kind == "todo":
            from apps.itsm.services.todo_sync import send_payload

            output = send_payload(item, inputs)
            status = "done"
        else:
            raise ValueError("未知集成类型")
    except TransformError as exc:
        code, output = exc.code, exc.message
    except Exception as exc:
        code = type(exc).__name__
        output = str(exc) if isinstance(exc, ValueError) else "执行失败，请检查配置与执行服务"
    run.status, run.code = status, code[:80]
    run.duration_ms = max(0, int((time.monotonic() - started) * 1000))
    run.save(update_fields=["status", "code", "duration_ms", "updated_at"])
    return {"run_id": run.id, "status": status, "code": code, "output": output, "duration_ms": run.duration_ms}


def run_for_ticket(ticket, config, operator="system"):
    item = Integration.objects.get(id=config.get("integration_id"), domain=ticket.domain, kind__in=["api", "python"])
    actor = operator if operator != "system" else ticket.workflow_version.updated_by or ticket.workflow_version.created_by
    identity = live_identity(item, actor=actor)
    field = str(config.get("result_field") or "")
    if field and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", field):
        raise ValueError("结果字段须为字母开头的字段标识")
    result = execute(item, resolve_inputs(config.get("inputs") or {}, ticket), identity)
    if result["status"] == "done" and field:
        ticket.form_data = {**ticket.form_data, field: result["output"]}
        ticket.save(update_fields=["form_data", "updated_at"])
    return result["status"], {key: result[key] for key in ["run_id", "status", "code", "duration_ms"]}
