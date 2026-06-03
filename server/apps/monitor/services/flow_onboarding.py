from django.db import transaction
from django.db.models import Q

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.logger import monitor_logger as logger
from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObject, MonitorObjectOrganizationRule
from apps.monitor.services.flow_sampling import FlowSamplingService
from apps.monitor.services.manual_collect import ManualCollectService
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


class FlowOnboardingService:
    SUPPORTED_PROTOCOLS = {"netflow", "sflow"}
    SUPPORTED_MONITOR_OBJECT_NAMES = {"Switch", "Router", "Firewall", "Loadbalance"}
    DEFAULT_FALLBACK_SAMPLING_RATE = 1000
    ORGANIZATIONS_UNSET = object()
    DUPLICATE_NAME_MESSAGE = "实例名称已存在"

    @classmethod
    def create_or_bind_asset(
        cls,
        *,
        monitor_object_id,
        protocol,
        cloud_region_id,
        ip,
        name,
        organizations=ORGANIZATIONS_UNSET,
        instance_id=None,
        allow_deleted_instance_reuse=False,
        fallback_sampling_rate=None,
        conflict_permission_checker=None,
    ):
        cls._validate_protocol(protocol)
        organizations_provided = organizations is not cls.ORGANIZATIONS_UNSET
        organizations = list(organizations or []) if organizations_provided else None

        with transaction.atomic():
            cls.lock_monitor_object(
                monitor_object_id=monitor_object_id,
                require_supported=True,
            )
            instance, created = cls._resolve_instance(
                monitor_object_id=monitor_object_id,
                cloud_region_id=cloud_region_id,
                ip=ip,
                name=name,
                organizations=organizations,
                instance_id=instance_id,
                allow_deleted_instance_reuse=allow_deleted_instance_reuse,
            )
            previous_cloud_region_id = instance.cloud_region_id
            restoring_deleted = instance.is_deleted
            restored_organizations = None
            if restoring_deleted:
                restored_organizations = organizations if organizations_provided else cls._get_instance_organizations(instance.id)
            cls._ensure_tuple_available(
                cloud_region_id=cloud_region_id,
                ip=ip,
                exclude_instance_id=instance.id,
                conflict_permission_checker=conflict_permission_checker,
            )
            instance.fallback_sampling_rate = cls._resolve_sampling_rate(
                fallback_sampling_rate,
                instance.fallback_sampling_rate,
            )
            instance.enabled_protocols = cls._merge_protocols(instance.enabled_protocols, protocol)
            instance.auto = False
            if restoring_deleted:
                final_name = name if name is not None else instance.name
                cls._normalize_duplicate_name_conflict(
                    MonitorObjectService.validate_new_instance_name_unique,
                    instance.monitor_object_id,
                    final_name,
                )
                instance.name = final_name
            instance.is_deleted = False
            instance.cloud_region_id = cloud_region_id
            instance.ip = ip
            update_fields = [
                "cloud_region_id",
                "ip",
                "fallback_sampling_rate",
                "enabled_protocols",
                "auto",
                "is_deleted",
                "name",
            ]
            instance.save(update_fields=update_fields)
            if organizations_provided:
                MonitorObjectService.set_instances_organizations([instance.id], organizations)
            if organizations_provided and (restoring_deleted or not created):
                cls._restore_organization_rules(
                    monitor_object_id=instance.monitor_object_id,
                    instance_id=instance.id,
                    organizations=organizations,
                )
            elif restoring_deleted:
                cls._restore_organization_rules(
                    monitor_object_id=instance.monitor_object_id,
                    instance_id=instance.id,
                    organizations=restored_organizations,
                )
            cls._schedule_region_refresh(previous_cloud_region_id, instance.cloud_region_id)

        return {"instance_id": instance.id, "enabled_protocols": instance.enabled_protocols}

    @classmethod
    def update_asset(
        cls,
        *,
        instance_id,
        name=None,
        organizations=None,
        cloud_region_id=None,
        ip=None,
        fallback_sampling_rate=None,
        conflict_permission_checker=None,
    ):
        with transaction.atomic():
            instance = cls._get_instance(instance_id=instance_id)
            cls.lock_monitor_object(monitor_object_id=instance.monitor_object_id, require_supported=True)
            instance = cls._get_instance(instance_id=instance_id, for_update=True)
            previous_cloud_region_id = instance.cloud_region_id
            target_cloud_region_id = cloud_region_id if cloud_region_id is not None else instance.cloud_region_id
            target_ip = ip if ip is not None else instance.ip
            target_fallback_sampling_rate = cls._resolve_sampling_rate(
                fallback_sampling_rate,
                instance.fallback_sampling_rate,
            )
            cls._ensure_tuple_available(
                cloud_region_id=target_cloud_region_id,
                ip=target_ip,
                exclude_instance_id=instance.id,
                conflict_permission_checker=conflict_permission_checker,
            )
            cls._normalize_duplicate_name_conflict(
                ManualCollectService.update_manual_collect_instance,
                instance_id=instance_id,
                name=name,
                organizations=organizations,
                cloud_region_id=cloud_region_id,
                ip=ip,
                fallback_sampling_rate=fallback_sampling_rate,
                auto=False,
            )
            if organizations is not None:
                cls._restore_organization_rules(
                    monitor_object_id=instance.monitor_object_id,
                    instance_id=instance.id,
                    organizations=organizations,
                )
            if (
                target_cloud_region_id != previous_cloud_region_id
                or target_ip != instance.ip
                or target_fallback_sampling_rate != instance.fallback_sampling_rate
            ):
                cls._schedule_region_refresh(previous_cloud_region_id, target_cloud_region_id)
        return {"instance_id": instance_id}

    @classmethod
    def _resolve_instance(
        cls,
        *,
        monitor_object_id,
        cloud_region_id,
        ip,
        name,
        organizations,
        instance_id=None,
        allow_deleted_instance_reuse=False,
    ):
        if instance_id:
            return cls._get_instance(
                instance_id=instance_id,
                monitor_object_id=monitor_object_id,
                for_update=True,
                include_deleted=allow_deleted_instance_reuse,
            ), False

        instance = cls.find_reusable_asset(
            monitor_object_id=monitor_object_id,
            cloud_region_id=cloud_region_id,
            ip=ip,
            for_update=True,
        )
        if instance:
            return instance, False

        result = cls._normalize_duplicate_name_conflict(
            ManualCollectService.create_manual_collect_instance,
            {
                "id": cls._build_asset_key(monitor_object_id, cloud_region_id, ip),
                "name": name,
                "monitor_object_id": monitor_object_id,
                "cloud_region_id": cloud_region_id,
                "ip": ip,
                "fallback_sampling_rate": cls._resolve_sampling_rate(fallback_sampling_rate=None),
                "enabled_protocols": [],
                "organizations": organizations or [],
            },
            allow_flow_fields=True,
        )
        return MonitorInstance.objects.get(id=result["instance_id"]), True

    @classmethod
    def find_existing_asset(cls, *, monitor_object_id, cloud_region_id, ip, is_deleted=False, for_update=False):
        queryset = MonitorInstance.objects.filter(
            monitor_object_id=monitor_object_id,
            cloud_region_id=cloud_region_id,
            ip=ip,
            is_deleted=is_deleted,
        ).order_by("created_at")
        if for_update:
            queryset = queryset.select_for_update()
        return queryset.first()

    @classmethod
    def find_reusable_asset(cls, *, monitor_object_id, cloud_region_id, ip, for_update=False):
        instance = cls.find_existing_asset(
            monitor_object_id=monitor_object_id,
            cloud_region_id=cloud_region_id,
            ip=ip,
            for_update=for_update,
        )
        if instance:
            return instance
        return cls.find_existing_asset(
            monitor_object_id=monitor_object_id,
            cloud_region_id=cloud_region_id,
            ip=ip,
            is_deleted=True,
            for_update=for_update,
        )

    @classmethod
    def _get_instance(cls, *, instance_id, monitor_object_id=None, for_update=False, include_deleted=False):
        filters = {
            "id": instance_id,
        }
        if not include_deleted:
            filters["is_deleted"] = False
        if monitor_object_id is not None:
            filters["monitor_object_id"] = monitor_object_id
        queryset = MonitorInstance.objects.filter(**filters)
        if for_update:
            queryset = queryset.select_for_update()
        instance = queryset.first()
        if not instance:
            raise ValidationAppException("Monitor instance does not exist")
        return instance

    @classmethod
    def validate_instance_id(cls, *, instance_id):
        cls._get_instance(instance_id=instance_id)
        return instance_id

    @classmethod
    def find_tuple_conflict(cls, *, cloud_region_id, ip, exclude_instance_id=None, for_update=False):
        if cloud_region_id is None or not ip:
            return None
        duplicates = (
            MonitorInstance.objects.filter(
                cloud_region_id=cloud_region_id,
                ip=ip,
                is_deleted=False,
                monitor_object__name__in=cls.SUPPORTED_MONITOR_OBJECT_NAMES,
            )
            .order_by("created_at", "id")
        )
        if exclude_instance_id is not None:
            duplicates = duplicates.exclude(id=exclude_instance_id)
        if for_update:
            duplicates = duplicates.select_for_update()
        return duplicates.first()

    @classmethod
    def _ensure_tuple_available(cls, *, cloud_region_id, ip, exclude_instance_id=None, conflict_permission_checker=None):
        duplicate = cls.find_tuple_conflict(
            cloud_region_id=cloud_region_id,
            ip=ip,
            exclude_instance_id=exclude_instance_id,
            for_update=True,
        )
        if duplicate:
            if conflict_permission_checker is not None:
                conflict_permission_checker(duplicate)
            raise ValidationAppException("Flow asset already exists")

    @classmethod
    def _normalize_duplicate_name_conflict(cls, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except BaseAppException as exc:
            if exc.message == cls.DUPLICATE_NAME_MESSAGE:
                raise ValidationAppException(exc.message) from exc
            raise

    @staticmethod
    def _get_instance_organizations(instance_id):
        return list(
            MonitorInstanceOrganization.objects.filter(monitor_instance_id=instance_id).values_list("organization", flat=True)
        )

    @staticmethod
    def _restore_organization_rules(*, monitor_object_id, instance_id, organizations):
        MonitorObjectOrganizationRule.objects.filter(monitor_instance_id=instance_id).delete()
        ManualCollectService.create_organization_rule_by_child_object(
            monitor_object_id,
            instance_id,
            organizations or [],
        )

    @classmethod
    def lock_monitor_object(cls, *, monitor_object_id, require_supported=True):
        locked_objects = list(
            MonitorObject.objects.select_for_update()
            .filter(Q(id=monitor_object_id) | Q(name__in=cls.SUPPORTED_MONITOR_OBJECT_NAMES))
            .order_by("id")
            .values("id", "name")
        )
        monitor_object_name = next(
            (monitor_object["name"] for monitor_object in locked_objects if monitor_object["id"] == monitor_object_id),
            None,
        )
        if not monitor_object_name:
            raise ValidationAppException("Monitor object does not exist")
        if require_supported and monitor_object_name not in cls.SUPPORTED_MONITOR_OBJECT_NAMES:
            raise ValidationAppException("Unsupported flow monitor object")
        return monitor_object_name

    @classmethod
    def _validate_protocol(cls, protocol):
        if protocol not in cls.SUPPORTED_PROTOCOLS:
            raise ValidationAppException("Unsupported flow protocol")

    @classmethod
    def _normalize_protocols(cls, protocols):
        normalized_protocols = []
        for protocol in protocols:
            cls._validate_protocol(protocol)
            if protocol not in normalized_protocols:
                normalized_protocols.append(protocol)
        return normalized_protocols

    @classmethod
    def _merge_protocols(cls, current_protocols, protocol):
        return sorted(set(cls._normalize_protocols(current_protocols or [])) | {protocol})

    @classmethod
    def detect_status(cls, *, instance_id, protocol, monitor_object_id, time_window="5m"):
        cls._validate_protocol(protocol)
        instance = cls._get_instance(
            instance_id=instance_id,
            monitor_object_id=monitor_object_id,
        )
        query = f"any({{instance_id='{parse_instance_id(instance.id)[0]}', collect_type='{protocol}'}}[{time_window}])"
        result = VictoriaMetricsAPI().query(query).get("data", {}).get("result", [])
        normalized_payload = FlowSamplingService.normalize_payload(
            result[0].get("metric", {}) if result else {},
            fallback_sampling_rate=instance.fallback_sampling_rate,
        )
        return {
            "success": bool(result),
            "protocol": protocol,
            "instance_id": instance_id,
            "last_seen_at": result[0]["value"][0] if result else None,
            "effective_sampling_rate": normalized_payload["effective_sampling_rate"],
            "sampling_rate_source": normalized_payload["sampling_rate_source"],
        }

    @classmethod
    def _resolve_sampling_rate(cls, fallback_sampling_rate, current_value=None):
        if fallback_sampling_rate is not None:
            return fallback_sampling_rate
        if current_value is not None:
            return current_value
        return cls.DEFAULT_FALLBACK_SAMPLING_RATE

    @staticmethod
    def _build_asset_key(monitor_object_id, cloud_region_id, ip):
        return f"flow:{monitor_object_id}:{cloud_region_id}:{ip}"

    @staticmethod
    def _schedule_region_refresh(*cloud_region_ids):
        target_region_ids = sorted({region_id for region_id in cloud_region_ids if region_id is not None})
        if not target_region_ids:
            return

        def _refresh():
            from apps.monitor.services.flow_env_config import FlowEnvConfigService

            for region_id in target_region_ids:
                try:
                    FlowEnvConfigService.refresh_collect_configs(cloud_region_id=region_id)
                except Exception:
                    logger.exception("刷新 Flow env_config 失败: cloud_region_id=%s", region_id)

        transaction.on_commit(_refresh)
