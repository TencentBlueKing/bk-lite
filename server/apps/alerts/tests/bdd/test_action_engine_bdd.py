"""
告警处理动作引擎 BDD — 中文 Gherkin。

场景 1: 创建告警命中规则 → running 执行记录 → 回调翻转 success
场景 2: 相同幂等键重复手动触发 → 单条 manual 执行记录
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pytest_bdd import given, scenarios, then, when
from rest_framework.test import APIClient

from apps.alerts.models.action import ActionExecution, ActionRule
from apps.alerts.models.models import Alert
from apps.base.models import User

FEATURE = str(Path(__file__).parent / "action_engine.feature")
scenarios(FEATURE)

# 模块级标记，确保所有场景均在 django_db 事务中执行
pytestmark = pytest.mark.django_db

# ---------------------------------------------------------------------------
# 共用脚本元数据（匹配 job handler 期望的格式）
# ---------------------------------------------------------------------------
MOCK_SCRIPT = {
    "id": 42,
    "name": "重启nginx",
    "script_type": "shell",
    "content": "echo test",
    "params": [{"name": "service", "default": "nginx"}],
    "timeout": 300,
}

MOCK_NODE = {
    "node_id": "n1",
    "name": "host-01",
    "ip": "10.0.0.5",
    "os": "linux",
    "cloud_region_id": 1,
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def superuser_client(db):
    user, _ = User.objects.get_or_create(
        username="bdd_admin",
        defaults={"is_superuser": True, "domain": "domain.com"},
    )
    user.is_superuser = True
    user.save()
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ---------------------------------------------------------------------------
# 场景 1: 创建告警命中规则触发作业并回写成功
# ---------------------------------------------------------------------------


@given("存在一条启用的作业规则监听创建事件且匹配级别为1", target_fixture="s1_ctx")
def _given_rule_created(db):
    rule = ActionRule.objects.create(
        name="自动重启作业",
        is_active=True,
        team=[1],
        trigger_events=["created"],
        match_rules=[[{"key": "level", "operator": "eq", "value": "1"}]],
        action_type="job",
        action_config={
            "script_id": 42,
            "target_binding": {
                "source": "node_mgmt",
                "match_by": "ip",
                "host_field": "labels.ip",
            },
            "param_bindings": [],
        },
    )
    return {"rule": rule, "task_id": 4821}


@given("节点管理中存在主机")
def _given_host_exists(s1_ctx):
    # node 在 execute 阶段通过 mock 返回，不需要真实 DB 记录
    s1_ctx["mock_node"] = MOCK_NODE


@when("一条级别为1的告警被创建并评估")
def _when_alert_created_and_evaluated(s1_ctx):
    alert = Alert.objects.create(
        alert_id="BDD-EVAL-1",
        fingerprint="fp-bdd-1",
        title="磁盘告警",
        content="磁盘使用率超过90%",
        level="1",
        status="unassigned",
        labels={"ip": "10.0.0.5"},
        team=[1],
    )
    s1_ctx["alert"] = alert

    with patch("apps.alerts.action.handlers.job.resolve_node_target", return_value=MOCK_NODE), \
         patch("apps.alerts.action.handlers.job.JobMgmt") as mock_job_cls:
        mock_job = mock_job_cls.return_value
        mock_job.get_script.return_value = MOCK_SCRIPT
        mock_job.job_script_execute.return_value = {
            "result": True,
            "data": {"task_id": s1_ctx["task_id"]},
        }
        from apps.alerts.action.engine import ActionEngine
        ActionEngine().evaluate(alert, "created")


@then("应生成一条running的执行记录")
def _then_execution_running(s1_ctx):
    alert = s1_ctx["alert"]
    execs = ActionExecution.objects.filter(alert=alert, trigger_type="auto")
    assert execs.exists(), (
        f"期望存在 alert={alert.alert_id} 的 auto 执行记录，"
        f"但实际 ActionExecution 数量为 {ActionExecution.objects.count()}"
    )
    ex = execs.first()
    assert ex.status == "running", f"期望 status=running，实际 status={ex.status}"
    assert ex.job_task_id == s1_ctx["task_id"], (
        f"期望 job_task_id={s1_ctx['task_id']}，实际={ex.job_task_id}"
    )
    s1_ctx["execution"] = ex


@when("job_mgmt回调该作业为成功")
def _when_callback_success(s1_ctx, api_client):
    body = {
        "task_id": s1_ctx["task_id"],
        "status": "success",
        "total_count": 1,
        "success_count": 1,
        "failed_count": 0,
        "finished_at": "2026-06-23T10:00:00Z",
    }
    with patch("apps.alerts.views.action.verify_job_signature", return_value=True):
        resp = api_client.post(
            "/api/v1/alerts/api/action_callback/",
            data=json.dumps(body),
            content_type="application/json",
        )
    assert resp.status_code == 200, f"回调返回 {resp.status_code}: {resp.content}"


@then("执行记录状态变为成功")
def _then_execution_success(s1_ctx):
    ex = s1_ctx["execution"]
    ex.refresh_from_db()
    assert ex.status == "success", f"期望 status=success，实际 status={ex.status}"
    assert ex.result.get("success_count") == 1, f"期望 success_count=1，实际={ex.result}"


# ---------------------------------------------------------------------------
# 场景 2: 手动重跑动作不受幂等限制
# ---------------------------------------------------------------------------


@given("存在一条作业规则但匹配条件不命中该告警", target_fixture="s2_ctx")
def _given_rule_no_match(db):
    alert = Alert.objects.create(
        alert_id="BDD-MANUAL-1",
        fingerprint="fp-bdd-manual",
        title="手动触发测试",
        content="c",
        level="0",  # level=0 不匹配 level=9
        status="unassigned",
        labels={"ip": "10.0.0.6"},
        team=[1],
    )
    rule = ActionRule.objects.create(
        name="手动作业规则",
        is_active=True,
        team=[1],
        trigger_events=["created"],
        match_rules=[[{"key": "level", "operator": "eq", "value": "9"}]],  # 不命中
        action_type="job",
        action_config={"script_id": 42},
    )
    return {"alert": alert, "rule": rule}


@when("使用同一幂等键对该告警手动触发该规则两次")
def _when_manual_trigger_twice(s2_ctx, superuser_client):
    alert = s2_ctx["alert"]
    rule = s2_ctx["rule"]
    superuser_client.cookies["current_team"] = "1"
    with patch("apps.alerts.views.action.get_handler") as mock_get:
        mock_get.return_value.execute.return_value = None
        for _ in range(2):
            resp = superuser_client.post(
                "/api/v1/alerts/api/action_execution/manual_trigger/",
                data={"alert_id": alert.alert_id, "rule_id": rule.id},
                format="json",
                HTTP_IDEMPOTENCY_KEY="bdd-manual-1",
            )
            assert resp.status_code in (200, 201), (
                f"手动触发失败: status={resp.status_code}, body={resp.content}"
            )


@then("应只生成一条手动执行记录")
def _then_two_manual_executions(s2_ctx):
    alert = s2_ctx["alert"]
    manual_execs = ActionExecution.objects.filter(alert=alert, trigger_type="manual")
    count = manual_execs.count()
    assert count == 1, f"期望1条手动执行记录，实际有 {count} 条"
    assert manual_execs.get().idempotency_key
