"""凭据认证：已注册前缀优先于形态，再路由到平台现有认证机制。

契约（design.md 3.2）：
- 已注册前缀 `bksys_` → 系统 Token（先于形态匹配，避免落入 JWT）；
- 64 字符十六进制 → API 令牌，走 APISecretAuthBackend；
- 三段式 → JWT 登录态，走 system_mgmt.verify_token；
- 仅接受显式 Authorization: Bearer 头；
- 身份永远从凭据重新推导，不信任任何入站头（安全红线 2 纵深防御）。

判别演进规则（冻结）：已注册前缀 > 形态。
"""

import re
from dataclasses import dataclass, field

from django.core.exceptions import ObjectDoesNotExist

from apps.core.openapi.envelope import ErrorCode

HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
JWT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
SYSTEM_TOKEN_RE = re.compile(r"^bksys_[0-9a-fA-F]{64}$")
SYSTEM_TOKEN_PREFIX = "bksys_"
ACTING_TEAM_RE = re.compile(r"^[1-9][0-9]*$")

CREDENTIAL_API_TOKEN = "api_token"
CREDENTIAL_JWT = "jwt"
CREDENTIAL_SYSTEM_TOKEN = "system_token"


class AuthenticationFailed(Exception):
    def __init__(self, message="", code=None, identity=None):
        super().__init__(message)
        self.code = code
        self.identity = identity


@dataclass
class CallerIdentity:
    user: str
    domain: str
    credential_type: str
    team_ids: list = field(default_factory=list)
    is_superuser: bool = False
    permission: dict = field(default_factory=dict)
    roles: list = field(default_factory=list)
    # JWT 路径带完整组织对象（[{id, name}]）；API 令牌路径为 None，_me 按需补齐名称
    groups: list = None
    caller_system: str = None
    token_scope: dict = None
    token_id: int = None
    token_name: str = None


def _audit_identity(
    *,
    credential_type,
    token_id=None,
    token_name=None,
    caller_system=None,
    user="",
    domain="",
    team_ids=None,
):
    return CallerIdentity(
        user=user or "",
        domain=domain or "",
        credential_type=credential_type,
        team_ids=list(team_ids or []),
        token_id=token_id,
        token_name=token_name or None,
        caller_system=caller_system,
    )


def authenticate_request(request) -> CallerIdentity:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        raise AuthenticationFailed("missing bearer credential")
    token = header[len("Bearer "):].strip()
    if not token:
        raise AuthenticationFailed("missing bearer credential")

    if token.startswith(SYSTEM_TOKEN_PREFIX):
        return _authenticate_system_token(request, token)
    if HEX64_RE.match(token):
        return _authenticate_api_token(token)
    if JWT_RE.match(token):
        return _authenticate_jwt(token)
    raise AuthenticationFailed("unrecognized credential form")


def _authenticate_api_token(token: str) -> CallerIdentity:
    from apps.base.models.user import UserAPISecret
    from apps.core.backends import APISecretAuthBackend

    user = APISecretAuthBackend().authenticate(request=None, api_token=token)
    if user is None:
        row = UserAPISecret.find_by_api_secret_including_expired(token)
        raise AuthenticationFailed(
            "invalid api token",
            identity=_audit_identity(
                credential_type=CREDENTIAL_API_TOKEN,
                token_id=row.pk,
                token_name=row.name,
                user=row.username,
                domain=row.domain,
                team_ids=[row.team],
            )
            if row is not None
            else None,
        )

    raw_permission = user.permission if isinstance(getattr(user, "permission", None), dict) else {}
    team = int(getattr(user, "_api_secret_team", 0))
    return CallerIdentity(
        user=user.username,
        domain=user.domain,
        credential_type=CREDENTIAL_API_TOKEN,
        team_ids=[team],
        is_superuser=bool(getattr(user, "is_superuser", False)),
        permission=raw_permission,
        roles=list(getattr(user, "roles", []) or []),
        groups=None,
        token_scope=getattr(user, "_api_secret_scope", None),
        token_id=getattr(user, "_api_secret_id", None),
        token_name=getattr(user, "_api_secret_name", None) or None,
    )


