import asyncio
import hashlib
import json
import os
import re
from typing import Any

from django.core.cache import cache

from apps.base.models import UserAPISecret
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import Metric, MonitorInstance, MonitorPlugin
from apps.monitor.models.monitor_object import MonitorInstanceOrganization
from apps.rpc.system_mgmt import SystemMgmt
from nats_client.clients import get_nc_client


def _escape_line_value(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def _escape_field_string(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


class PushAPIService:
    TOKEN_CACHE_TTL = 300
    TEMPLATE_META_CACHE_TTL = 300
    MAX_REQUEST_BYTES = 1024 * 1024
    MAX_INSTANCE_BATCH = 200
    MAX_METRICS_PER_INSTANCE = 200

    @staticmethod
    def get_team_secret(username: str, domain: str, team: int):
        return UserAPISecret._default_manager.filter(username=username, domain=domain, team=team).order_by("id").first()

    @staticmethod
    def get_custom_template_document(plugin: MonitorPlugin, team: int, user):
        plugin_qs = MonitorPlugin._default_manager.filter(pk=getattr(plugin, "pk", None))
        metrics = list(
            Metric._default_manager.filter(monitor_plugin=plugin)
            .order_by("sort_order", "id")
            .values("name", "display_name", "description", "unit", "data_type", "dimensions")
        )
        monitor_objects = plugin_qs.values_list("monitor_object__id", flat=True)
        instances = list(
            MonitorInstance._default_manager.filter(monitor_object_id__in=monitor_objects, is_deleted=False)
            .order_by("name")
            .values("id", "name")[:200]
        )
        token = PushAPIService.get_team_secret(user.username, user.domain, team)

        return {
            "template_id": plugin.template_id,
            "display_name": plugin.display_name or plugin.name,
            "plugin_id": getattr(plugin, "pk", None),
            "description": plugin.description,
            "team": team,
            "api_secret": token.api_secret if token else "",
            "api_secret_exists": bool(token),
            "metrics": metrics,
            "monitor_object_ids": list(monitor_objects),
            "instances": [{"instance_id": item["id"], "instance_name": item["name"]} for item in instances],
            "endpoint": "/api/v1/monitor/open_api/push_api/report/",
            "payload_example": {
                "template_id": plugin.template_id,
                "organization": team,
                "timestamp": 1710000000,
                "instances": [
                    {
                        "instance_id": instances[0]["id"] if instances else '("demo-instance")',
                        "metrics": [
                            {
                                "name": metrics[0]["name"] if metrics else "demo_metric",
                                "value": 1,
                                "tags": {},
                            }
                        ],
                    }
                ],
            },
        }

    @staticmethod
    def get_secret_preview(username: str, domain: str, team: int):
        secret = PushAPIService.get_team_secret(username, domain, team)
        if not secret:
            return {"exists": False, "team": team, "api_secret": ""}
        return {"exists": True, "team": team, "api_secret": secret.api_secret}

    @staticmethod
    def resolve_team(team) -> int:
        try:
            return int(team)
        except (TypeError, ValueError) as exc:
            raise BaseAppException("Invalid team") from exc

    @staticmethod
    def resolve_current_team(request) -> int:
        current_team = request.COOKIES.get("current_team", "0")
        try:
            return int(current_team)
        except (TypeError, ValueError) as exc:
            raise BaseAppException("Invalid current_team") from exc

    @staticmethod
    def get_template(plugin_id: int) -> MonitorPlugin:
        plugin = MonitorPlugin._default_manager.filter(id=plugin_id, template_type="custom_api").first()
        if not plugin:
            raise BaseAppException("模板不存在")
        return plugin

    @staticmethod
    def validate_report_payload(payload: dict):
        template_id = payload.get("template_id")
        instances = payload.get("instances") or []
        timestamp = payload.get("timestamp")
        if not template_id:
            raise BaseAppException("template_id不能为空")
        if not isinstance(instances, list) or not instances:
            raise BaseAppException("instances不能为空")
        if timestamp in (None, ""):
            raise BaseAppException("timestamp不能为空")

    @staticmethod
    def validate_enqueue_payload(payload: dict):
        PushAPIService.validate_report_payload(payload)
        instances = payload.get("instances") or []
        if len(instances) > PushAPIService.MAX_INSTANCE_BATCH:
            raise BaseAppException(f"instances数量不能超过{PushAPIService.MAX_INSTANCE_BATCH}")
        for inst in instances:
            metrics = inst.get("metrics") or []
            if metrics and len(metrics) > PushAPIService.MAX_METRICS_PER_INSTANCE:
                raise BaseAppException(f"单实例metrics数量不能超过{PushAPIService.MAX_METRICS_PER_INSTANCE}")

    @staticmethod
    def validate_request_size(payload: dict):
        payload_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if payload_bytes > PushAPIService.MAX_REQUEST_BYTES:
            raise BaseAppException(f"请求体不能超过{PushAPIService.MAX_REQUEST_BYTES}字节")

    @staticmethod
    def _token_cache_key(token: str) -> str:
        token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"monitor:push_api:token_team:{token_digest}"

    @staticmethod
    def authenticate_token(token: str) -> int:
        if not token:
            raise BaseAppException("token不能为空")

        cache_key = PushAPIService._token_cache_key(token)
        cached_team = cache.get(cache_key)
        if cached_team:
            return int(cached_team)

        local_secret = UserAPISecret._default_manager.filter(api_secret=token).values("team").first()
        if local_secret:
            cache.set(cache_key, int(local_secret["team"]), timeout=PushAPIService.TOKEN_CACHE_TTL)
            return int(local_secret["team"])

        result = SystemMgmt().verify_token(token)
        if not isinstance(result, dict):
            raise BaseAppException("token校验失败")
        if not result.get("result"):
            raise BaseAppException("token校验失败")

        data = result.get("data") or {}
        group_list = data.get("group_list") or []
        if not group_list:
            raise BaseAppException("token未关联组织")

        first_group = group_list[0]
        if isinstance(first_group, dict):
            team = int(first_group.get("id") or 0)
        else:
            team = int(first_group)
        cache.set(cache_key, team, timeout=PushAPIService.TOKEN_CACHE_TTL)
        return team

    @staticmethod
    def authenticate_and_prepare_enqueue(payload: dict):
        PushAPIService.validate_request_size(payload)
        PushAPIService.validate_enqueue_payload(payload)
        token_team = PushAPIService.authenticate_token(payload.get("token", ""))
        request_digest = PushAPIService.build_request_id(payload)
        return {
            "template_id": payload["template_id"],
            "token_team": token_team,
            "request_id": request_digest,
        }

    @staticmethod
    def build_request_id(payload: dict) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    @staticmethod
    def _template_meta_cache_key(template_id: str) -> str:
        return f"monitor:push_api:template_meta:{template_id}"

    @staticmethod
    def get_template_meta(template_id: str):
        cache_key = PushAPIService._template_meta_cache_key(template_id)
        cached = cache.get(cache_key)
        if cached:
            return cached

        template = MonitorPlugin._default_manager.filter(template_id=template_id, template_type="custom_api").first()
        if not template:
            raise BaseAppException("模板不存在")

        allowed_object_ids = list(template.monitor_object.all().values_list("id", flat=True))
        metric_queryset = Metric._default_manager.filter(monitor_plugin=template, monitor_object__in=allowed_object_ids)
        metric_map = {
            item.name: {
                "name": item.name,
                "instance_id_keys": item.instance_id_keys or [],
            }
            for item in metric_queryset
        }

        meta = {
            "template_id": template.template_id,
            "allowed_object_ids": allowed_object_ids,
            "metric_map": metric_map,
        }
        cache.set(cache_key, meta, timeout=PushAPIService.TEMPLATE_META_CACHE_TTL)
        return meta

    @staticmethod
    def _to_ns(timestamp: Any) -> int:
        if timestamp in (None, ""):
            return 0
        ts = int(timestamp)
        if len(str(ts)) == 10:
            return ts * 1000000000
        if len(str(ts)) == 13:
            return ts * 1000000
        return ts

    @staticmethod
    def _normalize_measurement(name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_:.-]", "_", name)

    @staticmethod
    def build_line(metric_name: str, tags: dict, value: Any, timestamp: Any) -> str:
        measurement = PushAPIService._normalize_measurement(metric_name)
        tag_part = ",".join([f"{_escape_line_value(k)}={_escape_line_value(v)}" for k, v in tags.items() if v not in (None, "")])
        if isinstance(value, bool):
            field_value = "true" if value else "false"
        elif isinstance(value, int) and not isinstance(value, bool):
            field_value = f"{value}i"
        elif isinstance(value, float):
            field_value = str(value)
        else:
            field_value = f'"{_escape_field_string(value)}"'

        ts = PushAPIService._to_ns(timestamp)
        if tag_part:
            return f"{measurement},{tag_part} value={field_value} {ts}"
        return f"{measurement} value={field_value} {ts}"

    @staticmethod
    def _batch_load_instances(instance_ids: list[str]):
        instances = MonitorInstance._default_manager.filter(id__in=instance_ids, is_deleted=False)
        instance_map = {str(item.id): item for item in instances}
        org_pairs = MonitorInstanceOrganization._default_manager.filter(monitor_instance_id__in=instance_ids).values_list(
            "monitor_instance_id", "organization"
        )
        org_map: dict[str, set[int]] = {}
        for monitor_instance_id, organization in org_pairs:
            org_map.setdefault(str(monitor_instance_id), set()).add(int(organization))
        return instance_map, org_map

    @staticmethod
    def process_report_async(payload: dict, token_team: int):
        template_meta = PushAPIService.get_template_meta(payload["template_id"])
        allowed_object_ids = set(template_meta["allowed_object_ids"])
        metric_map = template_meta["metric_map"]

        instance_ids = [str(item.get("instance_id")) for item in payload.get("instances", []) if item.get("instance_id")]
        instance_map, org_map = PushAPIService._batch_load_instances(instance_ids)

        accepted_lines = []
        filtered_details = []
        accepted_instance_ids = set()

        for inst in payload.get("instances", []):
            instance_id = str(inst.get("instance_id") or "")
            if not instance_id:
                filtered_details.append({"instance_id": "", "reason": "instance_id不能为空"})
                continue

            instance = instance_map.get(instance_id)
            if not instance:
                filtered_details.append({"instance_id": instance_id, "reason": "实例不存在"})
                continue

            if instance.monitor_object_id not in allowed_object_ids:
                filtered_details.append({"instance_id": instance_id, "reason": "实例对象与模板不匹配"})
                continue

            if token_team not in org_map.get(instance_id, set()):
                filtered_details.append({"instance_id": instance_id, "reason": "实例组织与token组织不匹配"})
                continue

            metrics = inst.get("metrics") or []
            if not metrics:
                filtered_details.append({"instance_id": instance_id, "reason": "metrics不能为空"})
                continue

            valid_metric_found = False
            for metric in metrics:
                metric_name = metric.get("name")
                metric_meta = metric_map.get(metric_name)
                if not metric_meta:
                    filtered_details.append({"instance_id": instance_id, "reason": f"指标不存在: {metric_name}"})
                    continue

                tags = {
                    "instance_id": instance_id,
                    "template_id": template_meta["template_id"],
                    "organization": token_team,
                }
                for dim in metric_meta["instance_id_keys"]:
                    value = inst.get(dim)
                    if value not in (None, ""):
                        tags[dim] = value
                for key, value in (metric.get("tags") or {}).items():
                    tags[key] = value

                accepted_lines.append(
                    PushAPIService.build_line(
                        metric_name=metric_name,
                        tags=tags,
                        value=metric.get("value"),
                        timestamp=metric.get("timestamp") or payload.get("timestamp"),
                    )
                )
                valid_metric_found = True

            if valid_metric_found:
                accepted_instance_ids.add(instance_id)

        return {
            "template_id": template_meta["template_id"],
            "accepted_lines": accepted_lines,
            "accepted_count": len(accepted_instance_ids),
            "accepted_metric_count": len(accepted_lines),
            "filtered_count": len(filtered_details),
            "filtered_details": filtered_details,
        }

    @staticmethod
    async def publish_lines(subject: str, lines: list[str]):
        nc = await get_nc_client()
        try:
            for line in lines:
                await nc.publish(subject, line.encode("utf-8"))
        finally:
            await nc.close()

    @staticmethod
    def publish_lines_sync(subject: str, lines: list[str]):
        asyncio.run(PushAPIService.publish_lines(subject, lines))

    @staticmethod
    def build_publish_subject(template_id: str) -> str:
        prefix = os.getenv("NATS_METRIC_TOPIC", "metrics")
        return f"{prefix}.{template_id}"
