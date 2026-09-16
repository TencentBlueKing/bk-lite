from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.apm.models import (
    ApmApplication,
    ApmApplicationOrganization,
    ApmService,
    ApmServiceInstance,
    ApmServiceInstanceOrganization,
    ApmServiceOrganization,
)
from apps.apm.services.contracts import CatalogDiscovery, CatalogDiscoveryResult
from apps.apm.services.identity import normalize_identity


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


@dataclass
class _PreparedDiscovery:
    original: CatalogDiscovery
    namespace: str = ""
    name: str = ""
    instance_id: str = ""
    environment: str = ""
    version: str = ""
    language: str = ""
    seen_at: datetime | None = None
    missing_instance_identity: bool = False
    error: BaseException | None = None
    application: ApmApplication | None = None
    organizations: tuple[int, ...] = ()
    service: ApmService | None = None
    instance: ApmServiceInstance | None = None


def _prepare_discovery(discovery: CatalogDiscovery) -> _PreparedDiscovery:
    try:
        namespace = _validate_identity(discovery.service_namespace, field="service.namespace", max_length=256)
        name = _validate_identity(discovery.service_name, field="service.name", max_length=256, required=True)
        instance_id = _validate_identity(discovery.instance_id, field="service.instance.id", max_length=512)
        environment = _validate_identity(discovery.environment, field="deployment.environment", max_length=256)
        version = _validate_identity(discovery.version, field="service.version", max_length=256)
        language = _validate_identity(discovery.language, field="telemetry.sdk.language", max_length=64)
    except InvalidCatalogIdentity as exc:
        return _PreparedDiscovery(original=discovery, error=exc)
    return _PreparedDiscovery(
        original=discovery,
        namespace=namespace,
        name=name,
        instance_id=instance_id,
        environment=environment,
        version=version,
        language=language,
        seen_at=discovery.seen_at or timezone.now(),
        missing_instance_identity=not instance_id,
    )


