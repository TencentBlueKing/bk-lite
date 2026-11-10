"""目录、概览和按路由页面列表在聚合起点覆盖窗口时改读聚合库。"""

import logging
import traceback
from datetime import UTC, datetime, timedelta

import pytest

from apps.core.aggregate_promql import AggregateMetricsUnavailable
from apps.core.logger import SafeLogException
from apps.rum.services.aggregate_reads import AggregateRumReader, _fill_spark
from apps.rum.services.analytics import _build_analytics
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import MemoryControl
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.victoria_analytics import VictoriaAnalytics

START = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
END = datetime(2026, 11, 10, 0, 16, 30, tzinfo=UTC)
# 00:16:30 对齐到 00:16:00，再留出 10 秒刷出周期（见下方 fixture）。
ALIGNED = datetime(2026, 11, 10, 0, 15, 50, tzinfo=UTC)
WINDOW = 950
POINT = START.timestamp() + 120
SELECTOR = 'tenant_id="core",rum_application=~"storefront|checkout"'
VIEWS = f"sum by (rum_application) (increase(rum_views_total{{{SELECTOR}}}[{WINDOW}s]))"
LCP = "histogram_quantile(0.75, sum by (le, rum_application) " f"(increase(rum_web_vital_lcp_milliseconds_bucket{{{SELECTOR}}}[{WINDOW}s])))"
ROUTE_SELECTOR = 'tenant_id="core",rum_application="storefront",rum_traffic_class!~"bot|synthetic|crawler"'
ROUTE_VIEWS = f"sum by (rum_aggregate_route) (increase(rum_views_total{{{ROUTE_SELECTOR}}}[{WINDOW}s]))"
ROUTE_CLS = "histogram_quantile(0.75, sum by (le, rum_aggregate_route) " f"(increase(rum_web_vital_cls_bucket{{{ROUTE_SELECTOR}}}[{WINDOW}s])))"


@pytest.fixture(autouse=True)
def _ten_second_flush(monkeypatch):
    # 时间点按 10 秒刷出周期构造；默认值由 core 的刷出间隔测试锁定。
    monkeypatch.setenv("RUM_AGG_BATCH_TIMEOUT", "10s")


def _settings() -> RumRuntimeSettings:
    return RumRuntimeSettings(
        collect_url="https://telemetry.example.test/rum/v1/collect",
        replay_url="https://telemetry.example.test/rum/v1/replay",
        sdk_cdn_url="https://cdn.example.test/rum/bklite-rum-sdk.js",
        nats_url="",
        nats_timeout_seconds=5,
        tenant_id="core",
        victoria_logs_url="http://logs.example.test",
        victoria_traces_url="",
        victoria_account_id=0,
        victoria_project_id=0,
        victoria_timeout_seconds=15,
    )


class _Client:
    def __init__(self, responder, *, available=True, error=None):
        self.available = available
        self.responder = responder
        self.error = error
        self.instant = []
        self.ranges = []

    def query_instant(self, expression, *, at):
        self.instant.append((expression, at))
        if self.error is not None:
            raise self.error
        return self.responder(expression, kind="instant")

    def query_range(self, expression, *, start, end, step_seconds):
        self.ranges.append((expression, start, end, step_seconds))
        if self.error is not None:
            raise self.error
        return self.responder(expression, kind="range")


class _Logs:
    def __init__(self):
        self.queries = []

    def query_logs(self, query, start, end, limit=0):
        self.queries.append(query)
        if "geo.country.iso_code" in query:
            return [{"geo.country.iso_code": "CN", "views": "3", "sessions": "2"}]
        if "quantile(0.75, `rum.measurement.lcp`)" in query:
            return [
                {
                    "rum.application": "storefront",
                    "sessions": "4",
                    "views": "9",
                    "errors": "8",
                    "errored_sessions": "1",
                    "lcp_p75": "999",
                    "inp_p75": "888",
                }
            ]
        if "rum.view.name" in query and "quantile" in query:
            return [
                {
                    "rum.view.name": "/cart",
                    "views": "9",
                    "sessions": "4",
                    "lcp_p75": "999",
                    "inp_p75": "888",
                    "cls_p75": "0.9",
                    "loading_p75": "80",
                    "lcp_good": "1",
                    "lcp_poor": "1",
                    "lcp_needs": "0",
                    "mobile": "1",
                }
            ]
        return []


