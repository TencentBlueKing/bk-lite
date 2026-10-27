"""
ActionCallbackView 测试。

覆盖内容：
1. 正常回调 → 状态翻转 (mock 签名)
2. 签名无效 → 401/403 (mock 签名)
3. 重复回调幂等 (mock 签名)
4. 真实签名通过 → 200 + 状态翻转 (不 mock)
5. 签名错误/缺失 → 401/403 (不 mock)
"""

import json
import time
import pytest
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
import apps.cmdb.models  # node_mgmt 装入后会加载 monitor，monitor 再引用 CMDB
import apps.monitor.models  # job_mgmt 回调测试会装入 node_mgmt，其路由导入监控模型
from apps.alerts.models.action import ActionRule, ActionExecution
from apps.alerts.models.models import Alert
from apps.job_mgmt.utils.callback_signer import get_signed_headers, sign_callback


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _exec(task_id=4821, status="running"):
    alert = Alert.objects.create(
        alert_id="A1", fingerprint="f", title="t", content="c", level="1"
    )
    rule = ActionRule.objects.create(name="r", team=[1])
    return ActionExecution.objects.create(
        rule=rule,
        alert=alert,
        trigger_event="created",
        trigger_type="auto",
        idempotency_key="k",
        status=status,
        job_task_id=task_id,
    )


# ---------------------------------------------------------------------------
# 签名 mock 测试
# ---------------------------------------------------------------------------

