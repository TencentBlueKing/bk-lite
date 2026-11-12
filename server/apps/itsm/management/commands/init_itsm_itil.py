from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.models.maintainer_info import DEFAULT_MAINTAINER_DOMAIN, SYSTEM_MAINTAINER
from apps.itsm.flowable.bpmn_builder import build_bpmn
from apps.itsm.flowable.client import FlowableClient, FlowableError
from apps.itsm.models import Service, ServiceCalendar, ServiceCatalog, SLAPolicy, Workflow, WorkflowStage, WorkflowVersion

PACKS = (
    ("request", "请求管理", "itsm_request", 60, 480),
    ("incident", "事件管理", "itsm_incident", 30, 240),
    ("problem", "问题管理", "itsm_problem", 60, 480),
)

DESIGN = {
    "nodes": [
        {"id": "start", "type": "start", "name": "开始"},
        {"id": "submit", "type": "submit", "name": "提单"},
        {
            "id": "approve",
            "type": "approval",
            "name": "分派",
            "assignee": {"source": "users", "value": ["alice", "bob"]},
            "multi": {"mode": "any"},
            "fallback": "admin",
        },
        {"id": "handle", "type": "handle", "name": "处理", "assignee": {"source": "users", "value": ["handler"]}, "fallback": "admin"},
        {"id": "end", "type": "end", "name": "结束"},
    ],
    "edges": [
        {"from": "start", "to": "submit"},
        {"from": "submit", "to": "approve"},
        {"from": "approve", "to": "handle"},
        {"from": "handle", "to": "end"},
    ],
}


class Command(BaseCommand):
    help = "初始化事件和问题流程、服务以及 SLA"

    def handle(self, *args, **options):
        actor = {
            "created_by": SYSTEM_MAINTAINER,
            "updated_by": SYSTEM_MAINTAINER,
            "domain": DEFAULT_MAINTAINER_DOMAIN,
            "updated_by_domain": DEFAULT_MAINTAINER_DOMAIN,
        }
        calendar, _ = ServiceCalendar.objects.get_or_create(
            domain=DEFAULT_MAINTAINER_DOMAIN,
            name="工作日",
            defaults={"work_days": [1, 2, 3, 4, 5], "work_start": "09:00", "work_end": "18:00", **actor},
        )
        catalog, _ = ServiceCatalog.objects.get_or_create(domain=DEFAULT_MAINTAINER_DOMAIN, name="事件与问题", defaults=actor)
        client = None
        if settings.FLOWABLE_PASSWORD:
            client = FlowableClient(settings.FLOWABLE_URL, settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD)
        for _key, name, process_key, response_minutes, resolve_minutes in PACKS:
            workflow, _ = Workflow.objects.get_or_create(domain=DEFAULT_MAINTAINER_DOMAIN, key=process_key, defaults={"name": name, **actor})
            version = workflow.versions.order_by("-version_no").first()
            if version is None:
                version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design=DESIGN, **actor)
            xml = build_bpmn(version.design or DESIGN, process_key)
            if client:
                try:
                    deployed = client.deploy_bpmn(process_key, xml)
                except FlowableError as exc:
                    raise RuntimeError(f"{name} 部署失败") from exc
                version.bpmn_xml = xml
                version.flowable_deployment_id = str(deployed.get("id") or "")
                version.process_definition_key = process_key
                version.is_published = True
                version.save()
                workflow.current_version = version
                workflow.save(update_fields=["current_version", "updated_at"])
            Service.objects.get_or_create(
                domain=DEFAULT_MAINTAINER_DOMAIN,
                name=name,
                defaults={"catalog": catalog, "workflow": workflow, "is_hot": True, "description": name, **actor},
            )
            for order, (stage_key, stage_name, node_id) in enumerate(
                (("submit", "提单", "submit"), ("approve", "分派", "approve"), ("handle", "处理", "handle")), start=1
            ):
                WorkflowStage.objects.get_or_create(
                    workflow=workflow,
                    key=stage_key,
                    defaults={"name": stage_name, "order": order, "node_ids": [node_id], **actor},
                )
            for target, minutes in (("response", response_minutes), ("resolve", resolve_minutes)):
                SLAPolicy.objects.get_or_create(
                    workflow=workflow,
                    target=target,
                    defaults={"name": f"{name}-{target}", "minutes": minutes, "calendar": calendar, **actor},
                )
        self.stdout.write(self.style.SUCCESS("init_itsm_itil done"))
