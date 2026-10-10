"""Derive credential bindings from a plugin UI template."""

from __future__ import annotations

import copy
import re

from apps.core.logger import monitor_logger as logger
from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES, usable_builtin_type_keys

_OBJECT_CATEGORY = {
    "database": "database",
    "数据库": "database",
    "middleware": "middleware",
    "中间件": "middleware",
    "os": "host",
    "host": "host",
    "操作系统": "host",
    "主机": "host",
    "network": "network",
    "network device": "network",
    "网络": "network",
    "网络设备": "network",
}

_PUBLIC_VARIANT_KEYS = (
    "key",
    "when",
    "type_keys",
    "category",
    "anchor_field",
    "managed_fields",
    "snmp_version_field",
)

_PATH_INDEX = re.compile(r"^([^\[\]]+)\[(\d+)\]$")


def public_credential_binding(binding):
    if not binding or not binding.get("variants"):
        return {"variants": []}
    variants = []
    for variant in binding["variants"]:
        variants.append({key: variant.get(key) for key in _PUBLIC_VARIANT_KEYS})
    return {"variants": variants}


def derive_credential_binding(ui_content, plugin):
    content = ui_content if isinstance(ui_content, dict) else {}
    if content.get("credential_binding") is False:
        return {"variants": []}
    fields = [field for field in (content.get("form_fields") or []) if isinstance(field, dict) and field.get("name")]
    by_name = {field["name"]: field for field in fields}
    names = set(by_name)
    config_types = _config_types(content)
    collect_type = str(content.get("collect_type") or "")
    variants = _match_variants(names, by_name, config_types, collect_type)
    if not variants:
        logger.debug(
            "event=credential_binding_unmatched plugin_id=%s field_names=%s",
            getattr(plugin, "id", "") or "",
            ",".join(field["name"] for field in fields),
        )
        return {"variants": []}
    built = []
    for spec in variants:
        variant = _materialize_variant(spec, by_name, plugin)
        if variant and variant.get("type_keys"):
            built.append(variant)
    if not built:
        logger.debug(
            "event=credential_binding_unmatched plugin_id=%s field_names=%s",
            getattr(plugin, "id", "") or "",
            ",".join(field["name"] for field in fields),
        )
        return {"variants": []}
    return {
        "variants": built,
        "_collect_type": collect_type,
        "_config_types": config_types,
        "_fields": {field["name"]: _field_snapshot(field) for field in fields},
    }


def binding_for_plugin(plugin):
    if plugin is None:
        return {"variants": []}
    from apps.monitor.models import MonitorPluginUITemplate
    from apps.monitor.services.ui_form_field_overlay import overlay_form_field_help_from_plugin_files
    from apps.monitor.services.ui_template_locale import enrich_ui_template_from_plugin_files

    row = MonitorPluginUITemplate.objects.filter(plugin=plugin).first()
    content = row.content if row is not None else {}
    enriched = overlay_form_field_help_from_plugin_files(enrich_ui_template_from_plugin_files(content, plugin), plugin)
    return derive_credential_binding(enriched or {}, plugin)


def select_variant(binding, values, requested_key=None):
    variants = list((binding or {}).get("variants") or [])
    if not variants:
        return None
    values = values if isinstance(values, dict) else {}
    matched = [variant for variant in variants if _when_matches(variant.get("when") or {}, values)]
    chosen = None
    if len(matched) == 1:
        chosen = matched[0]
    elif not matched and _when_field_submitted(variants, values):
        return None
    elif len(variants) == 1 and not (variants[0].get("when") or {}):
        chosen = variants[0]
    elif requested_key:
        chosen = next((variant for variant in variants if variant.get("key") == requested_key), None)
    if chosen is None:
        return None
    if requested_key not in (None, "") and chosen.get("key") != requested_key:
        return None
    return chosen


