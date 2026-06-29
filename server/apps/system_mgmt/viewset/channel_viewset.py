from django.db.models import Q
from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.viewset_utils import GenericViewSetFun
from apps.system_mgmt.models import Channel, ChannelChoices, User
from apps.system_mgmt.serializers import ChannelSerializer
from apps.system_mgmt.utils.channel_utils import send_by_dingtalk_bot, send_by_feishu_bot, send_by_wecom_bot, send_email
from apps.system_mgmt.utils.operation_log_utils import log_operation


class ChannelFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    channel_type = filters.CharFilter(field_name="channel_type", lookup_expr="exact")


class ChannelViewSet(viewsets.ModelViewSet, GenericViewSetFun):
    """渠道 ViewSet - 禁用未使用的 partial_update 接口

    权限校验：
    - 所有接口需要对应的 HasPermission 装饰器
    - list/retrieve/update/destroy/update_settings 需要校验用户对 Channel.team 的访问权限
    """

    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer
    filterset_class = ChannelFilter
    # 仅允许 GET (list, retrieve), POST (create, actions), PUT (update), DELETE (destroy)
    # 禁用 PATCH (partial_update)
    http_method_names = ["get", "post", "put", "delete", "options"]

    def _get_loader(self, request):
        """获取语言加载器"""
        locale = getattr(request.user, "locale", "en") if hasattr(request, "user") else "en"
        return LanguageLoader(app="system_mgmt", default_lang=locale)

    def _get_user_group_ids(self, user):
        """获取用户有权限的组ID集合"""
        if getattr(user, "is_superuser", False):
            return None  # superuser 返回 None 表示有权限访问所有组
        group_ids = set()
        for group in getattr(user, "group_list", []) or []:
            group_id = group.get("id") if isinstance(group, dict) else group
            try:
                group_ids.add(int(group_id))
            except (TypeError, ValueError):
                continue
        return group_ids

    def _parse_team_ids(self, team):
        """将 team 解析为 int ID 列表，返回 (ids, has_invalid_value)。"""
        if team is None:
            return [], False
        if isinstance(team, (int, str)):
            team = [team]
        if not isinstance(team, (list, tuple, set)):
            return [], True

        team_ids = []
        for team_id in team:
            try:
                team_ids.append(int(team_id))
            except (TypeError, ValueError):
                return [], True
        return team_ids, False

    def _validate_request_team_permission(self, request, require_team=False):
        """校验本次请求写入的 team 是否完全在用户组织范围内。"""
        if getattr(request.user, "is_superuser", False):
            return True, None

        has_team = "team" in request.data
        if not has_team and not require_team:
            return True, None

        requested_team_ids, has_invalid_team = self._parse_team_ids(request.data.get("team"))
        if has_invalid_team or not requested_team_ids:
            loader = self._get_loader(request)
            message = loader.get("error.channel_team_required", "请选择渠道所属组织")
            return False, JsonResponse({"result": False, "message": message}, status=400)

        user_group_ids = self._get_user_group_ids(request.user)
        if set(requested_team_ids) - user_group_ids:
            loader = self._get_loader(request)
            message = loader.get("error.no_permission_access_channel", "无权访问该渠道")
            return False, JsonResponse({"result": False, "message": message}, status=403)

        return True, None

    def _reject_if_opspilot_managed(self, request, channel):
        """OpsPilot 工作流自动托管的 NATS 通道禁止编辑/删除（防 API 绕过前端）。"""
        config = channel.config or {}
        if channel.channel_type == ChannelChoices.NATS and config.get("source") == "opspilot":
            loader = self._get_loader(request)
            message = loader.get(
                "error.opspilot_channel_readonly",
                "OpsPilot 工作流自动创建的通道不可编辑或删除",
            )
            return JsonResponse({"result": False, "message": message}, status=403)
        return None

    def _validate_channel_permission(self, request, channel):
        """校验用户是否有权限访问指定渠道

        Args:
            request: 请求对象
            channel: Channel 实例

        Returns:
            tuple: (is_valid, error_response)
        """
        if getattr(request.user, "is_superuser", False):
            return True, None

        user_group_ids = self._get_user_group_ids(request.user)
        channel_team_ids, has_invalid_team = self._parse_team_ids(channel.team)

        # 检查渠道的 team 是否与用户的组有交集
        if has_invalid_team or not user_group_ids.intersection(channel_team_ids):
            loader = self._get_loader(request)
            message = loader.get("error.no_permission_access_channel", "无权访问该渠道")
            return False, JsonResponse({"result": False, "message": message}, status=403)
        return True, None

    def _filter_by_accessible_teams(self, queryset, user):
        """按用户有权限的组筛选渠道

        Args:
            queryset: 原始查询集
            user: 当前用户对象

        Returns:
            QuerySet: 筛选后的查询集
        """
        if getattr(user, "is_superuser", False):
            return queryset

        user_group_ids = self._get_user_group_ids(user)
        if not user_group_ids:
            return queryset.none()

        # 构建查询条件：team 与用户有权限的组有交集
        query = Q()
        for group_id in user_group_ids:
            query |= Q(team__contains=group_id)
        return queryset.filter(query)

    @HasPermission("channel_list-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        # 按用户有权限的组筛选
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
        # 校验用户是否有权限访问该渠道
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

    @HasPermission("channel_list-Add")
    def create(self, request, *args, **kwargs):
        is_valid, error_response = self._validate_request_team_permission(request, require_team=True)
        if not is_valid:
            return error_response

        response = super().create(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 201:
            channel_name = response.data.get("name", "")
            channel_type = response.data.get("channel_type", "")
            log_operation(request, "create", "channel", f"新增{channel_type}渠道: {channel_name}")

        return response

    @HasPermission("channel_list-Edit")
    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        # 校验用户是否有权限访问该渠道
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response
        is_valid, error_response = self._validate_request_team_permission(request, require_team=True)
        if not is_valid:
            return error_response
        readonly_response = self._reject_if_opspilot_managed(request, obj)
        if readonly_response:
            return readonly_response

        response = super().update(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 200:
            channel_name = response.data.get("name", "")
            channel_type = response.data.get("channel_type", "")
            log_operation(request, "update", "channel", f"编辑{channel_type}渠道: {channel_name}")

        return response

    @HasPermission("channel_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        # 校验用户是否有权限访问该渠道
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response
        readonly_response = self._reject_if_opspilot_managed(request, obj)
        if readonly_response:
            return readonly_response

        channel_name = obj.name
        channel_type = obj.channel_type

        response = super().destroy(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 204:
            log_operation(request, "delete", "channel", f"删除{channel_type}渠道: {channel_name}")

        return response

    @action(methods=["POST"], detail=True)
    @HasPermission("channel_list-Edit")
    def update_settings(self, request, *args, **kwargs):
        obj: Channel = self.get_object()
        # 校验用户是否有权限访问该渠道
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response
        readonly_response = self._reject_if_opspilot_managed(request, obj)
        if readonly_response:
            return readonly_response

        config = request.data["config"]
        if obj.channel_type == "email":
            obj.encrypt_field("smtp_pwd", config)
            config.setdefault("smtp_pwd", obj.config["smtp_pwd"])
        elif obj.channel_type == "enterprise_wechat":
            obj.encrypt_field("secret", config)
            obj.encrypt_field("token", config)
            obj.encrypt_field("aes_key", config)
            config.setdefault("secret", obj.config["secret"])
            config.setdefault("token", obj.config["token"])
            config.setdefault("aes_key", obj.config["aes_key"])
        elif obj.channel_type == "enterprise_wechat_bot":
            obj.encrypt_field("webhook_url", config)
            config.setdefault("webhook_url", obj.config["webhook_url"])
        elif obj.channel_type == "nats":
            # NATS 配置无需加密处理
            pass
        obj.config = config
        obj.save()

        # 记录操作日志
        log_operation(request, "update", "channel", f"编辑{obj.channel_type}渠道: {obj.name}")

        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    @HasPermission("channel_list-Edit")
    def test_send(self, request, *args, **kwargs):
        channel_type = request.data.get("channel_type")
        config = request.data.get("config") or {}
        channel_name = request.data.get("name") or "Test Channel"

        supported_types = {
            ChannelChoices.EMAIL,
            ChannelChoices.ENTERPRISE_WECHAT_BOT,
            ChannelChoices.FEISHU_BOT,
            ChannelChoices.DINGTALK_BOT,
        }
        if channel_type not in supported_types:
            return Response({"result": False, "message": "Unsupported channel type"}, status=400)

        test_channel = Channel(name=channel_name, channel_type=channel_type, config=config, description="", team=[])
        title = f"[{channel_name}] Test Message"
        receiver_name = request.user.display_name or request.user.username
        content = f"This is a test message from channel '{channel_name}'.<br/>Receiver: {receiver_name}"

        if channel_type == ChannelChoices.EMAIL:
            if not request.user.email:
                return Response({"result": False, "message": "Current user email is empty"}, status=400)
            user_list = User.objects.filter(id=request.user.id)
            result = send_email(test_channel, title, content, user_list)
        elif channel_type == ChannelChoices.ENTERPRISE_WECHAT_BOT:
            result = send_by_wecom_bot(test_channel, content, [receiver_name])
        elif channel_type == ChannelChoices.FEISHU_BOT:
            result = send_by_feishu_bot(test_channel, title, content, [receiver_name])
        else:
            result = send_by_dingtalk_bot(test_channel, title, content, [receiver_name])

        if result.get("result") is False:
            return Response({"result": False, "message": result.get("message") or "Test send failed"}, status=400)

        if channel_type != ChannelChoices.EMAIL:
            if result.get("errcode") not in (None, 0) or result.get("code") not in (None, 0):
                return Response(
                    {
                        "result": False,
                        "message": result.get("errmsg") or result.get("msg") or result.get("message") or "Test send failed",
                    },
                    status=400,
                )

        return Response({"result": True})


class TemplateFilter(FilterSet):
    channel_type = filters.CharFilter(field_name="channel_type", lookup_expr="exact")
    name = filters.CharFilter(field_name="name", lookup_expr="lte")
