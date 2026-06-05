"""告警聚合 BDD（中文 Gherkin）。

对照 spec/prd/告警中心·聚合·策略参数加载与时间规范：
- _load_params 默认值；
- _build_heartbeat_context；
- _parse_runtime_datetime / _normalize_to_project_timezone；
- get_events_for_strategy 时间窗取事件。

2 happy + 5 corner（共 7 场景）。
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.utils import timezone
from pytest_bdd import given, parsers, scenarios, then, when

from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
from apps.alerts.constants.constants import EventAction
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event

FEATURE = str(Path(__file__).parent / "aggregation.feature")
scenarios(FEATURE)


@pytest.fixture
def ctx():
    return {"strategy": None, "params": None, "event": None, "result": None, "context": None, "source": None}


@pytest.fixture
def _agg_db(db):
    return db


# ---------------------------------------------------------------------------
# 假设
# ---------------------------------------------------------------------------

@given(parsers.parse('存在告警源 "{name}" source_id="{sid}"'))
def _seed_source(_agg_db, ctx, name, sid):
    ctx["source"] = AlertSource.objects.create(name=name, source_id=sid, source_type="restful", secret="x")


@given(parsers.parse("一个策略 params={raw}"))
def _seed_strategy(ctx, raw):
    ctx["strategy"] = SimpleNamespace(params=json.loads(raw))


@given(parsers.parse('已存在事件 "{eid}" title="{title}"'))
def _seed_event_db(_agg_db, ctx, eid, title):
    Event.objects.create(
        source=ctx["source"], raw_data={}, title=title, level="0",
        start_time=timezone.now(), event_id=eid, action=EventAction.CREATED,
    )


@given(parsers.re(r'已存在 smart_denoise 策略 name="(?P<name>[^"]+)" params=(?P<raw>\{.*\})'))
def _seed_db_strategy(_agg_db, ctx, name, raw):
    ctx["strategy"] = AlarmStrategy.objects.create(
        name=name, strategy_type="smart_denoise", params=json.loads(raw)
    )


@given(parsers.parse('事件具备 service="{service}" item="{item}" level="{level}"'))
def _seed_event_obj(ctx, service, item, level):
    ctx["event"] = SimpleNamespace(
        service=service, location="loc", resource_name="rn", resource_id="rid",
        resource_type="rt", item=item, title="t", level=level,
    )


# ---------------------------------------------------------------------------
# 当
# ---------------------------------------------------------------------------

@when("我加载策略参数")
def _load_params(ctx):
    ctx["params"] = AggregationProcessor._load_params(ctx["strategy"])


@when("我对策略调用 get_events_for_strategy")
def _query_window(ctx):
    ctx["result"] = AggregationProcessor.get_events_for_strategy(ctx["strategy"], timezone.now())


@when(parsers.parse('我解析运行时时间 "{value}"'))
def _parse_time_str(ctx, value):
    ctx["result"] = AggregationProcessor._parse_runtime_datetime(value)


@when('我解析运行时时间 ""')
def _parse_time_empty(ctx):
    ctx["result"] = AggregationProcessor._parse_runtime_datetime("")


@when("我规范化时间 None")
def _normalize_none(ctx):
    ctx["result"] = AggregationProcessor._normalize_to_project_timezone(None)


@when("我构造 heartbeat 上下文")
def _build_hb(ctx):
    ctx["context"] = AggregationProcessor._build_heartbeat_context(ctx["event"])


# ---------------------------------------------------------------------------
# 那么
# ---------------------------------------------------------------------------

@then(parsers.parse('策略 check_mode 应当为 "{value}"'))
def _check_mode(ctx, value):
    assert ctx["params"]["check_mode"] == value


@then(parsers.parse("策略 grace_period 应当为 {value:d}"))
def _grace(ctx, value):
    assert ctx["params"]["grace_period"] == value


@then(parsers.parse("策略 auto_recovery 应当为 {flag}"))
def _auto_recovery(ctx, flag):
    assert ctx["params"]["auto_recovery"] is (flag.lower() == "true")


@then(parsers.parse('策略 cron_expr 应当为 "{value}"'))
def _cron(ctx, value):
    assert ctx["params"]["cron_expr"] == value


@then(parsers.parse('候选事件应当包含 "{eid}"'))
def _candidate_has(ctx, eid):
    assert ctx["result"].filter(event_id=eid).exists()


@then("解析结果应当为 None")
def _none_result(ctx):
    assert ctx["result"] is None


@then("解析结果应当带时区")
def _aware(ctx):
    assert timezone.is_aware(ctx["result"])


@then("规范化结果应当为 None")
def _normalize_none_ok(ctx):
    assert ctx["result"] is None


@then(parsers.parse('上下文 service 应当为 "{value}"'))
def _ctx_service(ctx, value):
    assert ctx["context"]["service"] == value


@then(parsers.parse('上下文 item 应当为 "{value}"'))
def _ctx_item(ctx, value):
    assert ctx["context"]["item"] == value


@then(parsers.parse('上下文 level 应当为 "{value}"'))
def _ctx_level(ctx, value):
    assert ctx["context"]["level"] == value