class DjangoTelemetryCatalogService:
    """目录深模块；身份、继承和首次实例规则集中在此 seam 后。"""

    def discover(self, discovery: CatalogDiscovery) -> CatalogDiscoveryResult:
        outcome = self.discover_many((discovery,))[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    @transaction.atomic
    def discover_many(self, discoveries: Sequence[CatalogDiscovery]) -> list[CatalogDiscoveryResult | BaseException]:
        prepared = [_prepare_discovery(item) for item in discoveries]
        writable = [item for item in prepared if item.error is None]
        if writable:
            self._apply_batch(writable)
        outcomes: list[CatalogDiscoveryResult | BaseException] = []
        for item in prepared:
            if item.error is not None:
                outcomes.append(item.error)
                continue
            outcomes.append(
                CatalogDiscoveryResult(
                    service=item.service,
                    instance=item.instance,
                    missing_instance_identity=item.missing_instance_identity,
                )
            )
        return outcomes

    def _apply_batch(self, items: Sequence[_PreparedDiscovery]) -> None:
        now = timezone.now()
        namespaces = {item.namespace for item in items}
        applications = {
            application.application_id: application
            for application in ApmApplication.objects.select_for_update().filter(application_id__in=namespaces).order_by("application_id")
        }
        orgs_by_application_pk: dict[UUID, list[int]] = {}
        for organization, application_pk in (
            ApmApplicationOrganization.objects.filter(application__in=applications.values())
            .order_by("organization")
            .values_list("organization", "application_id")
        ):
            orgs_by_application_pk.setdefault(application_pk, []).append(organization)

        writable: list[_PreparedDiscovery] = []
        for item in items:
            application = applications.get(item.namespace)
            if application is None:
                item.error = ApmApplication.DoesNotExist()
                continue
            organizations = tuple(orgs_by_application_pk.get(application.id, ()))
            if not organizations:
                raise ValueError("应用没有默认组织")
            item.application = application
            item.organizations = organizations
            writable.append(item)
        if not writable:
            return

        service_keys = {(item.namespace, item.name) for item in writable}
        existing_services = {
            (service.normalized_namespace, service.normalized_name): service
            for service in ApmService.objects.select_for_update()
            .filter(
                normalized_namespace__in={key[0] for key in service_keys},
                normalized_name__in={key[1] for key in service_keys},
            )
            .order_by("normalized_namespace", "normalized_name")
        }
        created_services: dict[tuple[str, str], ApmService] = {}
        service_orgs: list[ApmServiceOrganization] = []
        for item in writable:
            key = (item.namespace, item.name)
            if key in existing_services or key in created_services:
                continue
            service = ApmService(
                namespace=item.original.service_namespace or "",
                normalized_namespace=item.namespace,
                application=item.application,
                name=item.original.service_name,
                normalized_name=item.name,
                language=item.language,
                first_seen_at=item.seen_at,
                last_seen_at=item.seen_at,
                created_at=now,
                updated_at=now,
            )
            created_services[key] = service
            service_orgs.extend(
                ApmServiceOrganization(service=service, organization=organization, created_at=now, updated_at=now)
                for organization in item.organizations
            )
        if created_services:
            ApmService.objects.bulk_create(created_services.values())
            ApmServiceOrganization.objects.bulk_create(service_orgs)

        services = existing_services | created_services
        dirty_services: dict[UUID, ApmService] = {}
        for item in writable:
            service = services[(item.namespace, item.name)]
            item.service = service
            changed = False
            if service.application_id is None:
                service.application = item.application
                changed = True
            if item.seen_at >= service.last_seen_at:
                if item.seen_at > service.last_seen_at:
                    service.last_seen_at = item.seen_at
                    changed = True
                if item.language and service.language != item.language:
                    service.language = item.language
                    changed = True
            if changed:
                service.updated_at = now
                dirty_services[service.id] = service
        if dirty_services:
            ApmService.objects.bulk_update(dirty_services.values(), ["application", "last_seen_at", "language", "updated_at"])

        instance_items = [item for item in writable if not item.missing_instance_identity]
        existing_instances = {
            (instance.service_id, instance.normalized_instance_id): instance
            for instance in ApmServiceInstance.objects.select_for_update()
            .filter(
                service_id__in={item.service.id for item in instance_items},
                normalized_instance_id__in={item.instance_id for item in instance_items},
            )
            .order_by("service_id", "normalized_instance_id")
        } if instance_items else {}
        created_instances: dict[tuple[UUID, str], ApmServiceInstance] = {}
        instance_orgs: list[ApmServiceInstanceOrganization] = []
        for item in instance_items:
            key = (item.service.id, item.instance_id)
            if key in existing_instances or key in created_instances:
                continue
            instance = ApmServiceInstance(
                service=item.service,
                instance_id=item.original.instance_id or "",
                normalized_instance_id=item.instance_id,
                environment=item.environment,
                version=item.version,
                first_seen_at=item.seen_at,
                last_seen_at=item.seen_at,
                created_at=now,
                updated_at=now,
            )
            created_instances[key] = instance
            instance_orgs.extend(
                ApmServiceInstanceOrganization(instance=instance, organization=organization, created_at=now, updated_at=now)
                for organization in item.organizations
            )
        if created_instances:
            ApmServiceInstance.objects.bulk_create(created_instances.values())
            ApmServiceInstanceOrganization.objects.bulk_create(instance_orgs)

        instances = existing_instances | created_instances
        dirty_instances: dict[UUID, ApmServiceInstance] = {}
        for item in instance_items:
            instance = instances[(item.service.id, item.instance_id)]
            item.instance = instance
            update_fields: list[str] = []
            is_latest_observation = item.seen_at >= instance.last_seen_at
            if item.seen_at > instance.last_seen_at:
                instance.last_seen_at = item.seen_at
                update_fields.append("last_seen_at")
            if is_latest_observation:
                for field, value in (("environment", item.environment), ("version", item.version)):
                    if getattr(instance, field) != value:
                        setattr(instance, field, value)
                        update_fields.append(field)
            if update_fields:
                instance.updated_at = now
                dirty_instances[instance.id] = instance
        if dirty_instances:
            ApmServiceInstance.objects.bulk_update(dirty_instances.values(), ["last_seen_at", "environment", "version", "updated_at"])

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
    def restore_service(self, service_id: UUID, *, actor: str) -> ApmService:
        service = ApmService.objects.select_for_update().get(id=service_id)
        service.archived_at = None
        service.archive_reason = ""
        service.updated_by = actor
        service.save(update_fields=("archived_at", "archive_reason", "updated_by", "updated_at"))
        return service
