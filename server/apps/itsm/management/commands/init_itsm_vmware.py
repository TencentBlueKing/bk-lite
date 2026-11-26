"""安装 VMware 申请服务。真实环境先绑定交付目录，再通过流程管理发布。"""

import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models.maintainer_info import DEFAULT_MAINTAINER_DOMAIN, maintainer_kwargs
from apps.itsm.flowable.client import FlowableClient, FlowableError
from apps.itsm.management.commands.init_itsm_itil import _publish_initial_version
from apps.itsm.models import FormModel, FormVersion, Service, ServiceCatalog, Trigger, Workflow, WorkflowVersion
from apps.itsm.models.integration import Integration
from apps.itsm.services.form.fetch import freeze_schema
from apps.itsm.services.service_assignment import eligible_handler_groups
from apps.itsm.services.trigger_config import normalize_trigger
from apps.system_mgmt.models import Group


def _form_schema(integration, profile, domain):
    fields = [
        {"key": "title", "type": "input", "label": "申请标题", "required": True},
        {"key": "purpose", "type": "textarea", "label": "所属业务与用途", "required": True},
    ]
    columns = []
    for key, label, kind in (
        ("flavor_id", "计算规格", "flavor"),
        ("template_id", "系统模板", "template"),
        ("network_id", "网络", "network"),
        ("disk_policy_id", "数据盘策略", "disk_policy"),
        ("data_disk_gib", "数据盘容量", "disk_size"),
    ):
        inputs = {"profile": profile, "kind": kind, "keyword": "${query.keyword}", "page": "${query.page}"}
        if kind == "disk_size":
            inputs["disk_policy_id"] = "${form.disk_policy_id}"
        columns.append(
            {
                "key": key,
                "label": label,
                "type": "select",
                "props": {"defaultFirstOption": True},
                "required": True,
                "fetch": {
                    "source": "integration",
                    "mode": "options",
                    "integration_id": integration.id,
                    "inputs": inputs,
                    "value_path": "value",
                    "label_path": "label",
                },
            }
        )
    table = {"key": "vm_requests", "type": "table", "label": "虚拟机配置", "required": True, "children": columns, "hint": "每行申请一台虚拟机"}
    if profile == "demo":
        from apps.itsm.services.vmware_catalog import DEMO_CONFIG

        table["props"] = {"maxRows": DEMO_CONFIG["max_quantity"]}
    fields.append(table)
    fields.append({"key": "delivery_result", "type": "textarea", "label": "逐台交付结果", "state": "readonly"})
    return freeze_schema({"version": 1, "fields": fields}, domain)


def _design(form, schema, profile):
    return {
        "form_model_id": form.pk,
        "form_schema": schema,
        "settings": {"fields": [field["key"] for field in schema["fields"]]},
        "nodes": [
            {"id": "start", "type": "start", "name": "开始"},
            {"id": "submit", "type": "submit", "name": "申请虚拟机", "field_perm": {"delivery_result": "read"}},
            {
                "id": "approve",
                "type": "approval",
                "name": "运维审批",
                "assignee": {"source": "service_group", "value": []},
                "multi": {"mode": "any"},
                "field_perm": {"*": "read"},
                "actions": ["approve", "reject", "return"],
                "required_opinion_actions": ["reject", "return"],
            },
            {"id": "decision", "type": "exclusive", "name": "审批结果"},
            {
                "id": "provision",
                "type": "auto",
                "name": "模拟创建虚拟机" if profile == "demo" else "创建并核对虚拟机",
                "auto": {"kind": "vmware_provision", "profile": profile, "result_field": "delivery_result"},
            },
            {"id": "end", "type": "end", "name": "结束"},
        ],
        "edges": [
            {"from": "start", "to": "submit"},
            {"from": "submit", "to": "approve"},
            {"from": "approve", "to": "decision"},
            {"from": "decision", "to": "provision", "condition": {"field": "out_approve_result", "op": "=", "value": "approve"}},
            {"from": "decision", "to": "end", "default": True},
            {"from": "provision", "to": "end"},
        ],
    }


def _delivery_notice(service, actor):
    config = {
        "scope": {"mode": "include", "workflow_ids": [service.workflow_id], "service_ids": [service.id]},
        "when": {"field": "$form.delivery_result", "op": "not_empty"},
        "actions": [
            {
                "type": "notice",
                "value": "$ticket_title 已完成，请在工单详情查看逐台交付结果。",
                "notice": {"content_mode": "custom", "recipients": {"roles": ["creator"]}, "channels": [{"type": "site"}]},
            }
        ],
    }
    rule = normalize_trigger(
        {"name": f"{service.name}交付通知", "event": "ticket_end", "action": "notice", "config": config}, domain=service.domain, user=None
    )
    Trigger.objects.create(**actor, **rule)