def managed_storage_targets(binding, config_ids):
    """Storage locations for every variant, expanded with concrete config ids."""
    targets = []
    child_ids = []
    base_ids = []
    for item in config_ids or []:
        if isinstance(item, dict):
            config_id = item.get("id")
            is_child = item.get("is_child", True)
        else:
            config_id = getattr(item, "id", None)
            is_child = getattr(item, "is_child", True)
        if not config_id:
            continue
        if is_child:
            child_ids.append(str(config_id))
        else:
            base_ids.append(str(config_id))
    for variant in (binding or {}).get("variants") or []:
        for target in variant.get("_targets") or []:
            scope = target.get("scope")
            ids = child_ids if scope == "child" else base_ids
            if target.get("kind") == "env":
                env_name = target.get("env_name") or ""
                if scope == "child":
                    for config_id in ids:
                        copied = dict(target)
                        copied["config_id"] = config_id
                        copied["env_key"] = f"{env_name}__{config_id.upper()}"
                        targets.append(copied)
                else:
                    for config_id in ids:
                        copied = dict(target)
                        copied["config_id"] = config_id
                        copied["env_key"] = env_name
                        targets.append(copied)
                if scope == "child" and base_ids and env_name:
                    for config_id in base_ids:
                        copied = dict(target)
                        copied["scope"] = "base"
                        copied["config_id"] = config_id
                        copied["env_key"] = env_name
                        targets.append(copied)
                continue
            for config_id in ids:
                copied = dict(target)
                copied["config_id"] = config_id
                targets.append(copied)
    return targets


def _when_field_submitted(variants, values):
    values = values if isinstance(values, dict) else {}
    for variant in variants or []:
        field_name = (variant.get("when") or {}).get("field")
        if field_name and field_name in values:
            return True
    return False


def managed_env_keys_by_config_ids(config_ids):
    """一次查出这批子配置里仓库行的受管 env 键。非仓库行不出现在结果里。"""
    from apps.monitor.models import CollectConfig

    wanted = [str(item) for item in (config_ids or []) if item]
    if not wanted:
        return {}
    rows = list(CollectConfig.objects.filter(id__in=wanted).select_related("monitor_plugin"))
    vault_rows = [row for row in rows if row.vault_credential_id]
    if not vault_rows:
        return {}
    pair_filter = None
    seen_pairs = set()
    for row in vault_rows:
        pair = (row.monitor_instance_id, row.monitor_plugin_id)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        clause = CollectConfig.objects.filter(monitor_instance_id=pair[0], monitor_plugin_id=pair[1])
        pair_filter = clause if pair_filter is None else pair_filter | clause
    grouped = {}
    for row in pair_filter.select_related("monitor_plugin"):
        grouped.setdefault((row.monitor_instance_id, row.monitor_plugin_id), []).append(row)
    bindings = {}
    result = {}
    for row in vault_rows:
        plugin = row.monitor_plugin
        plugin_id = getattr(plugin, "id", None)
        if plugin_id not in bindings:
            bindings[plugin_id] = binding_for_plugin(plugin)
        group = grouped.get((row.monitor_instance_id, row.monitor_plugin_id)) or [row]
        keys = []
        for target in managed_storage_targets(bindings[plugin_id], group):
            if target.get("kind") == "env" and target.get("config_id") == str(row.id) and target.get("env_key"):
                keys.append(target["env_key"])
        result[str(row.id)] = list(dict.fromkeys(keys))
    return result


def managed_env_keys_for_child(config_id):
    """Env key names for a vault child config. None when the row is not vault-backed."""
    from apps.monitor.models import CollectConfig

    row = CollectConfig.objects.filter(id=config_id).select_related("monitor_plugin").first()
    if row is None or not row.vault_credential_id:
        return None
    group = list(
        CollectConfig.objects.filter(
            monitor_instance_id=row.monitor_instance_id,
            monitor_plugin_id=row.monitor_plugin_id,
        )
    )
    binding = binding_for_plugin(row.monitor_plugin)
    keys = []
    for target in managed_storage_targets(binding, group):
        if target.get("kind") == "env" and target.get("config_id") == str(row.id) and target.get("env_key"):
            keys.append(target["env_key"])
    return list(dict.fromkeys(keys))


