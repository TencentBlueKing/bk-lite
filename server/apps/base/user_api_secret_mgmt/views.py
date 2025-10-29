from django.http import JsonResponse
from django.utils.translation import gettext as _
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.base.models import UserAPISecret
from apps.base.user_api_secret_mgmt.serializers import UserAPISecretSerializer
from apps.core.decorators.api_permission import HasPermission


class UserAPISecretViewSet(viewsets.ModelViewSet):
    queryset = UserAPISecret.objects.all()
    serializer_class = UserAPISecretSerializer
    ordering = ("-id",)

    @HasPermission("api_secret_key-View", "opspilot")
    def list(self, request, *args, **kwargs):
        current_team = request.COOKIES.get("current_team") or 0
        query = self.get_queryset().filter(username=request.user.username, team=int(current_team))
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
        current_team = request.COOKIES.get("current_team")
        if UserAPISecret.objects.filter(username=username, team=current_team).exists():
            return JsonResponse({"result": False, "message": _("This user already has an API Secret")})
        additional_data = {
            "username": username,
            "api_secret": UserAPISecret.generate_api_secret(),
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
