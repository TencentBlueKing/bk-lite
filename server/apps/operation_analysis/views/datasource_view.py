# -- coding: utf-8 --
# @File: datasource_view.py
# @Time: 2025/11/3 15:48
# @Author: windyzhao
from django.http import Http404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import operation_analysis_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.operation_analysis.common.get_nats_source_data import GetNatsData
from apps.operation_analysis.filters.datasource_filters import DataSourceAPIModelFilter, DataSourceTagModelFilter, NameSpaceModelFilter
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag, NameSpace
from apps.operation_analysis.serializers.datasource_serializers import (
    DataSourceAPIModelSerializer,
    DataSourceTagModelSerializer,
    NameSpaceModelSerializer,
)
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


def _normalize_downstream_result(result):
    if isinstance(result, dict) and "result" in result:
        return result
    return {"result": True, "data": result, "message": ""}


def _build_error_response(detail, status_code, data=None):
    payload = {
        "detail": detail,
    }
    if data is not None:
        payload["data"] = data
    return Response(payload, status=status_code)


def _get_downstream_failure_status(result):
    code = result.get("code")
    if code is not None:
        try:
            normalized_code = int(str(code))
        except (TypeError, ValueError):
            normalized_code = None
        if normalized_code and 400 <= normalized_code <= 599:
            return normalized_code
        if normalized_code and 40000 <= normalized_code <= 59999 and normalized_code % 100 == 0:
            return normalized_code // 100

    message = str(result.get("message") or "").strip()
    if not message:
        return status.HTTP_502_BAD_GATEWAY

    if any(keyword in message for keyword in ("无权", "权限", "未授权", "forbidden", "Forbidden")):
        return status.HTTP_403_FORBIDDEN
    if any(keyword in message for keyword in ("不存在", "未找到", "not found", "Not Found")):
        return status.HTTP_404_NOT_FOUND
    if any(keyword in message for keyword in ("缺少", "不能为空", "必须", "不能", "非法", "格式错误", "参数错误", "无效")):
        return status.HTTP_400_BAD_REQUEST
    return status.HTTP_502_BAD_GATEWAY


def _classify_runtime_exception(error):
    message = str(error).strip()
    if message == "未找到可用的命名空间":
        return status.HTTP_500_INTERNAL_SERVER_ERROR, "未找到可用命名空间"
    if "未配置服务器连接" in message:
        return status.HTTP_500_INTERNAL_SERVER_ERROR, "命名空间未配置连接信息"
    if "Module not found func" in message:
        return status.HTTP_500_INTERNAL_SERVER_ERROR, "数据源配置异常"
    return status.HTTP_500_INTERNAL_SERVER_ERROR, "数据查询失败"


class DataSourceTagModelViewSet(ModelViewSet):
    """
    数据源标签
    """

    queryset = DataSourceTag.objects.all()
    serializer_class = DataSourceTagModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = DataSourceTagModelFilter
    pagination_class = CustomPageNumberPagination


class NameSpaceModelViewSet(ModelViewSet):
    """
    命名空间
    """

    queryset = NameSpace.objects.all()
    serializer_class = NameSpaceModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = NameSpaceModelFilter
    pagination_class = CustomPageNumberPagination

    @HasPermission("namespace-View")
    def retrieve(self, request, *args, **kwargs):
        return super(NameSpaceModelViewSet, self).retrieve(request, *args, **kwargs)

    @HasPermission("namespace-View")
    def list(self, request, *args, **kwargs):
        return super(NameSpaceModelViewSet, self).list(request, *args, **kwargs)

    @HasPermission("namespace-Add")
    def create(self, request, *args, **kwargs):
        return super(NameSpaceModelViewSet, self).create(request, *args, **kwargs)

    @HasPermission("namespace-Edit")
    def update(self, request, *args, **kwargs):
        return super(NameSpaceModelViewSet, self).update(request, *args, **kwargs)

    @HasPermission("namespace-Delete")
    def destroy(self, request, *args, **kwargs):
        return super(NameSpaceModelViewSet, self).destroy(request, *args, **kwargs)


class DataSourceAPIModelViewSet(AuthViewSet):
    """
    数据源
    """

    queryset = DataSourceAPIModel.objects.all()
    serializer_class = DataSourceAPIModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = DataSourceAPIModelFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "datasource"
    ORGANIZATION_FIELD = "groups"  # 使用 groups 字段作为组织字段

    @HasPermission("data_source-View")
    @action(detail=False, methods=["post"], url_path=r"get_source_data/(?P<pk>[^/.]+)")
    def get_source_data(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Http404:
            return _build_error_response(
                "数据源不存在或已删除",
                status.HTTP_404_NOT_FOUND,
            )

        # 组织校验：当前组织必须在数据源的 groups 中
        current_team = self._parse_current_team_cookie(request)
        if current_team not in (instance.groups or []):
            return _build_error_response(
                "无权访问当前数据源",
                status.HTTP_403_FORBIDDEN,
            )

        params = dict(request.data)
        namespace_list = instance.namespaces.all()
        if "/" not in instance.rest_api:
            namespace = "default"
            path = instance.rest_api
        else:
            namespace, path = instance.rest_api.split("/", 1)
        client = GetNatsData(namespace=namespace, path=path, params=params, namespace_list=namespace_list, request=request)
        try:
            result = _normalize_downstream_result(client.get_data())
        except Exception as e:
            logger.error("获取数据源数据失败: {}".format(e))
            error_status, error_message = _classify_runtime_exception(e)
            return _build_error_response(error_message, error_status)

        if not result.get("result", True):
            error_status = _get_downstream_failure_status(result)
            return _build_error_response(
                result.get("message") or "数据查询失败",
                error_status,
                result.get("data"),
            )

        return Response(result.get("data"))

    @HasPermission("data_source-View")
    def retrieve(self, request, *args, **kwargs):
        return super(DataSourceAPIModelViewSet, self).retrieve(request, *args, **kwargs)

    @HasPermission("data_source-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        _, _, _, query = self.filter_by_group(queryset, request, request.user)
        queryset = queryset.filter(query).order_by(self.ORDERING_FIELD)
        return self._list(queryset)

    @HasPermission("data_source-Add")
    def create(self, request, *args, **kwargs):
        return super(DataSourceAPIModelViewSet, self).create(request, *args, **kwargs)

    @HasPermission("data_source-Edit")
    def update(self, request, *args, **kwargs):
        return super(DataSourceAPIModelViewSet, self).update(request, *args, **kwargs)

    @HasPermission("data_source-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        current_team = self._parse_current_team_cookie(request)

        if current_team not in (instance.groups or []):
            return Response({"detail": "无权删除该数据源"}, status=403)

        instance.delete()
        return Response(status=204)
