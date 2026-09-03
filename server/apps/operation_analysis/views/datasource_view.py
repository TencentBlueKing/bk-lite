# -- coding: utf-8 --
# @File: datasource_view.py
# @Time: 2025/11/3 15:48
# @Author: windyzhao
import json
from datetime import datetime, timedelta, timezone

from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import operation_analysis_logger as logger
from apps.core.utils.time_util import format_rfc3339_utc, parse_rfc3339_utc
from apps.core.utils.trend_granularity import TREND_GROUP_BY_AUTO_REST_APIS
from apps.core.utils.viewset_utils import AuthViewSet
from apps.operation_analysis.common.audit_log import get_response_name, log_ops_analysis_success
from apps.operation_analysis.common.datasource_security import LEGACY_RAW_MONITOR_QUERY_ERROR, is_legacy_raw_monitor_query
from apps.operation_analysis.common.datasource_visibility import (
    can_access_datasource_in_org,
    expand_datasource_org_query,
    is_builtin_globally_visible,
)
from apps.operation_analysis.common.get_nats_source_data import GetNatsData
from apps.operation_analysis.common.visibility_update import partial_update_groups_with_auth
from apps.operation_analysis.constants.import_export import SENSITIVE_PLACEHOLDER, is_sensitive_field_name
from apps.operation_analysis.filters.datasource_filters import DataSourceAPIModelFilter, DataSourceTagModelFilter, NameSpaceModelFilter
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag, NameSpace, NamespacePasswordDecryptionError
from apps.operation_analysis.serializers.datasource_serializers import (
    DataSourceAPIModelSerializer,
    DataSourceBriefSerializer,
    DataSourceDetailSerializer,
    DataSourceTagModelSerializer,
    NameSpaceModelSerializer,
    merge_redacted_config,
)
from apps.operation_analysis.services.data_connection import ConnectionResolveError, resolve_datasource_connection
from apps.operation_analysis.services.datasource_preview import ConnectorError, get_preview_executor
from apps.operation_analysis.services.table_query_list import apply_query_list_to_payload
from apps.operation_analysis.views.data_connection_view import extract_inline_connection
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet

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


