from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorInstance
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
            instance = cls._resolve_instance(
                monitor_object_id=monitor_object_id,
                cloud_region_id=cloud_region_id,
                ip=ip,
                name=name,
                organizations=organizations,
                instance_id=instance_id,
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
            instance = MonitorInstance.objects.filter(
                id=instance_id,
                monitor_object_id=monitor_object_id,
                is_deleted=False,
            ).first()
            if not instance:
                raise BaseAppException("Monitor instance does not exist")
            return instance

        instance = cls._find_existing_asset(
            monitor_object_id=monitor_object_id,
            cloud_region_id=cloud_region_id,
            ip=ip,
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
            }
        )
        return MonitorInstance.objects.get(id=result["instance_id"])

    @classmethod
    def _find_existing_asset(cls, *, monitor_object_id, cloud_region_id, ip):
        return (
            MonitorInstance.objects.filter(
                monitor_object_id=monitor_object_id,
                cloud_region_id=cloud_region_id,
                ip=ip,
                is_deleted=False,
            )
            .order_by("created_at")
            .first()
        )

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
