from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.cmdb.models import UserPersonalConfig
from apps.cmdb.serializers.user_personal_config import UserPersonalConfigSerializer
from config.drf.pagination import CustomPageNumberPagination


class UserPersonalConfigViewSet(viewsets.ModelViewSet):
    """用户个人配置视图集 - 通用配置API
    
    提供统一的用户配置管理接口，支持：
    - 标准CRUD操作（通过ID）
    - 按config_key查询和操作
    - 列出所有配置键
    """
    queryset = UserPersonalConfig.objects.all()
    serializer_class = UserPersonalConfigSerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """只返回当前用户的配置"""
        username = self.request.user.username
        domain = getattr(self.request.user, "domain", "domain.com")
        return UserPersonalConfig.objects.filter(
            username=username, domain=domain
        ).order_by("-updated_at")

    def perform_create(self, serializer):
        """创建时自动填充用户信息"""
        username = self.request.user.username
        domain = getattr(self.request.user, "domain", "domain.com")
        serializer.save(username=username, domain=domain)

    def create(self, request, *args, **kwargs):
        """创建配置"""
        # 检查config_value必须是dict
        config_value = request.data.get("config_value")
        if config_value is not None and not isinstance(config_value, dict):
            return Response(
                {"result": False, "message": "配置值必须是对象类型"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return Response({"result": True, "data": serializer.data})

    def update(self, request, *args, **kwargs):
        """更新配置"""
        # 检查config_value必须是dict
        config_value = request.data.get("config_value")
        if config_value is not None and not isinstance(config_value, dict):
            return Response(
                {"result": False, "message": "配置值必须是对象类型"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response({"result": True, "data": serializer.data})

    def retrieve(self, request, *args, **kwargs):
        """获取单个配置（通过ID）"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({"result": True, "data": serializer.data})

    def list(self, request, *args, **kwargs):
        """列出所有配置"""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response({"result": True, "data": serializer.data})

    def destroy(self, request, *args, **kwargs):
        """删除配置"""
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({"result": True})

    @action(methods=["GET"], detail=False, url_path=r"by_key/(?P<config_key>[^/.]+)")
    def get_by_key(self, request, config_key):
        """通过config_key获取配置
        
        GET /cmdb/api/user_configs/by_key/<config_key>/
        
        Returns:
            {
                "result": true,
                "data": {...}  # 配置值，不存在时返回空对象
            }
        """
        username = request.user.username
        domain = getattr(request.user, "domain", "domain.com")

        try:
            config = UserPersonalConfig.objects.get(
                username=username, domain=domain, config_key=config_key
            )
            return Response({"result": True, "data": config.config_value})
        except UserPersonalConfig.DoesNotExist:
            return Response({"result": True, "data": {}})

    @action(methods=["post"], detail=False)
    def update_key(self, request):
        """通过config_key保存/更新配置
        
        POST /cmdb/api/user_configs/update_key/
        Body: {配置对象}
        
        配置值必须是对象类型
        """
        username = request.user.username
        domain = getattr(request.user, "domain", "domain.com")
        config_key = request.data.get("config_key")
        config_value = request.data.get("config_value")
        if not isinstance(config_key, str) or not config_key.strip():
            return Response(
                {"result": False, "message": "config_key 不能为空"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 配置值校验
        if not isinstance(config_value, dict):
            return Response(
                {"result": False, "message": "配置值必须是对象类型"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config, created = UserPersonalConfig.objects.update_or_create(
            username=username,
            domain=domain,
            config_key=config_key,
            defaults={"config_value": config_value},
        )

        serializer = self.get_serializer(config)
        return Response({"result": True, "data": serializer.data})

    @action(methods=["delete"], detail=False, url_path=r"delete_key/(?P<config_key>[^/.]+)")
    def delete_key(self, request, config_key):
        """通过config_key删除配置
        
        DELETE /cmdb/api/user_configs/by_key/<config_key>/
        """
        username = request.user.username
        domain = getattr(request.user, "domain", "domain.com")

        deleted_count, _ = UserPersonalConfig.objects.filter(
            username=username, domain=domain, config_key=config_key
        ).delete()

        return Response(deleted_count > 0)

    @action(methods=["get"], detail=False, url_path="keys")
    def list_keys(self, request):
        """列出当前用户的所有配置键
        
        GET /cmdb/api/user_configs/keys/
        
        Returns:
            {
                "result": true,
                "data": ["search_inst_k8s_cluster", "dashboard_layout", ...]
            }
        """
        username = request.user.username
        domain = getattr(request.user, "domain", "domain.com")

        config_keys = UserPersonalConfig.objects.filter(
            username=username, domain=domain
        ).values_list("config_key", flat=True)

        return Response({"result": True, "data": list(config_keys)})
