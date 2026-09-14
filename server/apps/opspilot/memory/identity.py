"""记忆个人归属：对接系统管理用户 UUID（User.user_id）。

平台用户的记忆与会话不再以 username 作为稳定键，避免改名后读不到。
企微等外部渠道仍用 sender_id，不在系统用户表中则没有 UUID。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from apps.system_mgmt.models import User as SystemUser

_UUID_HEX_LEN = 36


def is_system_user_uuid(value: str | None) -> bool:
    text = (value or "").strip()
    if len(text) != _UUID_HEX_LEN:
        return False
    try:
        UUID(text)
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def split_external_user_id(external_user_id: str) -> tuple[str, str]:
    value = (external_user_id or "").strip()
    if "@" in value:
        username, domain = value.rsplit("@", 1)
        return username, domain
    return value, ""


def _ensure_user_id(user: SystemUser) -> str | None:
    current = (user.user_id or "").strip()
    if current:
        return current
    user.user_id = str(uuid4())
    user.save(update_fields=["user_id"])
    return user.user_id


def _system_user_by_uuid(user_id: str) -> SystemUser | None:
    return SystemUser.objects.filter(user_id=user_id).first()


def _system_user_by_username(username: str, domain: str) -> SystemUser | None:
    if not username:
        return None
    qs = SystemUser.objects.filter(username=username)
    if domain:
        return qs.filter(domain=domain).first()
    return qs.filter(domain="").first()


@dataclass(frozen=True)
class MemoryOwner:
    username: str
    domain: str
    user_id: str | None


def resolve_system_user_uuid(user, *, assign_if_missing: bool = False) -> str | None:
    """从 request.user / SimpleNamespace / UserAPISecret 解析系统用户 UUID。"""
    if user is None:
        return None
    raw = getattr(user, "user_id", None)
    if isinstance(raw, str) and is_system_user_uuid(raw):
        return raw
    username = getattr(user, "username", None) or ""
    domain = getattr(user, "domain", "") or ""
    if not username:
        return None
    sys_user = _system_user_by_username(username, domain)
    if sys_user is None:
        return None
    if assign_if_missing:
        return _ensure_user_id(sys_user)
    current = (sys_user.user_id or "").strip()
    return current or None


def resolve_owner_identity(
    *,
    user=None,
    external_user_id: str | None = None,
    username: str = "",
    domain: str = "",
    assign_if_missing: bool = False,
) -> MemoryOwner:
    """解析个人记忆主人：优先 UUID，其次 username+domain。"""
    if user is not None:
        owner_username = getattr(user, "username", "") or ""
        owner_domain = getattr(user, "domain", "") or ""
        user_id = resolve_system_user_uuid(user, assign_if_missing=assign_if_missing)
        if user_id:
            sys_user = _system_user_by_uuid(user_id)
            if sys_user is not None:
                return MemoryOwner(sys_user.username, sys_user.domain or "", user_id)
        return MemoryOwner(owner_username, owner_domain, user_id)

    token = (external_user_id or "").strip()
    if token:
        if is_system_user_uuid(token):
            sys_user = _system_user_by_uuid(token)
            if sys_user is not None:
                user_id = _ensure_user_id(sys_user) if assign_if_missing else (sys_user.user_id or "").strip() or None
                return MemoryOwner(sys_user.username, sys_user.domain or "", user_id)
            return MemoryOwner(token, "", None)
        owner_username, owner_domain = split_external_user_id(token)
        sys_user = _system_user_by_username(owner_username, owner_domain)
        if sys_user is not None:
            user_id = _ensure_user_id(sys_user) if assign_if_missing else (sys_user.user_id or "").strip() or None
            return MemoryOwner(sys_user.username, sys_user.domain or "", user_id)
        return MemoryOwner(owner_username, owner_domain, None)

    if username and is_system_user_uuid(username) and not domain:
        sys_user = _system_user_by_uuid(username)
        if sys_user is not None:
            user_id = _ensure_user_id(sys_user) if assign_if_missing else (sys_user.user_id or "").strip() or None
            return MemoryOwner(sys_user.username, sys_user.domain or "", user_id)
        return MemoryOwner(username, "", None)

    sys_user = _system_user_by_username(username, domain)
    if sys_user is not None:
        user_id = _ensure_user_id(sys_user) if assign_if_missing else (sys_user.user_id or "").strip() or None
        return MemoryOwner(sys_user.username, sys_user.domain or "", user_id)
    return MemoryOwner(username or "", domain or "", None)
