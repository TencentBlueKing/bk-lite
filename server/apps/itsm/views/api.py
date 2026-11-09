import json

from django.conf import settings
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

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
from apps.itsm.services.form.validator import FormValidator


def _body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _page(request, queryset):
    page = Paginator(queryset.order_by("-id"), int(request.GET.get("page_size") or 20))
    current = page.get_page(int(request.GET.get("page") or 1))
    return current


def _user(request):
    return getattr(getattr(request, "user", None), "username", "") or "admin"


@csrf_exempt
@HasPermission("form-View")
def forms(request):
    if request.method == "GET":
        current = _page(request, FormModel.objects.all())
        return WebUtils.response_success(
            {"count": current.paginator.count, "items": [{"id": item.id, "name": item.name, "key": item.key} for item in current]}
        )
    payload = _body(request)
    form = FormModel.objects.create(
        name=payload["name"], key=payload["key"], description=payload.get("description", ""), created_by=_user(request), updated_by=_user(request)
    )
    return WebUtils.response_success({"id": form.id})


@csrf_exempt
@HasPermission("form-Publish")
def publish_form(request, form_id):
    form = FormModel.objects.get(id=form_id)
    payload = _body(request)
    schema = payload.get("schema") or {}
    FormValidator(schema).validate(payload.get("sample") or {})
    version_no = (form.versions.order_by("-version_no").values_list("version_no", flat=True).first() or 0) + 1
    version = FormVersion.objects.create(
        form=form, version_no=version_no, schema=schema, is_published=True, created_by=_user(request), updated_by=_user(request)
    )
    form.current_version = version
    form.save(update_fields=["current_version", "updated_at"])
    return WebUtils.response_success({"id": version.id, "version_no": version_no})


@csrf_exempt
@HasPermission("form-View")
def form_versions(request, form_id):
    versions = FormVersion.objects.filter(form_id=form_id).order_by("-version_no")
    return WebUtils.response_success(
        {"count": versions.count(), "items": [{"id": item.id, "version_no": item.version_no, "is_published": item.is_published} for item in versions]}
    )


@csrf_exempt
@HasPermission("form-Edit")
def preview_form(request, form_id):
    form = FormModel.objects.get(id=form_id)
    schema = form.current_version.schema if form.current_version_id else _body(request).get("schema") or {"fields": []}
    errors = FormValidator(schema).validate(_body(request).get("data") or {})
    return WebUtils.response_success({"errors": errors})


@csrf_exempt
@HasPermission("data-View")
def dictionaries(request):
    if request.method == "GET":
        current = _page(request, DataDictionary.objects.all())
        return WebUtils.response_success(
            {"count": current.paginator.count, "items": [{"id": item.id, "key": item.key, "name": item.name} for item in current]}
        )
    payload = _body(request)
    item = DataDictionary.objects.create(key=payload["key"], name=payload["name"], created_by=_user(request), updated_by=_user(request))
    return WebUtils.response_success({"id": item.id})


