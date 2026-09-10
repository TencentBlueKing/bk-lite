from apps.apm.models import ApmApplication, ApmPolicy, ApmPolicyOrganization
from apps.apm.services import DjangoApmApplicationService


def create_application(
    application_id: str = "shop",
    organizations: tuple[int, ...] = (10,),
) -> ApmApplication:
    return DjangoApmApplicationService().create(
        application_id=application_id,
        name=f"{application_id} application",
        description="",
        organization_ids=organizations,
        actor="tester",
    )


def bind_policy_organizations(policy: ApmPolicy, organizations: tuple[int, ...] | None = None) -> ApmPolicy:
    organization_ids = organizations
    if organization_ids is None:
        organization_ids = tuple(policy.service.organization_links.values_list("organization", flat=True))
    ApmPolicyOrganization.objects.bulk_create(
        [
            ApmPolicyOrganization(policy=policy, organization=organization)
            for organization in organization_ids
        ],
        ignore_conflicts=True,
    )
    return policy
