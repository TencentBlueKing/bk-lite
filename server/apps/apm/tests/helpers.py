from apps.apm.models import ApmApplication
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
