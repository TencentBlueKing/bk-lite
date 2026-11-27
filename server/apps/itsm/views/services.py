import json

from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models import Service, ServiceCatalog, ServiceFavorite, ServiceRecent, TicketFormTemplate, Workflow
from apps.itsm.serializers import ServiceCatalogSerializer, ServiceSerializer
from apps.itsm.serializers.service import PortalServiceSerializer
from apps.itsm.services.service_access import visible_services
from apps.itsm.services.service_assignment import eligible_handler_groups, has_open_group_tickets, requires_handler_group
from apps.itsm.views.access import api_errors, domain_of, has_permission, list_page
from apps.itsm.views.base import ItsmAPIView


def _body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _user(request):
    return getattr(getattr(request, "user", None), "username", "") or ""


def _service_item(service):
    return PortalServiceSerializer(service).data


class CatalogView(ItsmAPIView):
    @api_errors
    @HasPermission("workflow-Edit")
    def get(self, request):
        items = ServiceCatalog.objects.filter(domain=domain_of(request)).order_by("order", "id")
        return Response({"items": ServiceCatalogSerializer(items, many=True).data})

    @api_errors
    @HasPermission("workflow-Edit")
    def post(self, request):
        payload = request.data
        if payload.get("id"):
            item = ServiceCatalog.objects.filter(domain=domain_of(request)).filter(id=payload["id"]).first()
            if item is None:
                return self.fail("目录不存在", 404)
            serializer = ServiceCatalogSerializer(item, data=payload, partial=True)
        else:
            serializer = ServiceCatalogSerializer(data=payload)
        serializer.context["domain"] = domain_of(request)
        serializer.is_valid(raise_exception=True)
        actor = self.actor(request)
        if serializer.instance is None:
            serializer.save(domain=domain_of(request), created_by=actor, updated_by=actor)
        else:
            serializer.save(updated_by=actor)
        return Response({"id": serializer.instance.id})

    @api_errors
    @HasPermission("workflow-Edit")
    def delete(self, request):
        item = ServiceCatalog.objects.filter(domain=domain_of(request)).filter(id=request.GET.get("id")).first()
        if item is None:
            return self.fail("目录不存在", 404)
        if Service.objects.filter(domain=domain_of(request)).filter(catalog=item).exists() or item.children.exists():
            return self.fail("目录下还有服务或子目录，不能删除")
        item.delete()
        return Response({"id": request.GET.get("id")})


class ServiceView(ItsmAPIView):
    @api_errors
    @HasPermission("workflow-Edit")
    def get(self, request):
        domain = domain_of(request)
        items = Service.objects.filter(domain=domain).select_related("workflow").order_by("order", "id")
        workflow_nodes = Workflow.objects.filter(domain=domain, current_version__is_published=True).values_list(
            "pk", "current_version__design__nodes"
        )
        group_workflows = {pk for pk, nodes in workflow_nodes if requires_handler_group({"nodes": nodes or []})}
        return Response(
            {
                "items": ServiceSerializer(items, many=True, context={"group_workflows": group_workflows}).data,
                "eligible_handler_groups": eligible_handler_groups(domain),
                "requires_handler_group_workflow_ids": sorted(group_workflows),
            }
        )

    @api_errors
    @HasPermission("workflow-Edit")
    @transaction.atomic
    def post(self, request):
        payload = request.data
        domain = domain_of(request)
        current = Service.objects.filter(domain=domain, id=payload.get("id"))
        target_workflow_id = payload.get("workflow_id") or current.values_list("workflow_id", flat=True).first()
        # 发布也先锁流程，再锁服务，避免并发启用沿用旧版本的处理人要求。
        if target_workflow_id:
            Workflow.objects.select_for_update().only("pk").filter(pk=target_workflow_id, domain=domain).first()
        if payload.get("id"):
            item = current.select_for_update().first()
            if item is None:
                return self.fail("服务不存在", 404)
            if not payload.get("workflow_id") and item.workflow_id != target_workflow_id:
                return self.fail("服务绑定的流程已变更，请刷新后重试", 409)
            serializer = ServiceSerializer(item, data=payload, partial=True)
        else:
            serializer = ServiceSerializer(data=payload)
        serializer.context["domain"] = domain_of(request)
        serializer.is_valid(raise_exception=True)
        actor = self.actor(request)
        workflow = serializer.validated_data.pop("workflow", None)
        serializer.validated_data.pop("workflow_id", None)
        extra = {"updated_by": actor, "domain": domain_of(request)}
        if serializer.instance is None:
            extra["created_by"] = actor
        serializer.save(workflow=workflow, **extra) if workflow is not None else serializer.save(**extra)
        return Response({"id": serializer.instance.id})

    @api_errors
    @HasPermission("workflow-Edit")
    @transaction.atomic
    def delete(self, request):
        service = Service.objects.select_for_update().filter(domain=domain_of(request), id=request.GET.get("id")).first()
        if service is None:
            return self.fail("服务不存在", 404)
        if has_open_group_tickets(service):
            return self.fail("服务有依赖处理组的在办工单，暂时无法删除")
        service.delete()
        return Response({"id": request.GET.get("id")})


