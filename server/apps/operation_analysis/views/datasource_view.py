# -- coding: utf-8 --
# @File: datasource_view.py
# @Time: 2025/11/3 15:48
# @Author: windyzhao
import json
from datetime import datetime, timedelta

from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import operation_analysis_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.operation_analysis.common.audit_log import get_response_name, log_ops_analysis_success
from apps.operation_analysis.common.get_nats_source_data import GetNatsData
from apps.operation_analysis.filters.datasource_filters import DataSourceAPIModelFilter, DataSourceTagModelFilter, NameSpaceModelFilter
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag, NameSpace
from apps.operation_analysis.serializers.datasource_serializers import (
    DataSourceAPIModelSerializer,
    DataSourceBriefSerializer,
    DataSourceDetailSerializer,
    DataSourceTagModelSerializer,
    NameSpaceModelSerializer,
    merge_redacted_config,
)
from apps.operation_analysis.services.datasource_preview import ConnectorError, get_preview_executor
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet

TIME_RANGE_FORMAT = "%Y-%m-%d %H:%M:%S"
RUNTIME_ALLOWED_KEYS = {"namespace_id", "page", "page_size", "query_list"}


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


def _normalize_preview_limit(value):
    try:
        return min(max(int(value or 100), 1), 1000)
    except (TypeError, ValueError):
        raise ValueError("limit 必须是整数")


def _normalize_preview_config(value):
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _execute_inline_preview(source_type, connection_config, query_config, limit):
    executor = get_preview_executor(source_type)
    result = executor.preview(
        connection_config if isinstance(connection_config, dict) else {},
        query_config if isinstance(query_config, dict) else {},
        limit=limit,
    )
    return result.as_dict()


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
    if message == "数据源未关联命名空间":
        return status.HTTP_400_BAD_REQUEST, "数据源未关联命名空间"
    if message == "数据源未关联所选命名空间":
        return status.HTTP_400_BAD_REQUEST, "数据源未关联所选命名空间"
    if message == "命名空间参数无效":
        return status.HTTP_400_BAD_REQUEST, "命名空间参数无效"
    if "未配置服务器连接" in message:
        return status.HTTP_500_INTERNAL_SERVER_ERROR, "命名空间未配置连接信息"
    if "Module not found func" in message:
        return status.HTTP_500_INTERNAL_SERVER_ERROR, "数据源配置异常"
    return status.HTTP_500_INTERNAL_SERVER_ERROR, "数据查询失败"


def _parse_time_value(value):
    if isinstance(value, datetime):
        return value

    if isinstance(value, (int, float)):
        timestamp = float(value)
        # 13 位时间戳视为毫秒
        if abs(timestamp) > 10**11:
            timestamp = timestamp / 1000.0
        return datetime.fromtimestamp(timestamp)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("timeRange 时间不能为空")

        # 兼容 ISO8601，例如 2026-04-19T09:34:13.712Z / +08:00
        iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(iso_text)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            pass

        for fmt in (
            TIME_RANGE_FORMAT,
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
        ):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue

    raise ValueError("timeRange 时间格式错误，需为 yyyy-MM-dd HH:mm:ss")


def _normalize_time_range(value):
    now = datetime.now()

    if isinstance(value, (int, float)):
        minutes = int(value)
        if minutes <= 0:
            raise ValueError("timeRange 必须为正整数分钟数")
        start = now - timedelta(minutes=minutes)
        return [start.strftime(TIME_RANGE_FORMAT), now.strftime(TIME_RANGE_FORMAT)]

    if isinstance(value, list) and len(value) == 2:
        start = _parse_time_value(value[0])
        end = _parse_time_value(value[1])
        if start >= end:
            raise ValueError("timeRange 开始时间必须小于结束时间")
        return [start.strftime(TIME_RANGE_FORMAT), end.strftime(TIME_RANGE_FORMAT)]

    if isinstance(value, dict) and value.get("start") and value.get("end"):
        start = _parse_time_value(value["start"])
        end = _parse_time_value(value["end"])
        if start >= end:
            raise ValueError("timeRange 开始时间必须小于结束时间")
        return [start.strftime(TIME_RANGE_FORMAT), end.strftime(TIME_RANGE_FORMAT)]

    raise ValueError("timeRange 参数格式错误")


