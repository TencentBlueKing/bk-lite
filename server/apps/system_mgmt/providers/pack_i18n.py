from pathlib import Path
from typing import Any

import yaml

from apps.system_mgmt.providers.schemas import ProviderManifest

REQUIRED_LANGUAGE_FILES = ("en.yaml", "zh-Hans.yaml")
_ZH_HANS_ALIASES = {"zh", "zh-cn", "zh-hans"}
_FIELD_COPY_KEYS = ("label", "help_text", "placeholder")


def normalize_locale(locale: str | None) -> str:
    raw = (locale or "").replace("_", "-").strip()
    if raw.lower() in _ZH_HANS_ALIASES:
        return "zh-Hans"
    return "en"


def load_language_catalog(pack_dir: Path) -> dict[str, dict[str, Any]]:
    language_dir = pack_dir / "language"
    if not language_dir.is_dir():
        raise ValueError(f"Provider pack '{pack_dir.name}' is missing language/")

    catalog: dict[str, dict[str, Any]] = {}
    for filename in REQUIRED_LANGUAGE_FILES:
        path = language_dir / filename
        if not path.is_file():
            raise ValueError(f"Provider pack '{pack_dir.name}' is missing language/{filename}")

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"Provider pack '{pack_dir.name}' language/{filename} must be a mapping")

        description = str(raw.get("description") or "").strip()
        if not description:
            raise ValueError(
                f"Provider pack '{pack_dir.name}' language/{filename} requires a non-empty description"
            )

        locale_key = filename.removesuffix(".yaml")
        raw["name"] = str(raw.get("name") or "").strip()
        raw["description"] = description
        catalog[locale_key] = raw
    return catalog


def resolve_provider_copy(manifest: ProviderManifest, locale: str | None) -> tuple[str, str]:
    catalog = getattr(manifest, "pack_i18n", None) or {}
    requested = catalog.get(normalize_locale(locale)) or {}
    english = catalog.get("en") or {}
    name = requested.get("name") or english.get("name") or getattr(manifest, "name", "") or getattr(manifest, "key", "")
    description = (
        requested.get("description")
        or english.get("description")
        or getattr(manifest, "description", "")
        or ""
    )
    return name, description


_REQUEST_LOCALE_ATTR = "_pack_i18n_locale"


def request_locale(request) -> str:
    if request is None:
        return "en"
    cached = getattr(request, _REQUEST_LOCALE_ATTR, None)
    if isinstance(cached, str) and cached:
        return cached

    user = getattr(request, "user", None)
    locale = "en"
    if user is not None:
        locale = _account_locale(user) or getattr(user, "locale", "en") or "en"
    setattr(request, _REQUEST_LOCALE_ATTR, locale)
    return locale


def _account_locale(user) -> str | None:
    username = getattr(user, "username", None)
    if not username:
        return None
    domain = getattr(user, "domain", None) or "domain.com"
    from apps.system_mgmt.models import User as AccountUser

    locale = (
        AccountUser.objects.filter(username=username, domain=domain)
        .values_list("locale", flat=True)
        .first()
    )
    if isinstance(locale, str) and locale.strip():
        return locale
    return None


def resolve_registered_provider_name(provider_key: str, locale: str | None) -> str:
    from apps.system_mgmt.providers.registry import get_provider_registry

    manifest = get_provider_registry().get(provider_key)
    if manifest is None:
        return provider_key
    name, _ = resolve_provider_copy(manifest, locale)
    return name


def resolve_bound_instance_provider_name(obj, request) -> str:
    if not getattr(obj, "integration_instance_id", None):
        return ""
    instance = getattr(obj, "integration_instance", None)
    if instance is None:
        return ""
    return resolve_registered_provider_name(instance.provider_key, request_locale(request))


def localize_public_manifest(manifest: ProviderManifest, locale: str | None) -> dict:
    payload = manifest.to_public_dict()
    name, description = resolve_provider_copy(manifest, locale)
    payload["name"] = name
    payload["description"] = description
    catalog = getattr(manifest, "pack_i18n", None) or {}
    requested = catalog.get(normalize_locale(locale)) or {}
    english = catalog.get("en") or {}
    _overlay_form_copy(payload, requested, english)
    return payload


