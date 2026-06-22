import base64
import difflib
import hashlib
from datetime import datetime

from django.db import transaction
from django.db.models import Max, Q
from django.utils.dateparse import parse_datetime
from django.utils.timezone import get_current_timezone, is_aware, is_naive, make_aware, now

from apps.cmdb.constants.constants import CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.config_file_version import ConfigFileVersion, ConfigFileVersionStatus
from apps.cmdb.utils.config_file_path import extract_file_name
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.permission_utils import get_permission_rules
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.core.utils.team_utils import get_current_team

MAX_CONFIG_FILE_SIZE_LIMIT = 5 * 1024 * 1024


class ConfigFileService(object):
    """配置文件版本管理服务。"""

    STATUS_MAP = {
        "success": ConfigFileVersionStatus.SUCCESS,
        "file_not_found": ConfigFileVersionStatus.FILE_NOT_FOUND,
        "permission_denied": ConfigFileVersionStatus.PERMISSION_DENIED,
        "file_too_large": ConfigFileVersionStatus.FILE_TOO_LARGE,
        "not_text": ConfigFileVersionStatus.NOT_TEXT,
        "error": ConfigFileVersionStatus.ERROR,
    }

    @staticmethod
    def generate_diff(content_1: str, content_2: str, label_1: str, label_2: str) -> str:
        lines_1 = content_1.splitlines(keepends=True)
        lines_2 = content_2.splitlines(keepends=True)
        return "".join(difflib.unified_diff(lines_1, lines_2, fromfile=label_1, tofile=label_2))

    @staticmethod
    def build_object_key(model_id: str, instance_id: str, file_path: str, timestamp: str) -> str:
        file_path_hash = hashlib.md5(file_path.encode("utf-8")).hexdigest()[:12]
        return f"{model_id}/{instance_id}/{file_path_hash}/{timestamp}.txt"

    @classmethod
    def process_collect_result(cls, data: dict) -> dict:
        payload = cls._normalize_collect_payload(data)
        task_id = payload.get("collect_task_id") or payload.get("task_id")
        if not task_id:
            raise BaseAppException("配置文件采集回调缺少任务 ID")

        task = CollectModels.objects.filter(id=task_id).first()
        if not task:
            raise BaseAppException(f"配置文件采集任务不存在: {task_id}")

        try:
            params = dict(task.params or {})
            instance_identifier = str(payload.get("instance_name") or payload.get("instance_id") or "")
            if not instance_identifier:
                raise BaseAppException("配置文件采集回调缺少目标实例标识")

            instance_id, instance = cls._get_task_instance_or_raise(task, instance_identifier)

            model_id = str(payload.get("model_id") or (instance or {}).get("model_id") or params.get("target_model_id") or task.model_id or "host")
            file_path = str(payload.get("file_path") or params.get("config_file_path") or "")
            file_name = str(payload.get("file_name") or params.get("config_file_name") or extract_file_name(file_path) or "")
            version = cls._normalize_version(str(payload.get("version") or payload.get("collected_at") or ""))
            status = cls.STATUS_MAP.get(str(payload.get("status") or "error").lower(), ConfigFileVersionStatus.ERROR)
            file_size = int(payload.get("size") or payload.get("file_size") or 0)
            error_message = str(payload.get("error") or payload.get("error_message") or "")
            content_base64 = payload.get("content_base64") or ""
            stale_callback = cls._is_stale_callback(task, version)

            with transaction.atomic():
                if status != ConfigFileVersionStatus.SUCCESS:
                    task_updated = cls._update_task_lifecycle(
                        task=task,
                        instance_id=instance_id,
                        version=version,
                        status=status,
                        changed=False,
                        version_obj=None,
                        error_message=error_message,
                        stale_callback=stale_callback,
                    )
                    return {"version_obj": None, "changed": False, "task_updated": task_updated}

                text_content = cls._decode_content(content_base64)
                text_content = cls._truncate_content_for_storage(
                    text_content=text_content,
                    file_size=file_size,
                    file_path=file_path,
                    task_id=task.id,
                    instance_id=instance_id,
                )
                content_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
                latest_success_version = cls._get_latest_success_version(task.id, instance_id, file_path)
                if latest_success_version and latest_success_version.content_hash == content_hash:
                    task_updated = cls._update_task_lifecycle(
                        task=task,
                        instance_id=instance_id,
                        version=version,
                        status=status,
                        changed=False,
                        version_obj=latest_success_version,
                        error_message="",
                        stale_callback=stale_callback,
                    )
                    return {"version_obj": latest_success_version, "changed": False, "task_updated": task_updated}

                version_obj, _ = ConfigFileVersion.objects.select_for_update().get_or_create(
                    collect_task=task,
                    instance_id=instance_id,
                    version=version,
                    defaults={
                        "model_id": model_id,
                        "file_path": file_path,
                        "file_name": file_name,
                        "status": status,
                        "file_size": file_size,
                        "error_message": error_message,
                    },
                )
                version_obj.model_id = model_id
                version_obj.file_path = file_path
                version_obj.file_name = file_name
                version_obj.file_size = file_size
                version_obj.status = status
                version_obj.error_message = error_message
                version_obj.content_hash = content_hash
                if not version_obj.content:
                    object_key = cls.build_object_key(model_id, instance_id, file_path, version)
                    version_obj.save_content(text_content, object_key)
                version_obj.save()
                task_updated = cls._update_task_lifecycle(
                    task=task,
                    instance_id=instance_id,
                    version=version,
                    status=status,
                    changed=True,
                    version_obj=version_obj,
                    error_message="",
                    stale_callback=stale_callback,
                )
                return {"version_obj": version_obj, "changed": True, "task_updated": task_updated}
        except Exception as err:
            logger.exception("[ConfigFileService] 处理配置文件回调失败并转为任务闭环: task_id=%s", task.id)
            task_updated = cls._close_task_on_processing_error(task=task, payload=payload, error=err)
            return {"version_obj": None, "changed": False, "task_updated": task_updated, "error": str(err)}

    @classmethod
    def _close_task_on_processing_error(cls, task: CollectModels, payload: dict, error: Exception) -> bool:
        version = cls._normalize_version(str(payload.get("version") or payload.get("collected_at") or ""))
        stale_callback = cls._is_stale_callback(task, version)
        if stale_callback:
            logger.info("[ConfigFileService] 忽略过期异常回调闭环 task_id=%s", task.id)
            return False

        error_message = str(error) or "配置文件采集结果处理失败"
        instance_identifier = str(payload.get("instance_name") or payload.get("instance_id") or "")
        expected_instance_ids = cls._get_expected_instance_ids(task)
        instance_id, _ = cls._resolve_task_instance(task, instance_identifier)

        if instance_id and instance_id in expected_instance_ids:
            return cls._update_task_lifecycle(
                task=task,
                instance_id=instance_id,
                version=version,
                status=ConfigFileVersionStatus.ERROR,
                changed=False,
                version_obj=None,
                error_message=error_message,
                stale_callback=False,
            )

        task_state = cls._build_task_state(task)
        items = dict(task_state.get("items") or {})
        target_instance_ids = [item_id for item_id in expected_instance_ids if item_id not in items]
        if not target_instance_ids:
            target_instance_ids = expected_instance_ids[:1]
        if not target_instance_ids:
            logger.error("[ConfigFileService] 无法为异常回调找到闭环实例 task_id=%s", task.id)
            return False

        for target_instance_id in target_instance_ids:
            items[target_instance_id] = {
                "instance_id": target_instance_id,
                "version": version,
                "changed": False,
                "content_key": "",
                "status": ConfigFileVersionStatus.ERROR,
                "error_message": error_message,
                "file_path": (task.params or {}).get("config_file_path", ""),
                "file_name": extract_file_name((task.params or {}).get("config_file_path", "")),
            }

        summary = cls._build_summary(task, items)
        task.collect_data = {"config_file": summary["config_file_data"]}
        task.format_data = summary["format_data"]
        task.collect_digest = summary["collect_digest"]
        task.exec_status = summary["exec_status"]
        task.save(update_fields=["collect_data", "format_data", "collect_digest", "exec_status", "updated_at"])
        return True

    @staticmethod
    def _normalize_collect_payload(data: dict) -> dict:
        if not isinstance(data, dict):
            raise BaseAppException("配置文件采集回调格式错误")

        payload = dict(data)
        collect_result = payload.get("collect_result")
        if isinstance(collect_result, dict):
            nested = dict(collect_result)
            payload.update(nested)
            payload.setdefault("file_path", data.get("config_file_path") or data.get("file_path") or "")
            payload.setdefault(
                "file_name",
                data.get("config_file_name") or data.get("file_name") or extract_file_name(payload.get("file_path") or "") or "",
            )
        return payload

    @staticmethod
    def _normalize_version(version: str) -> str:
        normalized = (version or "").strip()
        if not normalized:
            return str(int(now().timestamp() * 1000))

        if normalized.isdigit():
            if len(normalized) <= 10:
                return str(int(normalized) * 1000)
            return normalized

        version_time = parse_datetime(normalized)
        if version_time is None:
            return str(int(now().timestamp() * 1000))

        if is_naive(version_time):
            version_time = make_aware(version_time, get_current_timezone())
        return str(int(version_time.timestamp() * 1000))

    @staticmethod
    def _parse_version_datetime(version: str) -> datetime | None:
        normalized = (version or "").strip()
        if not normalized:
            return None
        if normalized.isdigit():
            version_int = int(normalized)
            version_seconds = version_int / 1000 if len(normalized) > 10 else version_int
            return datetime.fromtimestamp(version_seconds, tz=get_current_timezone())
        version_time = parse_datetime(normalized)
        if version_time is None:
            return None
        if is_naive(version_time):
            version_time = make_aware(version_time, get_current_timezone())
        return version_time

    @staticmethod
    def _truncate_content_for_storage(
        text_content: str,
        file_size: int,
        file_path: str,
        task_id: int | str,
        instance_id: str,
    ) -> str:
        raw_content = (text_content or "").encode("utf-8")
        if len(raw_content) <= MAX_CONFIG_FILE_SIZE_LIMIT:
            return text_content

        logger.warning(
            "[ConfigFileService] 配置文件内容超过 5MB，按上限截断后保存: task_id=%s, instance_id=%s, file_path=%s, original_size=%s",
            task_id,
            instance_id,
            file_path,
            file_size or len(raw_content),
        )
        truncated_content = raw_content[:MAX_CONFIG_FILE_SIZE_LIMIT].decode("utf-8", errors="ignore")
        return truncated_content

    @staticmethod
    def _is_stale_callback(task: CollectModels, version: str) -> bool:
        if not task.exec_time:
            return False
        version_time = ConfigFileService._parse_version_datetime(version)
        if version_time is None:
            return False
        exec_time = task.exec_time
        timezone = get_current_timezone()
        if is_naive(version_time) and is_aware(exec_time):
            version_time = make_aware(version_time, timezone)
        elif is_aware(version_time) and is_naive(exec_time):
            exec_time = make_aware(exec_time, timezone)
        return version_time < exec_time

    @classmethod
    def _update_task_lifecycle(
        cls,
        task: CollectModels,
        instance_id: str,
        version: str,
        status: str,
        changed: bool,
        version_obj: ConfigFileVersion | None,
        error_message: str,
        stale_callback: bool,
    ) -> bool:
        if stale_callback:
            logger.info(
                "[ConfigFileService] 忽略过期回调 task_id=%s, version=%s, exec_time=%s",
                task.id,
                version,
                task.exec_time,
            )
            return False

        task_state = cls._build_task_state(task)
        items = dict(task_state.get("items") or {})
        items[instance_id] = {
            "instance_id": instance_id,
            "version": version,
            "changed": changed,
            "content_key": version_obj.content_key if version_obj and version_obj.content else "",
            "status": status,
            "error_message": error_message,
            "file_path": version_obj.file_path if version_obj else (task.params or {}).get("config_file_path", ""),
            "file_name": version_obj.file_name if version_obj else extract_file_name((task.params or {}).get("config_file_path", "")),
        }

        summary = cls._build_summary(task, items)
        config_file_data = summary["config_file_data"]
        format_data = summary["format_data"]
        collect_digest = summary["collect_digest"]
        exec_status = summary["exec_status"]

        task.collect_data = {"config_file": config_file_data}
        task.format_data = format_data
        task.collect_digest = collect_digest
        task.exec_status = exec_status
        task.save(update_fields=["collect_data", "format_data", "collect_digest", "exec_status", "updated_at"])
        return True

    @staticmethod
    def _decode_content(content_base64: str) -> str:
        if not content_base64:
            return ""
        try:
            raw_content = base64.b64decode(content_base64)
            return raw_content.decode("utf-8")
        except Exception as err:
            raise BaseAppException(f"配置文件采集结果解码失败: {str(err)}")

    @staticmethod
    def _get_target_instance(task: CollectModels) -> dict:
        if not isinstance(task.instances, list) or not task.instances:
            return {}
        instance = task.instances[0]
        if not isinstance(instance, dict):
            return {}
        return instance

    @classmethod
    def _get_task_instance_or_raise(cls, task: CollectModels, instance_identifier: str) -> tuple[str, dict]:
        resolved_instance_id, instance = cls._resolve_task_instance(task, instance_identifier)
        if cls._get_expected_instance_map(task) and not instance:
            raise BaseAppException(f"配置文件采集回调实例不属于当前任务: {instance_identifier}")
        return resolved_instance_id, instance or {}

    @classmethod
    def _resolve_task_instance(cls, task: CollectModels, instance_identifier: str) -> tuple[str, dict]:
        normalized_identifier = str(instance_identifier or "").strip()
        if not normalized_identifier:
            return "", {}

        expected_instance_map = cls._get_expected_instance_map(task)
        instance = expected_instance_map.get(normalized_identifier)
        if instance:
            return normalized_identifier, instance

        expected_instance_name_map = cls._get_expected_instance_name_map(task)
        instance = expected_instance_name_map.get(normalized_identifier)
        if not instance:
            return "", {}

        resolved_instance_id = str(instance.get("_id") or instance.get("id") or "")
        return resolved_instance_id, instance

    @classmethod
    def _get_expected_instance_ids(cls, task: CollectModels) -> list[str]:
        return list(cls._get_expected_instance_map(task).keys())

    @staticmethod
    def _get_expected_instance_map(task: CollectModels) -> dict[str, dict]:
        instance_map = {}
        for instance in task.instances or []:
            if not isinstance(instance, dict):
                continue
            instance_id = str(instance.get("_id") or instance.get("id") or "")
            if not instance_id:
                continue
            instance_map[instance_id] = instance
        return instance_map

    @classmethod
    def _get_expected_instance_name_map(cls, task: CollectModels) -> dict[str, dict]:
        instance_name_map = {}
        for instance in task.instances or []:
            if not isinstance(instance, dict):
                continue
            instance_name = cls._build_task_instance_name(instance)
            if not instance_name:
                continue
            instance_name_map[instance_name] = instance
        return instance_name_map

    @staticmethod
    def _build_task_instance_name(instance: dict) -> str:
        if not isinstance(instance, dict):
            return ""

        connect_ip = str(instance.get("ip_addr") or instance.get("host") or "").strip()
        if not connect_ip:
            return ""

        inst_name = str(instance.get("inst_name") or "").strip()
        if inst_name.startswith(f"{connect_ip}[") and inst_name.endswith("]"):
            return inst_name

        cloud_label = str(instance.get("cloud_id") or instance.get("cloud") or "").strip()
        if cloud_label:
            return f"{connect_ip}[{cloud_label}]"
        return connect_ip

    @staticmethod
    def _build_task_state(task: CollectModels) -> dict:
        collect_data = task.collect_data or {}
        config_state = collect_data.get("config_file") or {}
        return config_state if isinstance(config_state, dict) else {}

    @classmethod
    def _build_summary(cls, task: CollectModels, items: dict | None = None) -> dict:
        task_state = cls._build_task_state(task)
        item_map = dict(items if items is not None else task_state.get("items") or {})
        expected_instance_ids = cls._get_expected_instance_ids(task)
        expected_total = len(expected_instance_ids) if expected_instance_ids else len(item_map)
        received_count = len(item_map)
        success_count = sum(1 for item in item_map.values() if item.get("status") == ConfigFileVersionStatus.SUCCESS)
        error_count = received_count - success_count
        changed_count = sum(1 for item in item_map.values() if item.get("changed"))
        pending_count = max(expected_total - received_count, 0) if expected_total else 0
        raw_items = sorted(item_map.values(), key=lambda item: (item.get("instance_id") or "", item.get("version") or ""))

        if pending_count > 0:
            overall_status = "pending"
            exec_status = CollectRunStatusType.RUNNING
            message = f"配置文件采集已触发，等待回传中 ({received_count}/{expected_total})"
        elif error_count > 0:
            overall_status = "error"
            exec_status = CollectRunStatusType.ERROR
            if success_count > 0:
                message = f"配置文件采集完成，成功 {success_count} 台，失败 {error_count} 台"
            else:
                first_error = next((item.get("error_message") for item in raw_items if item.get("error_message")), "配置文件采集失败")
                message = first_error or "配置文件采集失败"
        else:
            overall_status = "success"
            exec_status = CollectRunStatusType.SUCCESS
            if expected_total <= 1 and changed_count == 0:
                message = "配置文件内容无变化"
            elif changed_count == 0:
                message = f"配置文件采集完成，{success_count} 台主机内容无变化"
            else:
                message = f"配置文件采集完成，成功 {success_count} 台"

        latest_item = raw_items[-1] if raw_items else {}
        config_file_data = {
            "status": overall_status,
            "items": item_map,
            "expected_count": expected_total,
            "success_count": success_count,
            "error_count": error_count,
            "pending_count": pending_count,
            "changed_count": changed_count,
            "version": latest_item.get("version", ""),
            "changed": bool(latest_item.get("changed", False)),
            "content_key": latest_item.get("content_key", ""),
            "file_path": latest_item.get("file_path") or (task.params or {}).get("config_file_path", ""),
            "file_name": latest_item.get("file_name") or extract_file_name((task.params or {}).get("config_file_path", "")),
        }

        add_items = []
        add_error_count = 0
        for item in raw_items:
            is_success = item.get("status") == ConfigFileVersionStatus.SUCCESS
            add_entry = {
                "_status": "success" if is_success else "failed",
                "instance_id": item.get("instance_id", ""),
                "file_path": item.get("file_path") or (task.params or {}).get("config_file_path", ""),
                "file_name": item.get("file_name") or extract_file_name((task.params or {}).get("config_file_path", "")),
            }
            if not is_success:
                add_entry["_error"] = item.get("error_message", "")
                add_error_count += 1
            add_items.append(add_entry)

        format_data = {
            "add": add_items,
            "update": [],
            "delete": [],
            "association": [],
            "__raw_data__": [
                {
                    "__time__": item.get("version", ""),
                    "status": item.get("status", "pending"),
                    "instance_id": item.get("instance_id", ""),
                }
                for item in raw_items
            ],
            "all": success_count,
        }

        collect_digest = {
            "add": len(add_items),
            "add_error": add_error_count,
            "update": 0,
            "update_error": 0,
            "delete": 0,
            "delete_error": 0,
            "association": 0,
            "association_error": 0,
            "add_success": len(add_items) - add_error_count,
            "update_success": 0,
            "delete_success": 0,
            "association_success": 0,
            "all": success_count,
            "message": message,
        }
        if raw_items:
            collect_digest["last_time"] = max(item.get("version", "") for item in raw_items)

        return {
            "config_file_data": config_file_data,
            "format_data": format_data,
            "collect_digest": collect_digest,
            "exec_status": exec_status,
        }

    @classmethod
    def build_pending_result(cls, task: CollectModels):
        summary = cls._build_summary(task, items={})
        return {"config_file": summary["config_file_data"]}, summary["format_data"]

    @staticmethod
    def _get_latest_success_hash(task_id: int, instance_id: str, file_path: str, exclude_id: int | None = None) -> str:
        queryset = ConfigFileVersion.objects.filter(
            collect_task_id=task_id,
            instance_id=instance_id,
            file_path=file_path,
            status=ConfigFileVersionStatus.SUCCESS,
        )
        if exclude_id:
            queryset = queryset.exclude(id=exclude_id)
        latest_version = queryset.order_by("-created_at").first()
        return latest_version.content_hash if latest_version else ""

    @classmethod
    def _get_latest_success_version(cls, task_id: int, instance_id: str, file_path: str):
        return (
            ConfigFileVersion.objects.filter(
                collect_task_id=task_id,
                instance_id=instance_id,
                file_path=file_path,
                status=ConfigFileVersionStatus.SUCCESS,
            )
            .order_by("-created_at")
            .first()
        )

    @staticmethod
    def get_latest_version(collect_task_id: int, instance_id: str, file_path: str):
        return (
            ConfigFileVersion.objects.filter(
                collect_task_id=collect_task_id,
                instance_id=instance_id,
                file_path=file_path,
            )
            .order_by("-created_at")
            .first()
        )

    @staticmethod
    def get_file_list(instance_id: str, base_queryset=None) -> list[dict]:
        # 权限过滤必须先于聚合：传入的 base_queryset 已按任务权限收紧，
        # 在其之上做 Max 聚合，避免 latest_* 字段来自用户无权访问的任务版本。
        if base_queryset is None:
            base_queryset = ConfigFileVersion.objects.all()
        latest_ids = (
            base_queryset.filter(instance_id=instance_id).values("file_path").annotate(latest_id=Max("id")).values_list("latest_id", flat=True)
        )
        rows = ConfigFileVersion.objects.filter(id__in=latest_ids).order_by("file_name", "file_path")
        return [
            {
                "latest_version_id": row.id,
                "file_path": row.file_path,
                "file_name": row.file_name,
                "collect_task_id": row.collect_task_id,
                "latest_version": row.version,
                "latest_status": row.status,
                "latest_created_at": row.created_at,
            }
            for row in rows
        ]

    @staticmethod
    def filter_queryset_by_task_permission(request, queryset):
        current_team = get_current_team(request)
        if not current_team:
            return queryset.none()

        include_children = request.COOKIES.get("include_children", "0") == "1"
        try:
            current_team_int = int(current_team)
        except (TypeError, ValueError):
            return queryset.none()

        query_groups = GroupUtils.get_group_with_descendants(current_team_int) if include_children else [current_team_int]
        if not query_groups:
            query_groups = [current_team_int]

        team_query = Q()
        for team_id in query_groups:
            team_query |= Q(collect_task__team__contains=[team_id]) | Q(collect_task__team__contains=[str(team_id)])

        base_queryset = queryset.filter(team_query)
        permission_data = get_permission_rules(request.user, current_team_int, "cmdb", "task", include_children)
        if not isinstance(permission_data, dict) or not permission_data:
            return base_queryset

    @classmethod
    def create_manual_version(cls, instance_id: str, model_id: str, file_path: str, content: str) -> dict:
        """手动创建配置文件版本。"""
        file_name = extract_file_name(file_path) or file_path
        version = str(int(now().timestamp() * 1000))
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # 查重：同 instance_id + file_path 最新成功版本
        latest = (
            ConfigFileVersion.objects.filter(
                instance_id=instance_id,
                file_path=file_path,
                status=ConfigFileVersionStatus.SUCCESS,
            )
            .order_by("-created_at")
            .first()
        )
        if latest and latest.content_hash == content_hash:
            return {"unchanged": True, "version_obj": latest}

        # 截断超大内容
        text_content = cls._truncate_content_for_storage(
            text_content=content,
            file_size=len(content.encode("utf-8")),
            file_path=file_path,
            task_id="manual",
            instance_id=instance_id,
        )
        content_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
        file_size = len(text_content.encode("utf-8"))

        object_key = cls.build_object_key(model_id, instance_id, file_path, version)
        version_obj = ConfigFileVersion(
            collect_task=None,
            instance_id=instance_id,
            model_id=model_id,
            version=version,
            file_path=file_path,
            file_name=file_name,
            content_hash=content_hash,
            file_size=file_size,
            status=ConfigFileVersionStatus.SUCCESS,
            error_message="",
        )
        version_obj.save_content(text_content, object_key)
        version_obj.save()
        return {"unchanged": False, "version_obj": version_obj}
