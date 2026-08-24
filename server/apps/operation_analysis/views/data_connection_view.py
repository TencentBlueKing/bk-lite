from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import operation_analysis_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.operation_analysis.common.datasource_visibility import expand_datasource_org_query
from apps.operation_analysis.models.datasource_models import DataConnection, DataSourceAPIModel
from apps.operation_analysis.serializers.data_connection_serializers import (
    DataConnectionReferenceSerializer,
    DataConnectionSerializer,
    DataConnectionTestSerializer,
)
from apps.operation_analysis.services.data_connection.config_crypto import (
    decrypt_connection_config,
    encrypt_connection_config,
    merge_connection_config,
)
from apps.operation_analysis.services.datasource_preview import ConnectorError, get_preview_executor
from config.drf.pagination import CustomPageNumberPagination

REFERENCE_SUMMARY_LIMIT = 50


def visible_connection_references(instance, current_team):
    membership = Q(groups__contains=current_team)
    query = expand_datasource_org_query(membership, include_all_builtins=False)
    return instance.data_sources.filter(query).order_by("id")


class DataConnectionViewSet(AuthViewSet):
    queryset = DataConnection.objects.all().annotate(reference_count=Count("data_sources")).order_by("-id")
    serializer_class = DataConnectionSerializer
    pagination_class = CustomPageNumberPagination
    permission_key = "datasource"
    ORGANIZATION_FIELD = "groups"
    ordering = "-id"
    search_fields = ["name", "description"]
    filterset_fields = ["connection_type", "is_active", "name"]

    def get_queryset(self):
        return DataConnection.objects.all().annotate(reference_count=Count("data_sources")).order_by("-id")

    @HasPermission("data_source-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        _, _, _, query = self.filter_by_group(queryset, request, request.user)
        queryset = queryset.filter(query).order_by(self.ordering)
        return self._list(queryset)

    @HasPermission("data_source-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("data_source-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("data_source-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("data_source-Edit")
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("data_source-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        current_team = self._parse_current_team_cookie(request)
        if current_team not in (instance.groups or []):
            return Response({"detail": "无权删除当前数据连接"}, status=status.HTTP_403_FORBIDDEN)
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            visible_refs = visible_connection_references(instance, current_team)
            refs = list(visible_refs.values("id", "name")[:REFERENCE_SUMMARY_LIMIT])
            return Response(
                {
                    "detail": "数据连接仍被数据源引用，无法删除",
                    "data": {"references": refs, "reference_count": visible_refs.count()},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["get"], url_path="references")
    @HasPermission("data_source-View")
    def references(self, request, *args, **kwargs):
        instance = self.get_object()
        current_team = self._parse_current_team_cookie(request)
        if current_team not in (instance.groups or []):
            return Response({"detail": "无权查看当前数据连接"}, status=status.HTTP_403_FORBIDDEN)
        queryset = visible_connection_references(instance, current_team)[:REFERENCE_SUMMARY_LIMIT]
        return Response(DataConnectionReferenceSerializer(queryset, many=True).data)

    def _execute_connection_test(self, connection_type, config, *, connection_id=None):
        try:
            connection_config = decrypt_connection_config(config)
            if connection_type == DataConnection.TYPE_REST_API:
                connection_config = {
                    "url": connection_config.get("base_url") or connection_config.get("url"),
                    "method": "GET",
                    "timeout": connection_config.get("timeout") or 10,
                    "headers": connection_config.get("headers") or {},
                }
            executor = get_preview_executor(connection_type)
            executor.test_connection(connection_config)
        except ConnectorError as exc:
            return Response(
                {"result": False, "message": exc.message, "data": {"code": exc.code}},
                status=exc.status_code,
            )
        except Exception as exc:
            logger.error(
                "[DataConnection] 测试连接失败 id=%s type=%s: %s",
                connection_id,
                connection_type,
                exc,
                exc_info=True,
            )
            return Response(
                {"result": False, "message": "测试连接失败"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"result": True, "message": "连接成功"})

    @action(detail=False, methods=["post"], url_path="test_connection")
    @HasPermission("data_source-Edit")
    def test_connection_config(self, request, *args, **kwargs):
        serializer = DataConnectionTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._execute_connection_test(
            serializer.validated_data["connection_type"],
            serializer.validated_data["config"],
        )

    @action(detail=True, methods=["post"], url_path="test_connection")
    @HasPermission("data_source-Edit")
    def test_connection(self, request, *args, **kwargs):
        instance = self.get_object()
        current_team = self._parse_current_team_cookie(request)
        if current_team not in (instance.groups or []):
            return Response({"detail": "无权测试当前数据连接"}, status=status.HTTP_403_FORBIDDEN)
        if not instance.is_active:
            return Response({"detail": "数据连接已停用"}, status=status.HTTP_400_BAD_REQUEST)

        requested_type = request.data.get("connection_type")
        if requested_type not in (None, instance.connection_type):
            return Response({"detail": "连接类型创建后不可修改"}, status=status.HTTP_400_BAD_REQUEST)

        incoming_config = request.data.get("config")
        if incoming_config is None:
            config = instance.config or {}
        elif isinstance(incoming_config, dict):
            config = merge_connection_config(instance.config or {}, incoming_config)
        else:
            config = incoming_config

        serializer = DataConnectionTestSerializer(
            data={
                "connection_type": instance.connection_type,
                "config": config,
            }
        )
        serializer.is_valid(raise_exception=True)
        return self._execute_connection_test(
            serializer.validated_data["connection_type"],
            serializer.validated_data["config"],
            connection_id=instance.id,
        )


def extract_inline_connection(datasource, *, name=None, description=None, created_by="", connection_config=None):
    """将内联 connection_config 提取为公共连接并切换引用。

    name / description 由调用方传入；connection_config 可传入表单覆盖值（与库内敏感字段 merge）。
    """
    if datasource.connection_id:
        raise ValueError("数据源已引用公共连接")
    if datasource.source_type not in {
        DataSourceAPIModel.SOURCE_TYPE_MYSQL,
        DataSourceAPIModel.SOURCE_TYPE_POSTGRESQL,
        DataSourceAPIModel.SOURCE_TYPE_REST_API,
    }:
        raise ValueError("仅 MySQL/PostgreSQL/REST 支持提取为数据连接")

    connection_name = (name or "").strip()
    if not connection_name:
        raise ValueError("连接名称不能为空")
    connection_description = (description or "").strip() if isinstance(description, str) else ""

    if isinstance(connection_config, dict):
        config = merge_connection_config(datasource.connection_config or {}, connection_config)
    else:
        config = dict(datasource.connection_config or {})
    if datasource.source_type == DataSourceAPIModel.SOURCE_TYPE_REST_API:
        extracted = {
            "base_url": config.get("url") or config.get("base_url") or "",
            "headers": config.get("headers") if isinstance(config.get("headers"), dict) else {},
            "timeout": config.get("timeout") or 10,
        }
        overrides = {
            "path": "",
            "method": config.get("method") or "GET",
            "timeout": config.get("timeout") or 10,
        }
        # 若 url 含 path，尽量拆成 base + path
        url = extracted["base_url"]
        if url:
            from urllib.parse import urlsplit, urlunsplit

            parts = urlsplit(url)
            base = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
            path = parts.path or ""
            if parts.query:
                path = f"{path}?{parts.query}"
            extracted["base_url"] = base or url
            if path and path != "/":
                overrides["path"] = path
        cleaned_connection_config = {"method": overrides["method"], "timeout": overrides["timeout"]}
    else:
        extracted = {
            "host": config.get("host"),
            "port": config.get("port"),
            "database": config.get("database"),
            "username": config.get("username"),
            "password": config.get("password"),
        }
        overrides = {}
        cleaned_connection_config = {}

    connection_groups = list(datasource.groups or [])
    with transaction.atomic():
        connection = DataConnection.objects.create(
            name=connection_name,
            connection_type=datasource.source_type,
            description=connection_description,
            groups=connection_groups,
            is_active=True,
            config=encrypt_connection_config(extracted),
            created_by=created_by or datasource.created_by,
            updated_by=created_by or datasource.updated_by,
        )
        datasource.connection = connection
        datasource.connection_config = cleaned_connection_config
        datasource.connection_overrides = overrides
        datasource.save(update_fields=["connection", "connection_config", "connection_overrides", "updated_at", "updated_by"])
    return connection
