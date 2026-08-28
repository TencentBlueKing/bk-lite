import copy
import hashlib
import io
import json
import re
import uuid
import zipfile
from pathlib import PurePosixPath

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import MonitorObject, MonitorPlugin, PolicyTemplate
from apps.monitor.models.monitor_metrics import Metric

ARCHIVE_FORMAT = "bk-lite-monitor-policy-templates"
ARCHIVE_SCHEMA_VERSION = 1
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_FILES = 100
MAX_ARCHIVE_TEMPLATES = MAX_ARCHIVE_FILES - 1
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_TEMPLATE_BYTES = 2 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


class PolicyService:
    """策略模板模块。

    同一个 Interface 隐藏内置初始化、自定义模板、可移植配置及 ZIP 格式细节。
    """

    @staticmethod
    def build_builtin_key(object_name, plugin_name, template):
        explicit_key = str(template.get("key") or "").strip()
        identity = explicit_key or str(template.get("name") or template.get("alert_name") or template.get("metric_name") or "").strip()
        if not identity:
            raise BaseAppException("内置策略模板缺少 name")
        digest = hashlib.sha256(f"{object_name}\0{plugin_name}\0{identity}".encode("utf-8")).hexdigest()[:24]
        return f"builtin:{digest}"

    @staticmethod
    def _extract_builtin_pair(data):
        if not isinstance(data, dict):
            raise BaseAppException("policy.json 必须是对象")
        object_name = str(data.get("object") or "").strip()
        plugin_name = str(data.get("plugin") or "").strip()
        if not object_name or not plugin_name:
            raise BaseAppException("policy.json 缺少 object 或 plugin")
        return object_name, plugin_name

    @staticmethod
    def _normalize_builtin_documents(documents):
        normalized = []
        seen_pairs = set()
        seen_keys = set()
        for data in documents:
            object_name, plugin_name = PolicyService._extract_builtin_pair(data)
            pair = (object_name, plugin_name)
            if pair in seen_pairs:
                raise BaseAppException(f"内置策略模板重复定义: {object_name}/{plugin_name}")
            seen_pairs.add(pair)
            templates = data.get("templates")
            if not isinstance(templates, list):
                raise BaseAppException(f"{object_name}/{plugin_name} 的 templates 必须是列表")
            pair_keys = set()
            for raw_template in templates:
                if not isinstance(raw_template, dict):
                    raise BaseAppException(f"{object_name}/{plugin_name} 包含非法模板")
                name = str(raw_template.get("name") or raw_template.get("alert_name") or raw_template.get("metric_name") or "").strip()
                if not name:
                    raise BaseAppException(f"{object_name}/{plugin_name} 的模板缺少 name")
                key = PolicyService.build_builtin_key(object_name, plugin_name, raw_template)
                if key in pair_keys or key in seen_keys:
                    raise BaseAppException(f"内置策略模板 key 重复: {key}")
                pair_keys.add(key)
                seen_keys.add(key)
                config = copy.deepcopy(raw_template)
                config.pop("key", None)
                config.pop("name", None)
                description = str(config.pop("description", "") or "")
                if "threshold" in config and not isinstance(config["threshold"], list):
                    config["threshold"] = [
                        {
                            "level": config.pop("level", "warning"),
                            "method": config.pop("method", ">"),
                            "value": config["threshold"],
                        }
                    ]
                if str(config.get("algorithm") or "").lower() == "threshold":
                    config["group_algorithm"] = "avg"
                    config["algorithm"] = "avg_over_time"
                normalized.append(
                    {
                        "key": key,
                        "object_name": object_name,
                        "plugin_name": plugin_name,
                        "name": name,
                        "description": description,
                        "config": config,
                    }
                )
        return normalized

    @staticmethod
    def sync_builtin_policy_templates(documents):
        normalized = PolicyService._normalize_builtin_documents(documents)
        object_names = {item["object_name"] for item in normalized}
        plugin_names = {item["plugin_name"] for item in normalized}
        objects = {item.name: item for item in MonitorObject.objects.filter(name__in=object_names)}
        plugins = {item.name: item for item in MonitorPlugin.objects.filter(name__in=plugin_names)}
        missing_objects = sorted(object_names - objects.keys())
        missing_plugins = sorted(plugin_names - plugins.keys())
        if missing_objects:
            raise BaseAppException(f"监控对象不存在: {', '.join(missing_objects)}")
        if missing_plugins:
            raise BaseAppException(f"监控插件不存在: {', '.join(missing_plugins)}")

        expected_keys = {item["key"] for item in normalized}
        existing = {
            template.key: template
            for template in PolicyTemplate.objects.filter(
                template_type=PolicyTemplate.TYPE_BUILTIN,
                scope_key=PolicyTemplate.TYPE_BUILTIN,
            )
        }
        now = timezone.now()
        to_create = []
        to_update = []
        with transaction.atomic():
            for item in normalized:
                monitor_object = objects[item["object_name"]]
                plugin = plugins[item["plugin_name"]]
                current = existing.get(item["key"])
                if current is None:
                    to_create.append(
                        PolicyTemplate(
                            scope_key=PolicyTemplate.TYPE_BUILTIN,
                            key=item["key"],
                            template_type=PolicyTemplate.TYPE_BUILTIN,
                            organization=None,
                            monitor_object=monitor_object,
                            plugin=plugin,
                            name=item["name"],
                            description=item["description"],
                            config=item["config"],
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    continue
                if not PolicyService._builtin_template_changed(current, item, monitor_object, plugin):
                    continue
                current.monitor_object = monitor_object
                current.plugin = plugin
                current.name = item["name"]
                current.description = item["description"]
                current.config = item["config"]
                current.updated_at = now
                to_update.append(current)
            if to_create:
                PolicyTemplate.objects.bulk_create(to_create, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
            if to_update:
                PolicyTemplate.objects.bulk_update(
                    to_update,
                    ["name", "description", "config", "monitor_object", "plugin"],
                    batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE,
                )
            stale_ids = [template.id for template in existing.values() if template.key not in expected_keys]
            deleted_count = 0
            if stale_ids:
                deleted_count, _ = PolicyTemplate.objects.filter(id__in=stale_ids).delete()
        return {
            "created_count": len(to_create),
            "updated_count": len(to_update),
            "deleted_count": deleted_count,
        }

    @staticmethod
    def _builtin_template_changed(template, item, monitor_object, plugin):
        return (
            template.name != item["name"]
            or template.description != item["description"]
            or template.config != item["config"]
            or template.monitor_object_id != monitor_object.id
            or template.plugin_id != plugin.id
        )

    @staticmethod
    def _upsert_builtin_template(item, monitor_object, plugin):
        return PolicyTemplate.objects.update_or_create(
            scope_key=PolicyTemplate.TYPE_BUILTIN,
            key=item["key"],
            defaults={
                "template_type": PolicyTemplate.TYPE_BUILTIN,
                "organization": None,
                "monitor_object": monitor_object,
                "plugin": plugin,
                "name": item["name"],
                "description": item["description"],
                "config": item["config"],
            },
        )

    @staticmethod
    def import_monitor_policy(data):
        """兼容单文件调用；仅对账该对象和插件下的内置模板。"""
        normalized = PolicyService._normalize_builtin_documents([data])
        object_name = data["object"]
        plugin_name = data["plugin"]
        monitor_object = MonitorObject.objects.get(name=object_name)
        plugin = MonitorPlugin.objects.get(name=plugin_name)
        expected_keys = {item["key"] for item in normalized}
        with transaction.atomic():
            for item in normalized:
                PolicyService._upsert_builtin_template(item, monitor_object, plugin)
            PolicyTemplate.objects.filter(
                template_type=PolicyTemplate.TYPE_BUILTIN,
                monitor_object=monitor_object,
                plugin=plugin,
            ).exclude(key__in=expected_keys).delete()

    @staticmethod
    def _formula_query_ref(index, item):
        raw_ref = str(item.get("ref") or "").strip()
        if raw_ref:
            return raw_ref
        if index < 26:
            return chr(ord("a") + index)
        return f"q{index}"

    @staticmethod
    def _resolve_formula_expression_with_metrics(query):
        expression = str(query.get("expression") or "").strip()
        if not expression:
            return ""
        queries = query.get("queries") or []
        if not isinstance(queries, list):
            return expression
        ref_map = {}
        for index, item in enumerate(queries):
            if not isinstance(item, dict):
                continue
            raw_ref = PolicyService._formula_query_ref(index, item)
            metric_name = str(item.get("metric_name") or "").strip() or raw_ref
            ref_map[raw_ref.lower()] = metric_name
        if not ref_map:
            return expression
        pattern = re.compile(
            r"\b(?:" + "|".join(re.escape(ref) for ref in sorted(ref_map, key=len, reverse=True)) + r")\b",
            re.IGNORECASE,
        )

        def _replace(match):
            return ref_map.get(match.group(0).lower(), match.group(0))

        return pattern.sub(_replace, expression)

    @staticmethod
    def display_metric_name(config):
        config = config or {}
        query = config.get("query_condition") or {}
        if not isinstance(query, dict):
            query = {}
        if query.get("type") == "formula":
            expression = PolicyService._resolve_formula_expression_with_metrics(query)
            result_name = str(query.get("result_name") or "").strip()
            if expression:
                return f"{result_name}（{expression}）" if result_name else expression
            names = []
            for item in query.get("queries") or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("metric_name") or "").strip()
                if name:
                    names.append(name)
            if names:
                return " + ".join(names)
            return result_name
        if config.get("metric_name"):
            return str(config["metric_name"]).strip()
        return str(query.get("metric_name") or "").strip()

    @staticmethod
    def serialize_template(template):
        config = copy.deepcopy(template.config or {})
        metric_name = PolicyService.display_metric_name(config)
        return {
            **config,
            "id": template.id,
            "key": template.key,
            "template_key": f"{template.template_type}:{template.id}",
            "template_type": template.template_type,
            "deletable": template.template_type == PolicyTemplate.TYPE_CUSTOM,
            "name": template.name,
            "description": template.description or "--",
            "metric_name": metric_name,
            "trigger_count": config.get("trigger_count", 1),
            "monitor_object_id": template.monitor_object_id,
            "monitor_object_name": template.monitor_object.name,
            "monitor_object_display_name": template.monitor_object.display_name or template.monitor_object.name,
            "plugin_id": template.plugin_id,
            "plugin_name": template.plugin.name,
            "plugin_display_name": template.plugin.display_name or template.plugin.name,
            "plugin_collector": template.plugin.collector,
            "template_group": (
                f"{template.monitor_object.display_name or template.monitor_object.name}" f"（{template.plugin.display_name or template.plugin.name}）"
            ),
        }

    @staticmethod
    def get_policy_templates(monitor_object_name, organization=None, plugin_id=None):
        query = PolicyTemplate.objects.select_related("monitor_object", "plugin").filter(monitor_object__name=monitor_object_name)
        if plugin_id not in (None, ""):
            try:
                query = query.filter(plugin_id=int(plugin_id))
            except (TypeError, ValueError):
                return []
        if organization is None:
            query = query.filter(template_type=PolicyTemplate.TYPE_BUILTIN)
        else:
            query = query.filter(
                Q(template_type=PolicyTemplate.TYPE_BUILTIN) | Q(template_type=PolicyTemplate.TYPE_CUSTOM, organization=organization)
            )
        return [PolicyService.serialize_template(item) for item in query.order_by("plugin__name", "name", "id")]

    @staticmethod
    def get_policy_templates_monitor_object(organization=None):
        query = PolicyTemplate.objects.all()
        if organization is None:
            query = query.filter(template_type=PolicyTemplate.TYPE_BUILTIN)
        else:
            query = query.filter(
                Q(template_type=PolicyTemplate.TYPE_BUILTIN) | Q(template_type=PolicyTemplate.TYPE_CUSTOM, organization=organization)
            )
        return list(query.values_list("monitor_object_id", flat=True).distinct())

    @staticmethod
    def _portable_query_condition(query_condition):
        query = copy.deepcopy(query_condition or {})
        metric_ids = []
        if query.get("type") == "formula":
            metric_ids = [item.get("metric_id") for item in query.get("queries") or []]
        elif query.get("metric_id"):
            metric_ids = [query.get("metric_id")]
        metrics = {item.id: item for item in Metric.objects.select_related("monitor_plugin").filter(id__in=metric_ids)}
        if len(metrics) != len(set(metric_ids)):
            raise BaseAppException("模板引用的指标不存在")

        def replace(item):
            metric_id = item.pop("metric_id", None)
            if metric_id:
                metric = metrics[metric_id]
                item["metric_name"] = metric.name
                if metric.monitor_plugin:
                    item["metric_plugin"] = metric.monitor_plugin.name

        if query.get("type") == "formula":
            for item in query.get("queries") or []:
                replace(item)
        else:
            replace(query)
        return query

    @staticmethod
    def _runtime_query_condition(query_condition, monitor_object):
        query = copy.deepcopy(query_condition or {})

        def replace(item):
            metric_name = item.pop("metric_name", None)
            plugin_name = item.pop("metric_plugin", None)
            if not metric_name:
                return
            metrics = Metric.objects.filter(monitor_object=monitor_object, name=metric_name)
            if plugin_name:
                metrics = metrics.filter(monitor_plugin__name=plugin_name)
            metric = metrics.first()
            if not metric:
                raise BaseAppException(f"指标不存在: {metric_name}")
            item["metric_id"] = metric.id

        if query.get("type") == "formula":
            for item in query.get("queries") or []:
                replace(item)
        else:
            replace(query)
        return query

    @staticmethod
    def portable_config(config):
        portable = copy.deepcopy(config or {})
        for field in (
            "id",
            "key",
            "template_key",
            "template_type",
            "deletable",
            "monitor_object",
            "monitor_object_id",
            "monitor_object_name",
            "organizations",
            "source",
            "collect_type",
            "plugin",
            "plugin_id",
            "plugin_name",
            "notice",
            "notice_type",
            "notice_type_ids",
            "notice_users",
            "enable",
            "last_run_time",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
        ):
            portable.pop(field, None)
        if portable.get("query_condition"):
            portable["query_condition"] = PolicyService._portable_query_condition(portable["query_condition"])
        # 仅补齐稳定指标名；公式展示串不得写入 metric_name，避免导入/回填按 Metric.name 查找失败
        if not portable.get("metric_name"):
            query = portable.get("query_condition") or {}
            if isinstance(query, dict) and query.get("type") != "formula":
                metric_name = str(query.get("metric_name") or "").strip()
                if metric_name:
                    portable["metric_name"] = metric_name
        return portable

    @staticmethod
    def create_custom_template(*, organization, monitor_object_id, plugin_id, name, description, config, user):
        try:
            monitor_object = MonitorObject.objects.get(id=monitor_object_id)
            plugin = MonitorPlugin.objects.get(id=plugin_id, monitor_object=monitor_object)
        except (MonitorObject.DoesNotExist, MonitorPlugin.DoesNotExist) as exc:
            raise BaseAppException("监控对象或插件不存在") from exc
        return PolicyTemplate.objects.create(
            key=str(uuid.uuid4()),
            scope_key=f"custom:{organization}",
            template_type=PolicyTemplate.TYPE_CUSTOM,
            organization=organization,
            monitor_object=monitor_object,
            plugin=plugin,
            name=name,
            description=description or "",
            config=PolicyService.portable_config(config),
            created_by=user.username,
            updated_by=user.username,
            domain=getattr(user, "domain", "domain.com"),
            updated_by_domain=getattr(user, "domain", "domain.com"),
        )

    @staticmethod
    def parse_selection_keys(keys):
        if not isinstance(keys, list):
            raise BaseAppException("模板标识必须是列表")
        if len(keys) > MAX_ARCHIVE_TEMPLATES:
            raise BaseAppException(f"单次最多操作 {MAX_ARCHIVE_TEMPLATES} 个模板")
        ids = []
        for key in keys:
            try:
                _, raw_id = str(key).split(":", 1)
                ids.append(int(raw_id))
            except (TypeError, ValueError):
                raise BaseAppException(f"非法模板标识: {key}")
        if len(ids) != len(set(ids)):
            raise BaseAppException("模板标识不能重复")
        return ids

    @staticmethod
    def get_selected_templates(keys, organization):
        ids = PolicyService.parse_selection_keys(keys)
        templates = list(PolicyTemplate.objects.select_related("monitor_object", "plugin").filter(id__in=ids))
        if len(templates) != len(set(ids)):
            raise BaseAppException("模板不存在")
        templates_by_id = {item.id: item for item in templates}
        ordered_templates = []
        for key, template_id in zip(keys, ids):
            template = templates_by_id[template_id]
            template_type, _ = str(key).split(":", 1)
            if template_type != template.template_type:
                raise BaseAppException(f"模板标识不匹配: {key}")
            ordered_templates.append(template)
        for item in ordered_templates:
            if item.template_type == PolicyTemplate.TYPE_CUSTOM and item.organization != organization:
                raise BaseAppException("无权限访问指定模板")
        return ordered_templates

    @staticmethod
    def export_archive(keys, organization):
        selected_templates = PolicyService.get_selected_templates(keys, organization)
        templates_by_key = {}
        for template in selected_templates:
            current = templates_by_key.get(template.key)
            if current is None or template.template_type == PolicyTemplate.TYPE_CUSTOM:
                templates_by_key[template.key] = template
        buffer = io.BytesIO()
        manifest_items = []
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for template in templates_by_key.values():
                portable_identity = f"{template.template_type}:{template.key}"
                filename = f"templates/{hashlib.sha256(portable_identity.encode('utf-8')).hexdigest()}.json"
                payload = {
                    "key": template.key,
                    "name": template.name,
                    "description": template.description,
                    "monitor_object": template.monitor_object.name,
                    "plugin": template.plugin.name,
                    "config": template.config,
                }
                archive.writestr(filename, json.dumps(payload, ensure_ascii=False, indent=2))
                manifest_items.append({"file": filename, "key": template.key})
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format": ARCHIVE_FORMAT,
                        "schema_version": ARCHIVE_SCHEMA_VERSION,
                        "exported_at": timezone.now().isoformat(),
                        "templates": manifest_items,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        buffer.seek(0)
        return buffer

    @staticmethod
    def _read_archive(upload):
        content = upload.read(MAX_ARCHIVE_BYTES + 1)
        if len(content) > MAX_ARCHIVE_BYTES:
            raise BaseAppException("ZIP 包不能超过 10MB")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                names = [member.filename for member in members]
                if len(members) > MAX_ARCHIVE_FILES:
                    raise BaseAppException("ZIP 包文件数量超过限制")
                if len(names) != len(set(names)):
                    raise BaseAppException("ZIP 包包含重复文件名")
                total_size = 0
                for member in members:
                    path = PurePosixPath(member.filename)
                    if member.is_dir() or path.is_absolute() or ".." in path.parts or "\\" in member.filename:
                        raise BaseAppException("ZIP 包包含非法路径")
                    mode = member.external_attr >> 16
                    if mode & 0o170000 == 0o120000:
                        raise BaseAppException("ZIP 包不能包含符号链接")
                    if member.file_size > MAX_TEMPLATE_BYTES:
                        raise BaseAppException("ZIP 包单个文件不能超过 2MB")
                    total_size += member.file_size
                    if member.compress_size and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO:
                        raise BaseAppException("ZIP 包压缩比异常")
                if total_size > MAX_UNCOMPRESSED_BYTES:
                    raise BaseAppException("ZIP 包解压后大小超过限制")
                try:
                    manifest = json.loads(archive.read("manifest.json"))
                except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise BaseAppException("ZIP 包缺少有效的 manifest.json") from exc
                if not isinstance(manifest, dict):
                    raise BaseAppException("manifest.json 必须是对象")
                if manifest.get("format") != ARCHIVE_FORMAT or manifest.get("schema_version") != ARCHIVE_SCHEMA_VERSION:
                    raise BaseAppException("不支持的模板 ZIP 格式或版本")
                template_items = manifest.get("templates")
                if not isinstance(template_items, list) or not template_items:
                    raise BaseAppException("manifest.json 缺少模板清单")
                if len(template_items) > MAX_ARCHIVE_TEMPLATES:
                    raise BaseAppException(f"单次最多导入 {MAX_ARCHIVE_TEMPLATES} 个模板")
                payloads = []
                for item in template_items:
                    if not isinstance(item, dict):
                        raise BaseAppException("manifest.json 包含非法模板项")
                    filename = item.get("file")
                    if not filename or filename not in names or not filename.startswith("templates/"):
                        raise BaseAppException("manifest 引用了非法的模板文件")
                    try:
                        payload = json.loads(archive.read(filename))
                    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                        raise BaseAppException(f"模板文件无效: {filename}") from exc
                    if not isinstance(payload, dict) or item.get("key") != payload.get("key"):
                        raise BaseAppException(f"模板清单与文件不匹配: {filename}")
                    payloads.append(payload)
                return payloads
        except zipfile.BadZipFile as exc:
            raise BaseAppException("上传文件不是有效的 ZIP 包") from exc

    @staticmethod
    def import_archive(upload, *, organization, user, overwrite=False, authorize_monitor_object=None):
        payloads = PolicyService._read_archive(upload)
        prepared = []
        conflicts = []
        package_keys = set()
        for payload in payloads:
            key = str(payload.get("key") or "").strip()
            name = str(payload.get("name") or "").strip()
            if not key or not name or not isinstance(payload.get("config"), dict):
                raise BaseAppException("模板缺少 key、name 或 config")
            if len(key) > 255 or len(name) > 100:
                raise BaseAppException(f"模板标识或名称过长: {name}")
            try:
                monitor_object = MonitorObject.objects.get(name=payload.get("monitor_object"))
                plugin = MonitorPlugin.objects.get(name=payload.get("plugin"), monitor_object=monitor_object)
            except (MonitorObject.DoesNotExist, MonitorPlugin.DoesNotExist) as exc:
                raise BaseAppException(f"模板 {name} 引用的监控对象或插件不存在") from exc
            if authorize_monitor_object:
                authorize_monitor_object(monitor_object.id)
            if key in package_keys:
                raise BaseAppException(f"ZIP 包内模板重复: {name}")
            package_keys.add(key)
            config = PolicyService.portable_config(payload["config"])
            PolicyService._runtime_query_condition(config.get("query_condition"), monitor_object)
            payload["config"] = config
            existing = PolicyTemplate.objects.filter(
                template_type=PolicyTemplate.TYPE_CUSTOM,
                organization=organization,
                key=key,
            ).first()
            if existing:
                conflicts.append({"id": existing.id, "name": existing.name})
            prepared.append((payload, monitor_object, plugin, existing))
        if conflicts and not overwrite:
            return {"requires_overwrite": True, "conflicts": conflicts, "imported_count": 0}

        with transaction.atomic():
            for payload, monitor_object, plugin, existing in prepared:
                values = {
                    "key": payload["key"],
                    "scope_key": f"custom:{organization}",
                    "template_type": PolicyTemplate.TYPE_CUSTOM,
                    "organization": organization,
                    "monitor_object": monitor_object,
                    "plugin": plugin,
                    "name": payload["name"],
                    "description": payload.get("description") or "",
                    "config": payload["config"],
                    "updated_by": user.username,
                    "updated_by_domain": getattr(user, "domain", "domain.com"),
                }
                if existing:
                    for field, value in values.items():
                        setattr(existing, field, value)
                    existing.save()
                else:
                    PolicyTemplate.objects.create(
                        **values,
                        created_by=user.username,
                        domain=getattr(user, "domain", "domain.com"),
                    )
        return {"requires_overwrite": False, "conflicts": conflicts, "imported_count": len(prepared)}
