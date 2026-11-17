"""目录、概览、按路由页面列表，以及 Web Vitals 告警的聚合库读取。

聚合可用、已记录 RUM 起点、且窗口起点不早于起点时，浏览次数、JS 错误次数和
Web Vitals p75 读聚合库。会话、分布、按版本的页面列表，以及会话数、错误会话率
告警仍由调用方读 VictoriaLogs。页面数字在聚合库报错时降级；告警评估把这次读取
失败抛回现有状态机，告警详情趋势只清空曲线，都不回退扫明细。

p75 使用 ``histogram_quantile(0.75, sum by (le) (increase(..._bucket[窗口])))``。
这是桶上的估计分位数，不是 VictoriaLogs ``quantile(0.75)`` 的精确样本分位数。
LCP / INP / FCP / TTFB 直方图的数值仍是毫秒，CLS 无单位，与现有 LogsQL 字段一致。
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from apps.core.aggregate_origin import recorded_origin
from apps.core.aggregate_promql import AggregatePromqlClient, align_query_end, escape_promql_label_value, rum_flush_seconds
from apps.core.logger import rum_logger as logger
from apps.core.logger import safe_exception_info, safe_log_value
from apps.rum.services.victoria_client import sparkline_layout

# rumroutecap 超出每个应用 100 条路由后写入的标签值；空路由是 unknown。
OTHER_ROUTE = "其他"
VIEWS_METRIC = "rum_views_total"
ERRORS_METRIC = "rum_js_errors_total"
VITALS = {
    "lcp": "rum_web_vital_lcp_milliseconds",
    "inp": "rum_web_vital_inp_milliseconds",
    "cls": "rum_web_vital_cls",
}
# 告警策略只按应用收窄，没有环境、路由或版本。分位数用 sum by (le) 把这些标签并回同一组，
# 与不带这些条件的 LogsQL quantile 同宽。FCP / TTFB 只用于告警，不进页面列表。
ALERT_VITALS = {
    "lcp_p75": VITALS["lcp"],
    "inp_p75": VITALS["inp"],
    "cls_p75": VITALS["cls"],
    "fcp_p75": "rum_web_vital_fcp_milliseconds",
    "ttfb_p75": "rum_web_vital_ttfb_milliseconds",
}
# 与页面列表 LogsQL 一致：访客排除 bot / synthetic / crawler，其余（含 human、unknown）都算。
_VISITOR_EXCLUDE = "bot|synthetic|crawler"


def attach_aggregate_reader(analytics):
    analytics.aggregate = AggregateRumReader()
    return analytics


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _tenant(tenant_id: str) -> str:
    return (tenant_id or "").strip() or "core"


def _app_fragment(apps: list[str]) -> str:
    unique = list(dict.fromkeys(app for app in apps if str(app).strip()))
    if len(unique) == 1:
        return f'rum_application="{escape_promql_label_value(unique[0])}"'
    pattern = "|".join(re.escape(app) for app in unique)
    return f'rum_application=~"{escape_promql_label_value(pattern)}"'


def _traffic_fragment(traffic: str | None) -> str:
    want = (traffic or "").strip().lower()
    if want in {"", "all"}:
        return ""
    if want == "visitors":
        return f'rum_traffic_class!~"{_VISITOR_EXCLUDE}"'
    if want == "automated":
        return f'rum_traffic_class=~"{_VISITOR_EXCLUDE}"'
    return f'rum_traffic_class="{escape_promql_label_value(want)}"'


def _selector(tenant_id: str, apps: list[str], traffic: str | None) -> str:
    parts = [f'tenant_id="{escape_promql_label_value(_tenant(tenant_id))}"', _app_fragment(apps)]
    traffic_part = _traffic_fragment(traffic)
    if traffic_part:
        parts.append(traffic_part)
    return ",".join(parts)


def _alert_selector(tenant_id: str, opts: dict) -> str:
    apps = [str(app) for app in opts.get("applications") or [] if str(app).strip()]
    if not apps:
        application = str(opts.get("application") or "").strip()
        apps = [application] if application else []
    traffic = opts.get("traffic")
    if traffic is None or str(traffic).strip() == "":
        traffic = "visitors"
    return _selector(tenant_id, apps, str(traffic))


def _increase(metric: str, selector: str, window_seconds: int, by: str) -> str:
    inner = f"increase({metric}{{{selector}}}[{window_seconds}s])"
    return f"sum by ({by}) ({inner})"


def _quantile(metric: str, selector: str, window_seconds: int, by: str) -> str:
    return f"histogram_quantile(0.75, {_increase(metric + '_bucket', selector, window_seconds, by)})"


def _number(raw: object) -> float | None:
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _sample(series: dict) -> float | None:
    raw = series.get("value")
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    return _number(raw[1])


def _count(value: float | None) -> int | None:
    if value is None or value < 0:
        return None
    return int(round(value))


def _by_label(result: list[dict], label: str) -> dict[str, float]:
    grouped: dict[str, float] = {}
    for series in result:
        metric = series.get("metric")
        if not isinstance(metric, dict):
            continue
        name = str(metric.get(label) or "")
        if not name:
            continue
        value = _sample(series)
        if value is None:
            continue
        grouped[name] = value
    return grouped


def _matrix_by_label(result: list[dict], label: str) -> dict[str, list[tuple[float, float | None]]]:
    grouped: dict[str, list[tuple[float, float | None]]] = {}
    for series in result:
        metric = series.get("metric")
        if not isinstance(metric, dict):
            continue
        name = str(metric.get(label) or "")
        if not name:
            continue
        values = series.get("values")
        if not isinstance(values, list):
            continue
        points: list[tuple[float, float | None]] = []
        for pair in values:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            timestamp = _number(pair[0])
            if timestamp is None:
                continue
            points.append((timestamp, _number(pair[1])))
        grouped[name] = points
    return grouped


def _spark_step(start: datetime, end: datetime, buckets: int) -> int:
    """桶宽。按原窗口均分，不用对齐后缩短的窗口，否则步长会小于桶宽。"""

    width = (_as_utc(end) - _as_utc(start)).total_seconds()
    if buckets <= 0 or width <= 0:
        return 1
    return max(1, int(width // buckets))


def _interval_index(seen: datetime, start: datetime, buckets: int, step: int) -> int | None:
    """``increase[step]`` 在时刻 t 统计的是 ``[t-step, t]``，放进该区间开启的桶。"""

    if step <= 0:
        return None
    opened = (_as_utc(seen) - _as_utc(start)).total_seconds() - step
    if opened < 0:
        return None
    index = int(opened // step)
    if index >= buckets:
        return None
    return index


def _bucket_open(index: int, start: datetime, end: datetime, buckets: int) -> datetime:
    return _as_utc(start) + timedelta(seconds=_spark_step(start, end, buckets) * index)


def _fill_spark(
    points: list[tuple[float, float | None]],
    start: datetime,
    end: datetime,
    buckets: int,
    *,
    origin: datetime | None = None,
    zero_gaps: bool = False,
) -> list[int | None]:
    """Place count samples. Quiet buckets become 0 only when the whole-window series exists.

    A sample at time t covers ``[t-step, t]`` and is stored in the bucket that interval opens.
    Each bucket keeps one sample. A gap stays empty when it opens before the aggregate origin,
    or when ``zero_gaps`` is false (no count series, or a percentile trend). A trailing bucket
    with no complete interval keeps that same empty-or-zero rule.
    """

    if buckets <= 0 or (_as_utc(end) - _as_utc(start)).total_seconds() <= 0:
        return []
    step = _spark_step(start, end, buckets)
    totals: list[float | None] = [None] * buckets
    for timestamp, value in points:
        if value is None:
            continue
        index = _interval_index(datetime.fromtimestamp(timestamp, tz=UTC), start, buckets, step)
        if index is None or totals[index] is not None:
            continue
        totals[index] = value
    if zero_gaps and origin is not None:
        covered_from = _as_utc(origin)
        window_end = _as_utc(end)
        for index, item in enumerate(totals):
            if item is not None:
                continue
            opened = _bucket_open(index, start, end, buckets)
            if covered_from <= opened < window_end:
                totals[index] = 0
    return [None if item is None else _count(item) for item in totals]


class AggregateRumReader:
    def __init__(
        self,
        client: AggregatePromqlClient | None = None,
        *,
        origin_at: Callable[[], datetime | None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.client = client or AggregatePromqlClient.from_env()
        self.origin_at = origin_at or (lambda: recorded_origin("rum"))
        self.clock = clock or (lambda: datetime.now(UTC))

    def overlay_catalog(self, rows: list[dict], sparks: dict, *, tenant_id: str, apps: list[str], start: datetime, end: datetime) -> None:
        if not apps or not self._covered(start):
            return
        try:
            metrics = self._catalog(tenant_id, apps, start, end)
        except Exception as exc:  # noqa: BLE001 — 聚合失败只降级这组数字，页面其余部分继续
            self._fail(tenant_id, "catalog", exc)
            self._blank_catalog(rows, sparks, apps)
            return
        allowed = set(apps)
        for row in rows:
            app = row.get("application")
            if app not in allowed:
                continue
            item = metrics.get(app)
            if item is None:
                self._blank_app(row, sparks, app)
                continue
            row["views"] = item["views"]
            row["errors"] = item["errors"]
            row["lcpP75"] = item["lcpP75"]
            row["inpP75"] = item["inpP75"]
            sparks[app] = item["spark"]

    def overlay_views(self, page: dict, *, tenant_id: str, opts: dict) -> dict:
        if not self._routes_eligible(opts) or not self._covered(opts.get("from")):
            return page
        try:
            routes = self._routes(tenant_id, opts)
        except Exception as exc:  # noqa: BLE001 — 聚合失败只降级这组数字，页面其余部分继续
            self._fail(tenant_id, "views", exc)
            return _degrade_views(page)
        return _merge_views(page, routes)

    def _covered(self, started_at: datetime | None) -> bool:
        if not isinstance(started_at, datetime) or not self.client.available:
            return False
        origin = self.origin_at()
        if origin is None:
            return False
        return _as_utc(started_at) >= _as_utc(origin)

    def _routes_eligible(self, opts: dict) -> bool:
        if (opts.get("mode") or "route").strip() != "route":
            return False
        if str(opts.get("release") or "").strip():
            return False
        return any(str(app).strip() for app in opts.get("applications") or [])

    def _catalog(self, tenant_id: str, apps: list[str], start: datetime, end: datetime) -> dict[str, dict]:
        aligned = align_query_end(end, now=self.clock(), flush_seconds=rum_flush_seconds())
        window_seconds = int((aligned - _as_utc(start)).total_seconds())
        names = list(dict.fromkeys(app for app in apps if str(app).strip()))
        if window_seconds <= 0:
            return {app: _empty_app() for app in names}
        selector = _selector(tenant_id, names, None)
        views = _by_label(
            self.client.query_instant(_increase(VIEWS_METRIC, selector, window_seconds, "rum_application"), at=aligned),
            "rum_application",
        )
        errors = _by_label(
            self.client.query_instant(_increase(ERRORS_METRIC, selector, window_seconds, "rum_application"), at=aligned),
            "rum_application",
        )
        lcp = _by_label(
            self.client.query_instant(_quantile(VITALS["lcp"], selector, window_seconds, "le, rum_application"), at=aligned),
            "rum_application",
        )
        inp = _by_label(
            self.client.query_instant(_quantile(VITALS["inp"], selector, window_seconds, "le, rum_application"), at=aligned),
            "rum_application",
        )
        _, buckets = sparkline_layout(start, end)
        # 步长按原窗口均分。increase 在时刻 t 统计 [t-step, t]，所以从起点之后一个步长开始查，
        # 到对齐后的结束时间为止；还没有完整区间的尾桶不在这次结果里。
        step = _spark_step(start, end, buckets)
        range_start = _as_utc(start) + timedelta(seconds=step)
        series: dict[str, list[tuple[float, float | None]]] = {}
        if range_start <= aligned:
            series = _matrix_by_label(
                self.client.query_range(
                    _increase(VIEWS_METRIC, selector, step, "rum_application"),
                    start=range_start,
                    end=aligned,
                    step_seconds=step,
                ),
                "rum_application",
            )
        found: dict[str, dict] = {}
        for app in names:
            view_count = _count(views.get(app)) if app in views else None
            if view_count is None:
                found[app] = _empty_app()
                continue
            found[app] = {
                "views": view_count,
                "errors": _count(errors[app]) if app in errors else 0,
                "lcpP75": lcp.get(app),
                "inpP75": inp.get(app),
                "spark": _fill_spark(
                    series.get(app) or [],
                    start,
                    end,
                    buckets,
                    origin=self.origin_at(),
                    zero_gaps=True,
                ),
            }
        return found

    def _routes(self, tenant_id: str, opts: dict) -> list[dict]:
        aligned = align_query_end(opts["to"], now=self.clock(), flush_seconds=rum_flush_seconds())
        window_seconds = int((aligned - _as_utc(opts["from"])).total_seconds())
        apps = list(dict.fromkeys(app for app in opts.get("applications") or [] if str(app).strip()))
        if window_seconds <= 0:
            return []
        traffic = opts.get("traffic")
        if traffic is None or str(traffic).strip() == "":
            traffic = "visitors"
        selector = _selector(tenant_id, apps, str(traffic))
        views = _by_label(
            self.client.query_instant(_increase(VIEWS_METRIC, selector, window_seconds, "rum_aggregate_route"), at=aligned),
            "rum_aggregate_route",
        )
        errors = _by_label(
            self.client.query_instant(_increase(ERRORS_METRIC, selector, window_seconds, "rum_aggregate_route"), at=aligned),
            "rum_aggregate_route",
        )
        vitals = {
            name: _by_label(
                self.client.query_instant(_quantile(metric, selector, window_seconds, "le, rum_aggregate_route"), at=aligned),
                "rum_aggregate_route",
            )
            for name, metric in VITALS.items()
        }
        names = set(views) | set(errors) | set(vitals["lcp"]) | set(vitals["inp"]) | set(vitals["cls"])
        rows = []
        for route in names:
            view_count = _count(views.get(route)) if route in views else None
            if view_count is None:
                error_count = _count(errors[route]) if route in errors else None
            else:
                error_count = _count(errors[route]) if route in errors else 0
            rows.append(
                {
                    "route": route,
                    "views": view_count,
                    "errors": error_count,
                    "lcpP75": vitals["lcp"].get(route),
                    "inpP75": vitals["inp"].get(route),
                    "clsP75": vitals["cls"].get(route),
                }
            )
        return rows

    def monitor_vital(self, tenant_id: str, opts: dict) -> tuple[bool, float | None]:
        """读一条 Web Vitals 告警。未覆盖时交回 VictoriaLogs；缺样本是 None，不是 0。"""

        plan = self._alert_plan(opts)
        if plan is None:
            return False, None
        metric, aligned, window_seconds = plan
        result = self.client.query_instant(
            _quantile(metric, _alert_selector(tenant_id, opts), window_seconds, "le"),
            at=aligned,
        )
        if not result:
            return True, None
        return True, _sample(result[0])

    def vital_series(self, tenant_id: str, opts: dict) -> tuple[bool, list]:
        """告警详情里的 Web Vitals 趋势。聚合失败只清空曲线，不改已经写好的事件。"""

        plan = self._alert_plan(opts)
        if plan is None:
            return False, []
        metric, aligned, _window_seconds = plan
        try:
            return True, self._vital_points(tenant_id, opts, metric, aligned)
        except Exception as exc:  # noqa: BLE001 — 趋势失败只清空曲线，已固化的事件保持原样
            self._fail(tenant_id, "alert_trend", exc)
            return True, []

    def _alert_plan(self, opts: dict) -> tuple[str, datetime, int] | None:
        metric = ALERT_VITALS.get(str(opts.get("metric") or "").strip())
        if metric is None:
            return None
        start = opts.get("from")
        end = opts.get("to")
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            return None
        if not self.client.available:
            return None
        origin = self.origin_at()
        if origin is None:
            return None
        window_seconds = int((_as_utc(end) - _as_utc(start)).total_seconds())
        if window_seconds <= 0:
            return None
        aligned = align_query_end(end, now=self.clock(), flush_seconds=rum_flush_seconds())
        if aligned - timedelta(seconds=window_seconds) < _as_utc(origin):
            return None
        return metric, aligned, window_seconds

    def _vital_points(self, tenant_id: str, opts: dict, metric: str, aligned: datetime) -> list[dict]:
        buckets = int(opts.get("points") or 12)
        if buckets <= 0:
            buckets = 12
        start = _as_utc(opts["from"])
        end = _as_utc(opts["to"])
        step = (end - start) / buckets
        # 查询步长必须是整数秒。分桶用同一个步长，避免窗口不能被点数整除时样本落到前一个桶。
        # 第一个点从窗口起点之后一个步长开始，这样 increase 不会读到起点之前。
        step_seconds = max(1, int(step.total_seconds()))
        range_start = start + timedelta(seconds=step_seconds)
        points: list[dict] = [{"atMs": int((start + step * index).timestamp() * 1000), "value": None} for index in range(buckets)]
        if range_start > aligned:
            return points
        series = self.client.query_range(
            _quantile(metric, _alert_selector(tenant_id, opts), step_seconds, "le"),
            start=range_start,
            end=aligned,
            step_seconds=step_seconds,
        )
        for item in series:
            values = item.get("values")
            if not isinstance(values, list):
                continue
            for pair in values:
                if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                    continue
                timestamp = _number(pair[0])
                if timestamp is None:
                    continue
                index = int((timestamp - start.timestamp()) // step_seconds) - 1
                if index < 0 or index >= buckets:
                    continue
                value = _number(pair[1])
                if value is None:
                    continue
                points[index]["value"] = value
        return points

    def _blank_catalog(self, rows: list[dict], sparks: dict, apps: list[str]) -> None:
        allowed = set(apps)
        for row in rows:
            app = row.get("application")
            if app in allowed:
                self._blank_app(row, sparks, app)

    @staticmethod
    def _blank_app(row: dict, sparks: dict, app: str) -> None:
        row["views"] = None
        row["errors"] = None
        row["lcpP75"] = None
        row["inpP75"] = None
        sparks[app] = []

    def _fail(self, tenant_id: str, stage: str, exc: BaseException) -> None:
        logger.warning(
            "event=rum_aggregate_read_failed tenant_id=%s failed_stage=%s error_type=%s",
            safe_log_value(_tenant(tenant_id)),
            stage,
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )


def _empty_app() -> dict:
    return {"views": None, "errors": None, "lcpP75": None, "inpP75": None, "spark": []}


def _degrade_views(page: dict) -> dict:
    rows = []
    for row in page.get("rows") or []:
        item = dict(row)
        item["views"] = None
        item["errors"] = None
        item["lcpP75"] = None
        item["inpP75"] = None
        item["clsP75"] = None
        rows.append(item)
    return {**page, "rows": rows, "summary": {"lcpP75": None, "inpP75": None, "clsP75": None}}


def _merge_views(page: dict, routes: list[dict]) -> dict:
    by_route = {str(row.get("route") or ""): row for row in page.get("rows") or []}
    merged = []
    for item in routes:
        route = item["route"]
        base = dict(by_route.get(route) or _empty_route(route))
        base["key"] = route
        base["route"] = route
        base["views"] = item["views"]
        base["errors"] = item["errors"]
        base["lcpP75"] = item["lcpP75"]
        base["inpP75"] = item["inpP75"]
        base["clsP75"] = item["clsP75"]
        poor = int(((base.get("dist") or {}).get("poor")) or 0)
        base["impact"] = poor * 10 + (0 if item["views"] is None else int(item["views"]))
        merged.append(base)
    merged.sort(key=lambda row: (-(row.get("impact") or 0), str(row.get("route") or "")))
    return {
        **page,
        "rows": merged,
        "releases": sorted({row["release"] for row in merged if row.get("release")}),
        "summary": {
            "lcpP75": _avg(merged, "lcpP75"),
            "inpP75": _avg(merged, "inpP75"),
            "clsP75": _avg(merged, "clsP75"),
        },
    }


def _empty_route(route: str) -> dict:
    return {
        "key": route,
        "route": route,
        "release": "",
        "sessions": None,
        "loadingP75": None,
        "dist": {"good": 0, "needsImprove": 0, "poor": 0, "missing": 0},
        "mom": {"hasDelta": False, "spark": []},
        "deviceMix": {"mobile": 0, "desktop": 0},
    }


def _avg(rows: list[dict], name: str) -> float | None:
    values = [row[name] for row in rows if row.get(name) is not None]
    if not values:
        return None
    return sum(values) / len(values)
