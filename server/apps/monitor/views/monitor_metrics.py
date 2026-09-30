import re

from django.db import transaction
from django.db.models import Q, Subquery
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.logger import monitor_logger as logger
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.filters.monitor_metrics import MetricFilter, MetricGroupFilter
from apps.monitor.models import MonitorPlugin
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.serializers.monitor_metrics import (
    METRIC_BATCH_UPDATE_FIELDS,
    MetricBatchDeleteSerializer,
    MetricBatchUpdateSerializer,
    MetricGroupSerializer,
    MetricSerializer,
    merge_batch_dimensions,
    validate_batch_dimension_names,
)
from apps.monitor.services.custom_script_plugin import (
    SCRIPT_SELF_MONITOR_METRIC_DELETE_ERROR,
    is_script_collect_type,
    is_script_self_monitor_metric_name,
)
from apps.monitor.utils.metric_enum_locale import localize_metric_enum_unit
from apps.monitor.utils.metric_keyword import apply_metric_keyword_filter
from apps.monitor.utils.metric_query_labels import ensure_metric_labels_placeholder, is_raw_vector_selector
from apps.monitor.utils.snmp_ifmib_capability import COMMON_IFMIB_METRIC_NAMES, IFMIB_ZH_DISPLAY_TEXTS, is_ifmib_capable_plugin
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI

# PromQL 中紧跟 `{` 的指标名（用于目录兜底提取）。
_METRIC_NAME_BEFORE_BRACE = re.compile(r"([a-zA-Z_:][a-zA-Z0-9_:]*)\s*\{")


class MetricCatalogPagination(PageNumberPagination):
    """Bound metric catalog requests so a template cannot trigger an unbounded read."""

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({"count": self.page.paginator.count, "items": data})


IFMIB_RATE_DISPLAY_NAMES = {
    "interface_ifInOctets": {
        "zh-Hans": "接口接收流量速率（32 位）",
        "en": "Interface Incoming Traffic Rate (32-bit)",
    },
    "interface_ifOutOctets": {
        "zh-Hans": "接口发送流量速率（32 位）",
        "en": "Interface Outgoing Traffic Rate (32-bit)",
    },
    "interface_ifHCInOctets": {
        "zh-Hans": "接口接收流量速率（64 位）",
        "en": "Interface Incoming Traffic Rate (64-bit)",
    },
    "interface_ifHCOutOctets": {
        "zh-Hans": "接口发送流量速率（64 位）",
        "en": "Interface Outgoing Traffic Rate (64-bit)",
    },
    "device_total_incoming_traffic": {
        "zh-Hans": "设备接收总流量速率",
        "en": "Device Total Incoming Traffic Rate",
    },
    "device_total_outgoing_traffic": {
        "zh-Hans": "设备发送总流量速率",
        "en": "Device Total Outgoing Traffic Rate",
    },
}


def get_ifmib_rate_display_name(metric_name, locale):
    """Return an unambiguous IF-MIB rate label independent of vendor-local translations."""
    translations = IFMIB_RATE_DISPLAY_NAMES.get(metric_name)
    if translations is None:
        return None
    return translations["zh-Hans"] if str(locale).startswith("zh") else translations["en"]


def get_ifmib_display_text(metric_name, locale):
    """Return localized public IF-MIB label and description without vendor fallbacks."""
    if not str(locale).startswith("zh"):
        return None
    return IFMIB_ZH_DISPLAY_TEXTS.get(metric_name)


def get_optional_query_param_id(request, param_name):
    """Read an optional positive integer query parameter without leaking ORM errors."""
    return parse_optional_positive_id(request.query_params.get(param_name), param_name)


def get_required_query_param_id(request, param_name):
    """Read a required positive integer query parameter; empty or missing values are rejected."""
    parsed = get_optional_query_param_id(request, param_name)
    if parsed is None:
        raise ValidationAppException(f"{param_name} 不能为空")
    return parsed


