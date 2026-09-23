"""采集配置相对插件内容指纹的需更新判定与一键重渲染。

需更新是实例×插件的正交标志，不进入上报正常/失联，也不表示节点二进制可升级。
一键更新只覆盖未手改配置：服务端按新模板重渲染，失败回滚该条。
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from urllib.parse import urlparse

from django.db.models import F, Q

from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.core.logger import monitor_logger as logger
from apps.monitor.models import CollectConfig, MonitorPlugin, MonitorPluginConfigTemplate
from apps.monitor.utils.config_format import ConfigFormat
from apps.rpc.node_mgmt import NodeMgmt

_MAX_UPDATE_INSTANCES = 200


class HandEditedCollectConfigError(Exception):
    """采集配置已手改（含内容漂移），禁止一键覆盖。"""


def sha256_text(value) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def plugin_content_fingerprint(plugin) -> str:
    """当前插件内容指纹。空 pack_version 不是版本；空指纹不视为需更新。"""
    if plugin is None:
        return ""
    return (getattr(plugin, "pack_content_sha256", None) or "").strip()


def is_config_stale(config, plugin=None) -> bool:
    plugin = plugin or getattr(config, "monitor_plugin", None)
    current = plugin_content_fingerprint(plugin)
    if not current:
        return False
    return (getattr(config, "applied_content_sha256", None) or "") != current


def is_config_hand_edited(config, current_content: str | None = None) -> bool:
    if getattr(config, "content_hand_edited", False):
        return True
    applied = (getattr(config, "applied_rendered_sha256", None) or "").strip()
    if not applied or current_content is None:
        return False
    return sha256_text(current_content) != applied


def stamp_applied(
    config,
    *,
    plugin_fp: str,
    rendered_content: str,
    hand_edited: bool = False,
    pack_version: str | None = None,
):
    config.applied_content_sha256 = plugin_fp or ""
    config.applied_rendered_sha256 = sha256_text(rendered_content)
    config.content_hand_edited = bool(hand_edited)
    if pack_version is None:
        plugin = getattr(config, "monitor_plugin", None)
        pack_version = getattr(plugin, "pack_version", None) if plugin is not None else None
    if pack_version is not None:
        config.applied_pack_version = pack_version or ""


def _truthy(value) -> bool:
    return value in (True, 1, "1", "true", "True", "yes")


def _unwrap_env_config(env_config, config_id: str) -> dict:
    if not isinstance(env_config, dict):
        return {}
    suffix = f"__{(config_id or '').upper()}"
    result = {}
    for raw_key, value in env_config.items():
        key = str(raw_key)
        if suffix and key.upper().endswith(suffix):
            key = key[: -len(suffix)]
        result[key] = value
        result[f"ENV_{key}"] = value
    return result


def _normalize_duration(value):
    if isinstance(value, str) and value.endswith("s") and value[:-1].replace(".", "", 1).isdigit():
        return value[:-1]
    return value


def _parse_agent_ip_port(agent) -> tuple[str | None, int | None]:
    if not agent:
        return None, None
    parsed = urlparse(str(agent))
    return parsed.hostname, parsed.port


def _flatten_parsed_content(parsed) -> dict:
    if not isinstance(parsed, dict):
        return {}
    context = {}
    config = parsed.get("config") if isinstance(parsed.get("config"), dict) else {}
    context.update(config)
    tags = config.get("tags") if isinstance(config.get("tags"), dict) else parsed.get("tags")
    if isinstance(tags, dict):
        for key in ("instance_id", "instance_type"):
            if tags.get(key) not in (None, "") and not context.get(key):
                context[key] = tags[key]
    agents = config.get("agents") or parsed.get("agents") or []
    if isinstance(agents, list) and agents:
        ip, port = _parse_agent_ip_port(agents[0])
        if ip and not context.get("ip"):
            context["ip"] = ip
        if port and not context.get("port"):
            context["port"] = port
    for key in ("interval", "timeout"):
        if key in context:
            context[key] = _normalize_duration(context[key])
    return context


class CollectConfigUpdateService:
    @staticmethod
    def stale_config_qs(plugin: MonitorPlugin):
        current = plugin_content_fingerprint(plugin)
        if not current:
            return CollectConfig.objects.none()
        return CollectConfig.objects.filter(monitor_plugin=plugin).exclude(applied_content_sha256=current)

    @staticmethod
    def authorized_instance_ids(plugin: MonitorPlugin, actor_context, require_operate=False) -> set[str]:
        from apps.monitor.services.node_mgmt import InstanceConfigService

        if not actor_context:
            return set()
        object_ids = list(plugin.monitor_object.values_list("id", flat=True))
        if not object_ids:
            return set()
        ids: set[str] = set()
        for object_id in object_ids:
            ids.update(
                InstanceConfigService._get_authorized_monitor_instances(
                    actor_context,
                    object_id,
                    require_operate=require_operate,
                ).values_list("id", flat=True)
            )
        return ids

    @staticmethod
    def count_stale_instances(plugin: MonitorPlugin, actor_context) -> int:
        current = plugin_content_fingerprint(plugin)
        if not current:
            return 0
        authorized_ids = CollectConfigUpdateService.authorized_instance_ids(plugin, actor_context)
        if not authorized_ids:
            return 0
        return (
            CollectConfig.objects.filter(
                monitor_plugin=plugin,
                monitor_instance_id__in=authorized_ids,
            )
            .exclude(applied_content_sha256=current)
            .values("monitor_instance_id")
            .distinct()
            .count()
        )

    @staticmethod
    def count_stale_instances_for_plugins(plugins, actor_context) -> dict[int, int]:
        counts = {plugin.id: 0 for plugin in plugins or [] if getattr(plugin, "id", None) is not None}
        if not counts or not actor_context:
            return counts
        from apps.monitor.services.node_mgmt import InstanceConfigService

        plugin_fps: dict[int, str] = {}
        object_ids: set = set()
        for plugin in plugins or []:
            plugin_id = getattr(plugin, "id", None)
            if plugin_id is None:
                continue
            fingerprint = plugin_content_fingerprint(plugin)
            if not fingerprint:
                continue
            plugin_fps[plugin_id] = fingerprint
            object_ids.update(plugin.monitor_object.values_list("id", flat=True))
        if not plugin_fps:
            return counts

        authorized_ids: set[str] = set()
        for object_id in object_ids:
            try:
                authorized_ids.update(
                    InstanceConfigService._get_authorized_monitor_instances(
                        actor_context,
                        object_id,
                        require_operate=False,
                    ).values_list("id", flat=True)
                )
            except (UnauthorizedException, BaseAppException):
                logger.warning(
                    "event=collect_config_stale_count_skipped object_id=%s failed_stage=authorize error_type=auth_error",
                    object_id,
                )
            except Exception:
                logger.exception(
                    "event=collect_config_stale_count_failed object_id=%s failed_stage=authorize error_type=count_error",
                    object_id,
                )
        if not authorized_ids:
            return counts

        stale_q = Q()
        for plugin_id, fingerprint in plugin_fps.items():
            stale_q |= Q(monitor_plugin_id=plugin_id) & ~Q(applied_content_sha256=fingerprint)
        try:
            rows = (
                CollectConfig.objects.filter(stale_q, monitor_instance_id__in=authorized_ids)
                .values_list("monitor_plugin_id", "monitor_instance_id")
                .distinct()
            )
            grouped: dict[int, set] = defaultdict(set)
            for plugin_id, instance_id in rows:
                grouped[plugin_id].add(instance_id)
            for plugin_id in counts:
                counts[plugin_id] = len(grouped.get(plugin_id, ()))
        except Exception:
            logger.exception(
                "event=collect_config_stale_count_failed plugin_count=%s failed_stage=count error_type=count_error",
                len(plugin_fps),
            )
        return counts

    @staticmethod
    def annotate_plugin_stale_counts(plugins, results: list[dict], actor_context) -> None:
        try:
            counts = CollectConfigUpdateService.count_stale_instances_for_plugins(plugins, actor_context)
        except Exception:
            logger.exception(
                "event=collect_config_stale_count_failed plugin_count=%s failed_stage=annotate error_type=count_error",
                len(plugins or []),
            )
            counts = {}
        for result in results or []:
            plugin_id = result.get("id")
            result["stale_instance_count"] = int(counts.get(plugin_id, 0) or 0)

    @staticmethod
    def stale_summary(plugin: MonitorPlugin | None, actor_context, *, previous_fingerprint: str = "") -> dict:
        if plugin is None:
            return {
                "stale_instance_count": 0,
                "plugin_id": None,
                "monitor_object_id": None,
                "first_fingerprint": False,
            }
        from apps.monitor.services.collector_release_plugin import CollectorReleasePluginService

        current = plugin_content_fingerprint(plugin)
        previous = (previous_fingerprint or "").strip()
        first_fingerprint = bool(current) and not previous
        try:
            count = CollectConfigUpdateService.count_stale_instances(plugin, actor_context)
        except (UnauthorizedException, BaseAppException):
            logger.warning(
                "event=collect_config_stale_count_skipped plugin_id=%s failed_stage=authorize error_type=auth_error",
                plugin.id,
            )
            count = 0
        except Exception:
            logger.exception(
                "event=collect_config_stale_count_failed plugin_id=%s failed_stage=count error_type=count_error",
                plugin.id,
            )
            count = 0
        return {
            "stale_instance_count": count,
            "plugin_id": plugin.id,
            "monitor_object_id": CollectorReleasePluginService.resolve_entry_monitor_object_id(
                plugin_name=plugin.name,
                collector=plugin.collector,
            ),
            "first_fingerprint": first_fingerprint,
        }

    @staticmethod
    def filter_instance_qs(qs, query_data):
        if not _truthy((query_data or {}).get("need_update")):
            return qs
        plugin_id = (query_data or {}).get("monitor_plugin_id")
        configs = CollectConfig.objects.filter(
            monitor_plugin__isnull=False,
            monitor_plugin__pack_content_sha256__gt="",
        ).exclude(applied_content_sha256=F("monitor_plugin__pack_content_sha256"))
        if plugin_id not in (None, ""):
            configs = configs.filter(monitor_plugin_id=plugin_id)
        return qs.filter(id__in=configs.values("monitor_instance_id"))

    @staticmethod
    def annotate_instance_plugins(results: list[dict]) -> None:
        if not results:
            return
        instance_ids = [item.get("instance_id") for item in results if item.get("instance_id")]
        configs = list(
            CollectConfig.objects.filter(
                monitor_instance_id__in=instance_ids,
                monitor_plugin__isnull=False,
            ).select_related("monitor_plugin")
        )
        stale_by_instance_plugin: dict[tuple, dict] = {}
        applied_version_by_instance_plugin: dict[tuple, set[str]] = {}
        for config in configs:
            plugin = config.monitor_plugin
            key = (config.monitor_instance_id, plugin.id)
            applied_version = (getattr(config, "applied_pack_version", None) or "").strip()
            if applied_version:
                applied_version_by_instance_plugin.setdefault(key, set()).add(applied_version)
            elif not is_config_stale(config, plugin):
                # 已对齐但未落版本号：可安全回退到当前插件包版本
                current_version = (getattr(plugin, "pack_version", None) or "").strip()
                if current_version:
                    applied_version_by_instance_plugin.setdefault(key, set()).add(current_version)
            if not is_config_stale(config, plugin):
                continue
            bucket = stale_by_instance_plugin.setdefault(key, {"need_update": True, "unedited": False, "edited": False})
            if is_config_hand_edited(config):
                bucket["edited"] = True
            else:
                bucket["unedited"] = True

        for item in results:
            instance_id = item.get("instance_id")
            instance_need_update = False
            instance_can_update = False
            for plugin_info in item.get("plugins") or []:
                plugin_id = plugin_info.get("plugin_id")
                key = (instance_id, plugin_id)
                bucket = stale_by_instance_plugin.get(key)
                need_update = bool(bucket)
                can_update = bool(bucket and bucket["unedited"])
                hand_edited = bool(bucket and bucket["edited"] and not bucket["unedited"])
                applied_versions = sorted(applied_version_by_instance_plugin.get(key) or [])
                plugin_info["need_update"] = need_update
                plugin_info["hand_edited"] = hand_edited
                plugin_info["can_update"] = can_update
                plugin_info["applied_pack_version"] = " / ".join(applied_versions)
                plugin_info["latest_pack_version"] = plugin_info.get("pack_version") or ""
                instance_need_update = instance_need_update or need_update
                instance_can_update = instance_can_update or can_update
            item["need_update"] = instance_need_update
            item["can_update"] = instance_can_update

    @staticmethod
    def _resolve_template(config_obj: CollectConfig) -> MonitorPluginConfigTemplate:
        plugin = config_obj.monitor_plugin
        if plugin is None:
            raise BaseAppException("采集配置未绑定监控插件")
        qs = MonitorPluginConfigTemplate.objects.filter(
            plugin=plugin,
            type=config_obj.config_type,
            file_type=config_obj.file_type,
        )
        qs = qs.filter(config_type="child") if config_obj.is_child else qs.exclude(config_type="child")
        template = qs.order_by("id").first()
        if template is None:
            raise BaseAppException("未找到可用于重渲染的采集模板")
        return template

    @staticmethod
    def _load_node_payload(node_mgmt: NodeMgmt, config_obj: CollectConfig) -> dict:
        if config_obj.is_child:
            rows = node_mgmt.get_child_configs_by_ids([config_obj.id]) or []
        else:
            rows = node_mgmt.get_configs_by_ids([config_obj.id]) or []
        if not rows:
            raise BaseAppException("未找到已下发的采集配置内容")
        return rows[0]

    @staticmethod
    def _raw_content(config_obj: CollectConfig, payload: dict) -> str:
        if config_obj.is_child:
            return payload.get("content") or ""
        return payload.get("content") or payload.get("config_template") or ""

    @staticmethod
    def _build_render_context(config_obj: CollectConfig, payload: dict) -> dict:
        instance = config_obj.monitor_instance
        plugin = config_obj.monitor_plugin
        raw_content = CollectConfigUpdateService._raw_content(config_obj, payload)
        parsed = {}
        if config_obj.file_type == "toml" and raw_content:
            try:
                parsed = ConfigFormat.toml_to_dict(raw_content)
            except Exception as exc:
                raise BaseAppException("采集配置内容无法解析，无法按新模板重渲染") from exc
        elif config_obj.file_type == "yaml" and raw_content:
            try:
                parsed = ConfigFormat.yaml_to_dict(raw_content) or {}
            except Exception as exc:
                raise BaseAppException("采集配置内容无法解析，无法按新模板重渲染") from exc

        context = _flatten_parsed_content(parsed)
        context.update(_unwrap_env_config(payload.get("env_config") or {}, config_obj.id))
        context["type"] = config_obj.config_type
        context["config_id"] = config_obj.id.upper()
        context["collect_type"] = config_obj.collect_type
        context["collector"] = config_obj.collector
        context["plugin_id"] = plugin.template_id or plugin.id
        context["monitor_plugin_id"] = plugin.id
        context["instance_id"] = instance.id
        if instance.interval not in (None, "") and not context.get("interval"):
            context["interval"] = instance.interval
        if instance.ip not in (None, "") and not context.get("ip"):
            context["ip"] = instance.ip
        if not context.get("instance_type"):
            context["instance_type"] = getattr(instance.monitor_object, "name", "") or ""
        if not context.get("node_id"):
            context["node_id"] = getattr(instance, "node_id", None) or payload.get("node_id") or ""
        if not str(context.get("operating_system") or "").strip():
            from apps.monitor.utils.plugin_controller import resolve_operating_system

            resolved_os = resolve_operating_system(context)
            if resolved_os:
                context["operating_system"] = resolved_os
        try:
            from apps.monitor.utils.snmp_ifmib_capability import is_ifmib_capable_plugin
            from apps.monitor.utils.snmp_interface_template import has_interface_collection

            context["ifmib_capable"] = is_ifmib_capable_plugin(plugin)
            if context["ifmib_capable"]:
                context.setdefault("enable_ifmib", has_interface_collection(raw_content))
        except Exception:
            context.setdefault("ifmib_capable", False)
        return context

    @staticmethod
    def _write_content(node_mgmt: NodeMgmt, config_obj: CollectConfig, content: str, env_config=None):
        if config_obj.is_child:
            node_mgmt.update_child_config_content(config_obj.id, content, env_config)
        else:
            node_mgmt.update_config_content(config_obj.id, content, env_config)

    @staticmethod
    def _rerender_one(
        node_mgmt: NodeMgmt,
        config_obj: CollectConfig,
        plugin_fp: str,
        *,
        discard_hand_edited: bool = False,
    ) -> None:
        from apps.monitor.utils.plugin_controller import Controller

        payload = CollectConfigUpdateService._load_node_payload(node_mgmt, config_obj)
        original = CollectConfigUpdateService._raw_content(config_obj, payload)
        if not discard_hand_edited and is_config_hand_edited(config_obj, original):
            raise HandEditedCollectConfigError("采集配置已手改，禁止一键覆盖")
        template = CollectConfigUpdateService._resolve_template(config_obj)
        context = CollectConfigUpdateService._build_render_context(config_obj, payload)
        controller = Controller(
            {
                "collector": config_obj.collector,
                "collect_type": config_obj.collect_type,
                "monitor_plugin_id": config_obj.monitor_plugin_id,
            }
        )
        try:
            rendered = controller.render_template(
                template.content,
                context,
                escape_toml_strings=config_obj.file_type == "toml",
            )
        except Exception as exc:
            raise BaseAppException("采集配置重渲染失败") from exc
        try:
            CollectConfigUpdateService._write_content(node_mgmt, config_obj, rendered)
        except Exception as exc:
            try:
                CollectConfigUpdateService._write_content(node_mgmt, config_obj, original)
            except Exception:
                logger.exception(
                    "event=collect_config_update_rollback_failed config_id=%s failed_stage=rollback error_type=rollback_error",
                    config_obj.id,
                )
            raise BaseAppException("采集配置写入失败，已尝试回滚") from exc
        stamp_applied(config_obj, plugin_fp=plugin_fp, rendered_content=rendered, hand_edited=False)
        config_obj.save(
            update_fields=[
                "applied_content_sha256",
                "applied_rendered_sha256",
                "applied_pack_version",
                "content_hand_edited",
                "updated_at",
            ]
        )

    @staticmethod
    def update_instances(instance_ids, plugin_id, actor_context, discard_hand_edited=False) -> dict:
        raw_ids = [str(item) for item in (instance_ids or []) if item not in (None, "")]
        if not raw_ids:
            raise BaseAppException("instance_ids 不能为空")
        truncated = len(raw_ids) > _MAX_UPDATE_INSTANCES
        if truncated:
            raw_ids = raw_ids[:_MAX_UPDATE_INSTANCES]
        if plugin_id in (None, ""):
            plugins = list(
                MonitorPlugin.objects.filter(
                    id__in=CollectConfig.objects.filter(
                        monitor_instance_id__in=raw_ids,
                        monitor_plugin__isnull=False,
                    ).values("monitor_plugin_id")
                )
            )
        else:
            plugin = MonitorPlugin.objects.filter(id=plugin_id).first()
            if plugin is None:
                raise BaseAppException("监控插件不存在")
            plugins = [plugin]
        if not plugins:
            return {
                "updated": [],
                "skipped": [{"instance_id": item, "reason": "not_stale"} for item in raw_ids],
                "failed": [],
                "truncated": truncated,
                "max_instances": _MAX_UPDATE_INSTANCES,
            }

        merged = {"updated": [], "skipped": [], "failed": []}
        for plugin in plugins:
            result = CollectConfigUpdateService._update_instances_for_plugin(
                raw_ids,
                plugin,
                actor_context,
                discard_hand_edited=bool(discard_hand_edited),
            )
            merged["updated"].extend(result["updated"])
            merged["skipped"].extend(result["skipped"])
            merged["failed"].extend(result["failed"])
        # 同一实例多插件合并：任一失败则不算成功；跳过保留未成功也未失败的记录。
        failed_ids = {item.get("instance_id") for item in merged["failed"] if item.get("instance_id")}
        merged["updated"] = [item for item in dict.fromkeys(merged["updated"]) if item not in failed_ids]
        skipped_by_id = {}
        for item in merged["skipped"]:
            instance_id = item.get("instance_id")
            if not instance_id or instance_id in failed_ids or instance_id in merged["updated"]:
                continue
            skipped_by_id.setdefault(instance_id, item)
        merged["skipped"] = list(skipped_by_id.values())
        merged["truncated"] = truncated
        merged["max_instances"] = _MAX_UPDATE_INSTANCES
        return merged

    @staticmethod
    def _update_instances_for_plugin(raw_ids, plugin: MonitorPlugin, actor_context, discard_hand_edited=False) -> dict:
        plugin_fp = plugin_content_fingerprint(plugin)
        if not plugin_fp:
            return {
                "updated": [],
                "skipped": [{"instance_id": item, "reason": "not_stale"} for item in raw_ids],
                "failed": [],
            }

        authorized_ids = CollectConfigUpdateService.authorized_instance_ids(
            plugin,
            actor_context,
            require_operate=True,
        )
        requested = set(raw_ids)
        configs = list(
            CollectConfig.objects.filter(
                monitor_instance_id__in=requested,
                monitor_plugin=plugin,
            ).select_related("monitor_instance__monitor_object", "monitor_plugin")
        )
        by_instance = defaultdict(list)
        for config_obj in configs:
            by_instance[config_obj.monitor_instance_id].append(config_obj)

        node_mgmt = NodeMgmt(is_local_client=True)
        updated = []
        skipped = []
        failed = []

        for instance_id in raw_ids:
            instance_configs = by_instance.get(instance_id) or []
            if not instance_configs:
                skipped.append({"instance_id": instance_id, "reason": "not_stale"})
                continue
            if instance_id not in authorized_ids:
                # 无权限的请求实例按条跳过，避免整批失败。
                skipped.append({"instance_id": instance_id, "reason": "unauthorized"})
                continue
            instance_updated = False
            instance_edited = False
            instance_failed = False
            for config_obj in instance_configs:
                if not discard_hand_edited and not is_config_stale(config_obj, plugin):
                    continue
                if is_config_hand_edited(config_obj) and not discard_hand_edited:
                    instance_edited = True
                    continue
                try:
                    CollectConfigUpdateService._rerender_one(
                        node_mgmt,
                        config_obj,
                        plugin_fp,
                        discard_hand_edited=discard_hand_edited,
                    )
                    instance_updated = True
                except HandEditedCollectConfigError:
                    # 内容漂移等运行时手改检测：按跳过处理，勿计入失败回滚文案。
                    instance_edited = True
                    continue
                except Exception as exc:
                    instance_failed = True
                    logger.warning(
                        "event=collect_config_update_item_failed config_id=%s instance_id=%s failed_stage=rerender error_type=%s",
                        config_obj.id,
                        instance_id,
                        type(exc).__name__,
                    )
                    failed.append(
                        {
                            "instance_id": instance_id,
                            "config_id": config_obj.id,
                            "error_type": type(exc).__name__,
                        }
                    )
            if instance_failed:
                # 同实例部分配置写入失败：不记入 updated，避免前端显示「已升级」
                continue
            if instance_updated:
                updated.append(instance_id)
            elif instance_edited:
                skipped.append({"instance_id": instance_id, "reason": "hand_edited"})
            else:
                skipped.append({"instance_id": instance_id, "reason": "not_stale"})

        logger.info(
            "event=collect_config_update_finished plugin_id=%s updated=%s skipped=%s failed=%s",
            plugin.id,
            len(updated),
            len(skipped),
            len(failed),
        )
        return {"updated": updated, "skipped": skipped, "failed": failed}

    @staticmethod
    def mark_hand_edited(config_obj: CollectConfig, rendered_content: str, acknowledge_plugin: bool = False):
        """标记手改。默认不 acknowledge 新包指纹，避免「去编辑保存」误清 need_update。"""
        applied_rendered = (getattr(config_obj, "applied_rendered_sha256", None) or "").strip()
        content_changed = (not applied_rendered) or sha256_text(rendered_content) != applied_rendered
        update_fields = ["content_hand_edited", "updated_at"]
        if acknowledge_plugin:
            plugin_fp = plugin_content_fingerprint(config_obj.monitor_plugin)
            if plugin_fp:
                config_obj.applied_content_sha256 = plugin_fp
                plugin = config_obj.monitor_plugin
                config_obj.applied_pack_version = (getattr(plugin, "pack_version", None) or "") if plugin else ""
                update_fields.extend(["applied_content_sha256", "applied_pack_version"])
        if content_changed:
            config_obj.content_hand_edited = True
        config_obj.save(update_fields=update_fields)
