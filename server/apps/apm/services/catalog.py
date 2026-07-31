from collections.abc import Sequence
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.apm.models import (
    ApmIngestSource,
    ApmService,
    ApmServiceInstance,
    ApmServiceInstanceOrganization,
    ApmServiceOrganization,
)
from apps.apm.services.contracts import CatalogDiscovery, CatalogDiscoveryResult
from apps.apm.services.identity import (
    normalize_identity,
    normalize_instance_identity,
    normalize_service_identity,
)
from apps.apm.services.status import ARCHIVE_WINDOW


def _organization_ids(values: Sequence[int]) -> tuple[int, ...]:
    result = tuple(sorted({int(item) for item in values}))
    if not result:
        raise ValueError("至少需要一个组织")
    return result


class DjangoTelemetryCatalogService:
    """目录深模块；身份、继承和首次实例规则集中在此 seam 后。"""

    @transaction.atomic
    def discover(self, discovery: CatalogDiscovery) -> CatalogDiscoveryResult:
        normalized_namespace, normalized_name = normalize_service_identity(
            discovery.service_namespace,
            discovery.service_name,
        )
        seen_at = discovery.seen_at or timezone.now()
        source = ApmIngestSource.objects.select_for_update().get(id=discovery.ingest_source_id)
        missing_instance_identity = not normalize_identity(discovery.instance_id)
        source_update_fields: list[str] = []
        if source.first_received_at is None or seen_at < source.first_received_at:
            source.first_received_at = seen_at
            source_update_fields.append("first_received_at")
        if source.last_received_at is None or seen_at > source.last_received_at:
            source.last_received_at = seen_at
            source_update_fields.append("last_received_at")
        if missing_instance_identity and (
            source.last_missing_instance_identity_at is None
            or seen_at > source.last_missing_instance_identity_at
        ):
            source.last_missing_instance_identity_at = seen_at
            source_update_fields.append("last_missing_instance_identity_at")
        if source_update_fields:
            source.save(update_fields=(*source_update_fields, "updated_at"))

        source_organizations = tuple(
            source.organization_links.order_by("organization").values_list("organization", flat=True)
        )
        if not source_organizations:
            raise ValueError("接入源没有默认组织")

        service, service_created = ApmService.objects.get_or_create(
            normalized_namespace=normalized_namespace,
            normalized_name=normalized_name,
            defaults={
                "namespace": discovery.service_namespace or "",
                "name": discovery.service_name,
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
            },
        )
        if service_created:
            ApmServiceOrganization.objects.bulk_create(
                [
                    ApmServiceOrganization(service=service, organization=organization)
                    for organization in source_organizations
                ]
            )
        elif seen_at > service.last_seen_at or (
            service.archived_at is not None and seen_at >= service.last_seen_at
        ):
            service.last_seen_at = max(seen_at, service.last_seen_at)
            service.archived_at = None
            service.archive_reason = ""
            service.save(update_fields=("last_seen_at", "archived_at", "archive_reason", "updated_at"))

        if missing_instance_identity:
            return CatalogDiscoveryResult(
                service=service,
                instance=None,
                missing_instance_identity=True,
            )

        normalized_instance_id = normalize_instance_identity(discovery.instance_id)
        instance, instance_created = ApmServiceInstance.objects.get_or_create(
            service=service,
            normalized_instance_id=normalized_instance_id,
            defaults={
                "instance_id": discovery.instance_id or "",
                "environment": normalize_identity(discovery.environment),
                "version": normalize_identity(discovery.version),
                "ingest_source": source,
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
            },
        )

        if instance_created:
            ApmServiceInstanceOrganization.objects.bulk_create(
                [
                    ApmServiceInstanceOrganization(
                        instance=instance,
                        organization=organization,
                    )
                    for organization in source_organizations
                ]
            )
        else:
            update_fields: list[str] = []
            is_latest_observation = seen_at >= instance.last_seen_at
            source_changed = is_latest_observation and instance.ingest_source_id != source.id
            if seen_at > instance.last_seen_at:
                instance.last_seen_at = seen_at
                update_fields.append("last_seen_at")
            if is_latest_observation:
                for field, value in (
                    ("environment", normalize_identity(discovery.environment)),
                    ("version", normalize_identity(discovery.version)),
                    ("ingest_source", source),
                ):
                    if getattr(instance, field) != value:
                        setattr(instance, field, value)
                        update_fields.append(field)
            if instance.archived_at is not None and is_latest_observation:
                instance.archived_at = None
                instance.archive_reason = ""
                update_fields.extend(("archived_at", "archive_reason"))
            if update_fields:
                instance.save(update_fields=(*update_fields, "updated_at"))
            if source_changed and instance.permission_mode == ApmServiceInstance.PermissionMode.INHERITED:
                ApmServiceInstanceOrganization.objects.filter(instance=instance).delete()
                ApmServiceInstanceOrganization.objects.bulk_create(
                    [
                        ApmServiceInstanceOrganization(instance=instance, organization=organization)
                        for organization in source_organizations
                    ]
                )

        return CatalogDiscoveryResult(service=service, instance=instance)

    @transaction.atomic
    def set_service_organizations(
        self,
        service_id: UUID,
        organization_ids: Sequence[int],
        *,
        actor: str,
    ) -> ApmService:
        organizations = _organization_ids(organization_ids)
        service = ApmService.objects.select_for_update().get(id=service_id)
        ApmServiceOrganization.objects.filter(service=service).delete()
        ApmServiceOrganization.objects.bulk_create(
            [
                ApmServiceOrganization(
                    service=service,
                    organization=organization,
                    created_by=actor,
                    updated_by=actor,
                )
                for organization in organizations
            ]
        )
        service.updated_by = actor
        service.save(update_fields=("updated_by", "updated_at"))
        return service

    @transaction.atomic
    def set_instance_organizations(
        self,
        instance_id: UUID,
        organization_ids: Sequence[int],
        *,
        actor: str,
    ) -> ApmServiceInstance:
        organizations = _organization_ids(organization_ids)
        instance = ApmServiceInstance.objects.select_for_update().get(id=instance_id)
        ApmServiceInstanceOrganization.objects.filter(instance=instance).delete()
        ApmServiceInstanceOrganization.objects.bulk_create(
            [
                ApmServiceInstanceOrganization(
                    instance=instance,
                    organization=organization,
                    created_by=actor,
                    updated_by=actor,
                )
                for organization in organizations
            ]
        )
        instance.permission_mode = ApmServiceInstance.PermissionMode.CUSTOM
        instance.updated_by = actor
        instance.save(update_fields=("permission_mode", "updated_by", "updated_at"))
        return instance

    @transaction.atomic
    def archive_service(self, service_id: UUID, *, reason: str, actor: str) -> ApmService:
        service = ApmService.objects.select_for_update().get(id=service_id)
        service.archived_at = timezone.now()
        service.archive_reason = reason
        service.updated_by = actor
        service.save(update_fields=("archived_at", "archive_reason", "updated_by", "updated_at"))
        return service

    @transaction.atomic
    def archive_instance(self, instance_id: UUID, *, reason: str, actor: str) -> ApmServiceInstance:
        instance = ApmServiceInstance.objects.select_for_update().get(id=instance_id)
        instance.archived_at = timezone.now()
        instance.archive_reason = reason
        instance.updated_by = actor
        instance.save(update_fields=("archived_at", "archive_reason", "updated_by", "updated_at"))
        return instance

    @transaction.atomic
    def restore_service(self, service_id: UUID, *, actor: str) -> ApmService:
        service = ApmService.objects.select_for_update().get(id=service_id)
        service.archived_at = None
        service.archive_reason = ""
        service.updated_by = actor
        service.save(update_fields=("archived_at", "archive_reason", "updated_by", "updated_at"))
        return service

    @transaction.atomic
    def restore_instance(self, instance_id: UUID, *, actor: str) -> ApmServiceInstance:
        instance = ApmServiceInstance.objects.select_for_update().get(id=instance_id)
        instance.archived_at = None
        instance.archive_reason = ""
        instance.updated_by = actor
        instance.save(update_fields=("archived_at", "archive_reason", "updated_by", "updated_at"))
        return instance

    @transaction.atomic
    def archive_stale(self, *, observed_at) -> tuple[int, int]:
        cutoff = observed_at - ARCHIVE_WINDOW
        instance_count = ApmServiceInstance.objects.filter(
            archived_at__isnull=True,
            last_seen_at__lte=cutoff,
        ).update(archived_at=observed_at, archive_reason="silent_timeout", updated_at=observed_at)
        service_count = ApmService.objects.filter(
            archived_at__isnull=True,
            last_seen_at__lte=cutoff,
        ).update(archived_at=observed_at, archive_reason="silent_timeout", updated_at=observed_at)
        return service_count, instance_count