@pytest.mark.django_db
@patch("apps.alerts.views.action.verify_job_signature", return_value=True)
def test_callback_success_flips_status(_sig, api_client):
    ex = _exec()
    body = {
        "task_id": 4821,
        "status": "success",
        "total_count": 1,
        "success_count": 1,
        "failed_count": 0,
        "finished_at": "2026-06-23T10:32:00Z",
    }
    resp = api_client.post(
        "/api/v1/alerts/api/action_callback/",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert resp.status_code == 200
    ex.refresh_from_db()
    assert ex.status == "success"
    assert ex.result["success_count"] == 1


@pytest.mark.django_db
@patch("apps.alerts.views.action.verify_job_signature", return_value=False)
def test_callback_bad_signature_rejected(_sig, api_client):
    _exec()
    resp = api_client.post(
        "/api/v1/alerts/api/action_callback/",
        data=json.dumps({"task_id": 4821}),
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
@patch("apps.alerts.views.action.verify_job_signature", return_value=True)
def test_callback_idempotent_on_repeat(_sig, api_client):
    ex = _exec()
    body = {
        "task_id": 4821,
        "status": "failed",
        "total_count": 1,
        "success_count": 0,
        "failed_count": 1,
    }
    for _ in range(2):
        api_client.post(
            "/api/v1/alerts/api/action_callback/",
            data=json.dumps(body),
            content_type="application/json",
        )
    ex.refresh_from_db()
    assert ex.status == "failed"


# ---------------------------------------------------------------------------
# 真实签名测试（不 mock verify_job_signature）
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_callback_real_signature_passes(api_client):
    """使用与 job_mgmt 完全相同的签名算法生成有效请求头，期望 200。"""
    ex = _exec(task_id=9999, status="running")
    body = {
        "task_id": 9999,
        "status": "success",
        "total_count": 2,
        "success_count": 2,
        "failed_count": 0,
        "finished_at": "2026-06-23T12:00:00Z",
    }
    payload = body  # 这就是 job_mgmt 签名时传入的 payload dict
    headers = get_signed_headers(payload)
    # Django 测试客户端使用 HTTP_ 前缀 + 大写 + 破折号→下划线
    resp = api_client.post(
        "/api/v1/alerts/api/action_callback/",
        data=json.dumps(body),
        content_type="application/json",
        HTTP_X_BK_LITE_TIMESTAMP=headers["X-BK-Lite-Timestamp"],
        HTTP_X_BK_LITE_SIGNATURE=headers["X-BK-Lite-Signature"],
        HTTP_X_BK_LITE_SOURCE=headers["X-BK-Lite-Source"],
    )
    assert resp.status_code == 200
    ex.refresh_from_db()
    assert ex.status == "success"
    assert ex.result["success_count"] == 2


@pytest.mark.django_db
def test_callback_missing_signature_rejected(api_client):
    """不带签名头的请求应该被拒绝。"""
    _exec(task_id=7777, status="running")
    body = {"task_id": 7777, "status": "success"}
    resp = api_client.post(
        "/api/v1/alerts/api/action_callback/",
        data=json.dumps(body),
        content_type="application/json",
        # 故意不传签名头
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_callback_tampered_signature_rejected(api_client):
    """正确时间戳但签名被篡改，应该被拒绝。"""
    _exec(task_id=8888, status="running")
    body = {"task_id": 8888, "status": "success"}
    ts = str(int(time.time()))
    resp = api_client.post(
        "/api/v1/alerts/api/action_callback/",
        data=json.dumps(body),
        content_type="application/json",
        HTTP_X_BK_LITE_TIMESTAMP=ts,
        HTTP_X_BK_LITE_SIGNATURE="deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        HTTP_X_BK_LITE_SOURCE="bk-lite-job-mgmt",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
@patch("apps.alerts.views.action.JobMgmt")
def test_callback_before_job_task_id_is_retryable(_job, api_client):
    """签名合法但 job_task_id 尚未写入时必须可重试，且不能改写尚未关联的执行记录。"""
    execution = _exec(task_id=None, status="pending")
    before_count = ActionExecution.objects.count()
    body = {
        "task_id": 4821,
        "status": "success",
        "total_count": 3,
        "success_count": 2,
        "failed_count": 1,
        "finished_at": "2026-06-23T10:32:00Z",
    }
    early, headers = _post_signed(api_client, body)
    assert early.status_code == 503
    assert early.data == {"result": False}
    _job.assert_not_called()
    assert ActionExecution.objects.count() == before_count
    execution.refresh_from_db()
    assert execution.status == "pending"
    assert execution.job_task_id is None
    assert execution.result == {}

    execution.job_task_id = 4821
    execution.save(update_fields=["job_task_id"])
    linked, _headers = _post_signed(api_client, body, headers)
    assert linked.status_code == 200
    assert linked.data["result"] is True
    execution.refresh_from_db()
    assert execution.status == "success"
    assert execution.result["total_count"] == 3
    assert execution.result["success_count"] == 2
    assert execution.result["failed_count"] == 1
    assert ActionExecution.objects.count() == before_count

    duplicate, _headers = _post_signed(api_client, body, headers)
    assert duplicate.status_code == 200
    execution.refresh_from_db()
    assert execution.status == "success"
    assert execution.result["success_count"] == 2


def _post_signed(api_client, body, headers=None):
    headers = headers or get_signed_headers(body)
    response = api_client.post(
        "/api/v1/alerts/api/action_callback/",
        data=json.dumps(body),
        content_type="application/json",
        HTTP_X_BK_LITE_TIMESTAMP=headers["X-BK-Lite-Timestamp"],
        HTTP_X_BK_LITE_SIGNATURE=headers["X-BK-Lite-Signature"],
        HTTP_X_BK_LITE_SOURCE=headers["X-BK-Lite-Source"],
    )
    return response, headers


@pytest.mark.django_db
def test_callback_without_task_id_does_not_match_null_job_task(api_client):
    """没有 task_id 时返回 400，禁止用 job_task_id IS NULL 命中尚未回写的记录。"""
    execution = _exec(task_id=None, status="pending")
    body = {
        "status": "success",
        "total_count": 1,
        "success_count": 1,
        "failed_count": 0,
        "finished_at": "2026-06-23T10:32:00Z",
    }
    with CaptureQueriesContext(connection) as captured:
        response, _headers = _post_signed(api_client, body)
    sql = "\n".join(query["sql"] for query in captured.captured_queries)
    assert response.status_code == 400
    assert response.data == {"result": False}
    assert 'job_task_id" IS NULL' not in sql
    execution.refresh_from_db()
    assert execution.status == "pending"
    assert execution.job_task_id is None
    assert execution.result == {}


@pytest.mark.django_db
def test_callback_without_task_id_and_signature_stays_forbidden(api_client):
    """签名校验仍在 task_id 校验之前，缺签名保持 403，且不改写空 job_task_id。"""
    execution = _exec(task_id=None, status="pending")
    response = api_client.post(
        "/api/v1/alerts/api/action_callback/",
        data=json.dumps({"status": "success"}),
        content_type="application/json",
    )
    assert response.status_code == 403
    execution.refresh_from_db()
    assert execution.status == "pending"
    assert execution.job_task_id is None
