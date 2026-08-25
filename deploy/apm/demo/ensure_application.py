from apps.apm.models import ApmApplication
from apps.apm.services import DjangoApmApplicationService


application_id = "apm-demo-shop"
service = DjangoApmApplicationService()
application = ApmApplication.objects.filter(application_id=application_id).first()
if application is None:
    application = service.create(
        application_id=application_id,
        name="本机 APM 演示商城",
        description="由 deploy/apm/demo 产生真实 OpenTelemetry 调用链。",
        organization_ids=(1,),
        actor="apm-demo",
    )
    action = "created"
else:
    application = service.update(
        application.id,
        name="本机 APM 演示商城",
        description="由 deploy/apm/demo 产生真实 OpenTelemetry 调用链。",
        organization_ids=(1,),
        actor="apm-demo",
    )
    action = "updated"

print({"application": application.application_id, "action": action})
