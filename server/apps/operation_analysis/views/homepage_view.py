from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.operation_analysis.services.homepage import apply_global, apply_personal, build_access, build_landing, build_shortcut, build_state


class HomepageViewSet(ViewSet):
    """登录首页偏好。默认要求登录；功能权限和超管身份在服务里分开判断。"""

    @action(detail=False, methods=["get"])
    def state(self, request):
        return Response(build_state(request.user))

    @action(detail=False, methods=["get"])
    def landing(self, request):
        return Response(build_landing(request))

    @action(detail=False, methods=["get"])
    def access(self, request):
        return Response(build_access(request))

    @action(detail=False, methods=["get"])
    def shortcut(self, request):
        return Response(build_shortcut(request))

    @action(detail=False, methods=["post"])
    def personal(self, request):
        return Response(apply_personal(request))

    @action(detail=False, methods=["post"], url_path="global")
    def global_setting(self, request):
        return Response(apply_global(request))
