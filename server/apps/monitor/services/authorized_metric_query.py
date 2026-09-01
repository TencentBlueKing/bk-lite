import re
from dataclasses import dataclass

from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.models import Metric, MonitorInstance
from apps.monitor.services.metrics import Metrics
from apps.monitor.utils.dimension import parse_instance_id

ALLOWED_AGGREGATIONS = {
    "AVG": None,
    "SUM": "sum",
    "MAX": "max",
    "MIN": "min",
    "COUNT": "count",
}
ALLOWED_FILTER_OPERATORS = {"=", "!=", "=~", "!~"}


class AuthorizedMetricQueryError(ValueError):
    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AuthorizedMetricQuery:
    metric: Metric
    instance_ids: tuple[str, ...]
    query: str
    start: int
    end: int
    step: str
    detect_gaps: bool
    collection_interval: int | None
    card_budget: bool


def _escape_label_value(value) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _metric_instance_id_keys(metric: Metric) -> list[str]:
    keys = metric.instance_id_keys or getattr(metric.monitor_object, "instance_id_keys", None) or []
    normalized = [str(key).strip() for key in keys if key is not None and str(key).strip()]
    if not normalized:
        raise AuthorizedMetricQueryError(
            "监控指标缺少实例标识契约",
            code="metric_instance_keys_missing",
        )
    return normalized


def _instance_matchers(instance_ids: tuple[str, ...], keys: list[str]) -> list[str]:
    values_by_key = {key: set() for key in keys}
    for instance_id in instance_ids:
        values = parse_instance_id(instance_id)
        if len(values) < len(keys):
            raise AuthorizedMetricQueryError(
                "监控实例标识与指标契约不匹配",
                code="instance_identity_invalid",
            )
        for index, key in enumerate(keys):
            value = values[index]
            if value in (None, ""):
                raise AuthorizedMetricQueryError(
                    "监控实例标识与指标契约不匹配",
                    code="instance_identity_invalid",
                )
            values_by_key[key].add(str(value))

    matchers = []
    for key, values in values_by_key.items():
        escaped_values = [_escape_label_value(re.escape(value)) for value in sorted(values)]
        matchers.append(f'{key}=~"{"|".join(escaped_values)}"')
    return matchers


def _allowed_dimensions(metric: Metric) -> set[str]:
    allowed = set()
    for item in metric.dimensions or []:
        if isinstance(item, dict):
            name = item.get("name")
        else:
            name = item
        if name is not None and str(name).strip():
            allowed.add(str(name).strip())
    return allowed


def _filter_matchers(metric: Metric, filters) -> list[str]:
    if filters in (None, ""):
        return []
    if not isinstance(filters, list):
        raise AuthorizedMetricQueryError("filters 必须是列表", code="filters_invalid")

    allowed = _allowed_dimensions(metric)
    matchers = []
    for item in filters:
        if not isinstance(item, dict):
            raise AuthorizedMetricQueryError("filters 元素必须是对象", code="filters_invalid")
        label = str(item.get("label") or "").strip()
        operator = str(item.get("operator") or "").strip()
        value = item.get("value")
        if not label or label not in allowed:
            raise AuthorizedMetricQueryError("筛选维度未在指标中声明", code="filter_label_invalid")
        if operator not in ALLOWED_FILTER_OPERATORS:
            raise AuthorizedMetricQueryError("筛选操作符不受支持", code="filter_operator_invalid")
        if value in (None, ""):
            raise AuthorizedMetricQueryError("筛选值不能为空", code="filter_value_invalid")
        matchers.append(f'{label}{operator}"{_escape_label_value(value)}"')
    return matchers


def _build_query(metric: Metric, instance_ids: tuple[str, ...], filters, aggregation) -> str:
    template = metric.query or ""
    if "__$labels__" not in template:
        raise AuthorizedMetricQueryError(
            "监控指标不支持受控实例查询",
            code="metric_template_not_scoped",
        )

    instance_keys = _metric_instance_id_keys(metric)
    matchers = _instance_matchers(instance_ids, instance_keys)
    matchers.extend(_filter_matchers(metric, filters))
    query = template.replace("__$labels__", ", ".join(matchers))

    aggregation_name = str(aggregation or "AVG").upper()
    if aggregation_name not in ALLOWED_AGGREGATIONS:
        raise AuthorizedMetricQueryError("汇聚方式不受支持", code="aggregation_invalid")
    aggregation_func = ALLOWED_AGGREGATIONS[aggregation_name]
    if aggregation_func:
        query = f'{aggregation_func}({query}) by ({", ".join(instance_keys)})'
    return query


