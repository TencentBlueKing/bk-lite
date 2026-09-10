"""Transactional domain operations for credential types and instances."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from uuid import uuid4

from django.db import transaction
from django.db.models import Count, Q

from apps.core.models.maintainer_info import maintainer_kwargs
from apps.system_mgmt.models.credential import Credential, CredentialType
from apps.system_mgmt.models.user import Group
from apps.system_mgmt.services.credential_builtin import builtin_type_payloads
from apps.system_mgmt.services.credential_crypto import decrypt_instance_fields, encrypt_instance_fields, public_instance_fields
from apps.system_mgmt.services.credential_schema import SchemaError, secret_field_ids, validate_instance_fields, validate_type_fields
from apps.system_mgmt.services.credential_scope import is_current_team_authorized, manageable_owner_group_ids, usable_owner_group_ids


class CredentialServiceError(ValueError):
    """A stable, non-secret error returned by the credential domain service."""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or code)


def build_credential_id(type_key: str) -> str:
    return f"crd-{type_key}-{uuid4().hex}"


def _value(actor, key, default=None):
    if actor is None:
        return default
    if isinstance(actor, Mapping):
        return actor.get(key, default)
    return getattr(actor, key, default)


def _actor_scope(actor, *, current_team=None, group_list=None, is_superuser=None):
    if current_team is None:
        current_team = _value(actor, "current_team")
    if group_list is None:
        group_list = _value(actor, "group_list", ())
    if is_superuser is None:
        is_superuser = bool(_value(actor, "is_superuser", False))
    return current_team, group_list, is_superuser


def _maintainer(actor, *, include_created=True):
    if actor is None or isinstance(actor, Mapping):
        context = actor
    else:
        context = {
            "username": _value(actor, "username"),
            "domain": _value(actor, "domain"),
        }
    return maintainer_kwargs(actor_context=context, include_created=include_created)


def _payload(payload, values):
    data = dict(payload or {}) if isinstance(payload, Mapping) else {}
    data.update(values)
    return data


def _type_key(value):
    if isinstance(value, CredentialType):
        return value.key
    if isinstance(value, Mapping):
        return value.get("key") or value.get("type") or value.get("type_key")
    return value


def _load_type(type_ref, *, lock=False):
    key = _type_key(type_ref)
    queryset = CredentialType.objects
    if lock:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(key=key)
    except CredentialType.DoesNotExist as exc:
        raise CredentialServiceError("not_found") from exc


def _public_type(credential_type):
    return {
        "key": credential_type.key,
        "name": credential_type.name,
        "is_builtin": credential_type.is_builtin,
        "categories": deepcopy(credential_type.categories or []),
        "fields": deepcopy(credential_type.fields or []),
        "credential_count": int(getattr(credential_type, "credential_count", 0) or 0),
    }


def _public_credential(credential):
    return {
        "credential_id": credential.credential_id,
        "type": credential.type_id,
        "name": credential.name,
        "group_id": credential.group_id,
        "disabled": credential.disabled,
        "fields": public_instance_fields(credential.type.fields, credential.fields),
    }


public_credential = _public_credential


def _require_current_team(actor, *, current_team=None, group_list=None, is_superuser=None):
    current_team, group_list, is_superuser = _actor_scope(actor, current_team=current_team, group_list=group_list, is_superuser=is_superuser)
    if not is_current_team_authorized(current_team, group_list, is_superuser):
        raise CredentialServiceError("forbidden")
    return current_team, group_list, is_superuser


def _require_manageable(owner_id, actor, *, current_team=None, group_list=None, is_superuser=None):
    current_team, group_list, is_superuser = _actor_scope(actor, current_team=current_team, group_list=group_list, is_superuser=is_superuser)
    if owner_id not in manageable_owner_group_ids(current_team, group_list, is_superuser):
        raise CredentialServiceError("forbidden")
    return current_team, group_list, is_superuser


def _require_current_owner(owner_id, actor, *, current_team=None, group_list=None, is_superuser=None):
    current_team, group_list, is_superuser = _require_current_team(actor, current_team=current_team, group_list=group_list, is_superuser=is_superuser)
    if _coerce_owner_id(owner_id) != _coerce_owner_id(current_team):
        raise CredentialServiceError("forbidden")
    return current_team, group_list, is_superuser


def _coerce_owner_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _owner_ids_for_scope(owner_scope, current_team, group_list, is_superuser):
    if owner_scope == "manage":
        return manageable_owner_group_ids(current_team, group_list, is_superuser)
    if owner_scope in (None, "", "consume"):
        return usable_owner_group_ids(current_team)
    raise CredentialServiceError("invalid")


def seed_builtin_types():
    """Insert or refresh exactly the code-owned built-in types."""
    seeded = []
    with transaction.atomic():
        for key, definition in builtin_type_payloads().items():
            validate_type_fields(definition["fields"])
            credential_type, _ = CredentialType.objects.select_for_update().get_or_create(
                key=key,
                defaults={
                    "name": definition["name"],
                    "is_builtin": True,
                    "categories": definition["categories"],
                    "fields": definition["fields"],
                    **maintainer_kwargs(),
                },
            )
            update_fields = []
            if credential_type.name != definition["name"]:
                credential_type.name = definition["name"]
                update_fields.append("name")
            if not credential_type.is_builtin:
                credential_type.is_builtin = True
                update_fields.append("is_builtin")
            if credential_type.categories != definition["categories"]:
                credential_type.categories = definition["categories"]
                update_fields.append("categories")
            if credential_type.fields != definition["fields"]:
                credential_type.fields = definition["fields"]
                update_fields.append("fields")
            if update_fields:
                credential_type.save(update_fields=update_fields + ["updated_at"])
            seeded.append(credential_type)
    return seeded


def create_type(payload, actor=None):
    data = dict(payload or {})
    key = data.get("key")
    name = data.get("name")
    categories = data.get("categories", [])
    fields = data.get("fields", [])
    if not isinstance(key, str) or not key or not isinstance(name, str) or not name:
        raise CredentialServiceError("invalid")
    if not isinstance(categories, list) or any(not isinstance(category, str) or not category for category in categories):
        raise CredentialServiceError("invalid")
    try:
        validate_type_fields(fields)
    except SchemaError as exc:
        raise CredentialServiceError("invalid", str(exc)) from exc
    with transaction.atomic():
        if CredentialType.objects.filter(key=key).exists():
            raise CredentialServiceError("conflict")
        return CredentialType.objects.create(
            key=key,
            name=name,
            categories=deepcopy(categories),
            fields=deepcopy(fields),
            is_builtin=False,
            **_maintainer(actor),
        )


def update_type(type_ref, payload=None, actor=None, **values):
    if isinstance(type_ref, Mapping) and payload is not None and not isinstance(payload, Mapping) and actor is None:
        actor, payload = payload, type_ref
        type_ref = payload.get("key")
    elif isinstance(type_ref, Mapping):
        type_ref, payload = _type_key(type_ref), type_ref if payload is None else payload
    data = _payload(payload, values)
    with transaction.atomic():
        credential_type = _load_type(type_ref, lock=True)
        requested_key = data.get("key", credential_type.key)
        requested_categories = data.get("categories", credential_type.categories)
        requested_fields = data.get("fields", credential_type.fields)
        if credential_type.is_builtin and (
            requested_key != credential_type.key or requested_categories != credential_type.categories or requested_fields != credential_type.fields
        ):
            raise CredentialServiceError("immutable")
        if requested_key != credential_type.key and CredentialType.objects.filter(key=requested_key).exists():
            raise CredentialServiceError("conflict")
        try:
            validate_type_fields(requested_fields)
        except SchemaError as exc:
            raise CredentialServiceError("invalid", str(exc)) from exc
        if not isinstance(requested_categories, list) or any(not isinstance(category, str) or not category for category in requested_categories):
            raise CredentialServiceError("invalid")
        requested_name = data.get("name", credential_type.name)
        if not isinstance(requested_name, str) or not requested_name:
            raise CredentialServiceError("invalid")
        for field, value in (("key", requested_key), ("name", requested_name), ("categories", requested_categories), ("fields", requested_fields)):
            setattr(credential_type, field, deepcopy(value))
        maintainer = _maintainer(actor, include_created=False)
        credential_type.updated_by = maintainer["updated_by"]
        credential_type.updated_by_domain = maintainer["updated_by_domain"]
        credential_type.save(update_fields=["key", "name", "categories", "fields", "updated_at", "updated_by", "updated_by_domain"])
        return credential_type


def delete_type(type_ref, actor=None):
    with transaction.atomic():
        credential_type = _load_type(type_ref, lock=True)
        if credential_type.is_builtin:
            raise CredentialServiceError("immutable")
        if Credential.objects.filter(type_id=credential_type.key).exists():
            raise CredentialServiceError("in_use")
        credential_type.delete()
    return None


def create_credential(payload=None, actor=None, **values):
    data = _payload(payload, values)
    type_key = data.get("type") or data.get("type_key")
    owner_id = data.get("group_id")
    fields = data.get("fields", {})
    name = data.get("name")
    if not isinstance(name, str) or not name or owner_id is None:
        raise CredentialServiceError("invalid")
    try:
        owner_id = int(owner_id)
    except (TypeError, ValueError) as exc:
        raise CredentialServiceError("invalid") from exc
    owner_mode = data.get("owner_mode") or "manage"
    if owner_mode == "current":
        _require_current_owner(
            owner_id,
            actor,
            current_team=data.get("current_team"),
            group_list=data.get("group_list"),
            is_superuser=data.get("is_superuser"),
        )
    elif owner_mode == "manage":
        _require_manageable(
            owner_id,
            actor,
            current_team=data.get("current_team"),
            group_list=data.get("group_list"),
            is_superuser=data.get("is_superuser"),
        )
    else:
        raise CredentialServiceError("invalid")
    with transaction.atomic():
        credential_type = _load_type(type_key, lock=True)
        try:
            persisted = validate_instance_fields(type_fields=credential_type.fields, values=fields, require_secrets=True)
        except SchemaError as exc:
            raise CredentialServiceError("invalid", str(exc)) from exc
        encrypted = encrypt_instance_fields(credential_type.fields, persisted)
        credential = Credential.objects.create(
            credential_id=build_credential_id(credential_type.key),
            name=name,
            type=credential_type,
            group_id=owner_id,
            fields=encrypted,
            disabled=bool(data.get("disabled", False)),
            **_maintainer(actor),
        )
    return credential


def _load_credential(credential_id, *, lock=False):
    queryset = Credential.objects.select_related("type")
    if lock:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(credential_id=credential_id)
    except Credential.DoesNotExist as exc:
        raise CredentialServiceError("not_found") from exc


def update_credential(credential_id, payload=None, actor=None, **values):
    data = _payload(payload, values)
    peek = _load_credential(credential_id)
    if "group_id" in data and data["group_id"] not in (None, ""):
        try:
            requested_owner = int(data["group_id"])
        except (TypeError, ValueError) as exc:
            raise CredentialServiceError("invalid") from exc
        if requested_owner != peek.group_id:
            from apps.system_mgmt.services.credential_ref_count import assert_credential_unreferenced

            assert_credential_unreferenced(credential_id)
    with transaction.atomic():
        credential = _load_credential(credential_id, lock=True)
        if "credential_id" in data and data["credential_id"] != credential.credential_id:
            raise CredentialServiceError("immutable")
        if "type" in data or "type_key" in data:
            if (data.get("type") or data.get("type_key")) != credential.type_id:
                raise CredentialServiceError("immutable")
        owner_id = data.get("group_id", credential.group_id)
        try:
            owner_id = int(owner_id)
        except (TypeError, ValueError) as exc:
            raise CredentialServiceError("invalid") from exc
        _require_manageable(
            owner_id,
            actor,
            current_team=data.get("current_team"),
            group_list=data.get("group_list"),
            is_superuser=data.get("is_superuser"),
        )
        old_fields = deepcopy(credential.fields or {})
        incoming = data.get("fields")
        merged = deepcopy(old_fields)
        if incoming is not None:
            if not isinstance(incoming, Mapping):
                raise CredentialServiceError("invalid")
            merged.update(deepcopy(dict(incoming)))
        try:
            persisted = validate_instance_fields(type_fields=credential.type.fields, values=merged, require_secrets=False)
        except SchemaError as exc:
            raise CredentialServiceError("invalid", str(exc)) from exc
        incoming_values = dict(incoming) if isinstance(incoming, Mapping) else {}
        for field in credential.type.fields:
            if field.get("kind") == "secret" and field["id"] not in incoming_values:
                persisted.pop(field["id"], None)
        credential.fields = encrypt_instance_fields(credential.type.fields, persisted, old_fields)
        if "name" in data:
            if not isinstance(data["name"], str) or not data["name"]:
                raise CredentialServiceError("invalid")
            credential.name = data["name"]
        credential.group_id = owner_id
        if "disabled" in data:
            credential.disabled = bool(data["disabled"])
        maintainer = _maintainer(actor, include_created=False)
        credential.updated_by = maintainer["updated_by"]
        credential.updated_by_domain = maintainer["updated_by_domain"]
        credential.save(update_fields=["name", "group_id", "fields", "disabled", "updated_at", "updated_by", "updated_by_domain"])
    return credential


def set_disabled(credential_id, disabled, actor=None, *, current_team=None, group_list=None, is_superuser=None):
    with transaction.atomic():
        credential = _load_credential(credential_id, lock=True)
        if actor is not None or current_team is not None:
            _require_manageable(
                credential.group_id,
                actor,
                current_team=current_team,
                group_list=group_list,
                is_superuser=is_superuser,
            )
        credential.disabled = bool(disabled)
        credential.save(update_fields=["disabled", "updated_at", "updated_by", "updated_by_domain"])
    return _public_credential(credential)


def delete_credential(credential_id, actor=None, *, current_team=None, group_list=None, is_superuser=None):
    from apps.system_mgmt.services.credential_ref_count import assert_credential_unreferenced

    credential = _load_credential(credential_id)
    if actor is not None or current_team is not None:
        _require_manageable(
            credential.group_id,
            actor,
            current_team=current_team,
            group_list=group_list,
            is_superuser=is_superuser,
        )
    assert_credential_unreferenced(credential_id)
    with transaction.atomic():
        credential = _load_credential(credential_id, lock=True)
        if actor is not None or current_team is not None:
            _require_manageable(
                credential.group_id,
                actor,
                current_team=current_team,
                group_list=group_list,
                is_superuser=is_superuser,
            )
        credential.delete()
    return None


def get_credential(
    credential_id,
    current_team,
    actor=None,
    *,
    group_list=None,
    is_superuser=None,
    owner_scope="consume",
):
    credential = _load_credential(credential_id)
    current_team, group_list, is_superuser = _require_current_team(actor, current_team=current_team, group_list=group_list, is_superuser=is_superuser)
    if credential.group_id not in _owner_ids_for_scope(owner_scope, current_team, group_list, is_superuser):
        raise CredentialServiceError("forbidden")
    return _public_credential(credential)


def list_types(filters=None, **values):
    data = _payload(filters, values)
    queryset = CredentialType.objects.annotate(credential_count=Count("credential")).order_by("-is_builtin", "id")
    search = data.get("search")
    if search:
        queryset = queryset.filter(Q(name__icontains=str(search)) | Q(key__icontains=str(search)))
    category = data.get("category")
    if category:
        queryset = queryset.filter(categories__contains=[str(category)])
    return [_public_type(row) for row in queryset]


def _group_options(group_ids):
    if not group_ids:
        return []
    rows = Group.objects.filter(id__in=list(group_ids), is_delete=False).order_by("name")
    return [{"id": row.id, "name": row.name} for row in rows]


def list_assignable_groups(actor=None, *, current_team=None, group_list=None, is_superuser=None):
    current_team, group_list, is_superuser = _require_current_team(actor, current_team=current_team, group_list=group_list, is_superuser=is_superuser)
    return _group_options(manageable_owner_group_ids(current_team, group_list, is_superuser))


def list_usable_groups(actor=None, *, current_team=None, group_list=None, is_superuser=None):
    current_team, group_list, is_superuser = _require_current_team(actor, current_team=current_team, group_list=group_list, is_superuser=is_superuser)
    return _group_options(manageable_owner_group_ids(current_team, group_list, is_superuser))


def resolve_credential(credential_id, current_team, actor=None, *, group_list=None, is_superuser=None):
    credential = _load_credential(credential_id)
    current_team, group_list, is_superuser = _require_current_team(actor, current_team=current_team, group_list=group_list, is_superuser=is_superuser)
    if credential.group_id not in usable_owner_group_ids(current_team):
        raise CredentialServiceError("forbidden")
    if credential.disabled:
        raise CredentialServiceError("disabled")
    result = _public_credential(credential)
    result["fields"] = decrypt_instance_fields(credential.type.fields, credential.fields)
    return result


def resolve_secret_field(credential_id, field_id=None):
    """服务端专用：解出一个 secret 字段的明文（OpenAPI 网关 credential: 引用）。

    不做组织范围检查——网关密钥是平台级资源，能写注册表即有权引用。
    未指定 field_id 时该类型必须恰有一个 secret 字段，否则报 ambiguous_field。
    结果只应进入进程内渲染快照，禁止写日志或返回给客户端。
    """
    credential = _load_credential(credential_id)
    if credential.disabled:
        raise CredentialServiceError("disabled")
    secret_ids = secret_field_ids(credential.type.fields)
    if field_id:
        if field_id not in secret_ids:
            raise CredentialServiceError("unknown_field")
    elif len(secret_ids) == 1:
        field_id = secret_ids[0]
    else:
        raise CredentialServiceError("ambiguous_field")
    values = decrypt_instance_fields(credential.type.fields, credential.fields)
    value = values.get(field_id)
    if not isinstance(value, str) or not value:
        raise CredentialServiceError("empty")
    return value


def query_credentials(filters=None, actor=None, **values):
    data = _payload(filters, values)
    current_team, group_list, is_superuser = _require_current_team(
        actor,
        current_team=data.get("current_team"),
        group_list=data.get("group_list"),
        is_superuser=data.get("is_superuser"),
    )
    owner_ids = _owner_ids_for_scope(
        data.get("owner_scope") or "consume",
        current_team,
        group_list,
        is_superuser,
    )
    queryset = Credential.objects.select_related("type").filter(group_id__in=owner_ids)
    if "group_id" in data and data["group_id"] not in (None, ""):
        try:
            queryset = queryset.filter(group_id=int(data["group_id"]))
        except (TypeError, ValueError) as exc:
            raise CredentialServiceError("invalid") from exc
    if "disabled" in data and data["disabled"] is not None:
        queryset = queryset.filter(disabled=bool(data["disabled"]))
    type_key = data.get("type") or data.get("type_key")
    if type_key:
        queryset = queryset.filter(type_id=type_key)
    search = data.get("search")
    if search:
        queryset = queryset.filter(Q(name__icontains=str(search)))
    category = data.get("category")
    if category:
        queryset = queryset.filter(type__categories__contains=[str(category)])
    return queryset.order_by("id")


def list_credentials(filters=None, actor=None, **values):
    items = [_public_credential(row) for row in query_credentials(filters, actor=actor, **values)]
    from apps.system_mgmt.services.credential_ref_count import attach_public_refs

    return attach_public_refs(items)


def _bounded_page(page, page_size, *, default_size=20, max_size=100):
    try:
        page_number = int(page or 1)
    except (TypeError, ValueError):
        page_number = 1
    try:
        size = int(page_size if page_size not in (None, "") else default_size)
    except (TypeError, ValueError):
        size = default_size
    page_number = max(page_number, 1)
    if size < 1:
        size = default_size
    return page_number, min(size, max_size)


def page_credentials(filters=None, actor=None, page=1, page_size=20, **values):
    queryset = query_credentials(filters, actor=actor, **values)
    page_number, size = _bounded_page(page, page_size)
    start = (page_number - 1) * size
    count = queryset.count()
    items = [_public_credential(row) for row in queryset[start : start + size]]
    return items, count
