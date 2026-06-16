"""作业管理辅助视图测试（callback_test）"""

import json

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/v1/job_mgmt/callback_test/"


def test_callback_test_echoes_payload(client):
    payload = {"task_id": "t1", "status": "success", "total_count": 3}
    resp = client.post(URL, data=json.dumps(payload), content_type="application/json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] is True
    assert body["payload"]["task_id"] == "t1"


def test_callback_test_handles_invalid_json(client):
    resp = client.post(URL, data="not-json", content_type="application/json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] is True
    assert body["payload"] == {}