def _normalize_bool(value, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", 0, "0", "false", "False"):
        return False
    if value in (1, "1", "true", "True"):
        return True
    raise AuthorizedMetricQueryError(f"{field} 必须是布尔值", code=f"{field}_invalid")


class AuthorizedMetricQueryService:
    def __init__(self, *, user, current_team, include_children: bool):
        self.user = user
        self.current_team = current_team
        self.include_children = include_children

    def _prepare(self, payload: dict) -> AuthorizedMetricQuery:
        if not isinstance(payload, dict):
            raise AuthorizedMetricQueryError("请求体必须是对象", code="payload_invalid")
        if self.user is None or self.current_team in (None, ""):
            raise AuthorizedMetricQueryError(
                "缺少用户或组织信息",
                code="query_identity_required",
            )
        if "query" in payload:
            raise AuthorizedMetricQueryError(
                "受控查询不接受原始 PromQL",
                code="raw_query_not_allowed",
            )

        monitor_object_id = payload.get("monitor_object_id")
        metric_id = payload.get("metric_id")
        raw_instance_ids = payload.get("instance_ids")
        if monitor_object_id in (None, "") or metric_id in (None, ""):
            raise AuthorizedMetricQueryError(
                "monitor_object_id 和 metric_id 不能为空",
                code="metric_context_required",
            )
        if not isinstance(raw_instance_ids, list) or not raw_instance_ids:
            raise AuthorizedMetricQueryError(
                "instance_ids 不能为空",
                code="instance_ids_required",
            )

        instance_ids = tuple(dict.fromkeys(str(value) for value in raw_instance_ids if value not in (None, "")))
        if not instance_ids:
            raise AuthorizedMetricQueryError(
                "instance_ids 不能为空",
                code="instance_ids_required",
            )

        metric = Metric.objects.select_related("monitor_object").filter(id=metric_id, monitor_object_id=monitor_object_id).first()
        if metric is None:
            raise AuthorizedMetricQueryError(
                "监控对象或指标不存在",
                code="metric_not_found",
            )

        if getattr(self.user, "is_superuser", False):
            authorized_qs = MonitorInstance.objects.all()
        else:
            permission = get_permission_rules(
                self.user,
                self.current_team,
                "monitor",
                f"{PermissionConstants.INSTANCE_MODULE}.{monitor_object_id}",
                include_children=self.include_children,
            )
            authorized_qs = permission_filter(
                MonitorInstance,
                permission,
                team_key="monitorinstanceorganization__organization__in",
                id_key="id__in",
            )

        authorized_ids = set(
            authorized_qs.filter(
                id__in=instance_ids,
                monitor_object_id=monitor_object_id,
                is_deleted=False,
            ).values_list("id", flat=True)
        )
        if authorized_ids != set(instance_ids):
            raise AuthorizedMetricQueryError(
                "无权访问所选监控实例",
                code="monitor_instance_forbidden",
            )

        try:
            start = int(payload.get("start"))
            end = int(payload.get("end"))
        except (TypeError, ValueError) as exc:
            raise AuthorizedMetricQueryError(
                "start 和 end 必须是毫秒时间戳",
                code="time_range_invalid",
            ) from exc
        if start >= end:
            raise AuthorizedMetricQueryError(
                "start 必须小于 end",
                code="time_range_invalid",
            )

        step = str(payload.get("step") or "5m")
        try:
            Metrics.parse_step_to_seconds(step)
        except ValueError as exc:
            raise AuthorizedMetricQueryError(str(exc), code="step_invalid") from exc

        collection_interval = payload.get("collection_interval")
        if collection_interval not in (None, ""):
            try:
                collection_interval = int(collection_interval)
            except (TypeError, ValueError) as exc:
                raise AuthorizedMetricQueryError(
                    "collection_interval 必须是整数",
                    code="collection_interval_invalid",
                ) from exc
            if collection_interval <= 0:
                raise AuthorizedMetricQueryError(
                    "collection_interval 必须大于 0",
                    code="collection_interval_invalid",
                )
        else:
            collection_interval = None

        return AuthorizedMetricQuery(
            metric=metric,
            instance_ids=instance_ids,
            query=_build_query(
                metric,
                instance_ids,
                payload.get("filters"),
                payload.get("aggregation"),
            ),
            start=start,
            end=end,
            step=step,
            detect_gaps=_normalize_bool(payload.get("detect_gaps"), field="detect_gaps"),
            collection_interval=collection_interval,
            card_budget=_normalize_bool(payload.get("card_budget"), field="card_budget"),
        )

    def query_range(self, payload: dict) -> dict:
        prepared = self._prepare(payload)
        return Metrics.get_metrics_range(
            prepared.query,
            prepared.start,
            prepared.end,
            prepared.step,
            detect_gaps=prepared.detect_gaps,
            collection_interval_seconds=prepared.collection_interval,
            card_budget=prepared.card_budget,
        )

    def query_instant(self, payload: dict) -> dict:
        prepared = self._prepare(payload)
        return Metrics.get_metrics(prepared.query, time=prepared.end / 1000.0)
