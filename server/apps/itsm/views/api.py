import json

from django.conf import settings
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods
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
    ItsmSetting,
    NotifyTemplate,
    Workflow,
    WorkflowType,
    WorkflowVariable,
    WorkflowVersion,
)
from apps.itsm.serializers import HandlerGroupSerializer, NotifyTemplateSerializer
from apps.itsm.services.basic_settings import BASIC_SETTINGS_DEFAULTS, basic_settings_values, normalize_setting, read_basic_settings
from apps.itsm.services.form.validator import FormValidator
from apps.itsm.services.ticket.transfer import validate_transfer_scopes
from apps.itsm.views.access import api_errors, domain_of, has_permission, method_permission
from apps.itsm.views.base import ItsmAPIView
from apps.system_mgmt.models import User


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
@transaction.atomic
def publish_form(request, form_id):
    form = FormModel.objects.select_for_update().filter(domain=domain_of(request)).get(id=form_id)
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
@transaction.atomic
def form_detail(request, form_id):
    forms = FormModel.objects.filter(domain=domain_of(request))
    form = (forms.select_for_update() if request.method == "PUT" else forms).get(id=form_id)
    if request.method == "PUT":
        schema = _body(request).get("schema") or {"version": 1, "fields": []}
        drafts = form.versions.filter(is_published=False)
        if form.current_version_id:
            drafts = drafts.filter(version_no__gt=form.current_version.version_no)
        draft = drafts.order_by("-version_no").first()
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
    versions = list(form.versions.order_by("-version_no"))
    latest = versions[0] if versions else None
    if latest and latest.is_published:
        # 旧版本曾在发布后继续写入较早的草稿，仍应允许编辑者找回这些修改。
        latest = next((item for item in versions if not item.is_published and item.updated_at > latest.created_at), latest)
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
        current = _page(request, Workflow.objects.filter(domain=domain_of(request)).select_related("current_version"))
        return WebUtils.response_success(
            {
                "count": current.paginator.count,
                "can_add": has_permission(request, "workflow-Add"),
                "can_edit": has_permission(request, "workflow-Edit"),
                "can_publish": has_permission(request, "workflow-Publish"),
                "items": [
                    {
                        "id": item.id,
                        "name": item.name,
                        "key": item.key,
                        "form_id": item.form_id,
                        "current_version_id": item.current_version_id,
                        "current_version_no": item.current_version.version_no if item.current_version_id else None,
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
@require_POST
@api_errors
@HasPermission("workflow-Publish")
@transaction.atomic
def publish_workflow(request, workflow_id):
    workflow = Workflow.objects.select_for_update().filter(domain=domain_of(request)).get(id=workflow_id)
    version = workflow.versions.order_by("-version_no").first()
    if version is None:
        return WebUtils.response_error("没有设计稿")
    if version.is_published:
        return WebUtils.response_success({"deployment_id": version.flowable_deployment_id})
    if workflow.form_id and workflow.form.current_version_id:
        schema = workflow.form.current_version.schema

        def field_keys(fields):
            return [key for field in fields for key in [field["key"], *field_keys(field.get("children") or [])]]

        version.design = {
            **version.design,
            "form_schema": schema,
            "settings": {**version.design.get("settings", {}), "fields": field_keys(schema.get("fields", []))},
        }
    from apps.itsm.services.service_assignment import activate_service_version
    from apps.itsm.services.workflow.dependencies import validate_subprocesses

    try:
        validate_subprocesses(version.design, workflow)
        validate_transfer_scopes(version.design, workflow.domain)
    except ValueError as exc:
        return WebUtils.response_error(str(exc))
    try:
        xml = build_bpmn(version.design, workflow.key)
    except BpmnBuildError as exc:
        return WebUtils.response_error(str(exc))
    if not workflow.form_id and version.design.get("form_schema"):
        from apps.itsm.services.form.fetch import freeze_schema

        version.design = {**version.design, "form_schema": freeze_schema(version.design["form_schema"], domain_of(request))}
    client = FlowableClient(settings.FLOWABLE_URL, settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD)
    try:
        if not version.flowable_deployment_id or version.bpmn_xml != xml:
            deployed = client.deploy_bpmn(workflow.key, xml)
            version.bpmn_xml = xml
            version.flowable_deployment_id = str(deployed.get("id") or "")
            version.save(update_fields=["bpmn_xml", "flowable_deployment_id", "updated_at"])
        version.process_definition_id = client.definition_for_deployment(version.flowable_deployment_id, workflow.key)
    except FlowableError:
        return WebUtils.response_error("Flowable 部署失败", status_code=502)
    if workflow.form_id and workflow.form.current_version_id:
        version.design = {**version.design, "form_schema": workflow.form.current_version.schema}
    version.design = {**version.design, "form_model_id": workflow.form_id}
    version.process_definition_key = workflow.key
    version.is_published = True
    version.save()
    activate_service_version(workflow, version)
    return WebUtils.response_success({"deployment_id": version.flowable_deployment_id})


@require_GET
@api_errors
@HasPermission("workflow-Edit")
def handler_group_options(request):
    current = _page(request, HandlerGroup.objects.filter(domain=domain_of(request)).values("id", "name"))
    return WebUtils.response_success({"items": list(current), "count": current.paginator.count})


class HandlerGroupView(ItsmAPIView):
    @api_errors
    @HasPermission("org-View")
    def get(self, request):
        groups = HandlerGroup.objects.filter(domain=domain_of(request)).order_by("id")
        return Response({"items": HandlerGroupSerializer(groups, many=True).data, "can_edit": has_permission(request, "org-Edit")})

    @api_errors
    @HasPermission("org-Edit")
    @transaction.atomic
    def post(self, request):
        payload = request.data
        if payload.get("id"):
            item = HandlerGroup.objects.select_for_update().filter(domain=domain_of(request), id=payload["id"]).first()
            if item is None:
                return self.fail("处理组不存在", 404)
            serializer = HandlerGroupSerializer(item, data=payload, partial=True)
        else:
            serializer = HandlerGroupSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        existing = serializer.instance
        members = values.get("members", existing.members if existing else [])
        if not isinstance(members, list) or any(not isinstance(name, str) or not name for name in members):
            return self.fail("请选择有效的处理组成员")
        members = list(dict.fromkeys(members))
        leaders = values.get("leaders", [name for name in existing.leaders if name in members] if existing else members[:1])
        if not isinstance(leaders, list) or any(not isinstance(name, str) or name not in members for name in leaders):
            return self.fail("负责人必须属于当前处理组")
        new_users = (set(members) - set(existing.members if existing else [])) | (set(leaders) - set(existing.leaders if existing else []))
        if (
            new_users
            and set(User.objects.filter(domain=domain_of(request), disabled=False, username__in=new_users).values_list("username", flat=True))
            != new_users
        ):
            return self.fail("成员和负责人必须是当前组织的有效用户")
        values.update(members=members, leaders=list(dict.fromkeys(leaders)))
        actor = self.actor(request)
        extra = {"updated_by": actor, "domain": domain_of(request)}
        if serializer.instance is None:
            extra["created_by"] = actor
        serializer.save(**extra)
        return Response({"id": serializer.instance.id})

    @api_errors
    @HasPermission("org-Edit")
    def delete(self, request):
        try:
            deleted, _rows = HandlerGroup.objects.filter(domain=domain_of(request)).filter(id=request.GET.get("id")).delete()
        except ProtectedError:
            return self.fail("处理组仍绑定服务，请先更换服务处理组")
        if not deleted:
            return self.fail("处理组不存在", 404)
        return Response({"id": request.GET.get("id")})


class NotifyTemplateView(ItsmAPIView):
    @api_errors
    @HasPermission("notify-View")
    def get(self, request):
        templates = NotifyTemplate.objects.filter(domain=domain_of(request)).all()
        return Response({"items": NotifyTemplateSerializer(templates, many=True).data, "can_edit": has_permission(request, "notify-Edit")})

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
        instance = serializer.instance
        values = serializer.validated_data
        event = values.get("event", instance.event if instance else "")
        channel_type = values.get("channel_type", instance.channel_type if instance else "site")
        if instance and instance.is_builtin and (event != instance.event or channel_type != instance.channel_type):
            return self.fail("内置通知模板的事件和渠道不可修改")
        actor = self.actor(request)
        extra = {"updated_by": actor, "domain": domain_of(request)}
        if instance is None:
            extra["created_by"] = actor
        try:
            with transaction.atomic():
                serializer.save(**extra)
        except IntegrityError:
            return self.fail("此事件和渠道已存在通知模板")
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


BASIC_RUNTIME_PERMISSIONS = (
    "portal-View,ticket-View,workflow-View,form-View,data-View,rule-View,org-View,notify-View,setting-View,"
    "knowledge-View,duty-View,change-View,survey-View,print-View,handover-View,ai-View"
)


@HasPermission(BASIC_RUNTIME_PERMISSIONS)
def _basic_runtime(request):
    return WebUtils.response_success(read_basic_settings(domain_of(request)))


@method_permission("setting-View", "setting-Edit")
@transaction.atomic
def _basic_admin_settings(request):
    domain = domain_of(request)
    if request.method == "GET":
        return WebUtils.response_success({**read_basic_settings(domain), "can_edit": has_permission(request, "setting-Edit")})

    payload = _body(request)
    if not isinstance(payload, dict):
        return WebUtils.response_error("基础设置须为对象")
    try:
        updates = {key: normalize_setting(key, payload[key]) for key in BASIC_SETTINGS_DEFAULTS if key in payload}
    except ValueError as exc:
        return WebUtils.response_error(str(exc))

    setting, _created = ItsmSetting.objects.select_for_update().get_or_create(
        domain=domain, key="basic", defaults={"created_by": _user(request), "updated_by": _user(request)}
    )
    setting.value = {**basic_settings_values(setting.value), **updates}
    setting.updated_by = _user(request)
    setting.save(update_fields=["value", "updated_by", "updated_at"])
    return WebUtils.response_success(setting.value)


@csrf_exempt
@api_errors
@require_http_methods(["GET", "POST", "PUT", "PATCH"])
def basic_settings(request):
    if request.method == "GET" and request.GET.get("runtime") == "1":
        return _basic_runtime(request)
    return _basic_admin_settings(request)


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
