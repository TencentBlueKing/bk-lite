from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.system_mgmt.models import IMAccountAssociation, IMNotificationChannel
from apps.system_mgmt.serializers.im_notification_channel_serializer import IMNotificationChannelSerializer
from apps.system_mgmt.services.im_channel_access import can_access_im_channel, filter_accessible_im_channels, get_user_group_ids
from apps.system_mgmt.services.im_notification_service import send_im_notification, send_im_notification_to_users
from apps.system_mgmt.utils.operation_log_utils import log_operation
from apps.system_mgmt.viewset.im_account_association_viewset import optional_instance_id
from config.drf.pagination import CustomPageNumberPagination

_IM_CHANNEL_IN_USE_FALLBACK = "This IM notification channel is still used by other business configs and cannot be deleted"
ACCOUNT_ASSOCIATION_OPTION_LIMIT = 500


class IMNotificationChannelViewSet(MaintainerViewSet):
    queryset = (
        IMNotificationChannel.objects.select_related("integration_instance", "account_association")
        .prefetch_related("tags")
        .all()
        .order_by("name", "id")
    )
    serializer_class = IMNotificationChannelSerializer
    pagination_class = CustomPageNumberPagination
    ordering = ("-id",)

    def _get_user_group_ids(self, user):
        return get_user_group_ids(user)

    def _filter_by_accessible_teams(self, queryset, user):
        return filter_accessible_im_channels(queryset, user)

    def _validate_channel_permission(self, request, channel):
        if not can_access_im_channel(request.user, channel):
            message = self.loader.get("error.no_permission_access_team", "无权访问该团队数据") if self.loader else "无权访问该团队数据"
            return False, JsonResponse({"result": False, "message": message}, status=403)
        return True, None

    def _normalize_team_ids(self, team_values):
        if isinstance(team_values, (int, str)):
            team_values = [team_values]
        if team_values is None:
            return [], False
        if not isinstance(team_values, (list, tuple, set)):
            return [], True

        normalized = []
        for value in team_values:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return [], True
            if parsed <= 0:
                return [], True
            normalized.append(parsed)
        return normalized, False

    def _team_required_error(self):
        message = self.loader.get("error.channel_team_required", "请选择渠道所属组织") if self.loader else "请选择渠道所属组织"
        return JsonResponse({"result": False, "message": message}, status=400)

    def _validate_team_in_user_scope(self, request, team_values, require_team=False):
        normalized, has_invalid_team = self._normalize_team_ids(team_values)
        if has_invalid_team or (require_team and not normalized):
            return False, self._team_required_error()

        if getattr(request.user, "is_superuser", False):
            return True, None

        user_group_ids = self._get_user_group_ids(request.user)
        if not user_group_ids:
            message = self.loader.get("error.no_permission_access_team", "无权访问该团队数据") if self.loader else "无权访问该团队数据"
            return False, JsonResponse({"result": False, "message": message}, status=403)

        invalid = set(normalized) - user_group_ids
        if invalid:
            message = self.loader.get("error.no_permission_for_groups", "您没有以下组织的权限") if self.loader else "您没有以下组织的权限"
            return False, JsonResponse({"result": False, "message": message}, status=403)
        return True, None

    @HasPermission("channel_list-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = self._filter_by_accessible_teams(queryset, request.user)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @HasPermission("channel_list-View")
    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

    @HasPermission("channel_list-Add")
    def create(self, request, *args, **kwargs):
        team_values = request.data.get("team")
        is_valid, error_response = self._validate_team_in_user_scope(request, team_values, require_team=True)
        if not is_valid:
            return error_response

        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            log_operation(request, "create", "channel", f"新增IM应用通知: {response.data.get('name', '')}")
        return response

    @HasPermission("channel_list-Edit")
    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response

        has_team = "team" in request.data
        team_values = request.data.get("team") if has_team else getattr(obj, "team", None)
        is_valid, error_response = self._validate_team_in_user_scope(request, team_values, require_team=has_team)
        if not is_valid:
            return error_response

        response = super().update(request, *args, partial=True, **kwargs)
        if response.status_code == 200:
            log_operation(request, "update", "channel", f"编辑IM应用通知: {response.data.get('name', '')}")
        return response

    @HasPermission("channel_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response

        channel_name = obj.name
        try:
            with transaction.atomic():
                response = super().destroy(request, *args, **kwargs)
        except ProtectedError:
            loader = self.loader
            message = loader.get("error.im_channel_in_use", _IM_CHANNEL_IN_USE_FALLBACK) if loader else _IM_CHANNEL_IN_USE_FALLBACK
            return JsonResponse(
                {
                    "result": False,
                    "code": "IM_CHANNEL_IN_USE",
                    "message": message,
                },
                status=409,
            )

        if response.status_code in (200, 204):
            log_operation(request, "delete", "channel", f"删除IM应用通知: {channel_name}")
        return response

    @action(methods=["GET"], detail=False, url_path="account_association_options")
    @HasPermission("channel_list-View")
    def account_association_options(self, request, *args, **kwargs):
        queryset = IMAccountAssociation.objects.select_related("integration_instance").order_by("name", "id")
        try:
            instance_id = optional_instance_id(request.query_params.get("integration_instance_id"))
        except ValueError:
            return JsonResponse({"result": False, "message": "Integration instance must be an integer"}, status=400)
        if instance_id is not None:
            queryset = queryset.filter(integration_instance_id=instance_id)
        data = [
            {
                "id": item.id,
                "name": item.name,
                "integration_instance_id": item.integration_instance_id,
                "integration_instance_name": item.integration_instance.name,
                "status": item.status,
            }
            for item in queryset[:ACCOUNT_ASSOCIATION_OPTION_LIMIT]
        ]
        return JsonResponse({"result": True, "data": data})

    @action(methods=["POST"], detail=True)
    @HasPermission("channel_list-Edit")
    def test_send(self, request, *args, **kwargs):
        channel = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, channel)
        if not is_valid:
            return error_response
        result = send_im_notification(
            channel.id,
            title=request.data.get("title", "Test Message"),
            content=request.data.get("content", "This is a test message"),
            receivers=request.data.get("receivers") or [request.user.id],
        )
        status = 200 if result.get("result") else 400
        return JsonResponse(result, status=status)

    @action(methods=["POST"], detail=False)
    @HasPermission("channel_list-Edit")
    def send(self, request, *args, **kwargs):
        channel_id = request.data.get("channel_id")
        user_ids = request.data.get("user_ids") or []
        title = request.data.get("title", "")
        content = request.data.get("content", "")

        try:
            channel_id = int(channel_id)
            user_ids = [int(uid) for uid in user_ids]
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "Invalid channel_id or user_ids"}, status=400)

        channel = IMNotificationChannel.objects.filter(id=channel_id).first()
        if not channel:
            return JsonResponse({"result": False, "message": "IM notification channel not found"}, status=404)

        is_valid, error_response = self._validate_channel_permission(request, channel)
        if not is_valid:
            return error_response

        result = send_im_notification_to_users(channel_id, user_ids, title, content)
        status = 200 if result.get("result") else 400
        return JsonResponse(result, status=status)