def _catalog_response(expression, *, kind):
    if "shard=" in expression or "by (shard)" in expression or "rum_traffic_class" in expression:
        raise AssertionError(expression)
    if kind == "range":
        return [{"metric": {"rum_application": "storefront"}, "values": [[POINT, "15"], [POINT + 900, None]]}]
    if expression.startswith("histogram_quantile") and "lcp" in expression:
        return [
            {"metric": {"rum_application": "storefront"}, "value": [1, "2400"]},
            {"metric": {"rum_application": "billing"}, "value": [1, "10"]},
        ]
    if expression.startswith("histogram_quantile") and "inp" in expression:
        return [{"metric": {"rum_application": "storefront"}, "value": [1, "NaN"]}]
    if "rum_js_errors_total" in expression:
        return [{"metric": {"rum_application": "storefront"}, "value": [1, "6"]}]
    if "rum_views_total" in expression:
        return [
            {"metric": {"rum_application": "storefront"}, "value": [1, "120"]},
            {"metric": {"rum_application": "billing"}, "value": [1, "5"]},
        ]
    raise AssertionError(expression)


def _route_response(expression, *, kind):
    del kind
    if "shard=" in expression or "by (shard)" in expression:
        raise AssertionError(expression)
    if "histogram_quantile" in expression and "cls" in expression:
        return [
            {"metric": {"rum_aggregate_route": "/cart"}, "value": [1, "0.05"]},
            {"metric": {"rum_aggregate_route": "其他"}, "value": [1, "NaN"]},
        ]
    if "histogram_quantile" in expression and "lcp" in expression:
        return [{"metric": {"rum_aggregate_route": "/cart"}, "value": [1, "1800"]}]
    if "histogram_quantile" in expression and "inp" in expression:
        return [
            {"metric": {"rum_aggregate_route": "/cart"}, "value": [1, "90"]},
            {"metric": {"rum_aggregate_route": "其他"}, "value": [1, "40"]},
        ]
    if "rum_js_errors_total" in expression:
        return [{"metric": {"rum_aggregate_route": "/cart"}, "value": [1, "2"]}]
    if "rum_views_total" in expression:
        return [
            {"metric": {"rum_aggregate_route": "/cart"}, "value": [1, "40"]},
            {"metric": {"rum_aggregate_route": "其他"}, "value": [1, "7"]},
        ]
    raise AssertionError(expression)


def _assert_safe_failure(record, error):
    assert record.levelno == logging.WARNING
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[2] is error.__traceback__
    assert str(error) == "secret-prom-body"
    frames = traceback.extract_tb(record.exc_info[2])
    assert any(frame.name == "query_instant" for frame in frames)
    formatted = logging.Formatter().format(record)
    assert formatted.count("Traceback (most recent call last)") == 1
    assert "secret-prom-body" not in record.getMessage()
    assert "secret-prom-body" not in formatted
    return formatted


def _reader(client, *, origin=START):
    return AggregateRumReader(client, origin_at=lambda: origin, clock=lambda: END)


def _catalog_rows():
    return [
        {
            "application": "storefront",
            "sessions": 4,
            "views": 9,
            "errors": 8,
            "lcpP75": 999,
            "inpP75": 888,
            "errorRate": 0.25,
        },
        {
            "application": "checkout",
            "sessions": 1,
            "views": 3,
            "errors": 1,
            "lcpP75": 100,
            "inpP75": 20,
            "errorRate": 0,
        },
    ]


def _view_page():
    return {
        "mode": "route",
        "summary": {"lcpP75": 999.0, "inpP75": 888.0, "clsP75": 0.9},
        "releases": [],
        "rows": [
            {
                "key": "/cart",
                "route": "/cart",
                "release": "",
                "views": 9,
                "sessions": 4,
                "lcpP75": 999.0,
                "inpP75": 888.0,
                "clsP75": 0.9,
                "loadingP75": 80.0,
                "impact": 19,
                "dist": {"good": 1, "needsImprove": 0, "poor": 1, "missing": 0},
                "mom": {"hasDelta": False, "spark": [1]},
                "deviceMix": {"mobile": 1, "desktop": 1},
            }
        ],
        "truncated": False,
    }


