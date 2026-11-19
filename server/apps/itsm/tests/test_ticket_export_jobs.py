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


def test_export_has_grouped_system_columns_and_rich_form_fields(export_sample):
    from apps.itsm.models import Service, TicketTag, TicketTask
    from apps.itsm.services.ticket.export_jobs import generate, submit
    from apps.itsm.views.ticket_export import download_export, export_fields

    ticket, _ = export_sample
    ticket.service = Service.objects.create(name="账号申请", workflow=ticket.workflow, domain=ticket.domain)
    TicketTask.objects.create(ticket=ticket, node_id="handle", node_name="服务处理", assignee="handler")
    ticket.tags.add(TicketTag.objects.create(name="紧急", domain=ticket.domain))
    version = ticket.workflow_version
    version.design["form_schema"]["fields"] += [
        {"key": "choices", "type": "multiselect", "label": "影响范围", "source": {"options": [{"label": "桌面端", "value": "web"}]}},
        {"key": "people", "type": "multiUser", "label": "联系人"},
        {"key": "uploads", "type": "attachment", "label": "申请材料"},
        {
            "key": "lines",
            "type": "table",
            "label": "申请明细",
            "children": [
                {"key": "product", "type": "input", "label": "产品"},
                {"key": "internal", "type": "input", "label": "内部备注", "state": "hidden"},
            ],
        },
    ]
    version.save(update_fields=["design"])
    ticket.form_data.update(
        {
            "choices": ["web", "other"],
            "people": ["owner", "handler"],
            "uploads": ["attachments/abcd1234/验收.pdf"],
            "lines": [{"product": "笔记本", "internal": "保密"}],
        }
    )
    ticket.save(update_fields=["form_data", "service"])
    params = {"workflow_id": str(ticket.workflow_id)}
    assert export_fields(request(payload=params, username="owner")).status_code == 403
    assert export_fields(request(payload=params, username="outsider", permissions=EXPORT)).status_code == 404
    catalog = data(export_fields(request(payload=params, username="owner", permissions=EXPORT)))
    assert {group["key"] for group in catalog["groups"]} >= {"basic", "flow", "time", "sla"}
    assert {field["key"] for field in catalog["fields"]} >= {"choices", "people", "uploads", "lines"}
    assert {"secret", "internal", "product"}.isdisjoint(field["key"] for field in catalog["fields"])
    req = request(username="owner", permissions=EXPORT)
    task = submit(
        req,
        {
            "ids": [ticket.pk],
            "columns": ["service", "assignees", "tags", "node", "created_at"],
            "form_workflow_id": str(ticket.workflow_id),
            "form_columns": ["choices", "people", "uploads", "lines"],
        },
    )
    generate(task.pk)
    response = download_export(req, task.pk)
    assert response.status_code == 200
    sheet = load_workbook(BytesIO(b"".join(response.streaming_content))).active
    rows = list(sheet.values)
    assert rows[0] == ("单号", "服务", "当前处理人", "标签", "当前节点", "创建时间", "影响范围", "联系人", "申请材料", "申请明细")
    assert rows[1][:5] == (ticket.sn, "账号申请", "handler", "紧急", "服务处理")
    assert rows[1][5].date() == timezone.localtime(ticket.created_at).date()
    assert rows[1][6:] == ("桌面端、other", "owner、handler", "验收.pdf", "产品：笔记本")
    version.design["form_schema"]["fields"][-1]["children"][0]["state"] = "hidden"
    version.save(update_fields=["design"])
    assert download_export(req, task.pk).status_code == 403


def test_all_system_columns_and_foreign_workflow_only_gets_system_values(export_sample):
    from apps.itsm.models import Ticket, TicketLog, TicketSurvey, Workflow
    from apps.itsm.services.ticket.export_fields import COLUMNS
    from apps.itsm.services.ticket.export_jobs import generate, submit
    from apps.itsm.views.ticket_export import download_export

    ticket, _ = export_sample
    TicketLog.objects.create(ticket=ticket, action="submit", operator="owner")
    TicketSurvey.objects.create(ticket=ticket, score=5)
    other = Ticket.objects.create(
        sn="OTHER-FLOW",
        title="其他流程",
        workflow=Workflow.objects.create(name="其他流程", key="rich-other"),
        creator="owner",
        form_data={"amount": 999},
    )
    req = request(username="owner", permissions=EXPORT)
    task = submit(
        req,
        {
            "ids": [ticket.pk, other.pk],
            "columns": list(COLUMNS),
            "form_workflow_id": str(ticket.workflow_id),
            "form_columns": ["amount"],
        },
    )
    generate(task.pk)
    response = download_export(req, task.pk)
    assert response.status_code == 200
    sheet = load_workbook(BytesIO(b"".join(response.streaming_content))).active
    header, *rows = sheet.values
    records = {row[0]: dict(zip(header, row)) for row in rows}
    assert records[other.sn]["申请金额"] is None
    assert records[ticket.sn]["申请金额"] == 200 and records[ticket.sn]["满意度"] == 5
    assert records[ticket.sn]["流程版本"] == ticket.workflow_version.version_no
    assert records[ticket.sn]["首次提交时间"] is not None
