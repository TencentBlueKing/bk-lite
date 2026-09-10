# flake8: noqa
"""NATS handlers for the system-management credential vault."""

from apps.system_mgmt.models import Menu, Role
from apps.system_mgmt.services.credential_service import (
    CredentialServiceError,
    create_credential as create_credential_record,
    get_credential,
    page_credentials,
    resolve_credential as resolve_credential_record,
)

import nats_client

from .common import get_user_all_roles
from .users import _actor_scope_response, _is_persisted_superuser

_CREDENTIAL_APP = "system-manager"
_CREDENTIAL_ADD = "credential-Add"
_CREDENTIAL_VIEW = "credential-View"


def _actor_from_user(user_obj, actor_context):
    return {
        "username": user_obj.username,
        "domain": user_obj.domain,
        "current_team": (actor_context or {}).get("current_team"),
        "group_list": user_obj.group_list or (),
        "is_superuser": _is_persisted_superuser(user_obj),
    }


def _user_has_menu_permission(user_obj, permission_name):
    if _is_persisted_superuser(user_obj):
        return True
    role_ids = get_user_all_roles(user_obj)
    menu_ids = []
    for menu_list in Role.objects.filter(id__in=role_ids).values_list("menu_list", flat=True):
        if menu_list:
            menu_ids.extend(menu_list)
    return Menu.objects.filter(id__in=menu_ids, app=_CREDENTIAL_APP, name=permission_name).exists()


def _error_payload(exc):
    return {"result": False, "message": getattr(exc, "code", "invalid")}


def _paginate(page, page_size):
    try:
        page_number = int(page or 1)
        size = int(page_size or 20)
    except (TypeError, ValueError):
        page_number, size = 1, 20
    page_number = max(page_number, 1)
    size = min(max(size, 1), 100)
    return page_number, size


@nats_client.register
def list_credentials(actor_context, category=None, type=None, search="", page=1, page_size=20):
    """无密文。当前组织能选到：归属=当前或当前的活动祖先。默认仅 disabled=False。"""
    user_obj, _authorized_groups, error_response = _actor_scope_response(actor_context)
    if error_response is not None:
        return error_response
    if not user_obj:
        return {"result": True, "data": [], "count": 0}
    if not _user_has_menu_permission(user_obj, _CREDENTIAL_VIEW):
        return {"result": False, "message": "forbidden"}
    if type and not category:
        return {"result": False, "message": "invalid"}

    actor = _actor_from_user(user_obj, actor_context)
    page_number, size = _paginate(page, page_size)
    try:
        items, count = page_credentials(
            {
                "current_team": actor["current_team"],
                "category": category,
                "type": type,
                "search": search or "",
                "disabled": False,
            },
            actor=actor,
            page=page_number,
            page_size=size,
        )
    except CredentialServiceError as exc:
        return _error_payload(exc)

    return {"result": True, "data": items, "count": count}


@nats_client.register
def create_credential(actor_context, name, type, group_id, fields):
    """无 Add 权限则 result=False 等价 403。返回 credential_id 与非密字段。"""
    user_obj, _authorized_groups, error_response = _actor_scope_response(actor_context)
    if error_response is not None:
        return error_response
    if not user_obj:
        return {"result": False, "message": "forbidden"}
    if not _user_has_menu_permission(user_obj, _CREDENTIAL_ADD):
        return {"result": False, "message": "forbidden"}

    actor = _actor_from_user(user_obj, actor_context)
    try:
        created = create_credential_record(
            {
                "name": name,
                "type": type,
                "group_id": group_id,
                "fields": fields or {},
                "current_team": actor["current_team"],
                "owner_mode": "current",
            },
            actor=actor,
        )
        payload = get_credential(created.credential_id, actor["current_team"], actor=actor)
    except CredentialServiceError as exc:
        return _error_payload(exc)
    return {"result": True, "data": payload}


@nats_client.register
def resolve_credential(actor_context, credential_id):
    """返回 {credential_id, type, name, group_id, fields: 明文}。停用/越权失败。"""
    user_obj, _authorized_groups, error_response = _actor_scope_response(actor_context)
    if error_response is not None:
        return error_response
    if not user_obj:
        return {"result": False, "message": "forbidden"}
    if not _user_has_menu_permission(user_obj, _CREDENTIAL_VIEW):
        return {"result": False, "message": "forbidden"}

    actor = _actor_from_user(user_obj, actor_context)
    try:
        payload = resolve_credential_record(credential_id, actor["current_team"], actor=actor)
    except CredentialServiceError as exc:
        return _error_payload(exc)
    return {"result": True, "data": payload}