@csrf_exempt
@HasPermission("data-Edit")
def dictionary_items(request, dictionary_id):
    if request.method == "GET":
        items = DataDictionaryItem.objects.filter(dictionary_id=dictionary_id).order_by("order")
        return WebUtils.response_success({"items": [{"id": item.id, "key": item.key, "label": item.label} for item in items]})
    payload = _body(request)
    item = DataDictionaryItem.objects.create(
        dictionary_id=dictionary_id,
        key=payload["key"],
        label=payload["label"],
        order=payload.get("order") or 0,
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": item.id})


@HasPermission("data-View")
def export_dictionaries(request):
    rows = [
        {"key": item.key, "name": item.name, "items": [{"key": child.key, "label": child.label} for child in item.items.all()]}
        for item in DataDictionary.objects.all()
    ]
    return HttpResponse(json.dumps(rows, ensure_ascii=False), content_type="application/json")


@csrf_exempt
@HasPermission("data-Add")
def import_dictionaries(request):
    created = 0
    for row in _body(request):
        dictionary, was_created = DataDictionary.objects.get_or_create(
            domain="domain.com", key=row["key"], defaults={"name": row["name"], "created_by": _user(request), "updated_by": _user(request)}
        )
        created += int(was_created)
        for child in row.get("items") or []:
            DataDictionaryItem.objects.get_or_create(
                dictionary=dictionary,
                key=child["key"],
                defaults={"label": child["label"], "created_by": _user(request), "updated_by": _user(request)},
            )
    return WebUtils.response_success({"created": created})


@csrf_exempt
@HasPermission("workflow-View")
def workflows(request):
    if request.method == "GET":
        current = _page(request, Workflow.objects.all())
        return WebUtils.response_success(
            {"count": current.paginator.count, "items": [{"id": item.id, "name": item.name, "key": item.key} for item in current]}
        )
    payload = _body(request)
    item = Workflow.objects.create(
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
@HasPermission("workflow-Edit")
def workflow_design(request, workflow_id):
    workflow = Workflow.objects.get(id=workflow_id)
    if request.method == "GET":
        version = workflow.versions.filter(is_published=False).order_by("-version_no").first()
        return WebUtils.response_success(version.design if version else {})
    payload = _body(request)
    version_no = (workflow.versions.order_by("-version_no").values_list("version_no", flat=True).first() or 0) + 1
    version = WorkflowVersion.objects.create(
        workflow=workflow, version_no=version_no, design=payload, created_by=_user(request), updated_by=_user(request)
    )
    return WebUtils.response_success({"id": version.id, "version_no": version_no})


@csrf_exempt
@HasPermission("workflow-Publish")
def publish_workflow(request, workflow_id):
    workflow = Workflow.objects.get(id=workflow_id)
    version = workflow.versions.order_by("-version_no").first()
    if version is None:
        return WebUtils.response_error("没有设计稿")
    try:
        xml = build_bpmn(version.design, workflow.key)
    except BpmnBuildError as exc:
        return WebUtils.response_error(str(exc))
    client = FlowableClient(settings.FLOWABLE_URL, settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD)
    try:
        deployed = client.deploy_bpmn(workflow.key, xml)
    except FlowableError as exc:
        return WebUtils.response_error(exc.body or "Flowable 部署失败")
    version.bpmn_xml = xml
    version.flowable_deployment_id = str(deployed.get("id") or "")
    version.process_definition_key = workflow.key
    version.is_published = True
    version.save()
    workflow.current_version = version
    workflow.save(update_fields=["current_version", "updated_at"])
    return WebUtils.response_success({"deployment_id": version.flowable_deployment_id})


@csrf_exempt
@HasPermission("org-View")
def handler_groups(request):
    if request.method == "GET":
        items = HandlerGroup.objects.all()
        return WebUtils.response_success(
            {"items": [{"id": item.id, "name": item.name, "members": item.members, "leaders": item.leaders} for item in items]}
        )
    payload = _body(request)
    item = HandlerGroup.objects.create(
        name=payload["name"],
        members=payload.get("members") or [],
        leaders=payload.get("leaders") or [],
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success({"id": item.id})


@HasPermission("notify-View")
def notify_templates(request):
    items = NotifyTemplate.objects.all()
    return WebUtils.response_success({"items": [{"id": item.id, "event": item.event, "title_tpl": item.title_tpl} for item in items]})


@HasPermission("workflow-View")
def workflow_types(request):
    return WebUtils.response_success({"items": [{"id": item.id, "name": item.name, "key": item.key} for item in WorkflowType.objects.all()]})


@HasPermission("workflow-View")
def workflow_variables(request):
    return WebUtils.response_success({"items": [{"id": item.id, "key": item.key, "name": item.name} for item in WorkflowVariable.objects.all()]})