def _normalize_transform_config_payload(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _request_flag_true(data, key: str, *, default: bool = False) -> bool:
    """Parse multipart/form or JSON boolean-ish flags."""
    if not isinstance(data, dict) and data is not None:
        # QueryDict
        if hasattr(data, "get"):
            if key not in data:
                return default
            value = data.get(key)
        else:
            return default
    else:
        data = data or {}
        if key not in data:
            return default
        value = data.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _execute_inline_preview(
    source_type,
    connection_config,
    query_config,
    limit,
    *,
    transform_config=None,
    org_id=None,
):
    executor = get_preview_executor(source_type)
    result = executor.preview(
        connection_config if isinstance(connection_config, dict) else {},
        query_config if isinstance(query_config, dict) else {},
        limit=limit,
        transform_config=transform_config,
        org_id=org_id,
    )
    return result.as_dict()


def _strip_unmerged_placeholders(connection_config):
    return {key: None if item == SENSITIVE_PLACEHOLDER and is_sensitive_field_name(key) else item for key, item in connection_config.items()}


def _draft_inline_connection_config(instance, request_data):
    connection_config = request_data.get("connection_config")
    if not isinstance(connection_config, dict):
        return instance.connection_config or {}
    request_source_type = request_data.get("source_type") or instance.source_type
    if request_source_type != instance.source_type or getattr(instance, "connection_id", None):
        return _strip_unmerged_placeholders(connection_config)
    return merge_redacted_config(instance.connection_config or {}, connection_config)


def _connection_config_for_instance(instance, request_data=None, current_team=None):
    request_data = request_data if isinstance(request_data, dict) else {}
    has_connection_field = "connection" in request_data or "connection_id" in request_data
    requested_connection = request_data.get("connection") or request_data.get("connection_id")

    if requested_connection:
        groups = request_data.get("groups")
        if not isinstance(groups, list):
            groups = instance.groups or []
        return _resolve_preview_connection_config(
            request_data,
            current_team=current_team,
            groups=groups,
        )

    if has_connection_field:
        return _draft_inline_connection_config(instance, request_data)

    if getattr(instance, "connection_id", None):
        overrides = request_data.get("connection_overrides")
        original_overrides = instance.connection_overrides
        if isinstance(overrides, dict):
            instance.connection_overrides = overrides
        try:
            return resolve_datasource_connection(instance, current_team=current_team)
        finally:
            instance.connection_overrides = original_overrides

    connection_config = request_data.get("connection_config")
    if isinstance(connection_config, dict):
        return merge_redacted_config(instance.connection_config or {}, connection_config)
    return instance.connection_config or {}


def _resolve_preview_connection_config(request_data, *, current_team=None, groups=None):
    """未保存预览：支持 connection id + overrides，与已保存路径语义对齐。"""
    request_data = request_data if isinstance(request_data, dict) else {}
    connection_id = request_data.get("connection") or request_data.get("connection_id")
    if not connection_id:
        return _normalize_preview_config(request_data.get("connection_config"))

    from apps.operation_analysis.models.datasource_models import DataConnection

    try:
        connection = DataConnection.objects.get(pk=connection_id)
    except (DataConnection.DoesNotExist, TypeError, ValueError) as exc:
        raise ConnectionResolveError("数据连接不存在", code="connection_missing", status_code=400) from exc

    source_type = request_data.get("source_type") or connection.connection_type
    stub = DataSourceAPIModel(
        source_type=source_type,
        groups=groups if isinstance(groups, list) else [],
        connection=connection,
        connection_overrides=request_data.get("connection_overrides") if isinstance(request_data.get("connection_overrides"), dict) else {},
        connection_config=_normalize_preview_config(request_data.get("connection_config")),
    )
    return resolve_datasource_connection(stub, current_team=current_team)


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
    if isinstance(error, NamespacePasswordDecryptionError):
        return status.HTTP_500_INTERNAL_SERVER_ERROR, message
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
        try:
            return parse_rfc3339_utc(value)
        except ValueError as exc:
            raise ValueError("timeRange 时间必须包含时区") from exc

    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("timeRange 时间不能为空")
        try:
            return parse_rfc3339_utc(text)
        except ValueError as exc:
            raise ValueError("timeRange 时间必须为带时区的 RFC3339 格式") from exc

    raise ValueError("timeRange 时间必须为带时区的 RFC3339 字符串")


def _relative_time_range_minutes(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        minutes = int(value)
        if minutes <= 0:
            raise ValueError("timeRange 必须为正整数分钟数")
        return minutes
    if isinstance(value, dict):
        select_value = value.get("selectValue")
        if isinstance(select_value, (int, float)) and not isinstance(select_value, bool) and select_value > 0:
            return int(select_value)
    return None


def _normalize_time_range(value):
    now = datetime.now(timezone.utc)
    relative_minutes = _relative_time_range_minutes(value)
    if relative_minutes is not None:
        start = now - timedelta(minutes=relative_minutes)
        return [format_rfc3339_utc(start), format_rfc3339_utc(now)]

    if isinstance(value, list) and len(value) == 2:
        start = _parse_time_value(value[0])
        end = _parse_time_value(value[1])
        if start >= end:
            raise ValueError("timeRange 开始时间必须小于结束时间")
        return [format_rfc3339_utc(start), format_rfc3339_utc(end)]

    if isinstance(value, dict) and value.get("start") and value.get("end"):
        start = _parse_time_value(value["start"])
        end = _parse_time_value(value["end"])
        if start >= end:
            raise ValueError("timeRange 开始时间必须小于结束时间")
        return [format_rfc3339_utc(start), format_rfc3339_utc(end)]

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

    # 趋势数据源不再声明 group_by；剥离残留键，避免「未声明参数」400。
    sanitized_request = dict(request_data)
    if getattr(instance, "rest_api", None) in TREND_GROUP_BY_AUTO_REST_APIS:
        sanitized_request.pop("group_by", None)
        allowed_specs.pop("group_by", None)

    allowed_request_keys = set(allowed_specs.keys()) | RUNTIME_ALLOWED_KEYS
    unknown_keys = sorted(str(key) for key in sanitized_request.keys() if key not in allowed_request_keys)
    if unknown_keys:
        raise ValueError(f"存在未声明参数: {', '.join(unknown_keys)}")

    resolved = {}
    for param_name, spec in allowed_specs.items():
        filter_type = spec.get("filterType")
        default_value = spec.get("value")
        param_type = spec.get("type")

        if filter_type == "fixed":
            raw_value = default_value
        elif param_name in sanitized_request:
            raw_value = sanitized_request[param_name]
            # timeRange 空值视为"无过滤"跳过,避免 _normalize_time_range("") 抛 ValueError
            # 导致整个请求 400(空字符串、null、空数组都被视为"未选时段")
            if param_type == "timeRange" and raw_value in (None, "", [], {}):
                continue
        elif default_value not in (None, ""):
            raw_value = default_value
        else:
            continue

        resolved[param_name] = _normalize_param_value(param_name, param_type, raw_value)

    resolved.update(_normalize_runtime_params(sanitized_request))

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

    @HasPermission("data_source-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("data_source-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


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

    queryset = (
        DataSourceAPIModel.objects.select_related(
            "connection",
            "excel_success_slot",
            "excel_candidate_slot",
        )
        .prefetch_related("namespaces", "tag")
        .all()
    )
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

        if is_legacy_raw_monitor_query(source_type=instance.source_type, rest_api=instance.rest_api):
            return _build_error_response(LEGACY_RAW_MONITOR_QUERY_ERROR, status.HTTP_410_GONE)

        raw_request = getattr(request, "_request", request)
        render_scoped = getattr(raw_request, "dashboard_report_render_scope", None) is not None
        if render_scoped:
            # Render Session：实时复核创建者组织成员资格与实例级权限，
            # 不能只依赖冻结的 execution_team_id ∈ datasource.groups。
            try:
                current_team = self._validate_current_team_permission(request)
            except PermissionDenied:
                return _build_error_response(
                    "无权访问当前数据源",
                    status.HTTP_403_FORBIDDEN,
                )
        else:
            current_team = self._parse_current_team_cookie(request)

        if not can_access_datasource_in_org(instance, current_team):
            return _build_error_response("无权访问当前数据源", status.HTTP_403_FORBIDDEN)
        if render_scoped and not is_builtin_globally_visible(instance):
            if not self.get_has_permission(request.user, instance, current_team, is_check=True):
                return _build_error_response("无权访问当前数据源", status.HTTP_403_FORBIDDEN)

        try:
            params = _resolve_request_params(instance, dict(request.data))
        except ValueError as exc:
            return _build_error_response(str(exc), status.HTTP_400_BAD_REQUEST)

        if instance.source_type != DataSourceAPIModel.SOURCE_TYPE_NATS:
            try:
                if instance.source_type == DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS:
                    executor = get_preview_executor(instance.source_type)
                    result = executor.execute(instance.connection_config or {}, params)
                    return Response({"data": result.data, "warnings": result.warnings or []})
                runtime_limit = _normalize_preview_limit(params.get("page_size") or request.data.get("limit"))
                if instance.source_type == DataSourceAPIModel.SOURCE_TYPE_EXCEL:
                    from apps.operation_analysis.services.excel_materialize import load_excel_runtime

                    payload = load_excel_runtime(instance, limit=runtime_limit)
                    return Response(
                        {
                            "data": apply_query_list_to_payload(
                                payload.get("items", []),
                                params.get("query_list"),
                            ),
                            "warnings": payload.get("warnings", []),
                        }
                    )
                connection_config = _connection_config_for_instance(
                    instance,
                    request.data if isinstance(request.data, dict) else {},
                    current_team=current_team,
                )
                payload = _execute_inline_preview(
                    instance.source_type,
                    connection_config,
                    instance.query_config or {},
                    runtime_limit,
                    transform_config=instance.transform_config or {},
                    org_id=current_team,
                )
            except ConnectionResolveError as exc:
                return _build_error_response(exc.message, exc.status_code, {"code": exc.code})
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

            # Runtime must not fall back to untransformed wide rows.
            transform_error = payload.get("transform_error") if isinstance(payload, dict) else None
            if isinstance(transform_error, dict) and transform_error.get("message"):
                return _build_error_response(
                    transform_error.get("message") or "转换失败",
                    status.HTTP_400_BAD_REQUEST,
                    {"code": transform_error.get("code") or "transform_failed"},
                )

            return Response(
                {
                    "data": apply_query_list_to_payload(payload.get("items", []), params.get("query_list")),
                    "warnings": [],
                }
            )

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

        result["data"] = apply_query_list_to_payload(result.get("data"), params.get("query_list"))
        return Response({"data": result.get("data"), "warnings": []})

    @HasPermission("data_source-Add,data_source-Edit")
    @action(detail=False, methods=["post"], url_path="preview")
    def preview_config(self, request, *args, **kwargs):
        source_type = request.data.get("source_type") or DataSourceAPIModel.SOURCE_TYPE_NATS
        query_config = _normalize_preview_config(request.data.get("query_config"))
        current_team = self._parse_current_team_cookie(request)
        groups = request.data.get("groups")
        if not isinstance(groups, list):
            groups = [current_team] if current_team is not None else []
        try:
            if source_type == DataSourceAPIModel.SOURCE_TYPE_EXCEL and request.FILES.get("file"):
                connection_config = _normalize_preview_config(request.data.get("connection_config"))
                connection_config["file"] = request.FILES["file"]
                if request.data.get("sheet_name"):
                    query_config["sheet_name"] = request.data.get("sheet_name")
            else:
                connection_config = _resolve_preview_connection_config(
                    request.data if isinstance(request.data, dict) else {},
                    current_team=current_team,
                    groups=groups,
                )
            limit = _normalize_preview_limit(request.data.get("limit"))
            transform_config = _normalize_transform_config_payload(request.data.get("transform_config"))
            payload = _execute_inline_preview(
                source_type,
                connection_config,
                query_config,
                limit,
                transform_config=transform_config,
                org_id=current_team,
            )
        except ConnectionResolveError as exc:
            return _build_error_response(exc.message, exc.status_code, {"code": exc.code})
        except ValueError as exc:
            return _build_error_response(str(exc), status.HTTP_400_BAD_REQUEST)
        except ConnectorError as exc:
            return _build_error_response(exc.message, exc.status_code, {"code": exc.code})
        except Exception as exc:
            logger.error("[DataSourcePreview] 未保存配置预览失败 source_type=%s：%s", source_type, exc, exc_info=True)
            return _build_error_response("数据源预览失败", status.HTTP_502_BAD_GATEWAY)

        return Response(payload)

    @HasPermission("data_source-Edit")
    @action(detail=True, methods=["post"], url_path="preview")
    def preview(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Http404:
            return _build_error_response("数据源不存在或已删除", status.HTTP_404_NOT_FOUND)

        current_team = self._validate_current_team_permission(request)
        if not can_access_datasource_in_org(instance, current_team):
            return _build_error_response("无权访问当前数据源", status.HTTP_403_FORBIDDEN)

        try:
            limit = _normalize_preview_limit(request.data.get("limit"))
            source_type = request.data.get("source_type") or instance.source_type
            if source_type == DataSourceAPIModel.SOURCE_TYPE_EXCEL and not request.FILES.get("file"):
                transform_config = _normalize_transform_config_payload(request.data.get("transform_config"))
                if not transform_config:
                    transform_config = instance.transform_config or {}
                if isinstance(transform_config, dict) and transform_config.get("enabled"):
                    from apps.operation_analysis.services.datasource_preview.excel import preview_excel_from_saved_source

                    result = preview_excel_from_saved_source(
                        instance,
                        transform_config=transform_config,
                        limit=limit,
                        org_id=current_team,
                    )
                    return Response(result.as_dict())

                from apps.operation_analysis.services.excel_materialize import load_excel_runtime

                payload = load_excel_runtime(instance, limit=limit)
                return Response(
                    {
                        "items": payload.get("items", []),
                        "count": payload.get("count", 0),
                        "fields": payload.get("fields", []),
                        "warnings": payload.get("warnings", []),
                    }
                )
            connection_config = _connection_config_for_instance(
                instance,
                request.data if isinstance(request.data, dict) else {},
                current_team=current_team,
            )
            query_config = request.data.get("query_config")
            if not isinstance(query_config, dict):
                query_config = instance.query_config or {}
            transform_config = _normalize_transform_config_payload(request.data.get("transform_config"))
            if not transform_config:
                transform_config = instance.transform_config or {}
            payload = _execute_inline_preview(
                source_type,
                connection_config,
                query_config,
                limit,
                transform_config=transform_config,
                org_id=current_team,
            )
        except ConnectionResolveError as exc:
            return _build_error_response(exc.message, exc.status_code, {"code": exc.code})
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

    @HasPermission("data_source-Edit")
    @action(detail=False, methods=["post"], url_path="test_connection")
    def test_connection_config(self, request, *args, **kwargs):
        source_type = request.data.get("source_type") or DataSourceAPIModel.SOURCE_TYPE_NATS
        connection_config = _normalize_preview_config(request.data.get("connection_config"))
        try:
            executor = get_preview_executor(source_type)
            executor.test_connection(connection_config)
        except ConnectorError as exc:
            return _build_error_response(exc.message, exc.status_code, {"code": exc.code})
        except Exception as exc:
            logger.error(
                "[DataSourceTestConnection] 未保存配置连接测试失败 source_type=%s：%s",
                source_type,
                exc,
                exc_info=True,
            )
            return _build_error_response("连接测试失败", status.HTTP_502_BAD_GATEWAY)
        return Response({"result": True, "message": "连接成功"})

    @HasPermission("data_source-Edit")
    @action(detail=True, methods=["post"], url_path="test_connection")
    def test_connection(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Http404:
            return _build_error_response("数据源不存在或已删除", status.HTTP_404_NOT_FOUND)

        current_team = self._validate_current_team_permission(request)
        if not can_access_datasource_in_org(instance, current_team):
            return _build_error_response("无权访问当前数据源", status.HTTP_403_FORBIDDEN)

        source_type = request.data.get("source_type") or instance.source_type
        try:
            connection_config = _connection_config_for_instance(
                instance,
                request.data if isinstance(request.data, dict) else {},
                current_team=current_team,
            )
            executor = get_preview_executor(source_type)
            executor.test_connection(connection_config)
        except ConnectionResolveError as exc:
            return _build_error_response(exc.message, exc.status_code, {"code": exc.code})
        except ConnectorError as exc:
            return _build_error_response(exc.message, exc.status_code, {"code": exc.code})
        except Exception as exc:
            logger.error(
                "[DataSourceTestConnection] 保存数据源连接测试失败 datasource_id=%s source_type=%s：%s",
                instance.id,
                source_type,
                exc,
                exc_info=True,
            )
            return _build_error_response("连接测试失败", status.HTTP_502_BAD_GATEWAY)
        return Response({"result": True, "message": "连接成功"})

    @HasPermission("data_source-Edit")
    @action(detail=True, methods=["post"], url_path="extract_connection")
    def extract_connection(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Http404:
            return _build_error_response("数据源不存在或已删除", status.HTTP_404_NOT_FOUND)

        current_team = self._validate_current_team_permission(request)
        if not can_access_datasource_in_org(instance, current_team):
            return _build_error_response("无权访问当前数据源", status.HTTP_403_FORBIDDEN)

        body = request.data if isinstance(request.data, dict) else {}
        incoming_config = body.get("connection_config")
        extract_config = None
        if isinstance(incoming_config, dict):
            extract_config = merge_redacted_config(instance.connection_config or {}, incoming_config)

        try:
            connection = extract_inline_connection(
                instance,
                name=body.get("name"),
                description=body.get("description"),
                created_by=getattr(request.user, "username", "") or "",
                connection_config=extract_config,
            )
        except ValueError as exc:
            return _build_error_response(str(exc), status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error(
                "[DataSourceExtractConnection] 提取连接失败 datasource_id=%s：%s",
                instance.id,
                exc,
                exc_info=True,
            )
            return _build_error_response("提取数据连接失败", status.HTTP_502_BAD_GATEWAY)

        from apps.operation_analysis.serializers.data_connection_serializers import DataConnectionSerializer

        instance.refresh_from_db()
        return Response(
            {
                "connection": DataConnectionSerializer(connection).data,
                "datasource": DataSourceDetailSerializer(instance, context={"request": request}).data,
            }
        )

    @HasPermission("data_source-Edit")
    @action(detail=True, methods=["post"], url_path="submit_excel")
    def submit_excel(self, request, *args, **kwargs):
        """上传原 .xlsx，默认同步物化；新建失败可 discard_on_fail 清盘。"""
        try:
            instance = self.get_object()
        except Http404:
            return _build_error_response("数据源不存在或已删除", status.HTTP_404_NOT_FOUND)

        current_team = self._validate_current_team_permission(request)
        if not can_access_datasource_in_org(instance, current_team):
            return _build_error_response("无权访问当前数据源", status.HTTP_403_FORBIDDEN)
        if instance.source_type != DataSourceAPIModel.SOURCE_TYPE_EXCEL:
            return _build_error_response("仅 Excel 数据源支持提交文件处理", status.HTTP_400_BAD_REQUEST)

        uploaded = request.FILES.get("file")
        if not uploaded:
            return _build_error_response("请上传 Excel 文件", status.HTTP_400_BAD_REQUEST)

        transform_config = _normalize_transform_config_payload(request.data.get("transform_config"))
        if not transform_config:
            transform_config = instance.transform_config or {}
        sheet_name = request.data.get("sheet_name") or None
        # V1 上传主路径默认同步；显式 sync=0 仍可只落候选交给 Celery（兼容补扫）。
        sync = _request_flag_true(request.data, "sync", default=True)
        discard_on_fail = _request_flag_true(request.data, "discard_on_fail", default=False)

        try:
            from apps.operation_analysis.services.excel_materialize import (
                discard_unready_excel_datasource,
                materialize_candidate_inline,
                submit_excel_candidate,
            )

            if isinstance(transform_config, dict) and transform_config != (instance.transform_config or {}):
                instance.transform_config = transform_config
                instance.save(update_fields=["transform_config", "updated_at"])

            slot = submit_excel_candidate(
                instance,
                uploaded_file=uploaded,
                transform_config=transform_config,
                sheet_name=sheet_name,
                schedule=not sync,
            )
            materialize_result = None
            if sync:
                materialize_result = materialize_candidate_inline(slot.id)
                if not materialize_result.get("ok"):
                    instance.refresh_from_db()
                    if discard_on_fail and discard_unready_excel_datasource(instance):
                        return _build_error_response(
                            materialize_result.get("message") or "Excel 处理失败，已取消本次创建",
                            status.HTTP_400_BAD_REQUEST,
                            data={
                                "code": materialize_result.get("code"),
                                "discarded": True,
                            },
                        )
                    instance.refresh_from_db()
                    return _build_error_response(
                        materialize_result.get("message") or "Excel 处理失败",
                        status.HTTP_400_BAD_REQUEST,
                        data={
                            "code": materialize_result.get("code"),
                            "discarded": False,
                            "datasource": DataSourceDetailSerializer(instance, context={"request": request}).data,
                        },
                    )
        except ValueError as exc:
            return _build_error_response(str(exc), status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error(
                "[DataSourceSubmitExcel] 提交失败 datasource_id=%s：%s",
                instance.id,
                exc,
                exc_info=True,
            )
            if discard_on_fail:
                try:
                    from apps.operation_analysis.services.excel_materialize import discard_unready_excel_datasource

                    instance.refresh_from_db()
                    discard_unready_excel_datasource(instance)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "[DataSourceSubmitExcel] discard after error failed datasource_id=%s",
                        getattr(instance, "id", None),
                    )
            return _build_error_response("提交 Excel 文件失败", status.HTTP_502_BAD_GATEWAY)

        instance.refresh_from_db()
        slot.refresh_from_db()
        return Response(
            {
                "ok": True,
                "candidate_slot_id": slot.id,
                "generation": slot.generation,
                "status": slot.status,
                "materialize": materialize_result,
                "datasource": DataSourceDetailSerializer(instance, context={"request": request}).data,
            }
        )

    @HasPermission("data_source-Edit")
    @action(detail=True, methods=["post"], url_path="retry_excel_materialization")
    def retry_excel_materialization(self, request, *args, **kwargs):
        """用已保存原文件重提候选并默认同步处理。"""
        try:
            instance = self.get_object()
        except Http404:
            return _build_error_response("数据源不存在或已删除", status.HTTP_404_NOT_FOUND)

        current_team = self._validate_current_team_permission(request)
        if not can_access_datasource_in_org(instance, current_team):
            return _build_error_response("无权访问当前数据源", status.HTTP_403_FORBIDDEN)
        if instance.source_type != DataSourceAPIModel.SOURCE_TYPE_EXCEL:
            return _build_error_response("仅 Excel 数据源支持重试处理", status.HTTP_400_BAD_REQUEST)

        from apps.operation_analysis.services.excel_materialize import excel_can_retry

        if not excel_can_retry(instance):
            return _build_error_response(
                "当前没有可重试的已保存 Excel 原文件，请重新上传",
                status.HTTP_400_BAD_REQUEST,
            )

        transform_config = _normalize_transform_config_payload(request.data.get("transform_config"))
        if not transform_config:
            transform_config = instance.transform_config or {}
        sync = _request_flag_true(request.data, "sync", default=True)

        try:
            from apps.operation_analysis.services.excel_materialize import materialize_candidate_inline, submit_excel_candidate_from_saved_source

            slot = submit_excel_candidate_from_saved_source(
                instance,
                transform_config=transform_config,
                schedule=not sync,
            )
            materialize_result = None
            if sync:
                materialize_result = materialize_candidate_inline(slot.id)
                if not materialize_result.get("ok"):
                    instance.refresh_from_db()
                    return _build_error_response(
                        materialize_result.get("message") or "Excel 处理失败",
                        status.HTTP_400_BAD_REQUEST,
                        data={
                            "code": materialize_result.get("code"),
                            "datasource": DataSourceDetailSerializer(instance, context={"request": request}).data,
                        },
                    )
        except ValueError as exc:
            return _build_error_response(str(exc), status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error(
                "[DataSourceRetryExcel] 重试失败 datasource_id=%s：%s",
                instance.id,
                exc,
                exc_info=True,
            )
            return _build_error_response("重试 Excel 处理失败", status.HTTP_502_BAD_GATEWAY)

        instance.refresh_from_db()
        slot.refresh_from_db()
        return Response(
            {
                "ok": True,
                "candidate_slot_id": slot.id,
                "generation": slot.generation,
                "status": slot.status,
                "materialize": materialize_result,
                "datasource": DataSourceDetailSerializer(instance, context={"request": request}).data,
            }
        )

    @HasPermission("data_source-View")
    def retrieve(self, request, *args, **kwargs):
        return super(DataSourceAPIModelViewSet, self).retrieve(request, *args, **kwargs)

    @HasPermission("data_source-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        current_team, include_children, org_field, query = self.filter_by_group(queryset, request, request.user)
        query = expand_datasource_org_query(
            query,
            include_all_builtins=bool(getattr(request.user, "is_superuser", False)),
        )
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
        visibility_only = kwargs.get("partial", False) and set(request.data.keys()) == {"groups"}
        if instance.is_build_in and not visibility_only:
            return Response({"detail": "内置数据源不允许通过普通接口修改"}, status=status.HTTP_403_FORBIDDEN)
        if instance.is_build_in and visibility_only:
            if not getattr(request.user, "is_superuser", False):
                return Response({"detail": "只有超级管理员可以修改内置数据源的组织可见性"}, status=status.HTTP_403_FORBIDDEN)
            response = partial_update_groups_with_auth(self, request, instance)
        else:
            response = super(DataSourceAPIModelViewSet, self).update(request, *args, **kwargs)
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑数据源: {name}")
        return response

    @HasPermission("data_source-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_build_in:
            return Response({"detail": "内置数据源不允许通过普通接口删除"}, status=status.HTTP_403_FORBIDDEN)
        name = instance.name
        current_team = self._parse_current_team_cookie(request)

        if not can_access_datasource_in_org(instance, current_team):
            return Response({"detail": "无权删除该数据源"}, status=403)

        instance.delete()
        response = Response(status=204)
        log_ops_analysis_success(request, response, "delete", f"删除数据源: {name}")
        return response