def _normalize_param_value(param_name, param_type, raw_value):
    if param_type == "number":
        if raw_value in (None, ""):
            return raw_value

        if isinstance(raw_value, bool):
            raise ValueError(f"参数 {param_name} 必须是数值")

        if isinstance(raw_value, (int, float)):
            number_value = float(raw_value)
        else:
            try:
                number_value = float(str(raw_value).strip())
            except (TypeError, ValueError):
                raise ValueError(f"参数 {param_name} 必须是数值")

        if number_value.is_integer():
            return int(number_value)

        try:
            return number_value
        except (TypeError, ValueError):
            raise ValueError(f"参数 {param_name} 必须是数值")

    if param_type == "timeRange":
        return _normalize_time_range(raw_value)

    return raw_value


def _normalize_runtime_params(request_data):
    runtime_params = {}

    if "namespace_id" in request_data:
        runtime_params["namespace_id"] = request_data["namespace_id"]

    if "page" in request_data:
        try:
            page = int(request_data["page"])
        except (TypeError, ValueError):
            raise ValueError("参数 page 必须是整数")
        if page <= 0:
            raise ValueError("参数 page 必须大于 0")
        runtime_params["page"] = page

    if "page_size" in request_data:
        try:
            page_size = int(request_data["page_size"])
        except (TypeError, ValueError):
            raise ValueError("参数 page_size 必须是整数")
        if page_size <= 0:
            raise ValueError("参数 page_size 必须大于 0")
        runtime_params["page_size"] = page_size

    if "query_list" in request_data:
        query_list = request_data["query_list"]
        if not isinstance(query_list, (list, dict)):
            raise ValueError("参数 query_list 必须是数组或对象")
        runtime_params["query_list"] = query_list

    return runtime_params


def _resolve_request_params(instance, request_data):
    configured_params = instance.params if isinstance(instance.params, list) else []
    allowed_specs = {
        item.get("name"): item
        for item in configured_params
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item.get("name").strip()
    }

    allowed_request_keys = set(allowed_specs.keys()) | RUNTIME_ALLOWED_KEYS
    unknown_keys = sorted(str(key) for key in request_data.keys() if key not in allowed_request_keys)
    if unknown_keys:
        raise ValueError(f"存在未声明参数: {', '.join(unknown_keys)}")

    resolved = {}
    for param_name, spec in allowed_specs.items():
        filter_type = spec.get("filterType")
        default_value = spec.get("value")
        param_type = spec.get("type")

        if filter_type == "fixed":
            raw_value = default_value
        elif param_name in request_data:
            raw_value = request_data[param_name]
        elif default_value not in (None, ""):
            raw_value = default_value
        else:
            continue

        resolved[param_name] = _normalize_param_value(param_name, param_type, raw_value)

    resolved.update(_normalize_runtime_params(request_data))

    return resolved


