from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models.maintainer_info import DEFAULT_MAINTAINER_DOMAIN, SYSTEM_MAINTAINER
from apps.itsm.flowable.bpmn_builder import build_bpmn
from apps.itsm.flowable.client import FlowableClient, FlowableError
from apps.itsm.management.commands.init_itsm import ensure_builtin_dictionary
from apps.itsm.models import (
    DataDictionary,
    FormModel,
    FormVersion,
    Service,
    ServiceCalendar,
    ServiceCatalog,
    SLAPolicy,
    Workflow,
    WorkflowStage,
    WorkflowVersion,
)
from apps.itsm.services.form.fetch import freeze_schema

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
            "assignee": {"source": "service_group", "value": []},
            "multi": {"mode": "any"},
        },
        {"id": "handle", "type": "handle", "name": "处理", "assignee": {"source": "service_group", "value": []}},
        {"id": "end", "type": "end", "name": "结束"},
    ],
    "edges": [
        {"from": "start", "to": "submit"},
        {"from": "submit", "to": "approve"},
        {"from": "approve", "to": "handle"},
        {"from": "handle", "to": "end"},
    ],
}


def _create_form_and_design(workflow, actor):
    fields = [
        {"key": "title", "type": "input", "label": "标题", "required": True},
        {"key": "description", "type": "textarea", "label": "描述"},
    ]
    for key, label in (("priority", "优先级"), ("impact", "影响度")):
        if not DataDictionary.objects.filter(key=key, domain=workflow.domain).exists():
            ensure_builtin_dictionary(key, actor)
        fields.append({"key": key, "type": "select", "label": label, "fetch": {"mode": "options", "source": "dictionary", "resource_key": key}})
    schema = freeze_schema({"version": 1, "fields": fields}, workflow.domain)
    form = FormModel.objects.create(key=f"{workflow.key}_form_{workflow.pk}", name=f"{workflow.name}基础表单", **actor)
    form.current_version = FormVersion.objects.create(form=form, version_no=1, schema=schema, is_published=True, **actor)
    form.save(update_fields=["current_version", "updated_at"])
    workflow.form = form
    workflow.save(update_fields=["form", "updated_at"])
    return {**DESIGN, "form_model_id": form.pk, "form_schema": schema, "settings": {"fields": [field["key"] for field in fields]}}


def _publish_initial_version(client, workflow, version):
    xml = build_bpmn(version.design, workflow.key)
    deployed = client.deploy_bpmn(workflow.key, xml)
    version.flowable_deployment_id = str(deployed["id"])
    version.bpmn_xml = xml
    version.save(update_fields=["flowable_deployment_id", "bpmn_xml", "updated_at"])
    version.process_definition_id = client.definition_for_deployment(version.flowable_deployment_id, workflow.key)
    version.process_definition_key = workflow.key
    version.is_published = True
    version.save(update_fields=["process_definition_key", "process_definition_id", "is_published", "updated_at"])
    workflow.current_version = version
    workflow.save(update_fields=["current_version", "updated_at"])


class Command(BaseCommand):
    help = "安装请求、事件和问题流程及基础表单；保留已有流程及其版本"

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
            failure = None
            with transaction.atomic():
                workflow, created = Workflow.objects.get_or_create(
                    domain=DEFAULT_MAINTAINER_DOMAIN, key=process_key, defaults={"name": name, **actor}
                )
                if not created:
                    continue
                version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design=_create_form_and_design(workflow, actor), **actor)
                Service.objects.create(catalog=catalog, workflow=workflow, name=name, is_hot=True, is_enabled=False, description=name, **actor)
                for order, (node_id, stage_name) in enumerate((("submit", "提单"), ("approve", "分派"), ("handle", "处理")), start=1):
                    WorkflowStage.objects.create(workflow=workflow, key=node_id, name=stage_name, order=order, node_ids=[node_id], **actor)
                for target, minutes in (("response", response_minutes), ("resolve", resolve_minutes)):
                    SLAPolicy.objects.create(workflow=workflow, target=target, name=f"{name}-{target}", minutes=minutes, calendar=calendar, **actor)
                if client:
                    try:
                        _publish_initial_version(client, workflow, version)
                    except FlowableError as exc:
                        # 保留草稿和已收到的部署回执，由设计人核对后发布。
                        failure = exc
            if failure:
                raise RuntimeError(f"{name} 部署失败，请在流程管理中核对并发布已有草稿") from failure
        self.stdout.write(self.style.SUCCESS("init_itsm_itil done"))