@api_errors
@HasPermission("portal-View")
def service_portal(request):
    username = _user(request)
    org = domain_of(request)
    if request.GET.get("service_id"):
        target = visible_services(request, service_id=request.GET["service_id"]).select_related("workflow").get()
        return WebUtils.response_success({"can_apply": has_permission(request, "ticket-Add"), "services": [_service_item(target)]})
    if request.GET.get("directory"):
        catalog = request.GET.get("catalog")
        ids = None
        if catalog is not None:
            ids = set()
            if int(catalog) != 0:
                children = {}
                for pk, parent in ServiceCatalog.objects.filter(domain=org).values_list("id", "parent_id"):
                    children.setdefault(parent, []).append(pk)
                pending = [int(catalog)]
                while pending:
                    pk = pending.pop()
                    if pk not in ids:
                        ids.add(pk)
                        pending.extend(children.get(pk, []))
        services = visible_services(request, keyword=request.GET.get("keyword", "").strip(), catalog_ids=ids)
        page = list_page(request.GET, services.select_related("workflow").order_by("order", "pk"))
        return WebUtils.response_success({"items": [_service_item(item) for item in page], "total": page.paginator.count, "page": page.number})
    enabled = visible_services(request).select_related("workflow").order_by("order", "id")
    # 新版首页仅预载目录第一页，后续筛选走目录查询。
    summary = request.GET.get("summary") == "1"
    first = list(enabled[:10]) if summary else list(enabled)
    catalogs_qs = ServiceCatalog.objects.filter(domain=domain_of(request)).order_by("order", "id")
    favorite_ids = list(ServiceFavorite.objects.filter(domain=domain_of(request)).filter(username=username).values_list("service_id", flat=True))
    recent = (
        ServiceRecent.objects.filter(domain=domain_of(request))
        .filter(username=username, service_id__in=enabled.values("id"))
        .select_related("service__workflow")
        .order_by("-last_used_at")[:8]
    )
    return WebUtils.response_success(
        {
            "can_manage": has_permission(request, "workflow-Edit"),
            "can_apply": has_permission(request, "ticket-Add"),
            "catalogs": [{"id": item.id, "name": item.name, "parent_id": item.parent_id} for item in catalogs_qs],
            "services": [_service_item(item) for item in first],
            "service_total": enabled.count() if summary else len(first),
            "favorites": [_service_item(item) for item in enabled.filter(pk__in=favorite_ids)],
            "recents": [_service_item(item.service) for item in recent if item.service.is_enabled],
            "hots": [_service_item(item) for item in enabled.filter(is_hot=True)[:6]]
            if summary
            else [_service_item(item) for item in first if item.is_hot],
        }
    )


@api_errors
@HasPermission("portal-View")
def service_hot(request):
    items = visible_services(request, hot_only=True).select_related("workflow").order_by("order", "id")
    return WebUtils.response_success({"items": [_service_item(item) for item in items]})


@csrf_exempt
@api_errors
@HasPermission("portal-View")
def service_favorite(request, service_id):
    if request.method != "POST":
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    username = _user(request)
    service = visible_services(request, service_id=service_id).get()
    favorite = ServiceFavorite.objects.filter(domain=domain_of(request)).filter(username=username, service=service).first()
    if favorite:
        favorite.delete()
        return WebUtils.response_success({"favorite": False})
    ServiceFavorite.objects.create(domain=domain_of(request), username=username, service=service, created_by=username, updated_by=username)
    return WebUtils.response_success({"favorite": True, "service": _service_item(service)})


@csrf_exempt
@api_errors
@HasPermission("portal-View")
def service_use(request, service_id):
    if request.method != "POST":
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    username = _user(request)
    service = visible_services(request, service_id=service_id).get()
    recent, _ = ServiceRecent.objects.get_or_create(
        domain=domain_of(request),
        username=username,
        service=service,
        defaults={"created_by": username, "updated_by": username, "last_used_at": timezone.now()},
    )
    recent.last_used_at = timezone.now()
    recent.save(update_fields=["last_used_at", "updated_at"])
    return WebUtils.response_success({"id": service.id, "version_id": service.workflow.current_version_id})


@csrf_exempt
@api_errors
@HasPermission("ticket-Add")
def service_form_templates(request, service_id):
    from apps.itsm.services.form.templates import project_template_values
    from apps.itsm.services.ticket.service import _find_node, workflow_schema

    service = visible_services(request, service_id=service_id).select_related("workflow__current_version", "workflow__form__current_version").get()
    version = service.workflow.current_version
    schema = workflow_schema(version)
    permissions = _find_node(version.design, node_type="submit").get("field_perm", {})
    owner = {"domain": domain_of(request), "username": _user(request), "workflow": service.workflow}
    owned = TicketFormTemplate.objects.filter(**owner)

    def item_data(item):
        current = project_template_values(schema.get("fields") or [], item.form_data, permissions)
        return {"id": item.id, "name": item.name, "form_data": current, "changed": current != item.form_data}

    if request.method == "GET":
        return WebUtils.response_success({"items": [item_data(item) for item in owned.order_by("-updated_at", "-id")[:50]]})
    if request.method == "DELETE":
        item = owned.filter(id=request.GET.get("id")).first()
        if item is None:
            return WebUtils.response_error("模板不存在", status_code=404)
        item.delete()
        return WebUtils.response_success({"id": item.id})
    if request.method != "POST":
        return WebUtils.response_error("不支持的请求方法", status_code=405)
    payload = _body(request)
    if not isinstance(payload, dict):
        return WebUtils.response_error("请求体必须为对象")
    name = payload.get("name")
    values = payload.get("form_data")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        return WebUtils.response_error("模板名称应为 1 至 100 个字符")
    if not isinstance(values, dict) or len(json.dumps(values, ensure_ascii=False)) > 65536:
        return WebUtils.response_error("模板表单数据无效或超过 64 KB")
    if owned.count() >= 50:
        return WebUtils.response_error("每个流程最多保存 50 个模板")
    item = TicketFormTemplate.objects.create(
        **owner,
        name=name.strip(),
        form_data=project_template_values(schema.get("fields") or [], values, permissions),
        created_by=_user(request),
        updated_by=_user(request),
    )
    return WebUtils.response_success(item_data(item))