def managed_field_names(binding):
    names = []
    for variant in (binding or {}).get("variants") or []:
        for name in variant.get("managed_fields") or []:
            if name not in names:
                names.append(name)
    return names


def _match_variants(names, by_name, config_types, collect_type):
    config_set = set(config_types)
    if "community" in names and "sec_name" in names:
        return [_snmp_variant("2", by_name), _snmp_variant("3", by_name)]
    if "os_type" in names and "private_key_content" in names:
        return [
            _variant(
                "linux",
                {"field": "os_type", "value": "linux"},
                ["ssh"],
                "host",
                "username",
                ["username", "auth_type", "ENV_PASSWORD", "private_key_content", "private_key_passphrase"],
                "ssh",
            ),
            _variant("windows", {"field": "os_type", "value": "windows"}, ["winrm"], "host", "username", ["username", "ENV_PASSWORD"], "winrm"),
        ]
    if "private_key_content" in names and "os_type" not in names:
        return [
            _variant(
                "default",
                {},
                ["ssh"],
                "host",
                "username",
                ["username", "auth_type", "ENV_PASSWORD", "private_key_content", "private_key_passphrase"],
                "ssh",
            ),
        ]
    if config_set and config_set <= {"qcloud", "aliyun"}:
        return [_variant("default", {}, ["cloud"], "cloud", "username", ["username", "ENV_PASSWORD"], "cloud")]
    if "windows_wmi" in config_set:
        return [_variant("default", {}, ["winrm"], "host", "username", ["username", "ENV_PASSWORD"], "winrm")]
    if collect_type == "ipmi":
        return [_variant("default", {}, ["ipmi"], "host", "username", ["username", "ENV_PASSWORD"], "ipmi")]
    if collect_type == "redfish":
        return [_variant("default", {}, ["redfish"], "host", "username", ["username", "ENV_PASSWORD"], "redfish")]
    if "vmware" in config_set:
        return [_variant("default", {}, ["platform_api"], "cloud", "username", ["username", "ENV_PASSWORD"], "platform_api")]
    auth_values = set(_option_values(by_name.get("auth_type")))
    if {"basic", "bearer"} <= auth_values:
        return [
            _variant("basic", {"field": "auth_type", "value": "basic"}, ["sql"], "other", "username", ["username", "ENV_PASSWORD"], "basic"),
            _variant("bearer", {"field": "auth_type", "value": "bearer"}, ["token"], "other", "ENV_BEARER_TOKEN", ["ENV_BEARER_TOKEN"], "bearer"),
        ]
    if "ENV_BEARER_TOKEN" in names and {"bearer", "public"} <= auth_values:
        return [_variant("bearer", {"field": "auth_type", "value": "bearer"}, ["token"], "other", "ENV_BEARER_TOKEN", ["ENV_BEARER_TOKEN"], "bearer")]
    if any(name.startswith("ENV_SASL_") for name in names):
        return [
            _variant(
                "sasl",
                {"field": "ENV_SASL_ENABLED", "value": True},
                ["sql"],
                "middleware",
                "ENV_SASL_USERNAME",
                ["ENV_SASL_USERNAME", "ENV_SASL_PASSWORD"],
                "kafka",
            )
        ]
    username = by_name.get("username")
    password = by_name.get("password")
    if username and password and str((username.get("transform_on_edit") or {}).get("origin_path") or "").startswith("base."):
        return [_variant("default", {}, ["sql"], "middleware", "username", ["username", "password"], "jmx")]
    if "influxdb" in config_set:
        return [_variant("default", {}, ["sql", "token"], "database", "username", ["username", "ENV_PASSWORD"], "influx")]
    password_fields = [field["name"] for field in by_name.values() if field.get("type") == "password"]
    user_field = "username" if "username" in names else ("ENV_USER" if "ENV_USER" in names else "")
    if user_field and len(password_fields) == 1:
        hinted = collect_type if collect_type in {"database", "middleware", "host", "network"} else None
        return [_variant("default", {}, ["sql"], hinted, user_field, [user_field, password_fields[0]], "user_password")]
    if not user_field and len(password_fields) == 1:
        return [_variant("default", {}, ["token"], "other", password_fields[0], [password_fields[0]], "token")]
    return []


