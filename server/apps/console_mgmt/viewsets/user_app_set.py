from django.http import JsonResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action

from apps.console_mgmt.models import UserAppSet
from apps.console_mgmt.serializers import UserAppSetSerializer
from apps.core.utils.loader import LanguageLoader


class UserAppSetViewSet(viewsets.ModelViewSet):
    """用户应用配置集视图集"""

    serializer_class = UserAppSetSerializer
    queryset = UserAppSet.objects.all()
    http_method_names = ["get", "post"]

    def list(self, request, *args, **kwargs):
        """禁用列表接口"""
        return JsonResponse({"result": False, "message": "请使用 current_user_apps 接口获取用户应用配置"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def create(self, request, *args, **kwargs):
        """禁用创建接口"""
        return JsonResponse({"result": False, "message": "请使用 configure_user_apps 接口配置用户应用"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def retrieve(self, request, *args, **kwargs):
        """禁用详情接口"""
        return JsonResponse({"result": False, "message": "请使用 current_user_apps 接口获取用户应用配置"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def update(self, request, *args, **kwargs):
        """禁用完整更新接口"""
        return JsonResponse({"result": False, "message": "请使用 configure_user_apps 接口配置用户应用"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def partial_update(self, request, *args, **kwargs):
        """禁用部分更新接口"""
        return JsonResponse({"result": False, "message": "请使用 configure_user_apps 接口配置用户应用"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def destroy(self, request, *args, **kwargs):
        """禁用删除接口"""
        return JsonResponse({"result": False, "message": "不支持删除用户应用配置"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def get_queryset(self):
        """获取用户应用配置集列表"""
        queryset = super().get_queryset()

        # 支持按用户名过滤
        username = self.request.query_params.get("username")
        if username:
            queryset = queryset.filter(username=username)

        # 支持按域名过滤
        domain = self.request.query_params.get("domain")
        if domain:
            queryset = queryset.filter(domain=domain)

        return queryset

    @action(methods=["get"], detail=False)
    def current_user_apps(self, request):
        """获取当前用户的应用配置"""
        username = request.user.username
        domain = getattr(request.user, "domain", "domain.com")

        # 尝试从数据库获取
        user_app_set = UserAppSet.objects.filter(username=username, domain=domain).first()

        if user_app_set:
            app_config_list = user_app_set.app_config_list
            # 对内置应用的 description 进行翻译
            if app_config_list:
                locale = getattr(request.user, "locale", "en")
                loader = LanguageLoader(app="core", default_lang=locale)
                for app_config in app_config_list:
                    if app_config.get("is_build_in") and app_config.get("name"):
                        # 使用 app.{name} 作为翻译 key
                        translation_key = f"app.{app_config['name']}"
                        translated = loader.get(translation_key)
                        if translated:
                            app_config["description"] = translated
            return JsonResponse({"result": True, "data": app_config_list})

        return JsonResponse({"result": True, "data": []})

    @action(methods=["post"], detail=False)
    def configure_user_apps(self, request):
        """配置当前用户的应用配置"""
        username = request.user.username
        domain = getattr(request.user, "domain", "domain.com")
        app_config_list = request.data.get("app_config_list")

        if app_config_list is None:
            return JsonResponse({"result": False, "message": "app_config_list is required"}, status=status.HTTP_400_BAD_REQUEST)

        # 使用 update_or_create 实现新增或更新
        UserAppSet.objects.update_or_create(username=username, domain=domain, defaults={"app_config_list": app_config_list})

        return JsonResponse({"result": True})