def test_catalog_end_follows_the_gateway_batch_timeout(monkeypatch):
    monkeypatch.setenv("RUM_AGG_BATCH_TIMEOUT", "1m")
    client = _Client(_catalog_response)

    _reader(client).overlay_catalog(_catalog_rows(), {}, tenant_id="core", apps=["storefront"], start=START, end=END)

    assert {at for _expression, at in client.instant} == {datetime(2026, 11, 10, 0, 15, tzinfo=UTC)}


def test_catalog_maps_views_errors_and_millisecond_percentiles_without_traffic_or_shard():
    client = _Client(_catalog_response)
    rows = _catalog_rows()
    sparks = {"storefront": [0.0] * 12, "checkout": [0.0] * 12}

    _reader(client).overlay_catalog(rows, sparks, tenant_id="core", apps=["storefront", "checkout"], start=START, end=END)

    storefront = rows[0]
    # 120 次浏览、6 次错误来自聚合；会话和错误率仍是调用方已经读到的日志数字。
    assert storefront["views"] == 120
    assert storefront["errors"] == 6
    assert storefront["lcpP75"] == 2400
    assert storefront["inpP75"] is None
    assert storefront["sessions"] == 4
    assert storefront["errorRate"] == 0.25
    # 00:02:00 是 [00:00:38, 00:02:00] 的结束点，落在第 1 个桶。整窗有浏览序列时，没有样本的桶记 0。
    assert sparks["storefront"][0] == 15
    assert sparks["storefront"].count(0) == 11
    checkout = rows[1]
    assert checkout["views"] is None
    assert checkout["errors"] is None
    assert checkout["lcpP75"] is None
    assert checkout["sessions"] == 1
    assert sparks["checkout"] == []
    assert VIEWS in [expression for expression, _at in client.instant]
    assert LCP in [expression for expression, _at in client.instant]
    assert {at for _expression, at in client.instant} == {ALIGNED}
    assert "billing" not in "".join(expression for expression, _at in client.instant)
    assert all("rum_traffic_class" not in expression and "shard" not in expression for expression, _at in client.instant)
    _range, start, end, step = client.ranges[0]
    # 990 秒 / 12 桶 = 82 秒。range 从窗口起点之后一个步长开始，避免把起点之前的 increase 算进来。
    assert step == 82
    assert start == START + timedelta(seconds=step)
    assert end == ALIGNED
    assert "[82s]" in _range


def test_catalog_selector_escapes_tenant_and_application_and_drops_other_apps():
    client = _Client(lambda expression, **kwargs: [])
    rows = [{"application": 'shop"\nout', "sessions": 2, "views": 9, "errors": 1, "lcpP75": 1, "inpP75": 1, "errorRate": 0}]

    _reader(client).overlay_catalog(rows, {}, tenant_id='core"\nevil', apps=['shop"\nout', "a.b"], start=START, end=END)

    expression = client.instant[0][0]
    assert 'tenant_id="core\\"\\nevil"' in expression
    assert 'rum_application=~"shop\\"\\\\\\nout|a\\\\.b"' in expression
    assert "\n" not in expression
    assert 'tenant_id="evil"' not in expression
    assert rows[0]["views"] is None
    assert rows[0]["sessions"] == 2


def test_zero_increase_stays_zero_and_a_missing_error_series_is_zero_errors():
    def respond(expression, *, kind):
        del kind
        if "rum_views_total" in expression and "histogram" not in expression:
            return [{"metric": {"rum_application": "storefront"}, "value": [1, "0"]}]
        return []

    client = _Client(respond)
    rows = [{"application": "storefront", "sessions": 4, "views": 9, "errors": 8, "lcpP75": 999, "inpP75": 888, "errorRate": 0.25}]
    sparks = {"storefront": [1]}

    _reader(client).overlay_catalog(rows, sparks, tenant_id="core", apps=["storefront"], start=START, end=END)

    assert rows[0]["views"] == 0
    assert rows[0]["errors"] == 0
    assert rows[0]["lcpP75"] is None
    assert rows[0]["sessions"] == 4
    assert sparks["storefront"] == [0] * 12


