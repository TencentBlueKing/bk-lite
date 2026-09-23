from django.db import IntegrityError, transaction
from django.http import JsonResponse
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.loader import LanguageLoader
from apps.system_mgmt.models import SystemAPIToken
from apps.system_mgmt.serializers.system_api_token_serializer import SystemAPITokenSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation

_SECRET_LOG_VERBS = {"create": "创建", "update": "更新", "delete": "删除"}


def _get_loader(request) -> LanguageLoader:
    locale = getattr(getattr(request, "user", None), "locale", None) or "en"
    return LanguageLoader(app="system_mgmt", default_lang=locale)


class SystemAPITokenViewSet(viewsets.ModelViewSet):
    queryset = SystemAPIToken.objects.all().order_by("-id")
    serializer_class = SystemAPITokenSerializer

    def _log(self, request, action_type, instance):
        name = (instance.name or "").strip() or "未命名"
        log_operation(
            request,
            action_type,
            "system-manager",
            f"{_SECRET_LOG_VERBS[action_type]}系统令牌: {name} ({instance.system_id})",
            target_type="system_api_token",
            target_id=instance.pk,
            detail={"kind": "system", "name": instance.name or "", "system_id": instance.system_id},
        )

    @HasPermission("system_api_secret-View", "system-manager")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("system_api_secret-View", "system-manager")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("system_api_secret-Add", "system-manager")
    def create(self, request, *args, **kwargs):
        secret = SystemAPIToken.generate_secret()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        try:
            with transaction.atomic():
                instance = serializer.save(
                    secret_hash=SystemAPIToken.hash_secret(secret),
                    created_by=getattr(user, "username", "") or "",
                    created_by_domain=getattr(user, "domain", "domain.com") or "domain.com",
                )
        except IntegrityError:
            raise ValidationError({"name": "name already exists"})
        instance._plain_api_secret = secret
        self._log(request, "create", instance)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("system_api_secret-Edit", "system-manager")
    def update(self, request, *args, **kwargs):
        if not kwargs.get("partial"):
            loader = _get_loader(request)
            return JsonResponse(
                {
                    "result": False,
                    "message": loader.get("error.system_token_full_update_not_supported", "System tokens cannot be fully replaced"),
                }
            )
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                self.perform_update(serializer)
        except IntegrityError:
            raise ValidationError({"name": "name already exists"})
        self._log(request, "update", serializer.instance)
        return Response(serializer.data)

    @HasPermission("system_api_secret-Delete", "system-manager")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        response = super().destroy(request, *args, **kwargs)
        if response.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT):
            self._log(request, "delete", instance)
        return response