def _as_mapping(value: Any) -> dict[Any, Any]:
    return value if isinstance(value, dict) else {}


def _pick_text(*candidates: Any) -> str | None:
    for item in candidates:
        if isinstance(item, str) and item.strip():
            return item
    return None


def _lookup(mapping: dict[Any, Any], key: Any) -> Any:
    if key in mapping:
        return mapping[key]
    if key is None:
        return None
    text = str(key)
    if text in mapping:
        return mapping[text]
    return None


def _overlay_form_copy(payload: dict[str, Any], requested: dict[str, Any], english: dict[str, Any]) -> None:
    requested_templates = _as_mapping(requested.get("templates"))
    english_templates = _as_mapping(english.get("templates"))
    for bucket in ("instance_templates", "business_templates"):
        templates = payload.get(bucket) or {}
        if not isinstance(templates, dict):
            continue
        for template_key, template in templates.items():
            if not isinstance(template, dict):
                continue
            _overlay_template(
                template,
                _as_mapping(_lookup(requested_templates, template_key)),
                _as_mapping(_lookup(english_templates, template_key)),
            )

    requested_capabilities = _as_mapping(requested.get("capabilities"))
    english_capabilities = _as_mapping(english.get("capabilities"))
    for capability in payload.get("capabilities") or []:
        if not isinstance(capability, dict):
            continue
        requested_capability = _as_mapping(_lookup(requested_capabilities, capability.get("key")))
        english_capability = _as_mapping(_lookup(english_capabilities, capability.get("key")))
        _overlay_fields(
            capability.get("connection_template") or [],
            _as_mapping(requested_capability.get("fields")),
            _as_mapping(english_capability.get("fields")),
        )

    flattened: list[dict[str, Any]] = []
    for template in (payload.get("instance_templates") or {}).values():
        if not isinstance(template, dict):
            continue
        for group in template.get("groups") or []:
            if isinstance(group, dict):
                flattened.extend(field for field in (group.get("fields") or []) if isinstance(field, dict))
    payload["instance_template"] = flattened


def _overlay_template(template: dict[str, Any], requested: dict[str, Any], english: dict[str, Any]) -> None:
    title = _pick_text(requested.get("title"), english.get("title"))
    if title is not None:
        template["title"] = title

    requested_groups = _as_mapping(requested.get("groups"))
    english_groups = _as_mapping(english.get("groups"))
    for group in template.get("groups") or []:
        if not isinstance(group, dict):
            continue
        requested_group = _as_mapping(_lookup(requested_groups, group.get("key")))
        english_group = _as_mapping(_lookup(english_groups, group.get("key")))
        group_title = _pick_text(requested_group.get("title"), english_group.get("title"))
        if group_title is not None:
            group["title"] = group_title
        _overlay_fields(
            group.get("fields") or [],
            _as_mapping(requested_group.get("fields")),
            _as_mapping(english_group.get("fields")),
        )


def _overlay_fields(fields: list[Any], requested_fields: dict[str, Any], english_fields: dict[str, Any]) -> None:
    for field in fields:
        if not isinstance(field, dict):
            continue
        requested_field = _as_mapping(_lookup(requested_fields, field.get("key")))
        english_field = _as_mapping(_lookup(english_fields, field.get("key")))
        for copy_key in _FIELD_COPY_KEYS:
            value = _pick_text(requested_field.get(copy_key), english_field.get(copy_key))
            if value is not None:
                field[copy_key] = value
        _overlay_options(field, requested_field, english_field)


def _overlay_options(field: dict[str, Any], requested_field: dict[str, Any], english_field: dict[str, Any]) -> None:
    requested_options = _as_mapping(requested_field.get("options"))
    english_options = _as_mapping(english_field.get("options"))
    if not requested_options and not english_options:
        return
    for option in field.get("options") or []:
        if not isinstance(option, dict):
            continue
        label = _pick_text(
            _lookup(requested_options, option.get("value")),
            _lookup(english_options, option.get("value")),
        )
        if label is not None:
            option["label"] = label
