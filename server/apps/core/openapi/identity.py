"""双凭据认证：按凭据形态路由到平台现有认证机制。

契约（design.md 3.2）：
- 64 字符十六进制 → API 令牌，走 APISecretAuthBackend（含权限填充与版本围栏缓存）；
- 三段式 → JWT 登录态，走 system_mgmt.verify_token（含 jti 黑名单与 token 缓存）；
- 仅接受显式 Authorization: Bearer 头；
- 身份永远从凭据重新推导，不信任任何入站头（安全红线 2 纵深防御）；
- 两条路径各自复用现有缓存与 permission_version 围栏，本层不引入新缓存。

判别演进规则（冻结）：已注册前缀 > 形态；未来新增凭据类型必须携带前缀。
"""

import re
from dataclasses import dataclass, field

HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
JWT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")

CREDENTIAL_API_TOKEN = "api_token"
CREDENTIAL_JWT = "jwt"


class AuthenticationFailed(Exception):
    pass


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


def authenticate_request(request) -> CallerIdentity:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        raise AuthenticationFailed("missing bearer credential")
    token = header[len("Bearer "):].strip()
    if not token:
        raise AuthenticationFailed("missing bearer credential")

    if HEX64_RE.match(token):
        return _authenticate_api_token(token)
    if JWT_RE.match(token):
        return _authenticate_jwt(token)
    raise AuthenticationFailed("unrecognized credential form")


def _authenticate_api_token(token: str) -> CallerIdentity:
    from apps.core.backends import APISecretAuthBackend

    user = APISecretAuthBackend().authenticate(request=None, api_token=token)
    if user is None:
        raise AuthenticationFailed("invalid api token")

    permission = user.permission if isinstance(getattr(user, "permission", None), dict) else {}
    team = int(getattr(user, "_api_secret_team", 0))
    return CallerIdentity(
        user=user.username,
        domain=user.domain,
        credential_type=CREDENTIAL_API_TOKEN,
        team_ids=[team],
        is_superuser=bool(getattr(user, "is_superuser", False)),
        permission=permission,
        roles=list(getattr(user, "roles", []) or []),
        groups=None,
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