def get_snmp_base_plugin(request, monitor_object_id):
    """返回厂商 SNMP 模板应复用的同对象通用 SNMP 指标插件。"""
    plugin_id = get_optional_query_param_id(request, "monitor_plugin_id")
    if not plugin_id:
        return None
    plugin = MonitorPlugin.objects.filter(id=plugin_id, monitor_object__id=monitor_object_id).first()
    if (
        plugin is None
        or plugin.collect_type == "snmp"
        or not str(plugin.collect_type or "").startswith("snmp_")
        or plugin.template_type != "builtin"
        or not is_ifmib_capable_plugin(plugin)
    ):
        return None
    return (
        MonitorPlugin.objects.filter(
            monitor_object__id=monitor_object_id,
            collector="Telegraf",
            collect_type="snmp",
            template_type="builtin",
        )
        .order_by("id")
        .first()
    )


def apply_inherited_group_filters(queryset, query_params):
    """Apply user-facing group filters to the inherited public catalog."""
    name = query_params.get("name")
    if name:
        queryset = queryset.filter(name=name)
    keyword = str(query_params.get("keyword") or "").strip()
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(description__icontains=keyword))
    return queryset


def apply_inherited_metric_filters(queryset, query_params, locale=""):
    """Apply the same catalog filters to inherited IF-MIB metrics without the vendor plugin constraint."""
    metric_id = parse_optional_positive_id(query_params.get("id"), "id")
    if metric_id:
        queryset = queryset.filter(id=metric_id)
    metric_ids = parse_optional_positive_id_list(query_params.get("id_in"), "id_in")
    if metric_ids:
        queryset = queryset.filter(id__in=metric_ids)
    name = query_params.get("name")
    if name:
        queryset = queryset.filter(name=name)
    names = query_params.get("name_in")
    if names:
        queryset = queryset.filter(name__in=[value for value in names.split(",") if value])
    keyword = str(query_params.get("keyword") or "").strip()
    if keyword:
        queryset = apply_metric_keyword_filter(queryset, keyword, locale)
    is_ifmib = query_params.get("is_ifmib")
    if is_ifmib is not None and str(is_ifmib).strip() != "":
        normalized = str(is_ifmib).strip().lower()
        if normalized in {"true", "1"}:
            queryset = queryset.filter(is_ifmib=True)
        elif normalized in {"false", "0"}:
            queryset = queryset.filter(is_ifmib=False)
    return queryset


def parse_optional_positive_id(value, param_name):
    if value in (None, ""):
        return None
    try:
        normalized_value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationAppException(f"{param_name} 必须为正整数") from exc
    if normalized_value <= 0:
        raise ValidationAppException(f"{param_name} 必须为正整数")
    return normalized_value


def parse_optional_positive_id_list(value, param_name):
    if value in (None, ""):
        return None
    raw_values = [item.strip() for item in str(value).split(",") if item.strip()]
    if not raw_values:
        return None
    return [parse_optional_positive_id(item, param_name) for item in raw_values]


def _metric_batch_item_error(metric_id, name, field, message, code):
    """Structured per-item error so the metric table can mark the failing row."""
    return {
        "id": metric_id,
        "name": name or "",
        "field": field,
        "message": message,
        "code": code,
    }


def _flatten_serializer_errors(errors):
    flattened = []
    if isinstance(errors, dict):
        for field, value in errors.items():
            key = "" if field in ("non_field_errors", "non_field_error") else field
            if isinstance(value, dict):
                for nested_field, nested_message in _flatten_serializer_errors(value):
                    flattened.append((nested_field or key, nested_message))
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, dict):
                        flattened.extend((nested_field or key, nested_message) for nested_field, nested_message in _flatten_serializer_errors(item))
                    else:
                        flattened.append((key, str(item)))
            else:
                flattened.append((key, str(value)))
    elif isinstance(errors, (list, tuple)):
        for item in errors:
            flattened.append(("", str(item)))
    elif errors:
        flattened.append(("", str(errors)))
    return flattened