def test_view_trend_keeps_gaps_before_the_origin_and_does_not_zero_percentile_gaps():
    # 12 桶覆盖 990 秒，步长 82 秒。起点落在第 2 桶开端之后，第 1 桶仍早于起点。
    # 样本时刻是区间结束点，所以 +164 覆盖 [+82, +164]，放进第 2 个桶。
    origin = START + timedelta(seconds=90)
    points = [(START.timestamp() + 164, 15.0)]

    counted = _fill_spark(points, START, END, 12, origin=origin, zero_gaps=True)
    percentile = _fill_spark(points, START, END, 12, origin=origin, zero_gaps=False)

    assert counted[0] is None
    assert counted[1] == 15
    assert counted[2] == 0
    assert percentile[0] is None
    assert percentile[1] == 15
    assert percentile[2] is None
    assert _fill_spark([], START, END, 12, origin=START, zero_gaps=False) == [None] * 12


def test_view_trend_does_not_double_count_the_opening_bucket():
    # 不足 2 小时仍是 12 桶。对齐后窗口更短，旧步长 595 比桶宽 597 小，
    # 从起点开始的两个点会同时落进第 1 个桶。
    start = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 11, 10, 1, 59, 30, tzinfo=UTC)
    step = 597
    narrow = 595
    bucket_values = [1500 + index for index in range(11)]

    def respond(expression, *, kind):
        if kind == "range":
            points = [[start.timestamp(), "1552"], [start.timestamp() + narrow, "1500"]]
            points.extend([start.timestamp() + (index + 1) * step, str(value)] for index, value in enumerate(bucket_values))
            return [{"metric": {"rum_application": "storefront"}, "values": points}]
        if "rum_views_total" in expression and "histogram" not in expression:
            return [{"metric": {"rum_application": "storefront"}, "value": [1, str(sum(bucket_values))]}]
        return []

    client = _Client(respond)
    rows = [{"application": "storefront", "sessions": 4, "views": 9, "errors": 1, "lcpP75": 1, "inpP75": 1, "errorRate": 0}]
    sparks = {"storefront": []}
    reader = AggregateRumReader(client, origin_at=lambda: start, clock=lambda: end)

    reader.overlay_catalog(rows, sparks, tenant_id="core", apps=["storefront"], start=start, end=end)

    spark = sparks["storefront"]
    assert spark[:11] == bucket_values
    assert spark[11] == 0
    assert spark[0] == 1500
    assert sum(spark) == sum(bucket_values)
    assert rows[0]["views"] == sum(bucket_values)
    _range, range_start, range_end, queried_step = client.ranges[0]
    assert queried_step == step
    assert range_start == start + timedelta(seconds=step)
    assert range_end == datetime(2026, 11, 10, 1, 58, 50, tzinfo=UTC)
    assert f"[{step}s]" in _range


def test_route_list_uses_visitor_traffic_and_keeps_the_other_route():
    client = _Client(_route_response)
    page = _reader(client).overlay_views(
        _view_page(),
        tenant_id="core",
        opts={"from": START, "to": END, "applications": ["storefront"], "mode": "route"},
    )

    by_route = {row["route"]: row for row in page["rows"]}
    cart = by_route["/cart"]
    other = by_route["其他"]
    assert cart["views"] == 40
    assert cart["errors"] == 2
    assert cart["lcpP75"] == 1800
    assert cart["inpP75"] == 90
    assert cart["clsP75"] == 0.05
    assert cart["sessions"] == 4
    assert cart["loadingP75"] == 80
    assert cart["dist"]["poor"] == 1
    assert cart["deviceMix"] == {"mobile": 1, "desktop": 1}
    assert other["views"] == 7
    assert other["errors"] == 0
    assert other["lcpP75"] is None
    assert other["inpP75"] == 40
    assert other["clsP75"] is None
    assert other["sessions"] is None
    assert page["summary"]["lcpP75"] == 1800
    assert page["summary"]["inpP75"] == 65
    assert page["summary"]["clsP75"] == 0.05
    assert ROUTE_VIEWS in [expression for expression, _at in client.instant]
    assert ROUTE_CLS in [expression for expression, _at in client.instant]


