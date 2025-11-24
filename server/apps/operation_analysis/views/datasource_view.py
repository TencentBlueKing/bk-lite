# -- coding: utf-8 --
# @File: datasource_view.py
# @Time: 2025/11/3 15:48
# @Author: windyzhao
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.operation_analysis.common.get_nats_source_data import GetNatsData
from apps.operation_analysis.filters.datasource_filters import DataSourceAPIModelFilter, NameSpaceModelFilter, \
    DataSourceTagModelFilter
from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer, \
    NameSpaceModelSerializer, DataSourceTagModelSerializer
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace, DataSourceTag
from apps.core.logger import operation_analysis_logger as logger


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

    @action(detail=False, methods=["post"], url_path=r"get_source_data/(?P<pk>[^/.]+)")
    def get_source_data(self, request, *args, **kwargs):
        instance = self.get_object()
        params = request.data
        namespace_list = instance.namespaces.all()
        if "/" not in instance.rest_api:
            namespace = "default"
            path = instance.rest_api
        else:
            namespace, path = instance.rest_api.split("/", 1)
        client = GetNatsData(namespace=namespace, path=path, params=params, namespace_list=namespace_list,
                             request=request)
        result = []
        try:
            data = client.get_data()
            for namespace_id, _data in data.items():
                result.append({"namespace_id": namespace_id, "data": _data})
        except Exception as e:
            logger.error("获取数据源数据失败: {}".format(e))

        return Response(result)

    @HasPermission("data_source-View")
    def retrieve(self, request, *args, **kwargs):
        return super(DataSourceAPIModelViewSet, self).retrieve(request, *args, **kwargs)

    @HasPermission("data_source-View")
    def list(self, request, *args, **kwargs):
        return super(DataSourceAPIModelViewSet, self).list(request, *args, **kwargs)

    @HasPermission("data_source-Add")
    def create(self, request, *args, **kwargs):
        return super(DataSourceAPIModelViewSet, self).create(request, *args, **kwargs)

    @HasPermission("data_source-Edit")
    def update(self, request, *args, **kwargs):
        return super(DataSourceAPIModelViewSet, self).update(request, *args, **kwargs)

    @HasPermission("data_source-Delete")
    def destroy(self, request, *args, **kwargs):
        return super(DataSourceAPIModelViewSet, self).destroy(request, *args, **kwargs)
