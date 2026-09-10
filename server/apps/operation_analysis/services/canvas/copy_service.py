from __future__ import annotations

import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import translation
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.models.maintainer_info import maintainer_kwargs
from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, NetworkTopology, Report, Screen, Topology
from apps.operation_analysis.serializers.directory_serializers import DirectoryChainVisibilityMixin

COPY_ATTEMPT_LIMIT = 1000
BUILTIN_TARGET_DIRECTORY_ERROR = "不能复制到内置目录"
SOURCE_NOT_VISIBLE_ERROR = "源画布不可见"
TARGET_DIRECTORY_NOT_VISIBLE_ERROR = "目标目录不可见"
NAME_EXHAUSTED_ERROR = "无法生成唯一的副本名称"

COPY_CONTENT_FIELDS = {
    Dashboard: ("desc", "filters", "other", "view_sets", "refresh_interval"),
    Topology: ("desc", "other", "view_sets", "refresh_interval"),
    Architecture: ("desc", "other", "view_sets"),
    Screen: ("desc", "other", "view_sets", "refresh_interval"),
    Report: ("desc", "other", "view_sets", "refresh_interval"),
    NetworkTopology: ("desc", "base_url", "refresh_interval", "status", "view_sets"),
}


class CanvasCopyRequestSerializer(DirectoryChainVisibilityMixin, serializers.Serializer):
    directory = serializers.PrimaryKeyRelatedField(queryset=Directory.objects.all())
    groups = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


def copy_name_suffix(language: str | None) -> str:
    normalized = (language or "en").replace("_", "-")
    with translation.override(normalized):
        translated = gettext("copy")
    if normalized.lower().startswith("zh") and translated == "copy":
        return "副本"
    return translated or "copy"


def allocate_copy_name(model, source_name: str, language: str | None, reserved: set[str] | None = None) -> str:
    suffix = copy_name_suffix(language)
    max_length = model._meta.get_field("name").max_length or 128
    taken = reserved or set()
    for index in range(1, COPY_ATTEMPT_LIMIT + 1):
        extra = "" if index == 1 else str(index)
        suffix_text = f"-{suffix}{extra}"
        base_budget = max_length - len(suffix_text)
        if base_budget < 1:
            break
        candidate = f"{source_name[:base_budget]}{suffix_text}"
        if candidate in taken:
            continue
        if not model.objects.filter(name=candidate).exists():
            return candidate
    raise ValidationError(NAME_EXHAUSTED_ERROR)


def copy_canvas(*, viewset, request, source):
    viewset._validate_current_team_permission(request)
    _ensure_source_visible(viewset, request, source)
    directory = _resolve_target_directory(request.data)
    _ensure_target_directory(viewset, request, directory)
    serializer = CanvasCopyRequestSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    groups = serializer.validated_data["groups"]

    language = translation.get_language() or getattr(getattr(request, "user", None), "locale", None) or "en"
    model = source.__class__
    payload_base = _build_copy_payload(source, directory=directory, groups=groups)

    viewset._validate_org_field_permission(request, groups)

    last_error = None
    reserved_names: set[str] = set()
    for _attempt in range(COPY_ATTEMPT_LIMIT):
        payload = dict(payload_base)
        payload["name"] = allocate_copy_name(model, source.name, language, reserved=reserved_names)
        reserved_names.add(payload["name"])
        create_serializer = viewset.get_serializer(data=payload)
        try:
            create_serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                instance = create_serializer.save(**_actor_maintainer_fields(request))
                _strip_builtin_identity(instance)
                _clear_network_topology_runtime_cache(instance)
            return instance
        except DjangoValidationError as error:
            raise ValidationError(getattr(error, "message_dict", error.messages)) from error
        except ValidationError as error:
            if not _is_name_conflict(error):
                raise
            last_error = error
        except IntegrityError as error:
            if not _is_name_conflict(error):
                raise
            last_error = error

    raise ValidationError(NAME_EXHAUSTED_ERROR) from last_error


def _build_copy_payload(source, *, directory, groups) -> dict:
    payload = {
        "directory": directory.pk,
        "groups": list(groups),
    }
    for field in COPY_CONTENT_FIELDS[source.__class__]:
        payload[field] = copy.deepcopy(getattr(source, field))
    if isinstance(source, NetworkTopology):
        from apps.operation_analysis.serializers.network_topology_serializers import decrypt_token

        payload["token"] = decrypt_token(source.token)
    return payload


def _strip_builtin_identity(instance) -> None:
    if not getattr(instance, "is_build_in", False) and not getattr(instance, "build_in_key", None):
        return
    instance.is_build_in = False
    instance.build_in_key = None
    instance.save(update_fields=["is_build_in", "build_in_key"])


def _clear_network_topology_runtime_cache(instance) -> None:
    if not isinstance(instance, NetworkTopology):
        return
    if instance.last_runtime_cache in (None, {}):
        return
    instance.last_runtime_cache = {}
    instance.save(update_fields=["last_runtime_cache"])


def _resolve_target_directory(data) -> Directory:
    raw_directory = None if data is None else data.get("directory")
    if raw_directory in (None, ""):
        raise ValidationError({"directory": ["该字段是必填项。"]})
    try:
        return Directory.objects.get(pk=raw_directory)
    except (Directory.DoesNotExist, TypeError, ValueError) as error:
        raise ValidationError({"directory": ["目标目录不存在"]}) from error


def _actor_maintainer_fields(request) -> dict:
    user = getattr(request, "user", None)
    return maintainer_kwargs(
        {
            "username": getattr(user, "username", "") or "",
            "domain": getattr(user, "domain", "") or "",
        }
    )


def _ensure_source_visible(viewset, request, source) -> None:
    if not _is_groups_visible(viewset, request, source):
        raise PermissionDenied(SOURCE_NOT_VISIBLE_ERROR)


def _ensure_target_directory(viewset, request, directory: Directory) -> None:
    if directory.is_build_in:
        raise ValidationError({"directory": [BUILTIN_TARGET_DIRECTORY_ERROR]})
    if not _is_groups_visible(viewset, request, directory):
        raise PermissionDenied(TARGET_DIRECTORY_NOT_VISIBLE_ERROR)


def _is_groups_visible(viewset, request, instance) -> bool:
    user = getattr(request, "user", None)
    if getattr(user, "is_superuser", False):
        return True
    # 与 list/retrieve 一致：current_team 必须是用户真实加入的组织，不能只信 cookie。
    current_team = viewset._validate_current_team_permission(request)
    return current_team in (getattr(instance, "groups", None) or [])


def _is_name_conflict(error: Exception) -> bool:
    if isinstance(error, IntegrityError):
        return "name" in str(error).lower() or "unique" in str(error).lower()
    detail = getattr(error, "detail", None)
    return isinstance(detail, dict) and "name" in detail
