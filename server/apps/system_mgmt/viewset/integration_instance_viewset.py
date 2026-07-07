from django.db.models import Q
from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.system_mgmt.models import IntegrationInstance, IntegrationInstanceStatusChoices
from apps.system_mgmt.providers import RuntimeApplicationService, get_provider_registry
from apps.system_mgmt.serializers import IntegrationInstanceSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation


class IntegrationInstanceFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    provider_key = filters.CharFilter(field_name="provider_key", lookup_expr="exact")
    status = filters.CharFilter(field_name="status", lookup_expr="exact")


class IntegrationInstanceViewSet(MaintainerViewSet):
    queryset = IntegrationInstance.objects.all()
    serializer_class = IntegrationInstanceSerializer
    filterset_class = IntegrationInstanceFilter
    http_method_names = ["get", "post", "put", "delete", "options"]
    builtin_provider_key = "bk_lite_builtin"

    def _get_loader(self, request):
        locale = getattr(request.user, "locale", "en") if hasattr(request, "user") else "en"
        return LanguageLoader(app="system_mgmt", default_lang=locale)

    def _get_user_group_ids(self, user):
        if getattr(user, "is_superuser", False):
            return None
        return {group["id"] for group in getattr(user, "group_list", [])}

    def _validate_instance_permission(self, request, instance):
        if getattr(request.user, "is_superuser", False):
            return True, None

        user_group_ids = self._get_user_group_ids(request.user)
        instance_team_ids = set(instance.team or [])
        if user_group_ids and user_group_ids.intersection(instance_team_ids):
            return True, None

        loader = self._get_loader(request)
        return False, JsonResponse({"result": False, "message": loader.get("error.no_permission_access_team", "无权访问该团队数据")}, status=403)

    def _filter_by_accessible_teams(self, queryset, user):
        if getattr(user, "is_superuser", False):
            return queryset

        user_group_ids = self._get_user_group_ids(user)
        if not user_group_ids:
            return queryset.none()

        query = Q()
        for group_id in user_group_ids:
            query |= Q(team__contains=group_id)
        return queryset.filter(query)

    def _is_builtin_instance(self, instance):
        return instance.provider_key == self.builtin_provider_key

    @HasPermission("integration_center-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = self._filter_by_accessible_teams(queryset, request.user)
        queryset = queryset.exclude(provider_key=self.builtin_provider_key)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @HasPermission("integration_center-View")
    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        is_valid, error_response = self._validate_instance_permission(request, obj)
        if not is_valid:
            return error_response
        raw_origin = request.query_params.get("redirect_origin")
        redirect_origin = raw_origin if isinstance(raw_origin, str) and raw_origin.strip() else None
        context = self.get_serializer_context()
        context["redirect_origin"] = redirect_origin
        serializer = IntegrationInstanceSerializer(obj, context=context)
        return Response(serializer.data)

    @HasPermission("integration_center-Add")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            instance_name = response.data.get("name", "")
            log_operation(request, "create", "system-manager", f"新增集成实例: {instance_name}")
        return response

    @HasPermission("integration_center-Edit")
    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        if self._is_builtin_instance(obj):
            return JsonResponse({"result": False, "message": "Built-in integration instance cannot be modified"}, status=403)

        is_valid, error_response = self._validate_instance_permission(request, obj)
        if not is_valid:
            return error_response

        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            instance_name = response.data.get("name", "")
            log_operation(request, "update", "system-manager", f"编辑集成实例: {instance_name}")
        return response

    @HasPermission("integration_center-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if self._is_builtin_instance(obj):
            return JsonResponse({"result": False, "message": "Built-in integration instance cannot be deleted"}, status=403)

        is_valid, error_response = self._validate_instance_permission(request, obj)
        if not is_valid:
            return error_response

        instance_name = obj.name
        response = super().destroy(request, *args, **kwargs)
        if response.status_code == 204:
            log_operation(request, "delete", "system-manager", f"删除集成实例: {instance_name}")
        return response

    @action(methods=["GET"], detail=False)
    @HasPermission("integration_center-View")
    def providers(self, request, *args, **kwargs):
        data = [manifest.to_public_dict() for manifest in get_provider_registry().list()]
        return Response(data)

    @action(methods=["GET"], detail=True)
    @HasPermission("integration_center-View")
    def status(self, request, *args, **kwargs):
        obj = self.get_object()
        is_valid, error_response = self._validate_instance_permission(request, obj)
        if not is_valid:
            return error_response
        return Response(
            {
                "status": obj.status,
                "enabled": obj.enabled,
                "capability_status": obj.capability_status,
            }
        )

    @action(methods=["POST"], detail=True)
    @HasPermission("integration_center-Edit")
    def test_connection(self, request, *args, **kwargs):
        obj = self.get_object()
        is_valid, error_response = self._validate_instance_permission(request, obj)
        if not is_valid:
            return error_response

        capability_key = (request.data.get("capability_key") or "").strip()
        runtime_service = RuntimeApplicationService()
        result = runtime_service.test_connection(obj, capability_key=capability_key or None)
        payload = result.payload
        if capability_key:
            capability_status = dict(obj.capability_status or {})
            capability_status.update(payload.get("capability_status") or {})
            obj.capability_status = capability_status
            if capability_status and all(status == IntegrationInstanceStatusChoices.READY for status in capability_status.values()):
                obj.status = IntegrationInstanceStatusChoices.READY
            elif any(status == IntegrationInstanceStatusChoices.VERIFICATION_FAILED for status in capability_status.values()):
                obj.status = IntegrationInstanceStatusChoices.VERIFICATION_FAILED
            else:
                obj.status = IntegrationInstanceStatusChoices.PENDING_VERIFICATION
        else:
            obj.status = payload.get("instance_status", IntegrationInstanceStatusChoices.VERIFICATION_FAILED)
            obj.capability_status = payload.get("capability_status", obj.capability_status)
        obj.save(update_fields=["status", "capability_status", "updated_at"])

        log_operation(request, "execute", "system-manager", f"测试集成实例连接: {obj.name}")
        return Response({"result": result.success, "data": result.to_dict()})

    @action(methods=["GET"], detail=False)
    @HasPermission("integration_center-View")
    def available_instances(self, request, *args, **kwargs):
        capability = request.query_params.get("capability")
        if not capability:
            return Response({"result": False, "message": "capability is required"}, status=400)

        queryset = IntegrationInstance.objects.filter(
            enabled=True,
            status=IntegrationInstanceStatusChoices.READY,
        ).exclude(provider_key=self.builtin_provider_key)

        instances = []
        for item in queryset.order_by("name", "id"):
            if (
                item.capability_enabled.get(capability) is True
                and item.capability_status.get(capability) == IntegrationInstanceStatusChoices.READY
            ):
                manifest = get_provider_registry().get(item.provider_key)
                provider_name = manifest.name if manifest else item.provider_key
                instances.append({
                    "id": item.id,
                    "name": item.name,
                    "provider_key": item.provider_key,
                    "provider_name": provider_name,
                })
        return Response(instances)
