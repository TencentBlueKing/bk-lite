"""OpenAPI 网关视图：统一 invoke 端点与 /openapi/v1/_me 内省端点。

@api_exempt 在此仅豁免平台登录态中间件保护——本模块每个视图第一步都执行
自带的双凭据强制认证（fail-closed），不是公开裸端点；身份永远从凭据推导，
不信任任何入站头，也不假设流量必经 Traefik（安全红线 2 纵深防御）。
"""

import hmac
import json
import os
import re
import time

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.core.logger import openapi_logger as logger
from apps.core.openapi.dispatcher import dispatch
from apps.core.openapi.envelope import ErrorCode, fail, ok
from apps.core.openapi.identity import (
    CREDENTIAL_JWT,
    AuthenticationFailed,
    authenticate_request,
)
from apps.core.openapi.registry import default_registry
from apps.core.utils.exempt import api_exempt


def _extract_payload(request):
    if request.method == "GET":
        return {key: request.GET.get(key) for key in request.GET.keys()}, None
    body = request.body or b""
    if not body:
        return {}, None
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None, fail(ErrorCode.SCHEMA_INVALID, "request body must be JSON")
    if not isinstance(payload, dict):
        return None, fail(ErrorCode.SCHEMA_INVALID, "request body must be a JSON object")
    return payload, None


def _audit(request, identity, response, started_at):
    try:
        logger.info(
            "openapi_access user=%s domain=%s credential=%s method=%s path=%s "
            "status=%s duration_ms=%d size=%d",
            getattr(identity, "user", "-"),
            getattr(identity, "domain", "-"),
            getattr(identity, "credential_type", "-"),
            request.method,
            request.path,
            getattr(response, "status_code", "-"),
            int((time.monotonic() - started_at) * 1000),
            len(getattr(response, "content", b"") or b""),
        )
    except Exception:  # 审计日志绝不影响主流程
        logger.exception("openapi audit logging failed")


def _invoke(request, service, sub_path, identity):
    endpoint = default_registry.find(service, sub_path.strip("/"), request.method)
    if endpoint is None:
        # 对不存在的 path 与无权知晓的 path 返回一致，不泄漏资源存在性
        return fail(ErrorCode.NOT_FOUND, "no such endpoint")

    payload, error = _extract_payload(request)
    if error is not None:
        return error
    return dispatch(identity, endpoint, payload)


@api_exempt
def invoke_view(request, service, sub_path):
    started_at = time.monotonic()
    identity = None
    response = None
    try:
        try:
            identity = authenticate_request(request)
        except AuthenticationFailed as exc:
            response = fail(ErrorCode.AUTH_INVALID, str(exc) or "authentication failed")
        else:
            response = _invoke(request, service, sub_path, identity)
        return response
    finally:
        _audit(request, identity, response, started_at)


@api_exempt
@require_http_methods(["GET"])
def me_view(request):
    started_at = time.monotonic()
    identity = None
    response = None
    try:
        try:
            identity = authenticate_request(request)
        except AuthenticationFailed as exc:
            response = fail(ErrorCode.AUTH_INVALID, str(exc) or "authentication failed")
        else:
            response = ok(_build_me_payload(identity))
        return response
    finally:
        _audit(request, identity, response, started_at)


_FORWARDED_URI_RE = re.compile(r"^/openapi/(?P<version>[a-z0-9]+)/(?P<service>[a-z][a-z0-9-]*)(?:/|$)")


@api_exempt
@require_http_methods(["GET"])
def provider_view(request):
    """Traefik providers.http 拉取端点，返回原生动态配置（非 envelope）。

    渲染结果内含解引用后的密钥值，必须以共享令牌保护；
    OPENAPI_PROVIDER_TOKEN 未配置时拒绝服务（fail-closed）。
    """
    expected = os.getenv("OPENAPI_PROVIDER_TOKEN", "")
    if not expected:
        logger.warning("OPENAPI_PROVIDER_TOKEN 未配置，provider 端点拒绝服务")
        return JsonResponse({"detail": "provider token unconfigured"}, status=503)
    presented = request.META.get("HTTP_X_PROVIDER_TOKEN", "")
    if not hmac.compare_digest(presented, expected):
        return fail(ErrorCode.AUTH_INVALID, "invalid provider token")

    from apps.core.openapi.renderer import refresh_snapshot

    config = refresh_snapshot(internal_services=default_registry.services())
    return JsonResponse(config)


@api_exempt
def forward_auth_view(request):
    """Traefik ForwardAuth 回调：认证 + 外部服务级授权（required_roles）。

    与 invoke 路径复用同一认证函数与错误序列化器（错误体逐字段同构）。
    """
    started_at = time.monotonic()
    identity = None
    response = None
    try:
        try:
            identity = authenticate_request(request)
        except AuthenticationFailed as exc:
            response = fail(ErrorCode.AUTH_INVALID, str(exc) or "authentication failed")
            return response

        forwarded_uri = request.META.get("HTTP_X_FORWARDED_URI", "")
        matched = _FORWARDED_URI_RE.match(forwarded_uri)
        from apps.core.openapi.renderer import get_external_entry

        entry = get_external_entry(matched.group("service")) if matched else None
        if entry is None:
            # 快照中查无该外部服务：fail-closed，且与 invoke 的 404 语义一致
            response = fail(ErrorCode.NOT_FOUND, "no such endpoint")
            return response

        required = set(entry["required_roles"])
        # 空列表语义（冻结）：放行任意已认证身份
        if required and not identity.is_superuser and not (required & set(identity.roles)):
            response = fail(ErrorCode.ROLE_REQUIRED, "service role required")
            return response

        response = JsonResponse({"result": True})
        response["X-BK-User"] = f"{identity.user}@{identity.domain}"
        response["X-BK-Team"] = ",".join(str(t) for t in identity.team_ids)
        # X-On-Behalf-Of：仅服务账号（API 令牌）场景回显原值，其余场景覆盖清除
        if identity.credential_type == "api_token":
            response["X-On-Behalf-Of"] = request.META.get("HTTP_X_ON_BEHALF_OF", "")
        else:
            response["X-On-Behalf-Of"] = ""
        return response
    finally:
        _audit(request, identity, response, started_at)


def _build_me_payload(identity):
    from apps.system_mgmt.models import Group
    from apps.system_mgmt.utils.group_utils import GroupUtils

    if identity.groups is not None:
        groups = identity.groups
    else:
        name_map = dict(
            Group.objects.filter(id__in=identity.team_ids).values_list("id", "name")
        )
        groups = [
            {"id": team_id, "name": name_map.get(team_id, "")}
            for team_id in identity.team_ids
        ]

    anchor_scopes = []
    for team_id in identity.team_ids:
        try:
            cascaded = sorted(GroupUtils.get_group_with_descendants([team_id]))
        except Exception:
            logger.exception("anchor scope resolution failed for group %s", team_id)
            cascaded = [team_id]
        anchor_scopes.append({"anchor": team_id, "cascaded_group_ids": cascaded})

    from apps.core.openapi.renderer import get_external_services

    services = [
        {"name": name, "kind": "internal"} for name in default_registry.services()
    ] + [
        {"name": name, "kind": "external"} for name in get_external_services()
    ]

    return {
        "user": identity.user,
        "domain": identity.domain,
        "credential_type": identity.credential_type,
        "groups": groups,
        "anchor_scopes": anchor_scopes,
        "roles": identity.roles,
        "services": services,
    }
