"""Lock a collect-config group and write vault credentials onto node config."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.logger import monitor_logger as logger
from apps.monitor.models import CollectConfig
from apps.rpc.node_mgmt import NodeMgmt
from apps.rpc.system_mgmt import SystemMgmt

from .binding import binding_for_plugin, get_path, managed_field_names, managed_storage_targets, select_variant, set_path
from .errors import CLEARED_SYNC_ERRORS, VaultCredentialError, client_code
from .mapper import apply_storage_writes, stored_writes_for_variant, strip_managed_values, to_create_fields, to_storage_writes
from .resolver import describe_for_actor, resolve_for_actor

_ALLOWED_TRIGGERS = {"refresh", "reconcile"}
_CREDENTIAL_INPUT_KEYS = ("credential_source", "vault_credential_id", "vault_variant")
_CLIENT_VAULT_KEYS = ("vault_actor_context", "vault_applied_version", "vault_sync_error", "vault_synced_at")
_CONTENT_MASK_KEYS = {"community", "auth_password", "priv_password"}
_REDACTED = "***"


class _ApplyWriteError(Exception):
    def __init__(self, stage, original):
        self.stage = stage
        self.original = original
        super().__init__(stage)


def raise_client(error):
    if isinstance(error, VaultCredentialError):
        raise ValidationAppException(client_code(error.code))
    raise error


def stored_actor(actor_context):
    actor = actor_context or {}
    team = actor.get("current_team")
    try:
        team = int(team)
    except (TypeError, ValueError):
        pass
    return {
        "username": actor.get("username"),
        "domain": actor.get("domain"),
        "current_team": team,
    }


def lock_config_group(instance_id, monitor_plugin_id, *, skip_locked=False):
    queryset = CollectConfig.objects.filter(
        monitor_instance_id=instance_id,
        monitor_plugin_id=monitor_plugin_id,
    ).order_by("id")
    expected_ids = list(queryset.values_list("id", flat=True))
    locked = list(queryset.select_for_update(skip_locked=skip_locked))
    if skip_locked and len(locked) != len(expected_ids):
        return None
    return locked


def stamp_vault_binding(configs, *, credential_id, variant, actor_context, name, applied_version=None, sync_error=""):
    actor = stored_actor(actor_context)
    variant_key = variant if isinstance(variant, str) else (variant or {}).get("key") or ""
    now = timezone.now()
    for row in configs or []:
        row.vault_credential_id = credential_id or ""
        row.vault_variant = variant_key
        row.vault_actor_context = actor
        row.vault_credential_name = name or ""
        row.vault_sync_error = sync_error or ""
        fields = [
            "vault_credential_id",
            "vault_variant",
            "vault_actor_context",
            "vault_credential_name",
            "vault_sync_error",
            "updated_at",
        ]
        if applied_version is not None:
            row.vault_applied_version = int(applied_version)
            row.vault_synced_at = now
            fields.extend(["vault_applied_version", "vault_synced_at"])
        row.save(update_fields=fields)


def clear_vault_binding(configs):
    for row in configs or []:
        row.vault_credential_id = ""
        row.vault_variant = ""
        row.vault_actor_context = {}
        row.vault_credential_name = ""
        row.vault_applied_version = 0
        row.vault_sync_error = ""
        row.vault_synced_at = None
        row.save(
            update_fields=[
                "vault_credential_id",
                "vault_variant",
                "vault_actor_context",
                "vault_credential_name",
                "vault_applied_version",
                "vault_sync_error",
                "vault_synced_at",
                "updated_at",
            ]
        )


def purge_managed_secrets(configs, binding, config_ids, *, node_mgmt):
    targets = managed_storage_targets(binding, config_ids or configs)
    if not targets:
        return
    raw = _load_node_maps(configs, project=False)
    envs, contents = strip_managed_values(raw["env"], raw["content"], targets)
    _write_node_maps(configs, envs, contents, raw["serialized"], node_mgmt, file_types=raw["file_type"])


def local_node_mgmt():
    return NodeMgmt(is_local_client=True)


def apply_vault_credential(credential_id, instance_id, monitor_plugin_id, *, trigger, skip_locked=False):
    if trigger not in _ALLOWED_TRIGGERS:
        raise ValueError("invalid vault apply trigger")
    try:
        with transaction.atomic():
            locked = lock_config_group(instance_id, monitor_plugin_id, skip_locked=skip_locked)
            if not locked:
                return "skipped"
            if any(row.vault_credential_id != credential_id for row in locked):
                return "skipped"
            actor = _shared_actor(locked)
            if actor is None:
                _set_rows(locked, vault_sync_error="apply_failed")
                return "failed"
            variant_key = _shared_variant(locked)
            if not variant_key:
                _set_rows(locked, vault_sync_error="apply_failed")
                return "failed"
            plugin = locked[0].monitor_plugin
            stage = "read"
            try:
                binding = binding_for_plugin(plugin)
                variant = next((item for item in binding.get("variants") or [] if item.get("key") == variant_key), None)
                if variant is None:
                    _set_rows(locked, vault_sync_error="apply_failed")
                    return "failed"
                stage = "versions"
                versions = _versions_for([credential_id])
                remote_version = versions.get(credential_id)
                if remote_version is None:
                    stage = "purge"
                    if _already_cleared_not_found(locked, binding):
                        return "skipped"
                    purge_managed_secrets(locked, binding, locked, node_mgmt=local_node_mgmt())
                    _set_rows(locked, vault_sync_error="not_found")
                    return "success"
                applied = min(int(row.vault_applied_version or 0) for row in locked)
                if int(remote_version) <= applied:
                    return "skipped"
            except Exception as exc:
                raise _ApplyWriteError(stage, exc) from exc
            try:
                resolved = resolve_for_actor(
                    actor,
                    credential_id,
                    variant,
                    form_values=_snmp_form_values(variant),
                )
            except VaultCredentialError as exc:
                try:
                    return _persist_resolve_failure(locked, binding, exc.code, remote_version)
                except Exception as purge_exc:
                    raise _ApplyWriteError("purge", purge_exc) from purge_exc
            try:
                _apply_resolved_values(locked, binding, variant, resolved)
            except Exception as exc:
                raise _ApplyWriteError("write", exc) from exc
            _set_rows(
                locked,
                vault_applied_version=int(resolved.version),
                vault_credential_name=resolved.name or "",
                vault_sync_error="",
                vault_synced_at=timezone.now(),
            )
            return "success"
    except _ApplyWriteError as exc:
        _persist_apply_failed(credential_id, instance_id, monitor_plugin_id)
        logger.error(
            "event=vault_credential_apply_failed credential_id=%s instance_id=%s failed_stage=%s error_type=%s",
            credential_id,
            instance_id,
            exc.stage,
            type(exc.original).__name__,
            exc_info=(type(exc.original), exc.original, exc.original.__traceback__),
        )
        return "failed"


def _read_config_payload(ids, actor_context=None):
    """Raw env plus the edit-page content projection. Server-side only."""
    del actor_context
    rows = list(CollectConfig.objects.filter(id__in=list(ids or [])).select_related("monitor_plugin"))
    payload = _load_node_maps(rows, project=True)
    return {
        "configs": rows,
        "env": payload["env"],
        "content": payload["content"],
        "serialized": payload["serialized"],
        "file_type": payload["file_type"],
    }


def prepare_child_content_for_write(config_obj, content, env_config):
    from apps.monitor.services.website_config import validate_rendered_website_config
    from apps.monitor.utils.config_format import ConfigFormat

    content = content if isinstance(content, dict) else {}
    env_config = dict(env_config or {})
    if config_obj.collect_type == "web":
        try:
            validate_rendered_website_config(content, env_config)
        except ValueError as exc:
            raise BaseAppException(str(exc)) from exc
    from apps.monitor.utils.snmp_ifmib_capability import is_interface_filter_capable_plugin

    ifmib_capable = (config_obj.collect_type or "").startswith("snmp") and is_interface_filter_capable_plugin(
        getattr(config_obj, "monitor_plugin", None)
    )
    if ifmib_capable:
        from apps.monitor.utils.snmp_interface_filters import normalize_snmp_interface_filter_config
        from apps.monitor.utils.snmp_interface_template import has_interface_collection

        if has_interface_collection(ConfigFormat.json_to_toml(content)):
            content = normalize_snmp_interface_filter_config(content)
    if (config_obj.config_type or "").lower() == "kafka":
        from apps.monitor.utils.kafka_collect_timeouts import assert_kafka_group_metrics_timeout_lt_interval, extract_group_metrics_timeout_from_env
        from apps.monitor.utils.kafka_sasl import ensure_kafka_sasl_mechanism_in_env

        ensure_kafka_sasl_mechanism_in_env(env_config)
        child_interval = (content.get("config") or {}).get("interval") if isinstance(content, dict) else None
        assert_kafka_group_metrics_timeout_lt_interval(
            extract_group_metrics_timeout_from_env(env_config),
            child_interval,
        )
    from apps.monitor.utils.disk_fstype_filters import sync_disk_fstype_filters_on_writeback

    content = sync_disk_fstype_filters_on_writeback(content)
    if str(config_obj.collect_type or "").casefold() == "script":
        from apps.monitor.services.custom_script_plugin import prepare_script_child_content_for_save

        content = prepare_script_child_content_for_save(content or {})
    rendered = ConfigFormat.json_to_toml(content)
    if ifmib_capable:
        from apps.monitor.utils.snmp_interface_template import (
            isolate_snmp_interface_tagpass,
            preserve_closed_ifmib_markers,
            restore_managed_ifmib_markers,
        )

        rendered = isolate_snmp_interface_tagpass(rendered, force=True)
        rendered = restore_managed_ifmib_markers(rendered)
        rendered = preserve_closed_ifmib_markers(rendered, content)
    return rendered, env_config


def prepare_base_content_for_write(config_obj, content, env_config):
    from apps.monitor.utils.config_format import ConfigFormat

    env_config = dict(env_config or {})
    if (config_obj.config_type or "").lower() == "kafka":
        from apps.monitor.utils.kafka_sasl import ensure_kafka_sasl_mechanism_in_env

        ensure_kafka_sasl_mechanism_in_env(env_config)
    rendered = ConfigFormat.json_to_yaml(content or {})
    return rendered, env_config


def write_config_group(configs, writes, node_mgmt, *, replace_env=False):
    rendered = writes.get("rendered") or {}
    envs = writes.get("env") or {}
    for row in configs or []:
        config_id = str(row.id)
        if config_id not in rendered and config_id not in envs:
            continue
        content = rendered.get(config_id)
        env_config = envs.get(config_id)
        if row.is_child:
            node_mgmt.update_child_config_content(row.id, content, env_config, replace_env=replace_env)
        else:
            node_mgmt.update_config_content(row.id, content, env_config, replace_env=replace_env)


def prepare_onboarding_credential(data, plugin, actor_context):
    configs = data.get("configs") if isinstance(data, dict) else None
    if not isinstance(configs, list):
        return {"source": "inline"}
    extracted = [_pop_credential_input(item) for item in configs if isinstance(item, dict)]
    if not extracted:
        return {"source": "inline"}
    if any(item != extracted[0] for item in extracted[1:]):
        raise ValidationAppException()
    source, credential_id, variant_key = extracted[0]
    if source != "vault":
        return {"source": "inline", "plugin": plugin}
    if plugin is None or not credential_id or not variant_key:
        raise ValidationAppException()
    binding = binding_for_plugin(plugin)
    submitted = configs[0] if configs else {}
    variant = _select_onboarding_variant(binding, submitted, variant_key)
    managed = set(managed_field_names(binding))
    for item in configs:
        if not isinstance(item, dict):
            continue
        for name in managed:
            item.pop(name, None)
    for instance in data.get("instances") or []:
        if isinstance(instance, dict) and any(name in instance for name in managed):
            raise VaultCredentialError("managed_key_in_instances")
    try:
        resolved = resolve_for_actor(stored_actor(actor_context), credential_id, variant, form_values=submitted)
    except VaultCredentialError:
        raise
    created = to_create_fields(resolved, variant, binding)
    for item in configs:
        if isinstance(item, dict):
            item.update(created)
    return {
        "source": "vault",
        "plugin": plugin,
        "binding": binding,
        "variant": variant,
        "resolved": resolved,
        "actor": stored_actor(actor_context),
    }


def purge_reused_vault_rows(instance_ids, plugin, plan):
    if (plan or {}).get("source") == "vault" or plugin is None:
        return
    rows = list(
        CollectConfig.objects.filter(
            monitor_instance_id__in=list(instance_ids or []),
            monitor_plugin_id=plugin.id,
        )
        .exclude(vault_credential_id="")
        .order_by("id")
    )
    if not rows:
        return
    binding = binding_for_plugin(plugin)
    grouped = {}
    for row in rows:
        grouped.setdefault(row.monitor_instance_id, []).append(row)
    node_mgmt = local_node_mgmt()
    for instance_id in grouped:
        locked = lock_config_group(instance_id, plugin.id)
        vault_rows = [row for row in locked or [] if row.vault_credential_id]
        if not vault_rows:
            continue
        purge_managed_secrets(vault_rows, binding, locked, node_mgmt=node_mgmt)
        clear_vault_binding(vault_rows)


def finalize_onboarding_credential(instance_ids, plugin_id, plan, actor_context):
    if not plugin_id:
        return
    rows = list(
        CollectConfig.objects.filter(
            monitor_instance_id__in=list(instance_ids or []),
            monitor_plugin_id=plugin_id,
        ).order_by("id")
    )
    grouped = {}
    for row in rows:
        grouped.setdefault(row.monitor_instance_id, []).append(row)
    if (plan or {}).get("source") == "vault":
        resolved = plan["resolved"]
        for group in grouped.values():
            stamp_vault_binding(
                group,
                credential_id=resolved.credential_id,
                variant=plan["variant"],
                actor_context=actor_context,
                name=resolved.name,
                applied_version=resolved.version,
                sync_error="",
            )
        return
    for group in grouped.values():
        bound = [row for row in group if row.vault_credential_id]
        if bound:
            clear_vault_binding(bound)


def update_instance_collect_config(child_info, base_info, credential, actor_context):
    from apps.monitor.services.node_mgmt import InstanceConfigService

    if credential is not None and not isinstance(credential, dict):
        raise ValidationAppException()
    child_info = _drop_client_vault_keys(child_info)
    base_info = _drop_client_vault_keys(base_info)
    config_ids = []
    if base_info and base_info.get("id"):
        config_ids.append(base_info["id"])
    if child_info and child_info.get("id"):
        config_ids.append(child_info["id"])
    config_objs = InstanceConfigService._get_authorized_collect_configs(
        config_ids,
        actor_context,
        require_operate=True,
    )
    config_map = {config.id: config for config in config_objs}
    if base_info and child_info:
        base_config = config_map.get(base_info["id"])
        child_config = config_map.get(child_info["id"])
        if base_config and child_config and base_config.monitor_instance_id != child_config.monitor_instance_id:
            raise BaseAppException("基础配置与子配置不属于同一监控实例")
    anchor = next((config_map[item] for item in config_ids if item in config_map), None)
    if anchor is None:
        return InstanceConfigService.update_instance_config(child_info, base_info, actor_context)
    group = list(
        CollectConfig.objects.filter(
            monitor_instance_id=anchor.monitor_instance_id,
            monitor_plugin_id=anchor.monitor_plugin_id,
        )
    )
    stored_id = next((row.vault_credential_id for row in group if row.vault_credential_id), "")
    source = str((credential or {}).get("source") or "")
    if stored_id and not credential:
        raise VaultCredentialError("credential_required")
    if not ((stored_id and credential) or source == "vault"):
        return InstanceConfigService.update_instance_config(child_info, base_info, actor_context)
    with transaction.atomic():
        locked = lock_config_group(anchor.monitor_instance_id, anchor.monitor_plugin_id)
        return _write_unified_edit(locked or [], child_info, base_info, credential or {}, actor_context)


def public_config_content(config_objs, projected, actor_context):
    vault_rows = [row for row in config_objs if row.vault_credential_id]
    result = {}
    if not vault_rows:
        return result
    binding = binding_for_plugin(vault_rows[0].monitor_plugin)
    targets = managed_storage_targets(binding, config_objs)
    envs, contents = strip_managed_values(projected["env"], projected["content"], [item for item in targets if item.get("kind") == "env"])
    for row in config_objs:
        content = _mask_vault_content(contents.get(str(row.id)) or projected["content"].get(str(row.id)), is_base=not row.is_child)
        env = envs.get(str(row.id)) or {}
        entry = {"id": row.id, "content": content, "env_config": env}
        if row.is_child:
            result["child"] = entry
        else:
            result["base"] = entry
    sample = vault_rows[0]
    described = _describe_public(actor_context, sample, binding)
    usable = described.get("usable") is True
    result["credential"] = {
        "source": "vault",
        "vault_credential_id": sample.vault_credential_id,
        "variant": sample.vault_variant,
        "name": described.get("name") if usable else sample.vault_credential_name,
        "usable": usable,
        "sync_error": sample.vault_sync_error or "",
        "synced_at": sample.vault_synced_at.isoformat() if sample.vault_synced_at else None,
    }
    return result


def inline_credential_payload():
    return {
        "source": "inline",
        "vault_credential_id": "",
        "variant": "",
        "name": "",
        "usable": True,
        "sync_error": "",
        "synced_at": None,
    }


def retain_managed_content(config_id, original, updated, *, only_missing=False):
    row = CollectConfig.objects.filter(id=config_id).select_related("monitor_plugin").first()
    if row is None or not row.vault_credential_id:
        return updated
    binding = binding_for_plugin(row.monitor_plugin)
    targets = [
        target
        for target in managed_storage_targets(binding, [row])
        if str(target.get("config_id")) == str(row.id) and target.get("kind") in {"content", "dsn"}
    ]
    for target in targets:
        path = target.get("path")
        if not path:
            continue
        old = get_path(original, path)
        new = get_path(updated, path)
        if target.get("kind") == "dsn":
            if not isinstance(old, str) or not isinstance(new, str):
                continue
            from .mapper import _extract_capture, _replace_capture

            old_user = _extract_capture(target.get("regex"), old)
            if only_missing and new not in (None, "", _REDACTED):
                continue
            set_path(updated, path, _replace_capture(target.get("regex"), new, old_user))
            continue
        if only_missing and new not in (None, "", _REDACTED):
            continue
        set_path(updated, path, old)
    return updated


def retain_managed_env(config_id, original_env, updated_env):
    row = CollectConfig.objects.filter(id=config_id).select_related("monitor_plugin").first()
    if row is None or not row.vault_credential_id:
        return updated_env
    binding = binding_for_plugin(row.monitor_plugin)
    keys = [
        target.get("env_key")
        for target in managed_storage_targets(binding, [row])
        if target.get("kind") == "env" and str(target.get("config_id")) == str(row.id)
    ]
    result = dict(updated_env or {})
    original_env = original_env or {}
    for key in keys:
        if not key:
            continue
        if key not in result or result.get(key) in (None, "", _REDACTED):
            if key in original_env:
                result[key] = original_env[key]
    return result


def _write_unified_edit(locked, child_info, base_info, credential, actor_context):
    from apps.monitor.services.collect_config_update import CollectConfigUpdateService

    by_id = {row.id: row for row in locked}
    submitted = {}
    if child_info and child_info.get("id") in by_id:
        submitted[child_info["id"]] = child_info
    if base_info and base_info.get("id") in by_id:
        submitted[base_info["id"]] = base_info
    if not submitted:
        raise VaultCredentialError("credential_required")
    plugin = next(iter(by_id.values())).monitor_plugin
    binding = binding_for_plugin(plugin)
    raw = _read_config_payload(list(by_id))
    submitted_values = _submitted_form_values(binding, submitted, by_id)
    source = str(credential.get("source") or "")
    stored_id = next((row.vault_credential_id for row in locked if row.vault_credential_id), "")
    requested_id = str(credential.get("vault_credential_id") or "")
    clear_only = False
    reuse_name = ""
    if source == "inline":
        variant = _select_edit_variant(
            binding,
            submitted_values,
            credential.get("variant") or next(iter(by_id.values())).vault_variant,
            allow_unmatched=True,
        )
        if variant is None:
            clear_only = True
            values = {}
            resolved = None
            reuse = False
        else:
            _require_inline_fields(variant, credential.get("inline_fields") or {})
            values = dict(credential.get("inline_fields") or {})
            resolved = None
            reuse = False
    else:
        if not requested_id:
            raise ValidationAppException()
        variant = _select_edit_variant(binding, submitted_values, credential.get("variant"))
        if stored_id and requested_id == stored_id:
            values, resolved, reuse, reuse_name = _values_for_same_credential(locked, binding, variant, requested_id, actor_context, raw)
        else:
            resolved = resolve_for_actor(stored_actor(actor_context), requested_id, variant, form_values=submitted_values)
            values = None
            reuse = False
    env_by_config = {}
    content_by_config = {}
    for config_id, info in submitted.items():
        row = by_id[config_id]
        env_by_config[str(config_id)] = dict(info.get("env_config") or raw["env"].get(str(config_id)) or {})
        content_by_config[str(config_id)] = (
            info.get("content") if isinstance(info.get("content"), dict) else dict(raw["content"].get(str(config_id)) or {})
        )
        if not row.is_child and isinstance(content_by_config[str(config_id)], dict):
            pass
    targets = [target for target in managed_storage_targets(binding, locked) if str(target.get("config_id")) in env_by_config]
    env_by_config, content_by_config = strip_managed_values(env_by_config, content_by_config, targets)
    if clear_only:
        writes = []
    elif reuse:
        writes = stored_writes_for_variant(variant, raw["env"], raw["content"], locked)
    elif source == "inline":
        writes = to_storage_writes(None, variant, binding, locked, encode=True, inline_values=values)
    else:
        writes = to_storage_writes(resolved, variant, binding, locked, encode=True)
    writes = [item for item in writes if str(item.get("config_id")) in env_by_config]
    env_by_config, content_by_config = apply_storage_writes(env_by_config, content_by_config, writes)
    rendered = {}
    final_env = {}
    for config_id, row in ((item_id, by_id[item_id]) for item_id in submitted):
        content = content_by_config.get(str(config_id)) or {}
        env_config = env_by_config.get(str(config_id)) or {}
        if row.is_child:
            text, env_config = prepare_child_content_for_write(row, content, env_config)
        else:
            text, env_config = prepare_base_content_for_write(row, content, env_config)
        rendered[str(config_id)] = text
        final_env[str(config_id)] = env_config
    write_config_group(list(by_id.values()), {"rendered": rendered, "env": final_env}, local_node_mgmt(), replace_env=True)
    for config_id, text in rendered.items():
        CollectConfigUpdateService.mark_hand_edited(by_id[config_id], text)
    if source == "inline" or clear_only:
        clear_vault_binding(locked)
        return
    name = resolved.name if resolved is not None else reuse_name
    stamp_vault_binding(
        locked,
        credential_id=requested_id,
        variant=variant,
        actor_context=actor_context,
        name=name,
        applied_version=None if reuse else resolved.version,
        sync_error="",
    )


def _values_for_same_credential(locked, binding, variant, credential_id, actor_context, raw):
    del binding, raw
    sync_error = next((row.vault_sync_error for row in locked if row.vault_sync_error), "")
    described = describe_for_actor(stored_actor(actor_context), credential_id, variant)
    # 默认 0 表示尚未成功下发。secret_version 从 1 起，与 0 不相等就要解析，0 不是哨兵。
    applied = min(int(row.vault_applied_version or 0) for row in locked)
    if sync_error in CLEARED_SYNC_ERRORS or int(described.version or 0) != applied:
        resolved = resolve_for_actor(
            stored_actor(actor_context),
            credential_id,
            variant,
            form_values=_snmp_form_values(variant),
        )
        return None, resolved, False, resolved.name or ""
    return None, None, True, described.name or ""


def _select_onboarding_variant(binding, submitted, variant_key):
    chosen = _select_edit_variant(binding, submitted, variant_key)
    if chosen is None or chosen.get("key") != variant_key:
        raise ValidationAppException()
    return chosen


def _select_edit_variant(binding, submitted, requested_key, *, allow_unmatched=False):
    variants = list((binding or {}).get("variants") or [])
    fields = (binding or {}).get("_fields") or {}
    discriminant = False
    for variant in variants:
        field_name = (variant.get("when") or {}).get("field")
        origin = (fields.get(field_name) or {}).get("origin_path")
        if field_name and origin:
            discriminant = True
            break
    if discriminant:
        chosen = select_variant(binding, submitted, requested_key)
    elif requested_key:
        chosen = next((variant for variant in variants if variant.get("key") == requested_key), None)
    else:
        chosen = select_variant(binding, submitted, requested_key)
    if chosen is None or (requested_key not in (None, "") and chosen.get("key") != requested_key):
        if allow_unmatched:
            return None
        raise ValidationAppException()
    return chosen


def _require_inline_fields(variant, inline_fields):
    inline_fields = inline_fields or {}
    for target in (variant or {}).get("_targets") or []:
        if not _inline_target_required(variant, target, inline_fields):
            continue
        if inline_fields.get(target.get("field")) in (None, ""):
            raise VaultCredentialError("inline_secret_required")


def _inline_target_required(variant, target, inline_fields):
    profile = (variant or {}).get("_profile")
    field = str(target.get("field") or "")
    if profile == "ssh":
        auth = str(inline_fields.get("auth_type") or "password")
        if field == "ENV_PASSWORD":
            return auth == "password"
        if field == "private_key_content":
            return auth == "private_key"
        if field == "private_key_passphrase":
            return False
        return bool(target.get("required"))
    if profile == "snmp_v3":
        level = str(inline_fields.get("sec_level") or "")
        if field in {"ENV_AUTH_PASSWORD", "auth_password"}:
            return level in {"authNoPriv", "authPriv"}
        if field in {"ENV_PRIV_PASSWORD", "priv_password"}:
            return level == "authPriv"
        return bool(target.get("required"))
    return bool(target.get("required"))


def _submitted_form_values(binding, submitted, by_id):
    values = {}
    fields = (binding or {}).get("_fields") or {}
    for name in fields:
        for config_id, info in submitted.items():
            row = by_id[config_id]
            content = info.get("content") if isinstance(info.get("content"), dict) else {}
            if name in content:
                values[name] = content[name]
            config = content.get("config") if isinstance(content.get("config"), dict) else {}
            if name in config:
                values[name] = config[name]
            if isinstance(info, dict) and name in info:
                values[name] = info[name]
            if row is not None:
                continue
    return values


def _pop_credential_input(config):
    source = str(config.pop("credential_source", "") or "")
    credential_id = str(config.pop("vault_credential_id", "") or "")
    variant = str(config.pop("vault_variant", "") or "")
    return source, credential_id, variant


def _drop_client_vault_keys(info):
    if not isinstance(info, dict):
        return info
    for key in _CLIENT_VAULT_KEYS:
        info.pop(key, None)
    return info


def _shared_actor(rows):
    actors = []
    for row in rows:
        actor = row.vault_actor_context or {}
        if not actor.get("username") and not actor.get("domain") and actor.get("current_team") in (None, ""):
            continue
        normalized = stored_actor(actor)
        token = (normalized.get("username"), normalized.get("domain"), normalized.get("current_team"))
        if token not in actors:
            actors.append(token)
    if not actors:
        return None
    if len(actors) > 1:
        return None
    username, domain, team = actors[0]
    return {"username": username, "domain": domain, "current_team": team}


def _shared_variant(rows):
    keys = {row.vault_variant for row in rows}
    if len(keys) != 1:
        return ""
    return next(iter(keys)) or ""


def _versions_for(credential_ids):
    payload = SystemMgmt().get_credential_versions(list(credential_ids))
    if not isinstance(payload, dict) or payload.get("result") is False:
        raise VaultCredentialError("apply_failed")
    versions = (payload.get("data") or {}).get("versions")
    if not isinstance(versions, dict):
        raise VaultCredentialError("apply_failed")
    return versions


def _already_cleared_not_found(rows, binding):
    if not rows or any(row.vault_sync_error != "not_found" for row in rows):
        return False
    return not _group_has_managed_secrets(rows, binding)


def _group_has_managed_secrets(rows, binding):
    raw = _load_node_maps(rows, project=False)
    targets = managed_storage_targets(binding, rows)
    for target in targets:
        config_id = str(target.get("config_id") or "")
        if target.get("kind") == "dsn":
            continue
        if target.get("kind") == "env":
            value = (raw["env"].get(config_id) or {}).get(target.get("env_key"))
            if value not in (None, ""):
                return True
            continue
        value = get_path(raw["content"].get(config_id), target.get("path"))
        if value not in (None, ""):
            return True
    return False


def _persist_resolve_failure(rows, binding, code, remote_version):
    if code in {"forbidden", "disabled"}:
        purge_managed_secrets(rows, binding, rows, node_mgmt=local_node_mgmt())
        _set_rows(rows, vault_sync_error=code, vault_applied_version=int(remote_version))
        return "success"
    if code in {"type_mismatch", "incomplete"}:
        stored = code
    else:
        stored = "apply_failed"
    _set_rows(rows, vault_sync_error=stored)
    return "failed"


def _persist_apply_failed(credential_id, instance_id, monitor_plugin_id):
    with transaction.atomic():
        locked = lock_config_group(instance_id, monitor_plugin_id)
        if not locked or any(row.vault_credential_id != credential_id for row in locked):
            return
        _set_rows(locked, vault_sync_error="apply_failed")


def _apply_resolved_values(rows, binding, variant, resolved):
    from apps.monitor.services.collect_config_update import is_config_hand_edited, sha256_text

    raw = _read_config_payload([row.id for row in rows])
    writes = to_storage_writes(resolved, variant, binding, rows, encode=True)
    envs, contents = apply_storage_writes(raw["env"], raw["content"], writes)
    node_mgmt = local_node_mgmt()
    for row in rows:
        config_id = str(row.id)
        original = raw["serialized"].get(config_id) or ""
        new_content = contents.get(config_id)
        content_changed = new_content != raw["content"].get(config_id)
        env_config = envs.get(config_id) or {}
        if content_changed:
            was_hand_edited = is_config_hand_edited(row, original)
            if row.is_child:
                rendered, env_config = prepare_child_content_for_write(row, new_content or {}, env_config)
            else:
                rendered, env_config = prepare_base_content_for_write(row, new_content or {}, env_config)
            if row.is_child:
                node_mgmt.update_child_config_content(row.id, rendered, env_config, replace_env=True)
            else:
                node_mgmt.update_config_content(row.id, rendered, env_config, replace_env=True)
            if not was_hand_edited:
                row.applied_rendered_sha256 = sha256_text(rendered)
                row.save(update_fields=["applied_rendered_sha256", "updated_at"])
            continue
        if row.is_child:
            node_mgmt.update_child_config_content(row.id, original, env_config, replace_env=True)
        else:
            node_mgmt.update_config_content(row.id, original, env_config, replace_env=True)


def _set_rows(rows, **updates):
    fields = list(updates.keys()) + ["updated_at"]
    for row in rows:
        for key, value in updates.items():
            setattr(row, key, value)
        row.save(update_fields=fields)


def _snmp_form_values(variant):
    if not (variant or {}).get("snmp_version_field"):
        return {}
    try:
        return {"version": int(variant.get("key"))}
    except (TypeError, ValueError):
        return {"version": variant.get("key")}


def _load_node_maps(configs, *, project):
    node_mgmt = NodeMgmt()
    envs = {}
    contents = {}
    serialized = {}
    file_types = {}
    for row in configs or []:
        config_id = str(row.id)
        file_types[config_id] = row.file_type
        if row.is_child:
            loaded = node_mgmt.get_child_configs_by_ids([row.id])
            item = loaded[0] if loaded else {}
            raw = item.get("content") or ""
            key = "content"
        else:
            loaded = node_mgmt.get_configs_by_ids([row.id])
            item = loaded[0] if loaded else {}
            raw = item.get("config_template") or ""
            key = "config_template"
        envs[config_id] = dict(item.get("env_config") or {})
        serialized[config_id] = raw
        if not raw:
            contents[config_id] = {}
            continue
        contents[config_id] = _project_content(row, raw) if project else _parse_content(row, raw)
        del key
    return {"env": envs, "content": contents, "serialized": serialized, "file_type": file_types}


def _parse_content(row, raw):
    from apps.monitor.utils.config_format import ConfigFormat

    if row.file_type == "toml":
        return ConfigFormat.toml_to_dict(raw)
    if row.file_type == "yaml":
        return ConfigFormat.yaml_to_dict(raw)
    raise BaseAppException("file_type must be toml or yaml")


def _project_content(row, raw):
    from apps.monitor.utils.config_format import ConfigFormat

    if row.file_type == "toml":
        content = ConfigFormat.toml_to_dict(raw)
        from apps.monitor.utils.disk_fstype_filters import expose_disk_fstype_filters_for_edit
        from apps.monitor.utils.snmp_ifmib_capability import is_interface_filter_capable_plugin

        content = expose_disk_fstype_filters_for_edit(content)
        if (row.collect_type or "").startswith("snmp") and is_interface_filter_capable_plugin(getattr(row, "monitor_plugin", None)):
            from apps.monitor.utils.snmp_interface_filters import expose_snmp_interface_filters_for_edit
            from apps.monitor.utils.snmp_interface_template import mark_closed_ifmib_edit_state

            content = mark_closed_ifmib_edit_state(raw, content)
            content = expose_snmp_interface_filters_for_edit(content)
        return content
    if row.file_type == "yaml":
        return ConfigFormat.yaml_to_dict(raw)
    raise BaseAppException("file_type must be toml or yaml")


def _write_node_maps(configs, envs, contents, serialized, node_mgmt, *, file_types):
    from apps.monitor.utils.config_format import ConfigFormat

    for row in configs or []:
        config_id = str(row.id)
        content = contents.get(config_id)
        file_type = file_types.get(config_id) or row.file_type
        if file_type == "toml":
            rendered = ConfigFormat.json_to_toml(content or {})
        elif file_type == "yaml":
            rendered = ConfigFormat.json_to_yaml(content or {})
        else:
            rendered = serialized.get(config_id) or ""
        env_config = envs.get(config_id) or {}
        if row.is_child:
            node_mgmt.update_child_config_content(row.id, rendered, env_config, replace_env=True)
        else:
            node_mgmt.update_config_content(row.id, rendered, env_config, replace_env=True)


def _mask_vault_content(content, *, is_base):
    if isinstance(content, dict):
        masked = {}
        for key, item in content.items():
            if str(key).lower() in _CONTENT_MASK_KEYS and item not in (None, ""):
                masked[key] = _REDACTED
            elif is_base and str(key).lower() == "password" and item not in (None, ""):
                masked[key] = _REDACTED
            else:
                masked[key] = _mask_vault_content(item, is_base=is_base)
        return masked
    if isinstance(content, list):
        return [_mask_vault_content(item, is_base=is_base) for item in content]
    return content


def _describe_public(actor_context, row, binding):
    variant = next((item for item in (binding.get("variants") or []) if item.get("key") == row.vault_variant), None)
    if variant is None:
        return {"usable": False}
    try:
        described = describe_for_actor(stored_actor(actor_context), row.vault_credential_id, variant)
    except VaultCredentialError:
        return {"usable": False}
    if described.disabled:
        return {"usable": False, "name": described.name}
    return {"usable": True, "name": described.name}
