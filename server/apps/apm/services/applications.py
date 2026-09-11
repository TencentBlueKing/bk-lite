from collections.abc import Sequence
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


def _organization_ids(values: Sequence[int]) -> tuple[int, ...]:
    result = tuple(sorted({int(item) for item in values}))
    if not result:
        raise ValueError("应用至少需要一个组织")
    return result


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
        ApmApplicationOrganization.objects.filter(application=application).delete()
        ApmApplicationOrganization.objects.bulk_create(
            [
                ApmApplicationOrganization(
                    application=application,
                    organization=organization,
                    created_by=actor,
                    updated_by=actor,
                )
                for organization in organizations
            ]
        )

        services = list(ApmService.objects.select_for_update().filter(application=application))
        ApmServiceOrganization.objects.filter(service__in=services).delete()
        ApmServiceOrganization.objects.bulk_create(
            [
                ApmServiceOrganization(
                    service=service,
                    organization=organization,
                    created_by=actor,
                    updated_by=actor,
                )
                for service in services
                for organization in organizations
            ],
            ignore_conflicts=True,
        )

        inherited_instances = list(
            ApmServiceInstance.objects.select_for_update().filter(
                service__application=application,
                permission_mode=ApmServiceInstance.PermissionMode.INHERITED,
            )
        )
        ApmServiceInstanceOrganization.objects.filter(instance__in=inherited_instances).delete()
        ApmServiceInstanceOrganization.objects.bulk_create(
            [
                ApmServiceInstanceOrganization(
                    instance=instance,
                    organization=organization,
                    created_by=actor,
                    updated_by=actor,
                )
                for instance in inherited_instances
                for organization in organizations
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
