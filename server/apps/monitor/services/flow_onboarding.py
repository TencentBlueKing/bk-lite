from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorInstance, MonitorObject
from apps.monitor.services.manual_collect import ManualCollectService
from apps.monitor.services.monitor_object import MonitorObjectService


class FlowOnboardingService:
    SUPPORTED_PROTOCOLS = {"netflow", "sflow"}
    DEFAULT_FALLBACK_SAMPLING_RATE = 1000

    @classmethod
    def create_or_bind_asset(
        cls,
        *,
        monitor_object_id,
        protocol,
        cloud_region_id,
        ip,
        name,
        organizations,
        instance_id=None,
        fallback_sampling_rate=None,
    ):
        cls._validate_protocol(protocol)
        organizations = organizations or []

        with transaction.atomic():
            cls.lock_monitor_object(monitor_object_id=monitor_object_id)
            instance = cls._resolve_instance(
                monitor_object_id=monitor_object_id,
                cloud_region_id=cloud_region_id,
                ip=ip,
                name=name,
                organizations=organizations,
                instance_id=instance_id,
            )
            cls._ensure_tuple_available(
                monitor_object_id=monitor_object_id,
                cloud_region_id=cloud_region_id,
                ip=ip,
                exclude_instance_id=instance.id,
            )
            instance.fallback_sampling_rate = cls._resolve_sampling_rate(
                fallback_sampling_rate,
                instance.fallback_sampling_rate,
            )
            instance.enabled_protocols = cls._merge_protocols(instance.enabled_protocols, protocol)
            instance.auto = False
            instance.cloud_region_id = cloud_region_id
            instance.ip = ip
            instance.save(
                update_fields=[
                    "cloud_region_id",
                    "ip",
                    "fallback_sampling_rate",
                    "enabled_protocols",
                    "auto",
                ]
            )
            if organizations:
                MonitorObjectService.set_instances_organizations([instance.id], organizations)

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
        enabled_protocols=None,
    ):
        if enabled_protocols is not None:
            enabled_protocols = cls._normalize_protocols(enabled_protocols)

        with transaction.atomic():
            instance = cls._get_instance(instance_id=instance_id)
            cls.lock_monitor_object(monitor_object_id=instance.monitor_object_id)
            instance = cls._get_instance(instance_id=instance_id, for_update=True)
            cls._ensure_tuple_available(
                monitor_object_id=instance.monitor_object_id,
                cloud_region_id=cloud_region_id if cloud_region_id is not None else instance.cloud_region_id,
                ip=ip if ip is not None else instance.ip,
                exclude_instance_id=instance.id,
            )
            ManualCollectService.update_manual_collect_instance(
                instance_id=instance_id,
                name=name,
                organizations=organizations,
                cloud_region_id=cloud_region_id,
                ip=ip,
                fallback_sampling_rate=fallback_sampling_rate,
                enabled_protocols=enabled_protocols,
                auto=False,
            )
        return {"instance_id": instance_id}

    @classmethod
    def _resolve_instance(cls, *, monitor_object_id, cloud_region_id, ip, name, organizations, instance_id=None):
        if instance_id:
            return cls._get_instance(instance_id=instance_id, monitor_object_id=monitor_object_id, for_update=True)

        instance = cls.find_existing_asset(
            monitor_object_id=monitor_object_id,
            cloud_region_id=cloud_region_id,
            ip=ip,
            for_update=True,
        )
        if instance:
            return instance

        result = ManualCollectService.create_manual_collect_instance(
            {
                "id": cls._build_asset_key(cloud_region_id, ip),
                "name": name,
                "monitor_object_id": monitor_object_id,
                "cloud_region_id": cloud_region_id,
                "ip": ip,
                "fallback_sampling_rate": cls._resolve_sampling_rate(fallback_sampling_rate=None),
                "enabled_protocols": [],
                "organizations": organizations,
            },
            allow_flow_fields=True,
        )
        return MonitorInstance.objects.get(id=result["instance_id"])

    @classmethod
    def find_existing_asset(cls, *, monitor_object_id, cloud_region_id, ip, for_update=False):
        queryset = MonitorInstance.objects.filter(
            monitor_object_id=monitor_object_id,
            cloud_region_id=cloud_region_id,
            ip=ip,
            is_deleted=False,
        ).order_by("created_at")
        if for_update:
            queryset = queryset.select_for_update()
        return queryset.first()

    @classmethod
    def _get_instance(cls, *, instance_id, monitor_object_id=None, for_update=False):
        filters = {
            "id": instance_id,
            "is_deleted": False,
        }
        if monitor_object_id is not None:
            filters["monitor_object_id"] = monitor_object_id
        queryset = MonitorInstance.objects.filter(**filters)
        if for_update:
            queryset = queryset.select_for_update()
        instance = queryset.first()
        if not instance:
            raise BaseAppException("Monitor instance does not exist")
        return instance

    @classmethod
    def _ensure_tuple_available(cls, *, monitor_object_id, cloud_region_id, ip, exclude_instance_id=None):
        if cloud_region_id is None or not ip:
            return
        duplicates = MonitorInstance.objects.filter(
            monitor_object_id=monitor_object_id,
            cloud_region_id=cloud_region_id,
            ip=ip,
            is_deleted=False,
        )
        if exclude_instance_id is not None:
            duplicates = duplicates.exclude(id=exclude_instance_id)
        if duplicates.exists():
            raise BaseAppException("Flow asset already exists")

    @classmethod
    def lock_monitor_object(cls, *, monitor_object_id):
        exists = MonitorObject.objects.select_for_update().filter(id=monitor_object_id).exists()
        if not exists:
            raise BaseAppException("Monitor object does not exist")

    @classmethod
    def _validate_protocol(cls, protocol):
        if protocol not in cls.SUPPORTED_PROTOCOLS:
            raise BaseAppException("Unsupported flow protocol")

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
    def _resolve_sampling_rate(cls, fallback_sampling_rate, current_value=None):
        return fallback_sampling_rate or current_value or cls.DEFAULT_FALLBACK_SAMPLING_RATE

    @staticmethod
    def _build_asset_key(cloud_region_id, ip):
        return f"flow:{cloud_region_id}:{ip}"