@pytest.mark.parametrize(
    ("traffic", "fragment", "absent"),
    [
        ("all", None, "rum_traffic_class"),
        ("automated", 'rum_traffic_class=~"bot|synthetic|crawler"', 'rum_traffic_class!~"'),
        ("human", 'rum_traffic_class="human"', "bot|synthetic"),
        ('bo\nt"', 'rum_traffic_class="bo\\nt\\""', "\n"),
    ],
)
def test_route_traffic_matches_the_existing_page_list_parameter(traffic, fragment, absent):
    client = _Client(lambda expression, **kwargs: [])

    _reader(client).overlay_views(
        _view_page(),
        tenant_id="core",
        opts={"from": START, "to": END, "applications": ["storefront"], "mode": "route", "traffic": traffic},
    )

    expression = client.instant[0][0]
    if fragment:
        assert fragment in expression
    assert absent not in expression


@pytest.mark.parametrize(
    ("opts", "origin"),
    [
        ({"from": START, "to": END, "applications": ["storefront"], "mode": "release"}, START),
        ({"from": START, "to": END, "applications": ["storefront"], "mode": "route", "release": "2026.11"}, START),
        ({"from": START, "to": END, "applications": ["storefront"], "mode": "route"}, None),
        ({"from": START, "to": END, "applications": ["storefront"], "mode": "route"}, START + timedelta(seconds=1)),
    ],
)
def test_release_mode_missing_origin_and_early_windows_stay_on_logs(opts, origin):
    client = _Client(_route_response)
    page = _reader(client, origin=origin).overlay_views(_view_page(), tenant_id="core", opts=opts)

    assert page["rows"][0]["views"] == 9
    assert page["rows"][0]["lcpP75"] == 999
    assert client.instant == []
    assert client.ranges == []


def test_unconfigured_aggregate_keeps_the_log_numbers():
    client = _Client(_catalog_response, available=False)
    rows = _catalog_rows()

    _reader(client).overlay_catalog(rows, {"storefront": [1], "checkout": [1]}, tenant_id="core", apps=["storefront"], start=START, end=END)

    assert rows[0]["views"] == 9
    assert client.instant == []


def test_aggregate_errors_degrade_numbers_without_falling_back_or_logging_the_body(caplog):
    client = _Client(_catalog_response, error=AggregateMetricsUnavailable("secret-prom-body"))
    rows = _catalog_rows()
    sparks = {"storefront": [9], "checkout": [3]}

    with caplog.at_level(logging.WARNING, logger="rum"):
        _reader(client).overlay_catalog(rows, sparks, tenant_id="core", apps=["storefront", "checkout"], start=START, end=END)

    assert rows[0]["views"] is None
    assert rows[0]["errors"] is None
    assert rows[0]["lcpP75"] is None
    assert rows[0]["sessions"] == 4
    assert rows[0]["errorRate"] == 0.25
    assert sparks["storefront"] == []
    assert client.instant
    record = next(item for item in caplog.records if item.name == "rum")
    assert record.args == ("core", "catalog", "AggregateMetricsUnavailable")
    assert record.getMessage() == ("event=rum_aggregate_read_failed tenant_id=core failed_stage=catalog error_type=AggregateMetricsUnavailable")
    _assert_safe_failure(record, client.error)


def test_view_aggregate_errors_keep_sessions_and_clear_only_aggregate_fields(caplog):
    client = _Client(_route_response, error=AggregateMetricsUnavailable("secret-prom-body"))

    with caplog.at_level(logging.WARNING, logger="rum"):
        page = _reader(client).overlay_views(
            _view_page(),
            tenant_id="core",
            opts={"from": START, "to": END, "applications": ["storefront"], "mode": "route", "traffic": "visitors"},
        )

    row = page["rows"][0]
    assert row["views"] is None
    assert row["errors"] is None
    assert row["lcpP75"] is None
    assert row["clsP75"] is None
    assert row["sessions"] == 4
    assert row["loadingP75"] == 80
    assert row["dist"]["poor"] == 1
    assert page["summary"] == {"lcpP75": None, "inpP75": None, "clsP75": None}
    record = next(item for item in caplog.records if item.name == "rum")
    assert record.args == ("core", "views", "AggregateMetricsUnavailable")
    _assert_safe_failure(record, client.error)
    assert "secret-prom-body" not in caplog.text


