from django.http import JsonResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.base.models import UserAPISecret
from apps.base.user_api_secret_mgmt.serializers import UserAPISecretSerializer
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.loader import LanguageLoader


def _get_loader(request) -> LanguageLoader:
    """获取基于用户locale的LanguageLoader"""
    locale = getattr(getattr(request, "user", None), "locale", None) or "en"
    return LanguageLoader(app="core", default_lang=locale)


def _parse_current_team(request, loader: LanguageLoader):
    current_team = request.COOKIES.get("current_team", "0")
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

    @HasPermission("api_secret_key-View", "opspilot")
    def list(self, request, *args, **kwargs):
        loader = _get_loader(request)
        current_team, error_response = _parse_current_team(request, loader)
        if error_response:
            return error_response
        query = self.get_queryset().filter(username=request.user.username, domain=request.user.domain, team=current_team)
        queryset = self.filter_queryset(query)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["POST"])
    @HasPermission("api_secret_key-Add", "opspilot")
    def generate_api_secret(self, request):
        api_secret = UserAPISecret.generate_api_secret()
        return JsonResponse({"result": True, "data": {"api_secret": api_secret}})

    @HasPermission("api_secret_key-Add", "opspilot")
    def create(self, request, *args, **kwargs):
        username = request.user.username
        loader = _get_loader(request)
        current_team, error_response = _parse_current_team(request, loader)
        if error_response:
            return error_response
        if UserAPISecret.objects.filter(username=username, domain=request.user.domain, team=current_team).exists():
            return JsonResponse(
                {
                    "result": False,
                    "message": loader.get("error.api_secret_exists", "This user already has an API Secret"),
                }
            )
        additional_data = {
            "username": username,
            "api_secret": UserAPISecret.generate_api_secret(),
            "domain": request.user.domain,
            "team": current_team,
        }
        serializer = self.get_serializer(data=additional_data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        return JsonResponse({"result": False, "message": "API密钥不支持修改"})

    @HasPermission("api_secret_key-Delete", "opspilot")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