class Command(BaseCommand):
    help = "安装 VMware 虚拟机申请流程、动态表单和交付通知；演示和真实服务独立，保留已有配置"

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--demo", action="store_true", help="安装演示服务，作业在模拟模式运行")
        mode.add_argument("--profile", help="真实交付环境的英文标识")
        parser.add_argument("--team", type=int, required=True, help="资源目录和作业目标所属的组织 ID")
        parser.add_argument("--domain", default=DEFAULT_MAINTAINER_DOMAIN)
        parser.add_argument("--handler-group", type=int, help="本域包含有效账号的 ITSM 处理组 ID")
        parser.add_argument("--applicant-group", type=int, help="可在门户申请此服务的本域 ITSM 组 ID，默认使用处理组")
        parser.add_argument("--catalog-file", type=Path, help="真实环境的资源范围和作业绑定配置（无密码）")

    def handle(self, *args, **options):
        from apps.itsm.services.vmware_catalog import bind_catalog, install_demo_catalog

        demo, domain, team = options["demo"], options["domain"], options["team"]
        profile = "demo" if demo else options["profile"]
        if not profile or not re.fullmatch(r"[a-z][a-z0-9_]{0,24}", profile) or (profile == "demo" and not demo):
            raise CommandError("真实环境标识须为 1 至 25 位小写英文、数字或下划线，以字母开头；demo 留给演示服务")
        if not Group.objects.filter(id=team, is_delete=False).exists():
            raise CommandError("请选择有效的作业组织")
        group_id = options["handler_group"]
        if group_id is not None and not eligible_handler_groups(domain, group_ids=[group_id]):
            raise CommandError("请选择本域包含有效成员的服务处理组")
        applicant_group = options["applicant_group"]
        if applicant_group is not None and not eligible_handler_groups(domain, group_ids=[applicant_group]):
            raise CommandError("请选择本域包含有效成员的申请人组")
        if applicant_group is None:
            applicant_group = group_id
        catalog_config = None
        if options["catalog_file"]:
            if demo:
                raise CommandError("演示服务使用独立模拟目录")
            try:
                catalog_config = json.loads(Path(options["catalog_file"]).read_text(encoding="utf-8"))
                if not isinstance(catalog_config, dict):
                    raise ValueError()
            except (OSError, ValueError) as exc:
                raise CommandError("交付目录须为可读的 JSON 对象文件") from exc

        actor = {**maintainer_kwargs(domain=domain), "team": [team]}
        key = f"vmware_{profile}_{team}"
        name = "VMware 虚拟机申请（本地演示）" if demo else f"VMware 虚拟机申请（{profile}）"
        failure = None
        with transaction.atomic():
            workflow, created = Workflow.objects.get_or_create(domain=domain, key=key, defaults={"name": name, **actor})
            if not created:
                service = Service.objects.filter(domain=domain, workflow=workflow, team=[team]).first()
                if not service:
                    raise CommandError("已有同标识流程，未找到本组织对应服务，请核对后再安装")
                if catalog_config is not None:
                    bind_catalog(profile, service, team, catalog_config)
                self.stdout.write(f"保留已有服务 {service.pk} 和流程 {workflow.pk} 的版本与配置")
                return
            integration = Integration.objects.create(
                name=f"{name}资源目录",
                kind="api",
                config={"method": "GET", "path": "itsm/vmware/catalog"},
                **actor,
            )
            schema = _form_schema(integration, profile, domain)
            form = FormModel.objects.create(key=key, name=name, **actor)
            form.current_version = FormVersion.objects.create(form=form, version_no=1, schema=schema, is_published=True, **actor)
            form.save(update_fields=["current_version", "updated_at"])
            workflow.form = form
            workflow.save(update_fields=["form", "updated_at"])
            version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design=_design(form, schema, profile), **actor)
            catalog, _ = ServiceCatalog.objects.get_or_create(domain=domain, name="虚拟化服务", defaults=actor)
            service = Service.objects.create(
                name=name,
                catalog=catalog,
                workflow=workflow,
                handler_group_id=group_id,
                visibility="restricted",
                visible_groups=[applicant_group] if applicant_group else [],
                is_enabled=False,
                description="运维审批后模拟交付，不占用 vCenter 资源" if demo else "运维审批后由作业平台自动交付虚拟机",
                **actor,
            )
            _delivery_notice(service, actor)
            if demo:
                install_demo_catalog(service, team)
                if settings.FLOWABLE_PASSWORD:
                    try:
                        client = FlowableClient(settings.FLOWABLE_URL, settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD)
                        _publish_initial_version(client, workflow, version)
                    except FlowableError as exc:
                        failure = exc
                    else:
                        if group_id:
                            service.is_enabled = True
                            service.save(update_fields=["is_enabled", "updated_at"])
            elif catalog_config is not None:
                bind_catalog(profile, service, team, catalog_config)
        if failure:
            raise CommandError(f"服务 {service.pk} 已禁用，流程草稿 {workflow.pk} 已保留，请核对 Flowable 部署结果") from failure
        self.stdout.write(f"{service.name} 服务 ID={service.pk}，流程 ID={workflow.pk}，状态={'已启用' if service.is_enabled else '未启用'}")