def _snmp_variant(version, by_name):
    if version == "2":
        managed = ["community"]
        anchor = "community"
        profile = "snmp_v2"
    else:
        password_names = []
        for name in ("ENV_AUTH_PASSWORD", "auth_password", "ENV_PRIV_PASSWORD", "priv_password"):
            if name in by_name:
                password_names.append(name)
        managed = ["sec_name", "sec_level", "auth_protocol", "priv_protocol", *password_names]
        anchor = "sec_name"
        profile = "snmp_v3"
    return _variant(version, {"field": "version", "value": int(version)}, ["snmp"], "network", anchor, managed, profile, snmp_version_field="version")


def _variant(key, when, type_keys, category, anchor, managed, profile, snmp_version_field=None):
    return {
        "key": key,
        "when": when or {},
        "preferred_keys": list(type_keys),
        "hinted_category": category,
        "anchor_field": anchor,
        "managed_fields": [name for name in managed if name],
        "snmp_version_field": snmp_version_field,
        "_profile": profile,
    }


def _materialize_variant(spec, by_name, plugin):
    preferred = list(spec["preferred_keys"])
    category = _choose_category(plugin, preferred, spec.get("hinted_category"))
    if not category:
        return None
    type_keys = []
    for key in preferred:
        for actual in usable_builtin_type_keys(key, category):
            if actual not in type_keys:
                type_keys.append(actual)
    if not type_keys:
        return None
    targets = []
    for name in spec["managed_fields"]:
        field = by_name.get(name)
        if field is None:
            continue
        targets.append(_target_from_field(field))
    return {
        "key": spec["key"],
        "when": spec["when"] or {},
        "type_keys": type_keys,
        "category": category,
        "anchor_field": spec["anchor_field"],
        "managed_fields": list(spec["managed_fields"]),
        "snmp_version_field": spec.get("snmp_version_field"),
        "_profile": spec["_profile"],
        "_targets": targets,
        "_preferred_keys": preferred,
    }


def _choose_category(plugin, preferred_keys, hinted):
    lists = []
    for key in preferred_keys:
        definition = BUILTIN_TYPES.get(key) or {}
        lists.append(list(definition.get("categories") or []))
    if not lists or any(not item for item in lists):
        return None
    object_category = _object_category(plugin)
    if len(lists) > 1:
        shared = set(lists[0])
        for item in lists[1:]:
            shared &= set(item)
        if object_category in shared:
            return object_category
        if hinted in shared:
            return hinted
        for category in lists[0]:
            if category in shared:
                return category
        return None
    categories = lists[0]
    if object_category in categories:
        return object_category
    if hinted in categories:
        return hinted
    return categories[0]


def _object_category(plugin):
    if plugin is None:
        return None
    objects = getattr(plugin, "monitor_object", None)
    rows = []
    if objects is not None and hasattr(objects, "all"):
        try:
            rows = list(objects.all())
        except Exception:
            rows = []
    for row in rows:
        type_row = getattr(row, "type", None)
        for value in (getattr(type_row, "id", None), getattr(type_row, "name", None), getattr(row, "name", None)):
            mapped = _OBJECT_CATEGORY.get(str(value or "").strip().casefold())
            if mapped:
                return mapped
    return None