def merge_inherited_metric_groups(vendor_groups, base_groups):
    """Compatibility helper for pure callers; list endpoints merge in SQL instead."""
    vendor_names = {group.name for group in vendor_groups}
    return [*vendor_groups, *(group for group in base_groups if group.name not in vendor_names)]


def merge_inherited_metrics(vendor_metrics, base_metrics, vendor_groups_by_name, base_groups_by_id):
    """Compatibility helper for pure callers; list endpoints merge in SQL instead."""
    vendor_names = {metric.name for metric in vendor_metrics}
    merged = list(vendor_metrics)
    for metric in base_metrics:
        if metric.name not in vendor_names:
            target_group = vendor_groups_by_name.get(base_groups_by_id.get(metric.metric_group_id))
            if target_group is not None:
                metric.metric_group_id = target_group.id
            merged.append(metric)
    return merged


def sanitize_metric_query_for_vm(query):
    """Strip catalog placeholders so a draft formula can be sent to VictoriaMetrics."""
    normalized = ensure_metric_labels_placeholder(query)
    cleaned = (
        (normalized or "").replace("__$labels__", "").replace("{, ", "{").replace("{,", "{").replace(", }", "}").replace(",}", "}").replace("{}", "")
    )
    cleaned = re.sub(
        r"([a-zA-Z_:][a-zA-Z0-9_:]*)\s*,(?=\s*(?:[+\-*/)]|$))",
        r"\1",
        cleaned,
    )
    cleaned = re.sub(r"\{\s*,", "{", cleaned)
    cleaned = re.sub(r",\s*\}", "}", cleaned)
    cleaned = re.sub(r"\{\s*\}", "", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def collect_vm_field_names(metric_obj):
    api = VictoriaMetricsAPI()
    metric_name = (getattr(metric_obj, "name", "") or "").strip()
    if metric_name:
        response = api.labels(match=f'{{__name__="{metric_name}"}}')
        fields = set(response.get("data", []))
        fields.discard("__name__")
        if fields:
            return sorted(fields)

    query = sanitize_metric_query_for_vm(metric_obj.query)
    response = api.query(query)
    fields = set()
    for item in response.get("data", {}).get("result", []):
        fields.update(item.get("metric", {}).keys())
    fields.discard("__name__")
    return sorted(fields)


def build_template_vm_match(instance_type, collect_type=None):
    """Build a VM match[] selector for series belonging to a monitor template."""
    parts = [f'instance_type="{instance_type}"']
    if collect_type:
        parts.append(f'collect_type="{collect_type}"')
    return "{" + ",".join(parts) + "}"


def extract_metric_names_from_queries(queries):
    """Extract PromQL metric identifiers that appear before a label selector."""
    names = set()
    for query in queries:
        if not query:
            continue
        names.update(_METRIC_NAME_BEFORE_BRACE.findall(query))
    return sorted(names)


def collect_computed_catalog_metric_names(monitor_object_id, monitor_plugin_id):
    """本模板中公式非原始向量选择器的目录指标 ID（防点选套娃）。"""
    computed = set()
    rows = Metric.objects.filter(
        monitor_object_id=monitor_object_id,
        monitor_plugin_id=monitor_plugin_id,
    ).values_list("name", "query")
    for name, query in rows:
        metric_id = (name or "").strip()
        if metric_id and not is_raw_vector_selector(query):
            computed.add(metric_id)
    return computed


def extract_raw_catalog_metric_names(monitor_object_id, monitor_plugin_id):
    """兜底：仅从原始公式提取可点选的序列名。"""
    names = set()
    rows = Metric.objects.filter(
        monitor_object_id=monitor_object_id,
        monitor_plugin_id=monitor_plugin_id,
    ).values_list("query", flat=True)
    for query in rows:
        if not is_raw_vector_selector(query):
            continue
        trimmed = (query or "").strip()
        match = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)", trimmed)
        if match:
            names.add(match.group(1))
    return sorted(names)


