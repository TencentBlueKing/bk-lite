"""工单异步导出、重试和下载权限。"""
import json
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from openpyxl import load_workbook

from apps.itsm.models import TicketExportTask, TicketFollower
from apps.itsm.tests import test_ticket_list_workbench as workbench
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.tests.test_ticket_list_workbench import data

pytestmark = pytest.mark.django_db
EXPORT = ["ticket-View", "ticket-Export"]


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    def live(task, **kwargs):
        return SimpleNamespace(user=task.username, domain=task.domain, is_superuser=False, permission={"itsm": EXPORT})

    from apps.itsm.services.ticket import export_jobs

    monkeypatch.setattr(export_jobs, "live_identity", live)


@pytest.fixture
def export_sample():
    return workbench.dynamic_tickets.__wrapped__(workbench.sample.__wrapped__())


def test_submit_generate_download_and_owner_isolation(export_sample, django_capture_on_commit_callbacks):
    from apps.itsm.services.ticket.export_jobs import generate
    from apps.itsm.views.ticket_export import download_export, export_tasks

    ticket, invisible = export_sample
    payload = {
        "filters": {"workflow_id": str(ticket.workflow_id), "form_filters": [{"key": "amount", "operator": "gte", "value": 150}]},
        "form_columns": ["amount"],
        "ids": [ticket.pk, invisible.pk],
    }
    assert export_tasks(request("post", payload, "owner")).status_code == 403
    with patch("apps.itsm.services.ticket.export_jobs.enqueue") as enqueue:
        with django_capture_on_commit_callbacks(execute=True):
            task = data(export_tasks(request("post", payload, "owner", EXPORT)))
        enqueue.assert_called_once_with(task["id"])
    assert task["status"] == "pending" and "content_base64" not in task
    assert download_export(request(username="owner", permissions=EXPORT), task["id"]).status_code == 409
    generate(task["id"])
    generate(task["id"])
    history = data(export_tasks(request(username="owner", permissions=EXPORT)))
    assert len(history["items"]) == 1
    result = history["items"][0]
    assert result["status"] == "done" and result["count"] == 1 and result["downloadable"]
    assert data(export_tasks(request(username="other", permissions=EXPORT)))["items"] == []
    assert data(export_tasks(request(username="owner", permissions=EXPORT, domain="other")))["items"] == []
    assert download_export(request(username="other", permissions=EXPORT), task["id"]).status_code == 404
    assert download_export(request(username="owner", permissions=EXPORT, domain="other"), task["id"]).status_code == 404
    assert download_export(request(username="owner"), task["id"]).status_code == 403
    response = download_export(request(username="owner", permissions=EXPORT), task["id"])
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    sheet = load_workbook(BytesIO(b"".join(response.streaming_content))).active
    assert list(sheet.values) == [("单号", "标题", "提单人", "状态", "申请金额"), (ticket.sn, "=1+1", "owner", "new", 200)]
    assert sheet["B2"].data_type == "s"


def test_download_rechecks_current_visibility_and_field_schema(export_sample):
    from apps.itsm.services.ticket.export_jobs import generate, submit
    from apps.itsm.views.ticket_export import download_export

    ticket, _ = export_sample
    link = TicketFollower.objects.create(ticket=ticket, username="viewer")
    req = request(username="viewer", permissions=EXPORT)
    task = submit(req, {"filters": {"workflow_id": str(ticket.workflow_id)}, "form_columns": ["amount"], "ids": [ticket.pk]})
    generate(task.pk)
    assert download_export(req, task.pk).status_code == 200
    link.delete()
    assert download_export(req, task.pk).status_code == 403
    link.pk = None
    link.save()
    version = ticket.workflow_version
    version.design["nodes"][1]["field_perm"]["amount"] = "hidden"
    version.save(update_fields=["design"])
    assert download_export(req, task.pk).status_code == 403


def test_worker_permission_loss_and_timeout_are_retryable(export_sample):
    from apps.itsm.services.ticket import export_jobs
    from apps.itsm.views.ticket_export import export_tasks, retry_export

    ticket, _ = export_sample
    req = request(username="owner", permissions=EXPORT)
    task = export_jobs.submit(req, {"ids": [ticket.pk]})
    with patch.object(export_jobs, "live_identity", side_effect=PermissionError("角色收回")):
        export_jobs.generate(task.pk)
    task.refresh_from_db()
    assert task.status == "failed" and task.error and not task.content_base64
    assert retry_export(request("post", {}, "other", EXPORT), task.pk).status_code == 404
    replacement = data(retry_export(request("post", {}, "owner", EXPORT), task.pk))
    assert replacement["id"] != task.pk
    current = TicketExportTask.objects.get(pk=replacement["id"])
    TicketExportTask.objects.filter(pk=current.pk).update(updated_at=timezone.now() - timedelta(hours=1))
    history = data(export_tasks(req))
    assert history["items"][0]["status"] == "failed"
    export_jobs.generate(current.pk)
    current.refresh_from_db()
    assert current.status == "failed" and not current.content_base64
    assert "角色收回" not in json.dumps(history, ensure_ascii=False)


def test_worker_exports_more_than_synchronous_limit_and_cleans_expired_file(export_sample):
    from apps.itsm.models import Ticket
    from apps.itsm.services.ticket import export_jobs
    from apps.itsm.views.ticket_export import download_export, export_tasks

    ticket, _ = export_sample
    Ticket.objects.bulk_create(
        [
            Ticket(
                sn=f"ASYNC-EXPORT-{index}",
                title="批量导出样本",
                workflow_id=ticket.workflow_id,
                workflow_version_id=ticket.workflow_version_id,
                creator="owner",
                domain=ticket.domain,
            )
            for index in range(501)
        ]
    )
    req = request(username="owner", permissions=EXPORT)
    task = export_jobs.submit(req, {"filters": {"q": "ASYNC-EXPORT"}})
    export_jobs.generate(task.pk)
    task.refresh_from_db()
    assert task.ticket_count == 501 and task.status == "done"
    TicketExportTask.objects.filter(pk=task.pk).update(finished_at=timezone.now() - timedelta(days=8))
    assert download_export(req, task.pk).status_code == 409
    assert not data(export_tasks(req))["items"][0]["downloadable"]
    task.refresh_from_db()
    assert not task.content_base64 and not task.result_manifest


def test_queue_failure_is_visible_and_concurrent_submissions_are_bounded(export_sample, django_capture_on_commit_callbacks):
    from kombu.exceptions import OperationalError

    from apps.itsm.services.ticket import export_jobs
    from apps.itsm.tasks import generate_ticket_export
    from apps.itsm.views.ticket_export import export_tasks

    ticket, _ = export_sample
    selection = {"ids": [ticket.pk]}
    req = request("post", selection, "owner", EXPORT)
    with patch.object(generate_ticket_export, "apply_async", side_effect=OperationalError("broker offline")):
        with django_capture_on_commit_callbacks(execute=True):
            first = data(export_tasks(req))
    assert TicketExportTask.objects.get(pk=first["id"]).error == "暂时无法入队，请稍后重试"
    for _ in range(3):
        assert export_jobs.submit(req, selection).status == "pending"
    assert export_tasks(req).status_code == 400