def test_analytics_pages_replace_aggregate_numbers_and_keep_log_fields():
    logs = _Logs()
    client = _Client(_catalog_response)
    route_client = _Client(_route_response)
    analytics = VictoriaAnalytics(logs, aggregate=_reader(client))

    rows, sparks = analytics.applications_page("core", START, END, ["storefront", "checkout"])

    assert rows[0]["application"] == "storefront"
    assert rows[0]["sessions"] == 4
    assert rows[0]["views"] == 120
    assert rows[0]["errors"] == 6
    assert rows[0]["errorRate"] == pytest.approx(0.25)
    assert rows[1]["views"] is None
    assert rows[1]["sessions"] == 0
    assert sparks["storefront"][0] == 15
    assert any("count_uniq(`rum.session.key`)" in query for query in logs.queries)
    overview = analytics.application_overview("core", "storefront", START, END)
    assert overview["kpi"]["views"] == 120
    assert overview["kpi"]["sessions"] == 4
    assert overview["countries"] == [{"country": "CN", "views": 3, "sessions": 2}]
    assert isinstance(overview["trend"], list)

    analytics.aggregate = _reader(route_client)
    page = analytics.list_views(
        "core",
        {"from": START, "to": END, "applications": ["storefront"], "mode": "route", "traffic": "visitors"},
    )
    cart = next(row for row in page["rows"] if row["route"] == "/cart")
    other = next(row for row in page["rows"] if row["route"] == "其他")
    assert cart["views"] == 40
    assert cart["sessions"] == 4
    assert cart["loadingP75"] == 80.0
    assert other["views"] == 7
    assert other["sessions"] is None

    release = _reader(_Client(_route_response))
    analytics.aggregate = release
    kept = analytics.list_views(
        "core",
        {"from": START, "to": END, "applications": ["storefront"], "mode": "release", "traffic": "visitors"},
    )
    assert kept["rows"][0]["views"] == 9
    assert release.client.instant == []


def test_configured_analytics_attaches_the_aggregate_reader(monkeypatch):
    sentinel = VictoriaAnalytics(client=object())
    monkeypatch.setattr("apps.rum.services.victoria_analytics.VictoriaAnalytics.open", lambda **kwargs: sentinel)
    monkeypatch.setattr("apps.rum.services.settings.load_rum_settings", lambda: _settings())

    built = _build_analytics()

    assert built is sentinel
    assert isinstance(built.aggregate, AggregateRumReader)


@pytest.mark.django_db
def test_catalog_api_keeps_missing_aggregate_numbers_null_and_sums_known_sessions():
    control = MemoryControl()
    ApplicationsService(control, _settings()).create_application("tester", {"application": "checkout", "origins": ["https://shop.example.test"]})

    class _Analytics:
        def available(self):
            return True

        def applications_page(self, tenant_id, start, end, enabled_apps):
            del tenant_id, start, end, enabled_apps
            return (
                [
                    {
                        "application": "checkout",
                        "sessions": 4,
                        "views": None,
                        "errors": None,
                        "lcpP75": None,
                        "inpP75": None,
                        "errorRate": 0.25,
                    }
                ],
                {"checkout": []},
            )

    page = ApplicationsService(control, _settings(), analytics=_Analytics()).analytics_catalog("tester", "1h")
    item = page["applications"][0]

    assert item["sessions"] == 4
    assert item["views"] is None
    assert item["errors"] is None
    assert item["lcpP75"] is None
    assert page["kpi"]["sessions"] == 4
    assert page["kpi"]["views"] is None
    assert page["kpi"]["errors"] is None
    assert page["kpi"]["worstLcp"] is None
