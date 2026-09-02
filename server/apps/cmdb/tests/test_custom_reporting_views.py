"""自定义上报 ViewSet：列表/写操作委托、缺 credential_id 400、Bearer 与裸 token 解析。"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.cmdb.views.custom_reporting import CustomReportingIngestViewSet, CustomReportingTaskViewSet

pytestmark = pytest.mark.unit
VIEWS = "apps.cmdb.views.custom_reporting"


def _body(resp):
    return json.loads(resp.content.decode("utf-8"))


def _qp(**kwargs):
    return SimpleNamespace(dict=lambda: dict(kwargs))


def test_task_viewset_delegates_list_stats_crud_and_reviews():
    ext = MagicMock()
    ext.list_tasks.return_value = {"count": 0, "results": []}
    ext.get_stats.return_value = {"tasks": 2}
    ext.create_task.return_value = {"id": 11}
    ext.get_task.return_value = {"id": 11, "name": "t"}
    ext.update_task.return_value = {"id": 11, "name": "t2"}
    ext.get_field_registrations.return_value = [{"field": "cpu"}]
    ext.get_batch_activity.return_value = {"batches": []}
    ext.get_onboarding_document.return_value = {"md": "# doc"}
    ext.issue_credential.return_value = {"token": "cred"}
    ext.rotate_credential.return_value = {"token": "rotated"}
    ext.revoke_credential.return_value = {"ok": True}
    ext.approve_cleanup_review.return_value = {"approved": True}
    ext.reject_cleanup_review.return_value = {"rejected": True}

    vs = CustomReportingTaskViewSet()
    req = SimpleNamespace(query_params=_qp(q="x"), data={"name": "t", "team": [1], "config": {"a": 1}}, user=None)
    with patch(f"{VIEWS}.get_custom_reporting_extension", return_value=ext):
        assert _body(vs.list(req))["data"] == {"count": 0, "results": []}
        ext.list_tasks.assert_called_once_with(req, {"q": "x"})
        assert _body(vs.stats(req))["data"] == {"tasks": 2}
        created = _body(vs.create(req))["data"]
        assert created == {"id": 11}
        ext.create_task.assert_called_once()
        assert ext.create_task.call_args.args[1] == {"name": "t", "team": [1], "config": {"a": 1}, "is_enabled": True}
        assert _body(vs.retrieve(req, pk=11))["data"]["name"] == "t"
        upd = SimpleNamespace(data={"name": "t2"})
        assert _body(vs.update(upd, pk=11))["data"]["name"] == "t2"
        assert _body(vs.destroy(req, pk=11))["data"] == {}
        ext.delete_task.assert_called_once_with(req, 11)
        assert _body(vs.field_registrations(req, pk=11))["data"] == [{"field": "cpu"}]
        assert _body(vs.batch_activity(req, pk=11))["data"] == {"batches": []}
        assert _body(vs.onboarding_document(req, pk=11))["data"] == {"md": "# doc"}
        cred_req = SimpleNamespace(data={"name": "bot"})
        assert _body(vs.issue_credential(cred_req, pk=11))["data"]["token"] == "cred"
        rot_req = SimpleNamespace(data={"credential_id": "c1"})
        assert _body(vs.rotate_credential(rot_req, pk=11))["data"]["token"] == "rotated"
        ext.rotate_credential.assert_called_once_with(rot_req, 11, "c1")
        rev_req = SimpleNamespace(data={"credential_id": "c1"})
        assert _body(vs.revoke_credential(rev_req, pk=11))["data"] == {"ok": True}
        assert _body(vs.approve_review(req, pk=11, review_id="r1"))["data"] == {"approved": True}
        assert _body(vs.reject_review(req, pk=11, review_id="r1"))["data"] == {"rejected": True}


def test_rotate_and_revoke_require_credential_id():
    vs = CustomReportingTaskViewSet()
    req = SimpleNamespace(data={})
    rot = vs.rotate_credential(req, pk=1)
    assert rot.status_code == 400
    assert _body(rot) == {"data": {}, "result": False, "message": "credential_id is required"}
    rev = vs.revoke_credential(req, pk=1)
    assert rev.status_code == 400
    assert _body(rev)["message"] == "credential_id is required"


def test_ingest_strips_bearer_prefix_or_uses_raw_authorization():
    ext = MagicMock()
    ext.ingest.return_value = {"accepted": 1}
    vs = CustomReportingIngestViewSet()
    with patch(f"{VIEWS}.get_custom_reporting_extension", return_value=ext):
        bearer = SimpleNamespace(META={"HTTP_AUTHORIZATION": "Bearer secret-token"}, data={"rows": [1]})
        assert _body(vs.create(bearer))["data"] == {"accepted": 1}
        ext.ingest.assert_called_with(bearer, "secret-token", {"rows": [1]})

        raw = SimpleNamespace(META={"HTTP_AUTHORIZATION": "plain-token"}, data={"rows": []})
        vs.create(raw)
        ext.ingest.assert_called_with(raw, "plain-token", {"rows": []})

        empty = SimpleNamespace(META={}, data={})
        vs.create(empty)
        ext.ingest.assert_called_with(empty, None, {})