def list_vm_metric_names(monitor_object_id, monitor_plugin_id, keyword=""):
    """List live VM __name__ values for a template; fall back to catalog query names."""
    monitor_object = MonitorObject.objects.filter(id=monitor_object_id).only("id", "name").first()
    if monitor_object is None:
        raise ValidationAppException("monitor_object_id 无效")
    plugin = MonitorPlugin.objects.filter(id=monitor_plugin_id).only("id", "collect_type").first()
    if plugin is None:
        raise ValidationAppException("monitor_plugin_id 无效")

    instance_type = (monitor_object.name or "").strip()
    collect_type = (plugin.collect_type or "").strip() or None
    match = build_template_vm_match(instance_type, collect_type) if instance_type else None

    names = []
    try:
        response = VictoriaMetricsAPI().label_values("__name__", match=match)
        names = sorted({item for item in (response.get("data") or []) if isinstance(item, str) and item})
    except Exception:
        logger.error(
            "list_vm_metric_names failed to query VictoriaMetrics",
            extra={
                "monitor_object_id": monitor_object_id,
                "monitor_plugin_id": monitor_plugin_id,
                "failed_stage": "vm_label_values",
                "error_type": "VictoriaMetricsError",
            },
            exc_info=True,
        )

    if not names:
        names = extract_raw_catalog_metric_names(monitor_object_id, monitor_plugin_id)

    computed_names = collect_computed_catalog_metric_names(monitor_object_id, monitor_plugin_id)
    if computed_names:
        names = [name for name in names if name not in computed_names]

    keyword = (keyword or "").strip().lower()
    if keyword:
        names = [name for name in names if keyword in name.lower()]

    logger.info(
        "list_vm_metric_names completed",
        extra={
            "monitor_object_id": monitor_object_id,
            "monitor_plugin_id": monitor_plugin_id,
            "count": len(names),
        },
    )
    return names


def _bounded_vm_error_message(payload, fallback="公式语法错误"):
    """Prefer VM error text but keep it bounded for UI display."""
    raw = ""
    if isinstance(payload, dict):
        raw = payload.get("error") or payload.get("errorType") or ""
    text = str(raw).strip() or fallback
    if len(text) > 200:
        return f"{text[:200]}..."
    return text


