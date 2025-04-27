from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.services.user_group import UserGroup
from apps.core.utils.web_utils import WebUtils
from apps.rpc.system_mgmt import SystemMgmt
from config.components.drf import AUTH_TOKEN_HEADER_NAME


class UserGroupViewSet(viewsets.ViewSet):

    def __init__(self, *args, **kwargs):
        super(UserGroupViewSet, self).__init__(*args, **kwargs)
        self.system_mgmt_client = SystemMgmt()

    def get_first_and_max(self, params):
        """格式化page参数, 获取first与max"""
        page, page_size = int(params.get("page", 1)), int(params.get("page_size", 20))
        _first = (page - 1) * page_size
        _max = page_size
        return _first, _max

    @swagger_auto_schema(
        operation_id="user_list",
        operation_description="查询用户列表",
        manual_parameters=[
            openapi.Parameter("page", in_=openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("page_size", in_=openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter("search", in_=openapi.IN_QUERY, type=openapi.TYPE_STRING),
        ],
    )
    @action(methods=["get"], detail=False)
    def user_list(self, request):
        _first, _max = self.get_first_and_max(request.query_params)
        data = UserGroup().user_list(self.system_mgmt_client, query_params=dict(first=_first, max=_max,
                                                                                search=request.query_params.get(
                                                                                    "search", "")))
        return WebUtils.response_success(data)

    @swagger_auto_schema(
        operation_id="group_list",
        operation_description="组列表",
        manual_parameters=[
            openapi.Parameter("search", in_=openapi.IN_QUERY, type=openapi.TYPE_STRING),
        ],
    )
    @action(methods=["get"], detail=False)
    def group_list(self, request):
        data = UserGroup().groups_list(system_mgmt_client=self.system_mgmt_client,
                                       query_params=request.GET.get("search"))
        return WebUtils.response_success(data)

    @swagger_auto_schema(
        operation_id="user_groups",
        operation_description="用户组列表",
    )
    @action(methods=["get"], detail=False)
    def user_groups(self, request):
        data = UserGroup().user_groups_list(request.META.get(AUTH_TOKEN_HEADER_NAME).split("Bearer ")[-1], request)
        return WebUtils.response_success(data)
