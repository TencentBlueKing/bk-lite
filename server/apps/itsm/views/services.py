import json

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models import Service, ServiceCatalog, ServiceFavorite, ServiceRecent
from apps.itsm.serializers import ServiceCatalogSerializer, ServiceSerializer
from apps.itsm.views.base import ItsmAPIView


def _body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _user(request):
    return getattr(getattr(request, "user", None), "username", "") or "admin"


def _service_item(service):
    return ServiceSerializer(service).data


class CatalogView(ItsmAPIView):
    @HasPermission("workflow-Edit")
    def get(self, request):
        items = ServiceCatalog.objects.order_by("order", "id")
        return Response({"items": ServiceCatalogSerializer(items, many=True).data})

    @HasPermission("workflow-Edit")
    def post(self, request):
        payload = request.data
        if payload.get("id"):
            item = ServiceCatalog.objects.filter(id=payload["id"]).first()
            if item is None:
                return self.fail("目录不存在", 404)
            serializer = ServiceCatalogSerializer(item, data=payload, partial=True)
        else:
            serializer = ServiceCatalogSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        actor = self.actor(request)
        if serializer.instance is None:
            serializer.save(created_by=actor, updated_by=actor)
        else:
            serializer.save(updated_by=actor)
        return Response({"id": serializer.instance.id})

    @HasPermission("workflow-Edit")
    def delete(self, request):
        item = ServiceCatalog.objects.filter(id=request.GET.get("id")).first()
        if item is None:
            return self.fail("目录不存在", 404)
        if Service.objects.filter(catalog=item).exists() or item.children.exists():
            return self.fail("目录下还有服务或子目录，不能删除")
        item.delete()
        return Response({"id": request.GET.get("id")})


class ServiceView(ItsmAPIView):
    @HasPermission("workflow-Edit")
    def get(self, request):
        items = Service.objects.select_related("workflow").order_by("order", "id")
        return Response({"items": ServiceSerializer(items, many=True).data})

    @HasPermission("workflow-Edit")
    def post(self, request):
        payload = request.data
        if payload.get("id"):
            item = Service.objects.select_related("workflow").filter(id=payload["id"]).first()
            if item is None:
                return self.fail("服务不存在", 404)
            serializer = ServiceSerializer(item, data=payload, partial=True)
        else:
            serializer = ServiceSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        actor = self.actor(request)
        workflow = serializer.validated_data.pop("workflow", None)
        serializer.validated_data.pop("workflow_id", None)
        extra = {"updated_by": actor}
        if serializer.instance is None:
            extra["created_by"] = actor
        serializer.save(workflow=workflow, **extra) if workflow is not None else serializer.save(**extra)
        return Response({"id": serializer.instance.id})

    @HasPermission("workflow-Edit")
    def delete(self, request):
        deleted, _rows = Service.objects.filter(id=request.GET.get("id")).delete()
        if not deleted:
            return self.fail("服务不存在", 404)
        return Response({"id": request.GET.get("id")})


@HasPermission("portal-View")
def service_portal(request):
    username = _user(request)
    enabled = Service.objects.select_related("workflow").filter(is_enabled=True).order_by("order", "id")
    catalogs_qs = ServiceCatalog.objects.order_by("order", "id")
    favorite_ids = list(ServiceFavorite.objects.filter(username=username).values_list("service_id", flat=True))
    recent = ServiceRecent.objects.filter(username=username).select_related("service__workflow").order_by("-last_used_at")[:8]
    return WebUtils.response_success(
        {
            "catalogs": [{"id": item.id, "name": item.name, "parent_id": item.parent_id} for item in catalogs_qs],
            "services": [_service_item(item) for item in enabled],
            "favorites": [_service_item(item) for item in enabled if item.id in favorite_ids],
            "recents": [_service_item(item.service) for item in recent if item.service.is_enabled],
            "hots": [_service_item(item) for item in enabled if item.is_hot],
        }
    )


@HasPermission("portal-View")
def service_hot(request):
    items = Service.objects.select_related("workflow").filter(is_enabled=True, is_hot=True).order_by("order", "id")
    return WebUtils.response_success({"items": [_service_item(item) for item in items]})


@csrf_exempt
@HasPermission("portal-View")
def service_favorite(request, service_id):
    username = _user(request)
    service = Service.objects.get(id=service_id)
    favorite = ServiceFavorite.objects.filter(username=username, service=service).first()
    if favorite:
        favorite.delete()
        return WebUtils.response_success({"favorite": False})
    ServiceFavorite.objects.create(username=username, service=service, created_by=username, updated_by=username)
    return WebUtils.response_success({"favorite": True})


@csrf_exempt
@HasPermission("portal-View")
def service_use(request, service_id):
    username = _user(request)
    service = Service.objects.get(id=service_id)
    recent, _ = ServiceRecent.objects.get_or_create(
        username=username,
        service=service,
        defaults={"created_by": username, "updated_by": username, "last_used_at": timezone.now()},
    )
    recent.last_used_at = timezone.now()
    recent.save(update_fields=["last_used_at", "updated_at"])
    return WebUtils.response_success({"id": service.id, "version_id": service.workflow.current_version_id})
