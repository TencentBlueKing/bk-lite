from django.db.models import Q, Subquery
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.language import LanguageConstants
from apps.monitor.filters.monitor_metrics import MetricFilter, MetricGroupFilter
from apps.monitor.models import MonitorPlugin
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.serializers.monitor_metrics import MetricGroupSerializer, MetricSerializer
from apps.monitor.utils.snmp_ifmib_capability import IFMIB_ZH_DISPLAY_TEXTS
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


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
        or not plugin.monitor_object.filter(type_id="Network Device").exists()
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


def apply_inherited_metric_filters(queryset, query_params):
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
        queryset = queryset.filter(
            Q(name__icontains=keyword)
            | Q(display_name__icontains=keyword)
            | Q(description__icontains=keyword)
        )
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


def collect_vm_field_names(metric_obj):
    api = VictoriaMetricsAPI()
    metric_name = (getattr(metric_obj, "name", "") or "").strip()
    if metric_name:
        response = api.labels(match=f'{{__name__="{metric_name}"}}')
        fields = set(response.get("data", []))
        fields.discard("__name__")
        if fields:
            return sorted(fields)

    query = (
        (metric_obj.query or "")
        .replace("__$labels__", "")
        .replace("{, ", "{")
        .replace("{,", "{")
        .replace(", }", "}")
        .replace(",}", "}")
    )
    response = api.query(query)
    fields = set()
    for item in response.get("data", {}).get("result", []):
        fields.update(item.get("metric", {}).keys())
    fields.discard("__name__")
    return sorted(fields)


class MetricGroupViewSet(viewsets.ModelViewSet):
    queryset = MetricGroup.objects.all().order_by("sort_order")
    serializer_class = MetricGroupSerializer
    filterset_class = MetricGroupFilter
    pagination_class = MetricCatalogPagination

    @staticmethod
    def _ensure_modifiable(metric_group):
        if getattr(metric_group, "is_pre", False):
            raise BaseAppException("内置指标分组为只读，禁止修改或删除")

    def update(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().destroy(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        monitor_object_id = get_optional_query_param_id(request, "monitor_object_id")
        vendor_groups = self.filter_queryset(self.get_queryset()).order_by()
        base_plugin = get_snmp_base_plugin(request, monitor_object_id)
        if base_plugin is not None:
            vendor_group_names = MetricGroup.objects.filter(
                monitor_object_id=monitor_object_id,
                monitor_plugin_id=request.query_params.get("monitor_plugin_id"),
            )
            base_groups = MetricGroup.objects.filter(
                monitor_object_id=monitor_object_id,
                monitor_plugin=base_plugin,
            ).order_by()
            base_groups = apply_inherited_group_filters(base_groups, request.query_params)
            queryset = vendor_groups.union(
                base_groups.exclude(name__in=Subquery(vendor_group_names.values("name")))
            ).order_by("sort_order", "id")
        else:
            queryset = vendor_groups.order_by("sort_order", "id")
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        results = serializer.data

        # 获取监控对象ID与名称的映射
        object_ids = [i["monitor_object"] for i in results if i.get("monitor_object")]
        object_map = dict(
            MonitorObject.objects.filter(id__in=object_ids).values_list("id", "name")
        ) if object_ids else {}

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

    def update(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._ensure_modifiable(self.get_object())
        return super().destroy(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        # Do not union a select_related queryset: joins would make the two SELECT
        # column sets differ. The bounded page is hydrated below in one query.
        monitor_object_id = get_optional_query_param_id(request, "monitor_object_id")
        vendor_metrics = self.filter_queryset(Metric.objects.all()).order_by()
        base_plugin = get_snmp_base_plugin(request, monitor_object_id)
        if str(request.query_params.get("include_ifmib", "true")).lower() == "false":
            base_plugin = None
        if base_plugin is not None:
            vendor_metric_names = Metric.objects.filter(
                monitor_object_id=monitor_object_id,
                monitor_plugin_id=request.query_params.get("monitor_plugin_id"),
            )
            base_metrics = Metric.objects.filter(
                monitor_object_id=monitor_object_id,
                monitor_plugin=base_plugin,
            ).order_by()
            base_metrics = apply_inherited_metric_filters(base_metrics, request.query_params)
            queryset = vendor_metrics.union(
                base_metrics.exclude(name__in=Subquery(vendor_metric_names.values("name")))
            ).order_by("sort_order", "id")
        else:
            queryset = vendor_metrics.order_by("sort_order", "id")
        page = self.paginate_queryset(queryset)
        page_metric_ids = [metric.id for metric in page]
        page_metrics = Metric.objects.filter(id__in=page_metric_ids).select_related(
            "metric_group", "monitor_object", "monitor_plugin"
        )
        metrics_by_id = {metric.id: metric for metric in page_metrics}
        page = [metrics_by_id[metric_id] for metric_id in page_metric_ids]

        if base_plugin is not None:
            base_group_names = {
                metric.metric_group.name
                for metric in page
                if metric.monitor_plugin_id == base_plugin.id
            }
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
        object_map = dict(
            MonitorObject.objects.filter(id__in=object_ids).values_list("id", "name")
        ) if object_ids else {}

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
            result["display_description"] = (
                (ifmib_text[1] if ifmib_text else None)
                or lan.get(f"{lan_key}.desc")
                or result["description"]
            )

        metric_groups = MetricGroup.objects.filter(
            id__in={metric.metric_group_id for metric in page}
        ).order_by("sort_order", "id")
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
