import json

from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.flowable.bpmn_builder import BpmnBuildError, build_bpmn
from apps.itsm.flowable.client import FlowableClient, FlowableError
from apps.itsm.models import (
    DataDictionary,
    DataDictionaryItem,
    FormModel,
    FormVersion,
    HandlerGroup,
    NotifyTemplate,
    Workflow,
    WorkflowType,
    WorkflowVariable,
    WorkflowVersion,
)
from apps.itsm.serializers import HandlerGroupSerializer, NotifyTemplateSerializer
from apps.itsm.services.form.validator import FormValidator
from apps.itsm.views.access import api_errors, domain_of, has_permission, method_permission
from apps.itsm.views.base import ItsmAPIView


def _body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _page(request, queryset):
    page = Paginator(queryset.order_by("-id"), max(1, min(100, int(request.GET.get("page_size") or 20))))
    current = page.get_page(int(request.GET.get("page") or 1))
    return current


def _user(request):
    return getattr(getattr(request, "user", None), "username", "") or ""


@csrf_exempt
@api_errors
@method_permission("form-View", "form-Add")
def forms(request):
    if request.method == "GET":
        current = _page(request, FormModel.objects.filter(domain=domain_of(request)).all())
        return WebUtils.response_success(
            {"count": current.paginator.count, "items": [{"id": item.id, "name": item.name, "key": item.key} for item in current]}
        )
    payload = _body(request)
    form = FormModel.objects.create(
        domain=domain_of(request),
        name=payload["name"],
        key=payload["key"],
        description=payload.get("description", ""),
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": form.id})


@csrf_exempt
@api_errors
@HasPermission("form-Publish")
def publish_form(request, form_id):
    form = FormModel.objects.filter(domain=domain_of(request)).get(id=form_id)
    payload = _body(request)
    from apps.itsm.services.form.fetch import freeze_schema

    schema = freeze_schema(payload.get("schema") or {}, domain_of(request))
    FormValidator(schema).validate(payload.get("sample") or {})
    version_no = (form.versions.order_by("-version_no").values_list("version_no", flat=True).first() or 0) + 1
    version = FormVersion.objects.create(
        domain=domain_of(request),
        form=form,
        version_no=version_no,
        schema=schema,
        is_published=True,
        created_by=_user(request),
        updated_by=_user(request),
    )
    form.current_version = version
    form.save(update_fields=["current_version", "updated_at"])
    return WebUtils.response_success({"id": version.id, "version_no": version_no})


def _version_item(item):
    return {"id": item.id, "version_no": item.version_no, "is_published": item.is_published, "schema": item.schema}


@csrf_exempt
@api_errors
@method_permission("form-View", "form-Edit")
def form_detail(request, form_id):
    form = FormModel.objects.filter(domain=domain_of(request)).get(id=form_id)
    if request.method == "PUT":
        schema = _body(request).get("schema") or {"version": 1, "fields": []}
        draft = form.versions.filter(is_published=False).order_by("-version_no").first()
        if draft is None:
            version_no = (form.versions.order_by("-version_no").values_list("version_no", flat=True).first() or 0) + 1
            draft = FormVersion.objects.create(
                domain=domain_of(request),
                form=form,
                version_no=version_no,
                schema=schema,
                is_published=False,
                created_by=_user(request),
                updated_by=_user(request),
            )
        else:
            draft.schema = schema
            draft.updated_by = _user(request)
            draft.save(update_fields=["schema", "updated_by", "updated_at"])
        return WebUtils.response_success({"id": draft.id, "version_no": draft.version_no})
    latest = form.versions.order_by("-version_no").first()
    versions = form.versions.order_by("-version_no")
    return WebUtils.response_success(
        {
            "id": form.id,
            "name": form.name,
            "key": form.key,
            "schema": latest.schema if latest else {"version": 1, "fields": []},
            "versions": [_version_item(item) for item in versions],
        }
    )


@csrf_exempt
@api_errors
@HasPermission("form-View")
def form_versions(request, form_id):
    versions = FormVersion.objects.filter(domain=domain_of(request)).filter(form_id=form_id).order_by("-version_no")
    return WebUtils.response_success({"count": versions.count(), "items": [_version_item(item) for item in versions]})


@csrf_exempt
@api_errors
@HasPermission("form-Edit")
def preview_form(request, form_id):
    form = FormModel.objects.filter(domain=domain_of(request)).get(id=form_id)
    schema = form.current_version.schema if form.current_version_id else _body(request).get("schema") or {"fields": []}
    errors = FormValidator(schema).validate(_body(request).get("data") or {})
    return WebUtils.response_success({"errors": errors})


@csrf_exempt
@api_errors
@method_permission("data-View", "data-Edit")
def dictionaries(request):
    if request.method == "GET":
        current = _page(request, DataDictionary.objects.filter(domain=domain_of(request)).all())
        return WebUtils.response_success(
            {
                "count": current.paginator.count,
                "items": [{"id": item.id, "key": item.key, "name": item.name} for item in current],
                "can_edit": has_permission(request, "data-Edit"),
                "can_add": has_permission(request, "data-Add"),
            }
        )
    payload = _body(request)
    if payload.get("id"):
        item = DataDictionary.objects.filter(domain=domain_of(request)).get(id=payload["id"])
        item.name = payload.get("name") or item.name
        item.updated_by = _user(request)
        item.save(update_fields=["name", "updated_by", "updated_at"])
        return WebUtils.response_success({"id": item.id})
    item = DataDictionary.objects.create(
        domain=domain_of(request), key=payload["key"], name=payload["name"], created_by=_user(request), updated_by=_user(request)
    )
    return WebUtils.response_success({"id": item.id})


@csrf_exempt
@api_errors
@method_permission("data-View", "data-Edit")
@transaction.atomic
def dictionary_items(request, dictionary_id):
    dictionary = DataDictionary.objects.select_for_update().get(id=dictionary_id, domain=domain_of(request))
    items = DataDictionaryItem.objects.filter(domain=domain_of(request), dictionary=dictionary)
    if request.method == "GET":
        return WebUtils.response_success(
            {
                "items": [
                    {
                        "id": item.id,
                        "key": item.key,
                        "label": item.label,
                        "order": item.order,
                        "is_enabled": item.is_enabled,
                        "parent_id": item.parent_id,
                    }
                    for item in items.order_by("order", "id")
                ],
                "can_edit": has_permission(request, "data-Edit"),
            }
        )
    if request.method == "DELETE":
        item = items.get(id=request.GET.get("id"))
        if item.children.exists():
            return WebUtils.response_error("请先删除子字典项", status_code=400)
        item.delete()
        return WebUtils.response_success({"id": request.GET.get("id")})
    if request.method != "POST":
        return WebUtils.response_error("不支持的方法", status_code=405)
    payload = _body(request)
    item = items.get(id=payload["id"]) if payload.get("id") else None
    label = payload.get("label")
    key = item.key if item else payload.get("key")
    order = payload.get("order", item.order if item else 0)
    enabled = payload.get("is_enabled", item.is_enabled if item else True)
    if not isinstance(label, str) or not label.strip() or len(label.strip()) > 128:
        return WebUtils.response_error("请输入不超过 128 字的名称", status_code=400)
    if not isinstance(key, str) or not key.strip() or len(key.strip()) > 64:
        return WebUtils.response_error("请输入不超过 64 字的标识", status_code=400)
    if type(order) is not int or not 0 <= order <= 2147483647 or type(enabled) is not bool:
        return WebUtils.response_error("排序须为非负整数，启用状态须为布尔值", status_code=400)
    if not item and items.filter(key=key.strip()).exists():
        return WebUtils.response_error("字典项标识已存在", status_code=400)
    if item is None:
        item = DataDictionaryItem(dictionary=dictionary, domain=domain_of(request), key=key.strip(), created_by=_user(request))
    item.label, item.order, item.is_enabled, item.updated_by = label.strip(), order, enabled, _user(request)
    item.save()
    return WebUtils.response_success({"id": item.id})


@api_errors
@HasPermission("data-View")
def export_dictionaries(request):
    rows = [
        {
            "key": item.key,
            "name": item.name,
            "items": [
                {
                    "key": child.key,
                    "label": child.label,
                    "parent_key": child.parent.key if child.parent_id else None,
                    "order": child.order,
                    "is_enabled": child.is_enabled,
                }
                for child in item.items.all()
                if child.domain == domain_of(request)
            ],
        }
        for item in DataDictionary.objects.filter(domain=domain_of(request)).prefetch_related("items__parent")
    ]
    return HttpResponse(json.dumps(rows, ensure_ascii=False), content_type="application/json")


@csrf_exempt
@api_errors
@HasPermission("data-Add")
def import_dictionaries(request):
    from apps.itsm.services.import_copy import copy_dictionaries

    if request.method != "POST":
        return WebUtils.response_error("不支持的方法", status_code=405)
    return WebUtils.response_success(copy_dictionaries(request, _body(request)))


@csrf_exempt
@api_errors
@method_permission("workflow-View", "workflow-Add")
def workflows(request):
    if request.method == "GET":
        current = _page(request, Workflow.objects.filter(domain=domain_of(request)).all())
        return WebUtils.response_success(
            {
                "count": current.paginator.count,
                "items": [
                    {
                        "id": item.id,
                        "name": item.name,
                        "key": item.key,
                        "form_id": item.form_id,
                        "current_version_id": item.current_version_id,
                    }
                    for item in current
                ],
            }
        )
    payload = _body(request)
    if payload.get("form_id"):
        FormModel.objects.get(id=payload["form_id"], domain=domain_of(request))
    if payload.get("type_id"):
        WorkflowType.objects.get(id=payload["type_id"], domain=domain_of(request))
    item = Workflow.objects.create(
        domain=domain_of(request),
        name=payload["name"],
        key=payload["key"],
        description=payload.get("description", ""),
        workflow_type_id=payload.get("type_id"),
        form_id=payload.get("form_id"),
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": item.id})


@csrf_exempt
@api_errors
@HasPermission("workflow-Edit")
def workflow_design(request, workflow_id):
    workflow = Workflow.objects.filter(domain=domain_of(request)).get(id=workflow_id)
    if request.method == "GET":
        version = (
            workflow.versions.filter(is_published=False).order_by("-version_no").first()
            or workflow.current_version
            or workflow.versions.order_by("-version_no").first()
        )
        design = version.design if version and isinstance(version.design, dict) else {}
        return WebUtils.response_success(
            {
                **design,
                "locked": bool(version and version.is_published),
                "form_id": workflow.form_id,
                "workflow_name": workflow.name,
                "version_no": version.version_no if version else 0,
            }
        )
    payload = _body(request)
    if payload.get("form_id"):
        FormModel.objects.get(id=payload["form_id"], domain=domain_of(request))
        workflow.form_id = payload["form_id"]
        workflow.save(update_fields=["form", "updated_at"])
        payload = {key: value for key, value in payload.items() if key != "form_id"}
    draft = workflow.versions.filter(is_published=False).order_by("-version_no").first()
    if draft is not None and payload.get("nodes"):
        draft.design = payload
        draft.updated_by = _user(request)
        draft.save(update_fields=["design", "updated_by", "updated_at"])
        return WebUtils.response_success({"id": draft.id, "version_no": draft.version_no, "locked": False})
    version_no = (workflow.versions.order_by("-version_no").values_list("version_no", flat=True).first() or 0) + 1
    version = WorkflowVersion.objects.create(
        domain=domain_of(request),
        workflow=workflow,
        version_no=version_no,
        design=payload,
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": version.id, "version_no": version_no, "locked": False})


@csrf_exempt
@api_errors
@HasPermission("workflow-Publish")
def publish_workflow(request, workflow_id):
    workflow = Workflow.objects.filter(domain=domain_of(request)).get(id=workflow_id)
    version = workflow.versions.order_by("-version_no").first()
    if version is None:
        return WebUtils.response_error("没有设计稿")
    if workflow.form_id and workflow.form.current_version_id:
        schema = workflow.form.current_version.schema

        def field_keys(fields):
            return [key for field in fields for key in [field["key"], *field_keys(field.get("children") or [])]]

        version.design = {
            **version.design,
            "form_schema": schema,
            "settings": {**version.design.get("settings", {}), "fields": field_keys(schema.get("fields", []))},
        }
    try:
        xml = build_bpmn(version.design, workflow.key)
    except BpmnBuildError as exc:
        return WebUtils.response_error(str(exc))
    if not workflow.form_id and version.design.get("form_schema"):
        from apps.itsm.services.form.fetch import freeze_schema

        version.design = {**version.design, "form_schema": freeze_schema(version.design["form_schema"], domain_of(request))}
    client = FlowableClient(settings.FLOWABLE_URL, settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD)
    try:
        deployed = client.deploy_bpmn(workflow.key, xml)
    except FlowableError:
        return WebUtils.response_error("Flowable 部署失败", status_code=502)
    if workflow.form_id and workflow.form.current_version_id:
        version.design = {**version.design, "form_schema": workflow.form.current_version.schema}
    version.bpmn_xml = xml
    version.flowable_deployment_id = str(deployed.get("id") or "")
    version.process_definition_key = workflow.key
    version.is_published = True
    version.save()
    workflow.current_version = version
    workflow.save(update_fields=["current_version", "updated_at"])
    return WebUtils.response_success({"deployment_id": version.flowable_deployment_id})


class HandlerGroupView(ItsmAPIView):
    @api_errors
    @HasPermission("org-View")
    def get(self, request):
        return Response({"items": HandlerGroupSerializer(HandlerGroup.objects.filter(domain=domain_of(request)).all(), many=True).data})

    @api_errors
    @HasPermission("org-Edit")
    def post(self, request):
        payload = request.data
        if payload.get("id"):
            item = HandlerGroup.objects.filter(domain=domain_of(request)).filter(id=payload["id"]).first()
            if item is None:
                return self.fail("处理组不存在", 404)
            serializer = HandlerGroupSerializer(item, data=payload, partial=True)
        else:
            serializer = HandlerGroupSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data.get("leaders"):
            serializer.validated_data["leaders"] = (serializer.validated_data.get("members") or [])[:1]
        actor = self.actor(request)
        extra = {"updated_by": actor, "domain": domain_of(request)}
        if serializer.instance is None:
            extra["created_by"] = actor
        serializer.save(**extra)
        return Response({"id": serializer.instance.id})

    @api_errors
    @HasPermission("org-Edit")
    def delete(self, request):
        deleted, _rows = HandlerGroup.objects.filter(domain=domain_of(request)).filter(id=request.GET.get("id")).delete()
        if not deleted:
            return self.fail("处理组不存在", 404)
        return Response({"id": request.GET.get("id")})


class NotifyTemplateView(ItsmAPIView):
    @api_errors
    @HasPermission("notify-View")
    def get(self, request):
        return Response({"items": NotifyTemplateSerializer(NotifyTemplate.objects.filter(domain=domain_of(request)).all(), many=True).data})

    @api_errors
    @HasPermission("notify-Edit")
    def post(self, request):
        payload = request.data
        if payload.get("id"):
            item = NotifyTemplate.objects.filter(domain=domain_of(request)).filter(id=payload["id"]).first()
            if item is None:
                return self.fail("通知模板不存在", 404)
            serializer = NotifyTemplateSerializer(item, data=payload, partial=True)
        else:
            serializer = NotifyTemplateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        actor = self.actor(request)
        extra = {"updated_by": actor, "domain": domain_of(request)}
        if serializer.instance is None:
            extra["created_by"] = actor
        serializer.save(**extra)
        return Response({"id": serializer.instance.id})

    @api_errors
    @HasPermission("notify-Edit")
    def delete(self, request):
        item = NotifyTemplate.objects.filter(domain=domain_of(request)).filter(id=request.GET.get("id")).first()
        if item is None:
            return self.fail("通知模板不存在", 404)
        if item.is_builtin:
            return self.fail("内置模板不能删除")
        item.delete()
        return Response({"id": request.GET.get("id")})


@csrf_exempt
@api_errors
@method_permission("setting-View", "setting-Edit")
def basic_settings(request):
    from apps.itsm.models import ItsmSetting

    defaults = {
        "product_name": "ITSM",
        "tab_title": "ITSM",
        "attachment_types": "png,jpg,pdf,docx,xlsx",
        "show_process_log": True,
        "user_display": "display_name",
    }
    setting, _created = ItsmSetting.objects.get_or_create(
        domain=domain_of(request),
        key="basic",
        defaults={"value": defaults, "created_by": _user(request), "updated_by": _user(request)},
    )
    if request.method == "GET":
        value = dict(defaults)
        value.update(setting.value or {})
        return WebUtils.response_success(value)
    payload = _body(request)
    value = dict(defaults)
    value.update(setting.value or {})
    for key in defaults:
        if key in payload:
            value[key] = payload[key]
    setting.value = value
    setting.updated_by = _user(request)
    setting.save(update_fields=["value", "updated_by", "updated_at"])
    return WebUtils.response_success(value)


@api_errors
@HasPermission("workflow-View")
def workflow_types(request):
    return WebUtils.response_success(
        {"items": [{"id": item.id, "name": item.name, "key": item.key} for item in WorkflowType.objects.filter(domain=domain_of(request)).all()]}
    )


@api_errors
@HasPermission("workflow-View")
def workflow_variables(request):
    queryset = WorkflowVariable.objects.filter(domain=domain_of(request)).all()
    workflow_id = request.GET.get("workflow_id")
    if workflow_id:
        queryset = queryset.filter(workflow_id=workflow_id)
    return WebUtils.response_success({"items": [{"id": item.id, "key": item.key, "name": item.name, "source": item.source} for item in queryset]})
