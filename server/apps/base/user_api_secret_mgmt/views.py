from django.db import IntegrityError, transaction
from django.http import JsonResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.base.models.user import UserAPISecret
from apps.base.user_api_secret_mgmt.serializers import UserAPISecretCreateSerializer, UserAPISecretSerializer
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.team_utils import get_current_team
from apps.system_mgmt.utils.operation_log_utils import log_operation

_SECRET_LOG_VERBS = {"create": "创建", "update": "更新", "delete": "删除"}


def _log_secret_operation(request, action_type, instance):
    name = (instance.name or "").strip() or "未命名"
    log_operation(
        request,
        action_type,
        "system-manager",
        f"{_SECRET_LOG_VERBS[action_type]}个人令牌: {name}",
        target_type="user_api_secret",
        target_id=instance.pk,
        detail={"kind": "personal", "name": instance.name or "", "team": instance.team},
    )


def _get_loader(request) -> LanguageLoader:
    """获取基于用户locale的LanguageLoader"""
    locale = getattr(getattr(request, "user", None), "locale", None) or "en"
    return LanguageLoader(app="core", default_lang=locale)


def _parse_current_team(request, loader: LanguageLoader):
    current_team = get_current_team(request, "0")
    try:
        return int(current_team), None
    except (TypeError, ValueError):
        return None, JsonResponse(
            {
                "result": False,
                "message": loader.get("error.invalid_current_team", "Invalid current_team cookie"),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class UserAPISecretViewSet(viewsets.ModelViewSet):
    queryset = UserAPISecret.objects.all()
    serializer_class = UserAPISecretSerializer
    ordering = ("-id",)

    def get_queryset(self):
        request = getattr(self, "request", None)
        user = getattr(request, "user", None)
        if not request or not user or not user.is_authenticated:
            return UserAPISecret.objects.none()

        current_team = get_current_team(request, "0")
        try:
            current_team = int(current_team)
        except (TypeError, ValueError):
            return UserAPISecret.objects.none()

        return UserAPISecret.objects.filter(username=user.username, domain=user.domain, team=current_team)

    @HasPermission("api_secret_key-View", "system-manager")
    def list(self, request, *args, **kwargs):
        loader = _get_loader(request)
        _, error_response = _parse_current_team(request, loader)
        if error_response:
            return error_response
        query = self.get_queryset()
        queryset = self.filter_queryset(query)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @HasPermission("api_secret_key-View", "system-manager")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["POST"])
    @HasPermission("api_secret_key-Add", "system-manager")
    def generate_api_secret(self, request):
        api_secret = UserAPISecret.generate_api_secret()
        return JsonResponse({"result": True, "data": {"api_secret": api_secret}})

    @HasPermission("api_secret_key-Add", "system-manager")
    def create(self, request, *args, **kwargs):
        username = request.user.username
        loader = _get_loader(request)
        current_team, error_response = _parse_current_team(request, loader)
        if error_response:
            return error_response
        api_secret = UserAPISecret.generate_api_secret()
        additional_data = {
            "username": username,
            "api_secret": UserAPISecret.hash_api_secret(api_secret),
            "domain": request.user.domain,
            "team": current_team,
            "name": request.data.get("name") or "",
            "expires_at": request.data.get("expires_at"),
            "scope": request.data.get("scope"),
        }
        serializer = UserAPISecretCreateSerializer(data=additional_data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                self.perform_create(serializer)
        except IntegrityError:
            raise ValidationError({"name": "name already exists"})
        serializer.instance._plain_api_secret = api_secret
        _log_secret_operation(request, "create", serializer.instance)
        response_serializer = UserAPISecretCreateSerializer(serializer.instance, context=self.get_serializer_context())
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("api_secret_key-Add", "system-manager")
    def update(self, request, *args, **kwargs):
        loader = _get_loader(request)
        if not kwargs.get("partial"):
            return JsonResponse(
                {
                    "result": False,
                    "message": loader.get("error.api_token_update_not_supported", "API tokens cannot be fully replaced"),
                }
            )
        _, error_response = _parse_current_team(request, loader)
        if error_response:
            return error_response
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                self.perform_update(serializer)
        except IntegrityError:
            raise ValidationError({"name": "name already exists"})
        _log_secret_operation(request, "update", serializer.instance)
        return Response(serializer.data)

    @HasPermission("api_secret_key-Delete", "system-manager")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        response = super().destroy(request, *args, **kwargs)
        if response.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT):
            _log_secret_operation(request, "delete", instance)
        return response
