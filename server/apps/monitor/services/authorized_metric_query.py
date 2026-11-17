import re
from dataclasses import dataclass

from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.models import Metric, MonitorInstance, MonitorObject
from apps.monitor.services.metric_query_contract import (
    AuthorizedMetricQueryError,
    build_instance_matcher_groups,
    escape_metric_label_value,
    join_label_queries,
)
from apps.monitor.services.metrics import Metrics
from apps.monitor.utils.dimension import normalize_instance_identity, parse_instance_id

ALLOWED_AGGREGATIONS = {
    # AVG 按实例 + 已声明维度聚合，丢掉 collection_task_id / 采集器 host 等未声明标签。
    # 否则 Host Remote 每轮采集都是短命序列：折线合成一条，断点却按序列并集把整窗涂红。
    # 通用查询要按实例收成一个数时，调用方显式传 grouping="instance"，不改这里的默认。
    "AVG": "avg",
    "SUM": "sum",
    "MAX": "max",
    "MIN": "min",
    "COUNT": "count",
}

GROUPING_INSTANCE = "instance"


@dataclass(frozen=True)
class AuthorizedMetricQuery:
    metric: Metric | None
    instance_ids: tuple[str, ...]
    query: str
    start: int
    end: int
    step: str
    detect_gaps: bool
    collection_interval: int | None
    card_budget: bool


def _instance_lookup_candidates(value) -> tuple[str, ...]:
    """同一台实例的主键可能是纯字符串，也可能是单维元组串。两种都拿去对库。"""
    raw = str(value).strip()
    if not raw:
        return ()
    ordered = [raw]
    try:
        normalized = normalize_instance_identity(value)
    except ValueError:
        return tuple(ordered)
    storage_key = str(normalized.get("storage_instance_key") or "").strip()
    if storage_key and storage_key not in ordered:
        ordered.append(storage_key)
    if len(parse_instance_id(value)) == 1:
        logical = str(normalized.get("logical_instance_value") or "").strip()
        if logical and logical not in ordered:
            ordered.append(logical)
    return tuple(ordered)


def _metric_instance_id_keys(metric: Metric) -> list[str]:
    keys = metric.instance_id_keys or getattr(metric.monitor_object, "instance_id_keys", None) or []
    normalized = [str(key).strip() for key in keys if key is not None and str(key).strip()]
    if not normalized:
        raise AuthorizedMetricQueryError(
            "监控指标缺少实例标识契约",
            code="metric_instance_keys_missing",
        )
    return normalized


def _metric_dimension_names(metric: Metric) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in metric.dimensions or []:
        raw = item.get("name") if isinstance(item, dict) else item
        name = str(raw).strip() if raw is not None else ""
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _allowed_dimensions(metric: Metric) -> set[str]:
    return set(_metric_dimension_names(metric))


def _aggregation_grouping_labels(metric: Metric, aggregation_name: str) -> list[str]:
    grouping = list(_metric_instance_id_keys(metric))
    if aggregation_name == "AVG":
        for name in _metric_dimension_names(metric):
            if name not in grouping:
                grouping.append(name)
    return grouping


def _grouping_labels(metric: Metric, aggregation_name: str, grouping) -> list[str]:
    """默认沿用全局聚合。通用查询传入 instance 时只按实例标识分组。"""
    if grouping in (None, ""):
        return _aggregation_grouping_labels(metric, aggregation_name)
    if grouping == GROUPING_INSTANCE:
        return list(_metric_instance_id_keys(metric))
    raise AuthorizedMetricQueryError("分组方式不受支持", code="grouping_invalid")


def _select_authorized_instance(raw: str, authorized_ids: set[str], existing_ids: set[str]) -> str | None:
    """同一实例的原始串和存储键可以互换。另一个已存在的实例不能借写法混进来。"""
    text = str(raw).strip()
    if not text:
        return None
    if text in authorized_ids:
        return text
    if text in existing_ids:
        return None
    alternates = [item for item in _instance_lookup_candidates(text) if item != text]
    existing_alternates = [item for item in alternates if item in existing_ids]
    if len(existing_alternates) == 1 and existing_alternates[0] in authorized_ids:
        return existing_alternates[0]
    return None


def _open_dimension_names(metric: Metric) -> list[str]:
    """实例标识本身不是「一台机器上的多个数」。"""
    identity = set(_metric_instance_id_keys(metric))
    return [name for name in _metric_dimension_names(metric) if name not in identity]


