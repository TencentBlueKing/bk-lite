"""告警事件屏蔽 BDD（中文 Gherkin）。

对照 spec/prd/告警中心·屏蔽：
- match_type all / filter 双路径；
- 过期一次性时间窗的失效；
- 空事件列表 / 无活跃屏蔽的拒绝路径；
- ShieldNotFoundError 边界。

2 happy + 4 corner。
"""

import json
from pathlib import Path

import pytest
from django.utils import timezone
from pytest_bdd import given, parsers, scenarios, then, when

from apps.alerts.common.shield import EventShieldOperator, execute_shield_check_for_events
from apps.alerts.constants.constants import EventStatus
from apps.alerts.error import ShieldNotFoundError
from apps.alerts.models.alert_operator import AlertShield
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event

FEATURE = str(Path(__file__).parent / "shield.feature")
scenarios(FEATURE)


@pytest.fixture
def ctx():
    return {"result": None, "error": None, "source": None}


@pytest.fixture
def _shield_db(db):
    return db


# ---------------------------------------------------------------------------
# 假设
# ---------------------------------------------------------------------------

@given(parsers.parse('存在告警源 "{name}" source_id="{sid}"'))
def _seed_source(_shield_db, ctx, name, sid):
    ctx["source"] = AlertSource.objects.create(name=name, source_id=sid, source_type="restful", secret="x")


@given(parsers.parse('已存在事件 "{eid}" title="{title}"'))
def _seed_event(_shield_db, ctx, eid, title):
    Event.objects.create(
        source=ctx["source"], raw_data={}, title=title, level="0",
        start_time=timezone.now(), event_id=eid, status=EventStatus.RECEIVED,
    )


@given(parsers.parse('已存在屏蔽策略 name="{name}" match_type="{match_type}"'))
def _seed_shield_all(_shield_db, name, match_type):
    AlertShield.objects.create(name=name, match_type=match_type, match_rules=[], suppression_time={})


@given(parsers.re(
    r'已存在 filter 屏蔽策略 name="(?P<name>[^"]+)" match_rules=(?P<rules>\[.*\])'
))
def _seed_shield_filter(_shield_db, name, rules):
    AlertShield.objects.create(
        name=name, match_type="filter", match_rules=json.loads(rules), suppression_time={}
    )


@given(parsers.parse('已存在过期一次性屏蔽 name="{name}"'))
def _seed_shield_expired(_shield_db, name):
    AlertShield.objects.create(
        name=name, match_type="all", match_rules=[],
        suppression_time={"type": "one", "start_time": "2020-01-01 00:00:00", "end_time": "2020-01-02 00:00:00"},
    )


# ---------------------------------------------------------------------------
# 当
# ---------------------------------------------------------------------------

@when(parsers.parse("我对事件 {ids} 执行屏蔽检查"))
def _execute_shield(ctx, ids):
    ctx["result"] = execute_shield_check_for_events(json.loads(ids))


@when(parsers.parse("我尝试构造 EventShieldOperator({ids})"))
def _build_op(ctx, ids):
    try:
        EventShieldOperator(json.loads(ids))
    except ShieldNotFoundError as exc:
        ctx["error"] = exc


# ---------------------------------------------------------------------------
# 那么
# ---------------------------------------------------------------------------

@then(parsers.parse("屏蔽状态事件数量应当为 {n:d}"))
def _shield_count(_shield_db, n):
    assert Event.objects.filter(status=EventStatus.SHIELD).count() == n


@then(parsers.parse('事件 "{eid}" 应当处于屏蔽状态'))
def _event_shielded(eid):
    assert Event.objects.get(event_id=eid).status == EventStatus.SHIELD


@then(parsers.parse('事件 "{eid}" 应当处于已接收状态'))
def _event_received(eid):
    assert Event.objects.get(event_id=eid).status == EventStatus.RECEIVED


@then(parsers.parse("屏蔽数应当为 {n:d}"))
def _shielded(ctx, n):
    assert ctx["result"]["shielded_events"] == n


@then(parsers.parse("未屏蔽数应当为 {n:d}"))
def _unshielded(ctx, n):
    assert ctx["result"]["unshielded_events"] == n


@then(parsers.parse("总事件数应当为 {n:d}"))
def _total(ctx, n):
    assert ctx["result"]["total_events"] == n


@then("应当抛出屏蔽不存在异常")
def _shield_not_found(ctx):
    assert isinstance(ctx["error"], ShieldNotFoundError), ctx["error"]