def probe_metric_query(query):
    """Probe a draft formula against VM and classify syntax / data / infra failures."""
    cleaned = sanitize_metric_query_for_vm(query)
    if not cleaned.strip():
        return {
            "ok": False,
            "reason": "empty_query",
            "message": "公式不能为空",
            "label_keys": [],
            "sample_count": 0,
        }

    try:
        response, http_error = VictoriaMetricsAPI().query_allow_error(cleaned)
    except Exception as exc:
        logger.error(
            "probe_metric_query VictoriaMetrics request failed",
            extra={
                "failed_stage": "vm_query",
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
        return {
            "ok": False,
            "reason": "vm_error",
            "message": "指标试算失败，请稍后重试",
            "label_keys": [],
            "sample_count": 0,
        }

    if http_error is not None or (isinstance(response, dict) and response.get("status") == "error"):
        return {
            "ok": False,
            "reason": "syntax_error",
            "message": _bounded_vm_error_message(response if isinstance(response, dict) else {}),
            "label_keys": [],
            "sample_count": 0,
        }

    results = (response or {}).get("data", {}).get("result") or []
    if not results:
        return {
            "ok": False,
            "reason": "no_data",
            "message": "暂无匹配数据，可继续保存；有数据后可再测试以选择维度字段",
            "label_keys": [],
            "sample_count": 0,
        }

    label_keys = set()
    for item in results:
        label_keys.update((item.get("metric") or {}).keys())
    label_keys.discard("__name__")
    return {
        "ok": True,
        "reason": "ok",
        "message": "测试成功，可在下方选择维度字段",
        "label_keys": sorted(label_keys),
        "sample_count": len(results),
    }


def evaluate_metric_query(query):
    """Instant-query a draft formula for real samples; never blocks save."""
    return probe_metric_query(query)


class MetricGroupViewSet(viewsets.ModelViewSet):
    queryset = MetricGroup.objects.all().order_by("sort_order")
    serializer_class = MetricGroupSerializer
    filterset_class = MetricGroupFilter
    pagination_class = MetricCatalogPagination

    @staticmethod
    def _ensure_modifiable(metric_group):
        if getattr(metric_group, "is_pre", False):
            raise BaseAppException("内置指标分组为只读，禁止修改或删除")

    @HasPermission("integration_metric-Add Group")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("integration_metric-Edit Group")
    def update(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().update(request, *args, **kwargs)

    @HasPermission("integration_metric-Edit Group")
    def partial_update(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("integration_metric-Delete Group")
    def destroy(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().destroy(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        monitor_object_id = get_optional_query_param_id(request, "monitor_object_id")
        vendor_groups = self.filter_queryset(self.get_queryset()).order_by()
        base_plugin = get_snmp_base_plugin(request, monitor_object_id)
        if base_plugin is not None:
            base_groups = MetricGroup.objects.filter(
                monitor_object_id=monitor_object_id,
                monitor_plugin=base_plugin,
            ).order_by()
            base_groups = apply_inherited_group_filters(base_groups, request.query_params)
            queryset = vendor_groups.union(base_groups.exclude(name__in=Subquery(vendor_groups.values("name")))).order_by("sort_order", "id")
        else:
            queryset = vendor_groups.order_by("sort_order", "id")
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        results = serializer.data

        # 获取监控对象ID与名称的映射
        object_ids = [i["monitor_object"] for i in results if i.get("monitor_object")]
        object_map = dict(MonitorObject.objects.filter(id__in=object_ids).values_list("id", "name")) if object_ids else {}

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)
        for result in results:
            object_id = result.get("monitor_object")
            if not object_id:
                continue
            object_name = object_map.get(object_id)
            if not object_name:
                continue
            # 组装语言配置Key（基于监控对象名称）
            lan_key = f"{LanguageConstants.MONITOR_OBJECT_METRIC_GROUP}.{object_name}.{result['name']}"
            # 获取语言配置值
            result["display_name"] = lan.get(lan_key) or result["name"]

        return WebUtils.response_success(self.get_paginated_response(results).data)

    @action(detail=False, methods=["post"])
    @HasPermission("integration_metric-Edit Group")
    def set_order(self, request, *args, **kwargs):
        target_ids = [item["id"] for item in request.data]
        if MetricGroup.objects.filter(id__in=target_ids, is_pre=True).exists():
            raise BaseAppException("内置指标分组为只读，禁止调整顺序")
        updates = [
            MetricGroup(
                id=item["id"],
                sort_order=item["sort_order"],
            )
            for item in request.data
        ]
        MetricGroup.objects.bulk_update(updates, ["sort_order"], batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE)
        return WebUtils.response_success()


class MetricViewSet(viewsets.ModelViewSet):
    queryset = Metric.objects.select_related("monitor_object", "monitor_plugin").all().order_by("sort_order")
    serializer_class = MetricSerializer
    filterset_class = MetricFilter
    pagination_class = MetricCatalogPagination

    @staticmethod
    def _ensure_modifiable(metric):
        if getattr(metric, "is_pre", False):
            raise BaseAppException("内置指标为只读，禁止修改或删除")

    @HasPermission("integration_metric-Add Metric")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("integration_metric-Edit Metric")
    def update(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().update(request, *args, **kwargs)

    @HasPermission("integration_metric-Edit Metric")
    def partial_update(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("integration_metric-Delete Metric")
    def destroy(self, request, *args, **kwargs):
        metric = self.get_object()
        self._ensure_modifiable(metric)
        self._ensure_script_self_monitor_not_deleted(metric)
        return super().destroy(request, *args, **kwargs)

    @staticmethod
    def _ensure_script_self_monitor_not_deleted(metric):
        collect_type = getattr(getattr(metric, "monitor_plugin", None), "collect_type", None)
        if is_script_self_monitor_metric_name(getattr(metric, "name", None), collect_type):
            raise BaseAppException(SCRIPT_SELF_MONITOR_METRIC_DELETE_ERROR)

    @action(detail=False, methods=["post"], url_path="batch_delete")
    @HasPermission("integration_metric-Delete Metric")
    def batch_delete(self, request, *args, **kwargs):
        serializer = MetricBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        metric_ids = serializer.validated_data["ids"]
        plugin_id = serializer.validated_data["monitor_plugin"]

        metrics = list(Metric.objects.select_related("monitor_object", "monitor_plugin").filter(id__in=metric_ids))
        found_ids = {metric.id for metric in metrics}
        missing_ids = [metric_id for metric_id in metric_ids if metric_id not in found_ids]
        if missing_ids:
            raise ValidationAppException("部分指标不存在")
        if any(metric.monitor_plugin_id != plugin_id for metric in metrics):
            raise ValidationAppException("只能删除当前插件的指标")
        for metric in metrics:
            self._ensure_modifiable(metric)
            self._ensure_script_self_monitor_not_deleted(metric)

        with transaction.atomic():
            for metric in metrics:
                metric.delete()

        logger.info(
            "metric batch_delete completed monitor_plugin_id=%s count=%s",
            plugin_id,
            len(metrics),
        )
        return WebUtils.response_success({"deleted": len(metrics)})

    @action(detail=False, methods=["post"], url_path="batch_update")
    @HasPermission("integration_metric-Edit Metric")
    def batch_update(self, request, *args, **kwargs):
        serializer = MetricBatchUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        plugin_id = payload["monitor_plugin"]
        items = payload["items"]
        metric_ids = [item["id"] for item in items]

        metrics = list(Metric.objects.select_related("monitor_object", "monitor_plugin", "metric_group").filter(id__in=metric_ids))
        metrics_by_id = {metric.id: metric for metric in metrics}
        errors = []
        prepared = []

        for item in items:
            metric_id = item["id"]
            metric = metrics_by_id.get(metric_id)
            name = getattr(metric, "name", "") if metric is not None else ""
            patch = {field: item[field] for field in METRIC_BATCH_UPDATE_FIELDS if field in item}
            if metric is None:
                errors.append(_metric_batch_item_error(metric_id, "", "id", "指标不存在", "not_found"))
                continue
            if metric.monitor_plugin_id != plugin_id:
                errors.append(_metric_batch_item_error(metric_id, name, "id", "只能批量编辑同一插件的指标", "wrong_plugin"))
                continue
            if getattr(metric, "is_pre", False):
                errors.append(_metric_batch_item_error(metric_id, name, "id", "内置指标为只读，禁止修改或删除", "builtin_readonly"))
                continue
            if not patch:
                errors.append(_metric_batch_item_error(metric_id, name, None, "未指定要更新的字段", "empty_patch"))
                continue
            if "dimensions" in patch:
                preserve_hidden = is_script_collect_type(getattr(metric.monitor_plugin, "collect_type", None))
                dimension_error = validate_batch_dimension_names(patch["dimensions"], name, preserve_hidden=preserve_hidden)
                if dimension_error:
                    errors.append(_metric_batch_item_error(metric_id, name, "dimensions", dimension_error, "invalid_dimension"))
                    continue
                patch["dimensions"] = merge_batch_dimensions(metric.dimensions, patch["dimensions"], preserve_hidden=preserve_hidden)
            if patch.get("data_type") == "Enum" and "unit" not in patch:
                errors.append(_metric_batch_item_error(metric_id, name, "unit", "设为枚举时必须提供映射", "enum_mapping_required"))
                continue
            if "unit" in patch and patch.get("data_type") != "Number" and (metric.data_type or "") == "Enum":
                errors.append(_metric_batch_item_error(metric_id, name, "unit", "枚举指标不能直接改单位", "enum_unit_blocked"))
                continue
            item_patch = dict(patch)
            if item_patch.get("data_type") == "Number" and "unit" not in item_patch and (metric.data_type or "") == "Enum":
                item_patch["unit"] = "none"
            item_serializer = MetricSerializer(metric, data=item_patch, partial=True)
            if not item_serializer.is_valid():
                for field, message in _flatten_serializer_errors(item_serializer.errors):
                    errors.append(_metric_batch_item_error(metric_id, name, field or None, message, "validation"))
                continue
            prepared.append(item_serializer)

        if errors:
            return WebUtils.response_error(
                response_data={"errors": errors},
                error_message="部分指标无法更新",
            )

        with transaction.atomic():
            for item_serializer in prepared:
                item_serializer.save()

        logger.info(
            "metric batch_update completed monitor_plugin_id=%s count=%s",
            plugin_id,
            len(prepared),
        )
        return WebUtils.response_success({"updated": len(prepared)})

    def list(self, request, *args, **kwargs):
        # Do not union a select_related queryset: joins would make the two SELECT
        # column sets differ. The bounded page is hydrated below in one query.
        monitor_object_id = get_required_query_param_id(request, "monitor_object_id")
        vendor_metrics = self.filter_queryset(Metric.objects.all()).order_by()
        base_plugin = get_snmp_base_plugin(request, monitor_object_id)
        include_ifmib = str(request.query_params.get("include_ifmib", "true")).lower() != "false"
        if base_plugin is not None:
            # 仅在 base 已提供对应公共指标时，才剥掉厂商未标记的同名脏数据，
            # 避免升级窗口里 base 尚未导入时目录出现空洞。关闭 IF-MIB 时仍需全部隐藏。
            stale_ifmib_names = (
                COMMON_IFMIB_METRIC_NAMES
                if not include_ifmib
                else set(
                    Metric.objects.filter(
                        monitor_object_id=monitor_object_id,
                        monitor_plugin=base_plugin,
                        name__in=COMMON_IFMIB_METRIC_NAMES,
                    ).values_list("name", flat=True)
                )
            )
            if stale_ifmib_names:
                vendor_metrics = vendor_metrics.exclude(
                    name__in=stale_ifmib_names,
                    is_ifmib=False,
                )
        if not include_ifmib:
            base_plugin = None
        if base_plugin is not None:
            base_metrics = Metric.objects.filter(
                monitor_object_id=monitor_object_id,
                monitor_plugin=base_plugin,
            ).order_by()
            base_metrics = apply_inherited_metric_filters(
                base_metrics,
                request.query_params,
                request.user.locale,
            )
            queryset = vendor_metrics.union(base_metrics.exclude(name__in=Subquery(vendor_metrics.values("name")))).order_by("sort_order", "id")
        else:
            queryset = vendor_metrics.order_by("sort_order", "id")
        page = self.paginate_queryset(queryset)
        page_metric_ids = [metric.id for metric in page]
        page_metrics = Metric.objects.filter(id__in=page_metric_ids).select_related("metric_group", "monitor_object", "monitor_plugin")
        metrics_by_id = {metric.id: metric for metric in page_metrics}
        page = [metrics_by_id[metric_id] for metric_id in page_metric_ids]

        if base_plugin is not None:
            base_group_names = {metric.metric_group.name for metric in page if metric.monitor_plugin_id == base_plugin.id}
            vendor_groups_by_name = {
                group.name: group.id
                for group in MetricGroup.objects.filter(
                    monitor_object_id=monitor_object_id,
                    monitor_plugin_id=request.query_params.get("monitor_plugin_id"),
                    name__in=base_group_names,
                )
            }
            for metric in page:
                if metric.monitor_plugin_id == base_plugin.id:
                    metric.metric_group_id = vendor_groups_by_name.get(metric.metric_group.name, metric.metric_group_id)

        serializer = self.get_serializer(page, many=True)
        results = serializer.data

        # 获取监控对象ID与名称的映射
        object_ids = [i["monitor_object"] for i in results if i.get("monitor_object")]
        object_map = dict(MonitorObject.objects.filter(id__in=object_ids).values_list("id", "name")) if object_ids else {}

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)
        for result in results:
            object_id = result.get("monitor_object")
            if not object_id:
                continue
            object_name = object_map.get(object_id)
            if not object_name:
                continue
            # 组装语言配置Key（基于监控对象名称）
            lan_key = f"{LanguageConstants.MONITOR_OBJECT_METRIC}.{object_name}.{result['name']}"
            # HC 与 32 位计数器必须在名称中直接区分，不能被厂商旧翻译覆盖为同名。
            ifmib_text = get_ifmib_display_text(result["name"], request.user.locale) if result.get("is_ifmib") else None
            result["display_name"] = (
                (ifmib_text[0] if ifmib_text else None)
                or get_ifmib_rate_display_name(result["name"], request.user.locale)
                or lan.get(f"{lan_key}.name")
                or result["display_name"]
            )
            result["display_description"] = (ifmib_text[1] if ifmib_text else None) or lan.get(f"{lan_key}.desc") or result["description"]
            if (result.get("data_type") or "").lower() == "enum":
                result["unit"] = localize_metric_enum_unit(
                    result.get("unit") or "",
                    enum_translations=lan.get(f"{lan_key}.enum"),
                )

        metric_groups = MetricGroup.objects.filter(id__in={metric.metric_group_id for metric in page}).order_by("sort_order", "id")
        metric_group_results = MetricGroupSerializer(metric_groups, many=True).data
        for result in metric_group_results:
            object_name = object_map.get(result.get("monitor_object"))
            if object_name:
                lan_key = f"{LanguageConstants.MONITOR_OBJECT_METRIC_GROUP}.{object_name}.{result['name']}"
                result["display_name"] = lan.get(lan_key) or result["name"]

        response_data = self.get_paginated_response(results).data
        response_data["metric_groups"] = metric_group_results
        return WebUtils.response_success(response_data)

    @action(detail=False, methods=["post"])
    @HasPermission("integration_metric-Edit Metric")
    def set_order(self, request, *args, **kwargs):
        target_ids = [item["id"] for item in request.data]
        if Metric.objects.filter(id__in=target_ids, is_pre=True).exists():
            raise BaseAppException("内置指标为只读，禁止调整顺序")
        updates = [
            Metric(
                id=item["id"],
                sort_order=item["sort_order"],
            )
            for item in request.data
        ]
        Metric.objects.bulk_update(updates, ["sort_order"], batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE)
        return WebUtils.response_success()

    @action(detail=True, methods=["get"], url_path="vm-fields")
    def vm_fields(self, request, *args, **kwargs):
        metric = self.get_object()
        return WebUtils.response_success(collect_vm_field_names(metric))

    @action(detail=False, methods=["get"], url_path="vm-metric-names")
    def vm_metric_names(self, request, *args, **kwargs):
        monitor_object_id = get_required_query_param_id(request, "monitor_object_id")
        monitor_plugin_id = get_required_query_param_id(request, "monitor_plugin_id")
        keyword = request.query_params.get("keyword") or ""
        names = list_vm_metric_names(monitor_object_id, monitor_plugin_id, keyword=keyword)
        return WebUtils.response_success(names)

    @action(detail=False, methods=["post"], url_path="test_query")
    @HasPermission("integration_metric-Edit Metric")
    def test_query(self, request, *args, **kwargs):
        query = request.data.get("query")
        if query is None or not isinstance(query, str):
            raise ValidationAppException("query 不能为空")
        return WebUtils.response_success(evaluate_metric_query(query))
