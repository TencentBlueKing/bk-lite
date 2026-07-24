from dataclasses import dataclass
from typing import Iterable

from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.monitor.models import CollectConfig, MonitorInstance, MonitorObjectOrganizationRule
from apps.monitor.services.flow_onboarding import FlowOnboardingService
from apps.monitor.services.policy_source_cleanup import cleanup_policy_sources
from apps.rpc.node_mgmt import NodeMgmt


@dataclass(frozen=True)
class RemovalResult:
    removed_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    cleaned_policy_ids: tuple[int, ...]
    disabled_policy_ids: tuple[int, ...]


class MonitorInstanceRemovalService:
    MAX_BATCH_SIZE = 500

    @classmethod
    def remove(cls, instance_ids: Iterable[str]) -> RemovalResult:
        normalized_ids = cls._normalize_ids(instance_ids)
        if not normalized_ids:
            return RemovalResult((), (), (), ())
        if len(normalized_ids) > cls.MAX_BATCH_SIZE:
            raise BaseAppException(f"单次最多删除 {cls.MAX_BATCH_SIZE} 个监控实例")

        try:
            with transaction.atomic():
                instances = list(
                    MonitorInstance.objects.select_for_update()
                    .filter(id__in=normalized_ids)
                    .only("id", "cloud_region_id", "enabled_protocols", "monitor_object__name")
                    .select_related("monitor_object")
                    .order_by("id")
                )
                existing_ids = {str(instance.id) for instance in instances}
                removed_ids = tuple(instance_id for instance_id in normalized_ids if instance_id in existing_ids)
                missing_ids = tuple(instance_id for instance_id in normalized_ids if instance_id not in existing_ids)

                config_rows = CollectConfig.objects.filter(monitor_instance_id__in=removed_ids).values_list("id", "is_child")
                child_config_ids = []
                base_config_ids = []
                for config_id, is_child in config_rows:
                    (child_config_ids if is_child else base_config_ids).append(config_id)

                if child_config_ids or base_config_ids:
                    node_mgmt = NodeMgmt()
                    if child_config_ids:
                        node_mgmt.delete_child_configs(child_config_ids)
                    if base_config_ids:
                        node_mgmt.delete_configs(base_config_ids)

                cleanup_result = cleanup_policy_sources(removed_ids)
                MonitorObjectOrganizationRule.objects.filter(monitor_instance_id__in=removed_ids).delete()

                refresh_region_ids = list(
                    dict.fromkeys(
                        instance.cloud_region_id
                        for instance in instances
                        if instance.cloud_region_id is not None
                        and instance.enabled_protocols
                        and instance.monitor_object.name in FlowOnboardingService.SUPPORTED_MONITOR_OBJECT_NAMES
                    )
                )
                MonitorInstance.objects.filter(id__in=removed_ids).delete()
                FlowOnboardingService._schedule_region_refresh(*refresh_region_ids)

            logger.info(f"物理删除监控实例成功: {list(removed_ids)}")
            return RemovalResult(
                removed_ids=removed_ids,
                missing_ids=missing_ids,
                cleaned_policy_ids=tuple(cleanup_result["policy_ids"]),
                disabled_policy_ids=tuple(cleanup_result["disabled_policy_ids"]),
            )
        except Exception as exc:
            logger.error(f"物理删除监控实例失败: {normalized_ids}", exc_info=True)
            raise BaseAppException("删除监控实例失败，请稍后重试") from exc

    @staticmethod
    def _normalize_ids(instance_ids: Iterable[str]) -> tuple[str, ...]:
        normalized_ids = []
        seen_ids = set()
        for value in instance_ids or []:
            if value in (None, ""):
                continue
            instance_id = str(value)
            if instance_id in seen_ids:
                continue
            seen_ids.add(instance_id)
            normalized_ids.append(instance_id)
        return tuple(normalized_ids)
