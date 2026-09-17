from collections.abc import Iterable, Sequence
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.apm.models import (
    ApmApplication,
    ApmApplicationOrganization,
    ApmService,
    ApmServiceOrganization,
    ApmServiceInstance,
    ApmServiceInstanceOrganization,
)
from apps.apm.services.identity import normalize_identity

_ORGANIZATION_SYNC_CHUNK_SIZE = 500


def _organization_ids(values: Sequence[int]) -> tuple[int, ...]:
    result = tuple(sorted({int(item) for item in values}))
    if not result:
        raise ValueError("应用至少需要一个组织")
    return result


def _id_chunks(values: Sequence[UUID], size: int = _ORGANIZATION_SYNC_CHUNK_SIZE) -> Iterable[Sequence[UUID]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


class DjangoApmApplicationService:
    """维护应用及其默认组织边界；服务与实例本身仍只能由遥测发现。"""

    @transaction.atomic
    def create(
        self,
        *,
        application_id: str,
        name: str,
        description: str,
        organization_ids: Sequence[int],
        actor: str,
    ) -> ApmApplication:
        organizations = _organization_ids(organization_ids)
        application = ApmApplication.objects.create(
            application_id=normalize_identity(application_id),
            name=normalize_identity(name),
            description=description.strip(),
            created_by=actor,
            updated_by=actor,
        )
        self._replace_organizations(application, organizations, actor=actor)
        return application

    @transaction.atomic
    def update(
        self,
        application_id: UUID,
        *,
        name: str,
        description: str,
        organization_ids: Sequence[int],
        actor: str,
    ) -> ApmApplication:
        organizations = _organization_ids(organization_ids)
        application = ApmApplication.objects.select_for_update().get(id=application_id)
        application.name = normalize_identity(name)
        application.description = description.strip()
        application.updated_by = actor
        application.save(update_fields=("name", "description", "updated_by", "updated_at"))
        self._replace_organizations(application, organizations, actor=actor)
        return application

    @staticmethod
    def _replace_organizations(
        application: ApmApplication,
        organizations: Sequence[int],
        *,
        actor: str,
    ) -> None:
        target = tuple(organizations)
        current = set(
            ApmApplicationOrganization.objects.filter(application=application).values_list("organization", flat=True)
        )
        added = tuple(organization for organization in target if organization not in current)
        removed = tuple(organization for organization in current if organization not in set(target))
        if not added and not removed:
            return

        if removed:
            ApmApplicationOrganization.objects.filter(application=application, organization__in=removed).delete()
        if added:
            ApmApplicationOrganization.objects.bulk_create(
                [
                    ApmApplicationOrganization(
                        application=application,
                        organization=organization,
                        created_by=actor,
                        updated_by=actor,
                    )
                    for organization in added
                ]
            )

        service_ids = list(
            ApmService.objects.select_for_update().filter(application=application).values_list("id", flat=True)
        )
        for service_id_chunk in _id_chunks(service_ids):
            if removed:
                ApmServiceOrganization.objects.filter(service_id__in=service_id_chunk, organization__in=removed).delete()
            if added:
                ApmServiceOrganization.objects.bulk_create(
                    [
                        ApmServiceOrganization(
                            service_id=service_id,
                            organization=organization,
                            created_by=actor,
                            updated_by=actor,
                        )
                        for service_id in service_id_chunk
                        for organization in added
                    ],
                    ignore_conflicts=True,
                )

        inherited_instance_ids = list(
            ApmServiceInstance.objects.select_for_update()
            .filter(
                service__application=application,
                permission_mode=ApmServiceInstance.PermissionMode.INHERITED,
            )
            .values_list("id", flat=True)
        )
        for instance_id_chunk in _id_chunks(inherited_instance_ids):
            if removed:
                ApmServiceInstanceOrganization.objects.filter(
                    instance_id__in=instance_id_chunk,
                    organization__in=removed,
                ).delete()
            if added:
                ApmServiceInstanceOrganization.objects.bulk_create(
                    [
                        ApmServiceInstanceOrganization(
                            instance_id=instance_id,
                            organization=organization,
                            created_by=actor,
                            updated_by=actor,
                        )
                        for instance_id in instance_id_chunk
                        for organization in added
                    ],
                    ignore_conflicts=True,
                )

    @transaction.atomic
    def delete(self, application_id: UUID, *, actor: str) -> None:
        application = ApmApplication.objects.select_for_update().get(id=application_id)
        if application.is_builtin:
            raise ValueError("内置应用不可删除")
        services = list(ApmService.objects.select_for_update().filter(application=application))
        if services:
            ApmService.objects.filter(id__in=[service.id for service in services]).update(
                application=None,
                updated_by=actor,
                updated_at=timezone.now(),
            )
        application.delete()