class DataSourceTagModelViewSet(viewsets.ReadOnlyModelViewSet):
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
        queryset = self.filter_queryset(self.get_queryset())
        ids = [item.strip() for item in (request.query_params.get("ids") or "").split(",") if item.strip()]
        if ids:
            queryset = queryset.filter(id__in=ids)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @HasPermission("namespace-Add")
    def create(self, request, *args, **kwargs):
        response = super(NameSpaceModelViewSet, self).create(request, *args, **kwargs)
        name = get_response_name(response, request.data.get("name", ""))
        log_ops_analysis_success(request, response, "create", f"新增命名空间: {name}")
        return response

    @HasPermission("namespace-Edit")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        response = super(NameSpaceModelViewSet, self).update(request, *args, **kwargs)
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑命名空间: {name}")
        return response

    @HasPermission("namespace-Edit")
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @HasPermission("namespace-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        name = instance.name
        response = super(NameSpaceModelViewSet, self).destroy(request, *args, **kwargs)
        log_ops_analysis_success(request, response, "delete", f"删除命名空间: {name}")
        return response


class DataSourceAPIModelViewSet(AuthViewSet):
    """
    数据源
    """

    queryset = DataSourceAPIModel.objects.prefetch_related("namespaces", "tag").all()
    serializer_class = DataSourceAPIModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = DataSourceAPIModelFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "datasource"
    ORGANIZATION_FIELD = "groups"  # 使用 groups 字段作为组织字段

    def get_serializer_class(self):
        if self.action == "list":
            mode = (self.request.query_params.get("mode") or "").strip().lower()
            if mode == "brief":
                return DataSourceBriefSerializer
            return DataSourceDetailSerializer

        if self.action == "retrieve":
            return DataSourceDetailSerializer

        return super().get_serializer_class()

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

        try:
            params = _resolve_request_params(instance, dict(request.data))
        except ValueError as exc:
            return _build_error_response(str(exc), status.HTTP_400_BAD_REQUEST)

        if instance.source_type != DataSourceAPIModel.SOURCE_TYPE_NATS:
            try:
                runtime_limit = _normalize_preview_limit(params.get("page_size") or request.data.get("limit"))
                payload = _execute_inline_preview(
                    instance.source_type,
                    instance.connection_config or {},
                    instance.query_config or {},
                    runtime_limit,
                )
            except ValueError as exc:
                return _build_error_response(str(exc), status.HTTP_400_BAD_REQUEST)
            except ConnectorError as exc:
                return _build_error_response(exc.message, exc.status_code, {"code": exc.code})
            except Exception as exc:
                logger.error(
                    "[DataSourceQuery] Inline 取数失败 datasource_id=%s name=%s source_type=%s：%s",
                    instance.id,
                    instance.name,
                    instance.source_type,
                    exc,
                    exc_info=True,
                )
                return _build_error_response("数据查询失败", status.HTTP_502_BAD_GATEWAY)

            return Response(payload.get("items", []))

        namespace_list = instance.namespaces.all()
        if "/" not in instance.rest_api:
            namespace = "default"
            path = instance.rest_api
        else:
            namespace, path = instance.rest_api.split("/", 1)

        # 演示静态数据源（已注释，仅用于无 NATS 时本地预览组件效果，勿提交启用）：
        # namespace=="demo" 时短路返回固定数据，无需 NATS。取消下方注释即可恢复。
        # if namespace == "demo":
        #     from apps.operation_analysis.common.demo_source import get_demo_source_data
        #
        #     demo_data = get_demo_source_data(path, params)
        #     if demo_data is not None:
        #         return Response(demo_data)
        #     return _build_error_response("演示数据源不存在", status.HTTP_404_NOT_FOUND)

        client = GetNatsData(namespace=namespace, path=path, params=params, namespace_list=namespace_list, request=request)
        try:
            result = _normalize_downstream_result(client.get_data())
        except Exception as e:
            logger.error(
                "[DataSourceQuery] 取数失败 datasource_id=%s name=%s namespace=%s path=%s：%s",
                instance.id,
                instance.name,
                namespace,
                path,
                e,
                exc_info=True,
            )
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
    @action(detail=False, methods=["post"], url_path="preview")
    def preview_config(self, request, *args, **kwargs):
        source_type = request.data.get("source_type") or DataSourceAPIModel.SOURCE_TYPE_NATS
        connection_config = _normalize_preview_config(request.data.get("connection_config"))
        query_config = _normalize_preview_config(request.data.get("query_config"))
        if source_type == DataSourceAPIModel.SOURCE_TYPE_EXCEL and request.FILES.get("file"):
            connection_config["file"] = request.FILES["file"]
            if request.data.get("sheet_name"):
                query_config["sheet_name"] = request.data.get("sheet_name")
        try:
            limit = _normalize_preview_limit(request.data.get("limit"))
            payload = _execute_inline_preview(source_type, connection_config, query_config, limit)
        except ValueError as exc:
            return _build_error_response(str(exc), status.HTTP_400_BAD_REQUEST)
        except ConnectorError as exc:
            return _build_error_response(exc.message, exc.status_code, {"code": exc.code})
        except Exception as exc:
            logger.error("[DataSourcePreview] 未保存配置预览失败 source_type=%s：%s", source_type, exc, exc_info=True)
            return _build_error_response("数据源预览失败", status.HTTP_502_BAD_GATEWAY)

        return Response(payload)

    @HasPermission("data_source-View")
    @action(detail=True, methods=["post"], url_path="preview")
    def preview(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Http404:
            return _build_error_response("数据源不存在或已删除", status.HTTP_404_NOT_FOUND)

        current_team = self._parse_current_team_cookie(request)
        if current_team not in (instance.groups or []):
            return _build_error_response("无权访问当前数据源", status.HTTP_403_FORBIDDEN)

        try:
            limit = _normalize_preview_limit(request.data.get("limit"))
            source_type = request.data.get("source_type") or instance.source_type
            connection_config = request.data.get("connection_config")
            if isinstance(connection_config, dict):
                connection_config = merge_redacted_config(instance.connection_config or {}, connection_config)
            else:
                connection_config = instance.connection_config or {}
            query_config = request.data.get("query_config")
            if not isinstance(query_config, dict):
                query_config = instance.query_config or {}
            payload = _execute_inline_preview(
                source_type,
                connection_config,
                query_config,
                limit,
            )
        except ValueError as exc:
            return _build_error_response(str(exc), status.HTTP_400_BAD_REQUEST)
        except ConnectorError as exc:
            return _build_error_response(exc.message, exc.status_code, {"code": exc.code})
        except Exception as exc:
            logger.error(
                "[DataSourcePreview] 保存数据源预览失败 datasource_id=%s source_type=%s：%s",
                instance.id,
                instance.source_type,
                exc,
                exc_info=True,
            )
            return _build_error_response("数据源预览失败", status.HTTP_502_BAD_GATEWAY)

        return Response(payload)

    @HasPermission("data_source-View")
    def retrieve(self, request, *args, **kwargs):
        return super(DataSourceAPIModelViewSet, self).retrieve(request, *args, **kwargs)

    @HasPermission("data_source-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        _, _, _, query = self.filter_by_group(queryset, request, request.user)
        queryset = queryset.filter(query).order_by(self.ORDERING_FIELD)
        ids = [item.strip() for item in (request.query_params.get("ids") or "").split(",") if item.strip()]
        if ids:
            queryset = queryset.filter(id__in=ids)
        return self._list(queryset)

    @HasPermission("data_source-Add")
    def create(self, request, *args, **kwargs):
        response = super(DataSourceAPIModelViewSet, self).create(request, *args, **kwargs)
        name = get_response_name(response, request.data.get("name", ""))
        log_ops_analysis_success(request, response, "create", f"新增数据源: {name}")
        return response

    @HasPermission("data_source-Edit")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        response = super(DataSourceAPIModelViewSet, self).update(request, *args, **kwargs)
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑数据源: {name}")
        return response

    @HasPermission("data_source-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        name = instance.name
        current_team = self._parse_current_team_cookie(request)

        if current_team not in (instance.groups or []):
            return Response({"detail": "无权删除该数据源"}, status=403)

        instance.delete()
        response = Response(status=204)
        log_ops_analysis_success(request, response, "delete", f"删除数据源: {name}")
        return response