def empty_aggregation_needs_choice(metric: Metric, filters) -> bool:
    """有维度却没被等于定死时，空的聚合方式不能偷偷按平均。"""
    names = _open_dimension_names(metric)
    if not names:
        return False
    logic, items = _condition_clauses(filters)
    if logic != "AND":
        return True
    pinned: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            return True
        label = str(item.get("field") if item.get("field") not in (None, "") else item.get("label") or "").strip()
        operator = str(item.get("op") if item.get("op") not in (None, "") else item.get("operator") or "").strip()
        value = item.get("value")
        if label == "" and operator == "" and value in (None, ""):
            continue
        if operator not in {"eq", "="} or value in (None, "") or label not in names:
            return True
        text = str(value)
        previous = pinned.get(label)
        if previous is not None and previous != text:
            return True
        pinned[label] = text
    return any(name not in pinned for name in names)


_METRIC_CONDITION_OPERATORS = {
    "eq": "=",
    "=": "=",
    "ne": "!=",
    "!=": "!=",
    "regex": "=~",
    "=~": "=~",
    "notRegex": "!~",
    "!~": "!~",
}


def _condition_clauses(filters) -> tuple[str, list]:
    if filters in (None, "", [], {}):
        return "AND", []
    if isinstance(filters, list):
        return "AND", filters
    if isinstance(filters, dict) and set(filters) <= {"logic", "items"}:
        logic = str(filters.get("logic") or "AND").strip().upper()
        if logic not in {"AND", "OR"}:
            raise AuthorizedMetricQueryError("条件关系不受支持", code="filter_logic_invalid")
        items = filters.get("items") or []
        if not isinstance(items, list):
            raise AuthorizedMetricQueryError("filters 必须是条件", code="filters_invalid")
        return logic, items
    raise AuthorizedMetricQueryError("filters 必须是条件", code="filters_invalid")


def _matcher_for_condition(metric: Metric, item) -> str | None:
    if not isinstance(item, dict):
        raise AuthorizedMetricQueryError("filters 元素必须是对象", code="filters_invalid")
    label = str(item.get("field") if item.get("field") not in (None, "") else item.get("label") or "").strip()
    operator = str(item.get("op") if item.get("op") not in (None, "") else item.get("operator") or "").strip()
    value = item.get("value")
    if label == "" and operator == "" and value in (None, ""):
        return None
    if label == "":
        raise AuthorizedMetricQueryError("维度名不能为空", code="filter_label_invalid")
    mapped = _METRIC_CONDITION_OPERATORS.get(operator)
    if mapped is None:
        raise AuthorizedMetricQueryError("当前查询不支持该运算符", code="filter_operator_invalid")
    if value in (None, ""):
        raise AuthorizedMetricQueryError("筛选值不能为空", code="filter_value_invalid")
    if label not in _allowed_dimensions(metric):
        raise AuthorizedMetricQueryError("筛选维度未在指标中声明", code="filter_label_invalid")
    return f'{label}{mapped}"{escape_metric_label_value(value)}"'


def _dimension_matcher_groups(metric: Metric, filters) -> list[list[str]]:
    """并且放进同一组；或者每条单独成组，调用方再用 or 接上。"""
    logic, items = _condition_clauses(filters)
    matchers = []
    for item in items:
        matcher = _matcher_for_condition(metric, item)
        if matcher:
            matchers.append(matcher)
    if not matchers:
        return []
    if logic == "OR":
        return [[matcher] for matcher in matchers]
    return [matchers]


def _render_metric_query(metric: Metric, matcher_groups: list[list[str]], aggregation, grouping=None) -> str:
    template = metric.query or ""
    if "__$labels__" not in template:
        raise AuthorizedMetricQueryError(
            "监控指标不支持受控实例查询",
            code="metric_template_not_scoped",
        )

    query = join_label_queries(template, matcher_groups)

    aggregation_name = str(aggregation or "AVG").upper()
    if aggregation_name not in ALLOWED_AGGREGATIONS:
        raise AuthorizedMetricQueryError("汇聚方式不受支持", code="aggregation_invalid")
    aggregation_func = ALLOWED_AGGREGATIONS[aggregation_name]
    if aggregation_func:
        labels = _grouping_labels(metric, aggregation_name, grouping)
        query = f'{aggregation_func}({query}) by ({", ".join(labels)})'
    return query