def _authenticate_jwt(token: str) -> CallerIdentity:
    from apps.system_mgmt.nats.auth import verify_token

    result = verify_token(token)
    if not isinstance(result, dict) or not result.get("result"):
        message = (result or {}).get("message") if isinstance(result, dict) else None
        raise AuthenticationFailed(message or "invalid token")

    ctx = result.get("data") or {}
    permission = {
        app: set(items or [])
        for app, items in (ctx.get("permission") or {}).items()
    }
    raw_groups = [g for g in (ctx.get("group_list") or []) if isinstance(g, dict)]
    return CallerIdentity(
        user=ctx.get("username", ""),
        domain=ctx.get("domain", ""),
        credential_type=CREDENTIAL_JWT,
        team_ids=[int(g["id"]) for g in raw_groups if "id" in g],
        is_superuser=bool(ctx.get("is_superuser")),
        permission=permission,
        roles=list(ctx.get("roles") or []),
        groups=[{"id": g.get("id"), "name": g.get("name")} for g in raw_groups],
    )


def _parse_acting_headers(request):
    user_header = (request.META.get("HTTP_X_BKLITE_ACTING_USER") or "").strip()
    team_header = (request.META.get("HTTP_X_BKLITE_ACTING_TEAM") or "").strip()
    if not user_header or not team_header:
        raise AuthenticationFailed("acting headers required")
    if "@" in user_header:
        username, domain = user_header.rsplit("@", 1)
    else:
        username, domain = user_header, "domain.com"
    if not username or not domain or not ACTING_TEAM_RE.fullmatch(team_header):
        raise AuthenticationFailed("acting headers required")
    return username, domain, int(team_header)


def _authenticate_system_token(request, token: str) -> CallerIdentity:
    from apps.base.models.user import User as BaseUser
    from apps.core.backends import APISecretAuthBackend, _normalize_group_ids
    from apps.system_mgmt.models import SystemAPIToken
    from apps.system_mgmt.models import User as SystemUser

    if not SYSTEM_TOKEN_RE.fullmatch(token):
        raise AuthenticationFailed("invalid system token")

    token_row = SystemAPIToken.find_by_secret_including_disabled(token)
    if token_row is None:
        raise AuthenticationFailed("invalid system token")

    live = token_row.is_live()
    audit = _audit_identity(
        credential_type=CREDENTIAL_SYSTEM_TOKEN,
        token_id=token_row.pk,
        token_name=token_row.name,
        caller_system=token_row.system_id,
    )
    try:
        username, domain, team_id = _parse_acting_headers(request)
    except AuthenticationFailed as exc:
        raise AuthenticationFailed(str(exc), code=exc.code, identity=audit)

    try:
        user = BaseUser._default_manager.get(username=username, domain=domain)
    except ObjectDoesNotExist:
        raise AuthenticationFailed("acting user not found or disabled", identity=audit)
    if not user.is_active:
        raise AuthenticationFailed("acting user not found or disabled", identity=audit)

    sys_user = SystemUser.objects.filter(username=username, domain=domain, disabled=False).first()
    if sys_user is None:
        raise AuthenticationFailed("acting user not found or disabled", identity=audit)

    audit.user = user.username
    audit.domain = user.domain
    audit.team_ids = [team_id]

    if not live:
        raise AuthenticationFailed("invalid system token", identity=audit)

    if team_id not in _normalize_group_ids(sys_user.group_list):
        raise AuthenticationFailed("team out of scope", code=ErrorCode.TEAM_OUT_OF_SCOPE, identity=audit)

    user._api_secret_team_scope = True
    user._api_secret_team = team_id
    APISecretAuthBackend()._populate_user_permissions(user, team_id)
    raw_permission = user.permission if isinstance(getattr(user, "permission", None), dict) else {}
    return CallerIdentity(
        user=user.username,
        domain=user.domain,
        credential_type=CREDENTIAL_SYSTEM_TOKEN,
        team_ids=[team_id],
        is_superuser=bool(getattr(user, "is_superuser", False)),
        permission=raw_permission,
        roles=list(getattr(user, "roles", []) or []),
        groups=None,
        caller_system=token_row.system_id,
        token_scope=token_row.scope,
        token_id=token_row.pk,
        token_name=token_row.name or None,
    )
