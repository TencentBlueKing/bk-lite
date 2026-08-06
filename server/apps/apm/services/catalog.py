from collections.abc import Sequence
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.apm.models import ApmApplication, ApmService, ApmServiceInstance, ApmServiceInstanceOrganization, ApmServiceOrganization
from apps.apm.services.contracts import CatalogDiscovery, CatalogDiscoveryResult
from apps.apm.services.identity import normalize_identity
from apps.apm.services.status import ARCHIVE_WINDOW


class InvalidCatalogIdentity(ValueError):
    """单条遥测身份无法安全映射到目录字段。"""

    def __init__(self, field: str, reason: str, *, length: int | None = None, limit: int | None = None):
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason
        self.length = length
        self.limit = limit


def _validate_identity(value: str | None, *, field: str, max_length: int, required: bool = False) -> str:
    if value is not None and not isinstance(value, str):
        raise InvalidCatalogIdentity(field, "invalid_type")
    raw = value or ""
    if len(raw) > max_length:
        raise InvalidCatalogIdentity(field, "raw_too_long", length=len(raw), limit=max_length)
    normalized = normalize_identity(raw)
    if len(normalized) > max_length:
        raise InvalidCatalogIdentity(field, "normalized_too_long", length=len(normalized), limit=max_length)
    if required and not normalized:
        raise InvalidCatalogIdentity(field, "empty")
    return normalized


def _organization_ids(values: Sequence[int]) -> tuple[int, ...]:
    result = tuple(sorted({int(item) for item in values}))
    if not result:
        raise ValueError("至少需要一个组织")
    return result


class DjangoTelemetryCatalogService:
    """目录深模块；身份、继承和首次实例规则集中在此 seam 后。"""

    @transaction.atomic
    def discover(self, discovery: CatalogDiscovery) -> CatalogDiscoveryResult:
        normalized_namespace = _validate_identity(
            discovery.service_namespace,
            field="service.namespace",
            max_length=256,
        )
        normalized_name = _validate_identity(
            discovery.service_name,
            field="service.name",
            max_length=256,
            required=True,
        )
        normalized_instance_id = _validate_identity(
            discovery.instance_id,
            field="service.instance.id",
            max_length=512,
        )
        normalized_environment = _validate_identity(
            discovery.environment,
            field="deployment.environment",
            max_length=256,
        )
        normalized_version = _validate_identity(
            discovery.version,
            field="service.version",
            max_length=256,
        )
        seen_at = discovery.seen_at or timezone.now()
        application = ApmApplication.objects.select_for_update().get(
            application_id=normalized_namespace,
        )
        missing_instance_identity = not normalized_instance_id
        application_organizations = tuple(application.organization_links.order_by("organization").values_list("organization", flat=True))
        if not application_organizations:
            raise ValueError("应用没有默认组织")

        service, service_created = ApmService.objects.get_or_create(
            normalized_namespace=normalized_namespace,
            normalized_name=normalized_name,
            defaults={
                "namespace": discovery.service_namespace or "",
                "application": application,
                "name": discovery.service_name,
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
            },
        )
        if service_created:
            ApmServiceOrganization.objects.bulk_create(
                [ApmServiceOrganization(service=service, organization=organization) for organization in application_organizations]
            )
        elif service.application_id is None:
            service.application = application
            service.save(update_fields=("application", "updated_at"))
        if not service_created and (
            seen_at > service.last_seen_at
            or (service.archived_at is not None and service.archive_reason == "silent_timeout" and seen_at >= service.last_seen_at)
        ):
            service.last_seen_at = max(seen_at, service.last_seen_at)
            update_fields = ["last_seen_at"]
            if service.archived_at is not None and service.archive_reason == "silent_timeout":
                service.archived_at = None
                service.archive_reason = ""
                update_fields.extend(("archived_at", "archive_reason"))
            service.save(update_fields=(*update_fields, "updated_at"))

        if missing_instance_identity:
            return CatalogDiscoveryResult(
                service=service,
                instance=None,
                missing_instance_identity=True,
            )

        instance, instance_created = ApmServiceInstance.objects.get_or_create(
            service=service,
            normalized_instance_id=normalized_instance_id,
            defaults={
                "instance_id": discovery.instance_id or "",
                "environment": normalized_environment,
                "version": normalized_version,
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
                    for organization in application_organizations
                ]
            )
        else:
            update_fields: list[str] = []
            is_latest_observation = seen_at >= instance.last_seen_at
            if seen_at > instance.last_seen_at:
                instance.last_seen_at = seen_at
                update_fields.append("last_seen_at")
            if is_latest_observation:
                for field, value in (
                    ("environment", normalized_environment),
                    ("version", normalized_version),
                ):
                    if getattr(instance, field) != value:
                        setattr(instance, field, value)
                        update_fields.append(field)
            if instance.archived_at is not None and instance.archive_reason == "silent_timeout" and is_latest_observation:
                instance.archived_at = None
                instance.archive_reason = ""
                update_fields.extend(("archived_at", "archive_reason"))
            if update_fields:
                instance.save(update_fields=(*update_fields, "updated_at"))
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