def _build_query(metric: Metric, instance_ids: tuple[str, ...], filters, aggregation, grouping=None) -> str:
    instance_keys = _metric_instance_id_keys(metric)
    base_groups = build_instance_matcher_groups(instance_ids, instance_keys)
    dimension_groups = _dimension_matcher_groups(metric, filters)
    if not dimension_groups:
        matcher_groups = base_groups
    else:
        matcher_groups = [list(base) + extra for base in base_groups for extra in dimension_groups]
    return _render_metric_query(metric, matcher_groups, aggregation, grouping)


def _normalize_bool(value, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", 0, "0", "false", "False"):
        return False
    if value in (1, "1", "true", "True"):
        return True
    raise AuthorizedMetricQueryError(f"{field} 必须是布尔值", code=f"{field}_invalid")


class AuthorizedMetricQueryService:
    def __init__(self, *, user, current_team, include_children: bool, organization_scope=None):
        self.user = user
        self.current_team = current_team
        self.include_children = include_children
        # None 保持旧 HTTP 入口：超管可见全部实例。通用查询传入当前组织范围。
        self.organization_scope = organization_scope

    def _authorize_instances(self, monitor_object_id, raw_instance_ids) -> tuple[MonitorObject, tuple[str, ...]]:
        if monitor_object_id in (None, ""):
            raise AuthorizedMetricQueryError("monitor_object_id 不能为空", code="metric_context_required")
        if not isinstance(raw_instance_ids, list) or not raw_instance_ids:
            raise AuthorizedMetricQueryError(
                "instance_ids 不能为空",
                code="instance_ids_required",
            )

        lookups = []
        candidate_ids = []
        for value in raw_instance_ids:
            if value in (None, ""):
                continue
            candidates = _instance_lookup_candidates(value)
            if not candidates:
                continue
            lookups.append(candidates)
            for item in candidates:
                if item not in candidate_ids:
                    candidate_ids.append(item)
        if not lookups:
            raise AuthorizedMetricQueryError(
                "instance_ids 不能为空",
                code="instance_ids_required",
            )

        monitor_object = MonitorObject.objects.filter(id=monitor_object_id).first()
        if monitor_object is None:
            raise AuthorizedMetricQueryError(
                "监控对象不存在",
                code="monitor_object_not_found",
            )

        if getattr(self.user, "is_superuser", False):
            authorized_qs = MonitorInstance.objects.all()
            if self.organization_scope is not None:
                authorized_qs = authorized_qs.filter(monitorinstanceorganization__organization__in=list(self.organization_scope))
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

        identity = dict(
            id__in=candidate_ids,
            monitor_object_id=monitor_object_id,
            is_deleted=False,
        )
        existing_ids = set(MonitorInstance.objects.filter(**identity).values_list("id", flat=True))
        authorized_ids = set(authorized_qs.filter(**identity).values_list("id", flat=True))
        resolved = []
        seen = set()
        for candidates in lookups:
            match = _select_authorized_instance(candidates[0], authorized_ids, existing_ids)
            if match is None:
                raise AuthorizedMetricQueryError(
                    "无权访问所选监控实例",
                    code="monitor_instance_forbidden",
                )
            if match not in seen:
                seen.add(match)
                resolved.append(match)
        return monitor_object, tuple(resolved)

    def _authorize_host_process_scope(self, monitor_object_id, scope) -> tuple[MonitorObject, tuple[str, ...], list[str]]:
        if not isinstance(scope, dict) or scope.get("type") != "host_process":
            raise AuthorizedMetricQueryError("查询作用域无效", code="query_scope_invalid")
        process_object = MonitorObject.objects.filter(id=monitor_object_id, name="Process").first()
        if process_object is None:
            raise AuthorizedMetricQueryError("进程查询对象无效", code="query_scope_invalid")
        host_object, host_instance_ids = self._authorize_instances(
            scope.get("host_monitor_object_id"),
            [scope.get("host_instance_id")],
        )
        if host_object.name != "Host" or len(host_instance_ids) != 1:
            raise AuthorizedMetricQueryError("主机查询作用域无效", code="query_scope_invalid")

        host_values = parse_instance_id(host_instance_ids[0])
        if not host_values or host_values[0] in (None, ""):
            raise AuthorizedMetricQueryError("主机实例标识无效", code="query_scope_invalid")
        matchers = [f'instance_id=~"{escape_metric_label_value(re.escape(str(host_values[0])))}"']

        raw_names = scope.get("process_names") or []
        if not isinstance(raw_names, list) or len(raw_names) > 100:
            raise AuthorizedMetricQueryError("进程筛选范围无效", code="query_scope_invalid")
        process_names = sorted({str(name).strip() for name in raw_names if str(name).strip()})
        if any(len(name) > 200 for name in process_names):
            raise AuthorizedMetricQueryError("进程筛选范围无效", code="query_scope_invalid")
        if process_names:
            values = "|".join(escape_metric_label_value(re.escape(name)) for name in process_names)
            matchers.append(f'process_name=~"{values}"')
        return process_object, host_instance_ids, matchers

    def _prepare(self, payload: dict, *, bucket_window: bool = False) -> AuthorizedMetricQuery:
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
        capability_id = str(payload.get("capability_id") or "").strip()
        if (metric_id in (None, "")) == (not capability_id):
            raise AuthorizedMetricQueryError(
                "metric_id 与 capability_id 必须且只能提供一个",
                code="metric_context_required",
            )
        scope_matchers = None
        if payload.get("scope") is not None:
            if capability_id:
                raise AuthorizedMetricQueryError("查询能力不接受自定义作用域", code="query_scope_invalid")
            monitor_object, instance_ids, scope_matchers = self._authorize_host_process_scope(
                monitor_object_id,
                payload.get("scope"),
            )
        else:
            monitor_object, instance_ids = self._authorize_instances(
                monitor_object_id,
                payload.get("instance_ids"),
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
            step_seconds = Metrics.parse_step_to_seconds(step)
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

        metric = None
        if capability_id:
            if payload.get("filters") not in (None, [], "") or payload.get("aggregation") not in (None, ""):
                raise AuthorizedMetricQueryError(
                    "仪表盘查询能力不接受自定义筛选或汇聚",
                    code="capability_params_invalid",
                )
            from apps.monitor.services.dashboard_query_capabilities import build_dashboard_query

            query = build_dashboard_query(
                capability_id=capability_id,
                monitor_object=monitor_object,
                instance_ids=instance_ids,
                start=start,
                end=end,
                params=payload.get("capability_params"),
                step_seconds=step_seconds if bucket_window else None,
            )
        else:
            metric = (
                Metric.objects.select_related("monitor_object")
                .filter(
                    id=metric_id,
                    monitor_object_id=monitor_object.id,
                )
                .first()
            )
            if metric is None:
                raise AuthorizedMetricQueryError(
                    "监控对象或指标不存在",
                    code="metric_not_found",
                )
            if scope_matchers is not None:
                if payload.get("filters") not in (None, [], ""):
                    raise AuthorizedMetricQueryError("进程查询不接受额外筛选", code="query_scope_invalid")
                query = _render_metric_query(metric, [scope_matchers], payload.get("aggregation"), payload.get("grouping"))
            else:
                query = _build_query(
                    metric,
                    instance_ids,
                    payload.get("filters"),
                    payload.get("aggregation"),
                    payload.get("grouping"),
                )

        return AuthorizedMetricQuery(
            metric=metric,
            instance_ids=instance_ids,
            query=query,
            start=start,
            end=end,
            step=step,
            detect_gaps=_normalize_bool(payload.get("detect_gaps"), field="detect_gaps"),
            collection_interval=collection_interval,
            card_budget=_normalize_bool(payload.get("card_budget"), field="card_budget"),
        )

    def query_range(self, payload: dict) -> dict:
        prepared = self._prepare(payload, bucket_window=True)
        return Metrics.get_metrics_range(
            prepared.query,
            prepared.start,
            prepared.end,
            prepared.step,
            detect_gaps=prepared.detect_gaps,
            collection_interval_seconds=prepared.collection_interval,
            card_budget=prepared.card_budget,
        )

    def prepare(self, payload: dict) -> AuthorizedMetricQuery:
        return self._prepare(payload)

    def query_instant(self, payload: dict) -> dict:
        prepared = self.prepare(payload)
        return Metrics.get_metrics(prepared.query, time=prepared.end / 1000.0)