def _target_from_field(field):
    transform = field.get("transform_on_edit") or {}
    origin = str(transform.get("origin_path") or "")
    to_form = transform.get("to_form") if isinstance(transform.get("to_form"), dict) else {}
    regex = to_form.get("regex")
    target = {
        "field": field.get("name"),
        "encrypted": bool(field.get("encrypted")),
        "required": bool(field.get("required")),
        "regex": regex or None,
        "url_encode": bool(transform.get("url_encode")),
        "scope": "base" if origin.startswith("base.") else "child",
    }
    if ".env_config." in origin:
        env_name = origin.split(".env_config.", 1)[1]
        env_name = env_name.split("__{{config_id}}", 1)[0]
        target.update({"kind": "env", "env_name": env_name})
        return target
    if ".content." in origin:
        path = origin.split(".content.", 1)[1]
        target.update({"kind": "dsn" if regex else "content", "path": path})
        return target
    target.update({"kind": "form"})
    return target


def _field_snapshot(field):
    return {
        "name": field.get("name"),
        "type": field.get("type"),
        "required": bool(field.get("required")),
        "encrypted": bool(field.get("encrypted")),
        "origin_path": str((field.get("transform_on_edit") or {}).get("origin_path") or ""),
    }


def _config_types(content):
    raw = content.get("config_type")
    if isinstance(raw, list):
        return [str(item) for item in raw if item not in (None, "")]
    if raw not in (None, ""):
        return [str(raw)]
    return []


def _option_values(field):
    if not isinstance(field, dict):
        return []
    options = field.get("options") or (field.get("widget_props") or {}).get("options") or []
    values = []
    for option in options:
        if isinstance(option, dict):
            values.append(option.get("value"))
        else:
            values.append(option)
    return values


def _when_matches(when, values):
    if not when:
        return True
    field = when.get("field")
    expected = when.get("value")
    actual = values.get(field)
    if isinstance(expected, bool):
        return _as_bool(actual) is expected
    if isinstance(expected, int) and not isinstance(expected, bool):
        try:
            return int(actual) == expected
        except (TypeError, ValueError):
            return str(actual) == str(expected)
    return actual == expected or str(actual) == str(expected)


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().casefold()
    return text in {"1", "true", "yes", "on"}


def parse_content_path(path):
    parts = []
    for piece in str(path or "").split("."):
        if not piece:
            continue
        matched = _PATH_INDEX.match(piece)
        if matched:
            parts.append(matched.group(1))
            parts.append(int(matched.group(2)))
        else:
            parts.append(piece)
    return parts


def get_path(payload, path):
    current = payload
    for part in parse_content_path(path):
        if isinstance(part, int):
            if not isinstance(current, list) or part >= len(current):
                return None
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
    return current


def set_path(payload, path, value):
    parts = parse_content_path(path)
    if not parts:
        return payload
    current = payload
    for index, part in enumerate(parts[:-1]):
        next_is_index = isinstance(parts[index + 1], int)
        if isinstance(part, int):
            while len(current) <= part:
                current.append([] if next_is_index else {})
            if not isinstance(current[part], (dict, list)):
                current[part] = [] if next_is_index else {}
            current = current[part]
            continue
        nxt = current.get(part) if isinstance(current, dict) else None
        if not isinstance(nxt, (dict, list)):
            nxt = [] if next_is_index else {}
            current[part] = nxt
        current = nxt
    last = parts[-1]
    if isinstance(last, int):
        while len(current) <= last:
            current.append(None)
        current[last] = value
    else:
        current[last] = value
    return payload


def delete_path(payload, path):
    parts = parse_content_path(path)
    if not parts or not isinstance(payload, dict):
        return
    current = payload
    for part in parts[:-1]:
        if isinstance(part, int):
            if not isinstance(current, list) or part >= len(current):
                return
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                return
            current = current[part]
    last = parts[-1]
    if isinstance(last, int):
        if isinstance(current, list) and last < len(current):
            current[last] = None
        return
    if isinstance(current, dict):
        current.pop(last, None)


def values_for_variant(binding, content_by_config):
    """Read current-branch stored values. Used when an edit keeps an unchanged credential."""
    return copy.deepcopy(content_by_config or {})
