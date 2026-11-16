"""显式启用的真实隔离 Runner / HTTP 待办闭环（使用测试数据库）。"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from apps.core.openapi.identity import CallerIdentity
from apps.itsm.models.integration import Integration, TodoDelivery
from apps.itsm.services.integrations import execute
from apps.itsm.services.todo_sync import deliver, sync_todos
from apps.itsm.tests.test_review_regressions import sample as sample_fixture

sample = sample_fixture

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(os.environ.get("ITSM_INTEGRATION_RUNTIME_TEST") != "1", reason="显式启用真实集成服务测试"),
]


def test_real_isolated_python_success_failure_and_timeout():
    item = Integration.objects.create(
        name="真实 Python",
        kind="python",
        config={"script": 'def transform(rows, params):\n    return [{"value": row["amount"] * params["rate"]} for row in rows]'},
        created_by="owner",
    )
    identity = CallerIdentity("owner", item.domain, "jwt")
    result = execute(item, {"rows": [{"amount": 100}], "params": {"rate": 2}}, identity)
    assert result["status"] == "done", result
    assert result["output"] == [{"value": 200}]
    item.config["script"] = "import os\ndef transform(rows, params):\n    return rows"
    assert execute(item, {}, identity)["status"] == "failed"
    item.config["script"] = "def transform(rows, params):\n    while True:\n        pass"
    result = execute(item, {}, identity)
    assert result["status"] == "failed", result
    assert "timeout" in result["code"]


def test_real_todo_create_transfer_close_and_retry(sample):
    from apps.system_mgmt.models.network_white_list import NetworkWhiteList
    from apps.system_mgmt.utils.network_whitelist_cache import invalidate_network_whitelist_cache

    received = []
    state = {"fail": False}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(503 if state["fail"] else 204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    NetworkWhiteList.objects.create(network="127.0.0.1/32", remark="仅测试数据库")
    invalidate_network_whitelist_cache()
    ticket, task = sample
    Integration.objects.create(name="本地待办接收器", kind="todo", config={"url": f"http://127.0.0.1:{server.server_port}/events"})
    try:
        sync_todos(ticket.id)
        row = TodoDelivery.objects.latest("id")
        state["fail"] = True
        deliver(row.id)
        row.refresh_from_db()
        assert row.status == "failed"
        state["fail"] = False
        deliver(row.id)
        row.refresh_from_db()
        assert row.status == "done"
        assert received[0]["event_id"] == received[1]["event_id"]
        task.assignee = "next"
        task.save()
        sync_todos(ticket.id)
        deliver(TodoDelivery.objects.latest("id").id)
        assert received[-1]["event"] == "update"
        task.status = "done"
        task.save()
        sync_todos(ticket.id)
        deliver(TodoDelivery.objects.latest("id").id)
        assert received[-1]["event"] == "close"
    finally:
        server.shutdown()
        server.server_close()
        invalidate_network_whitelist_cache()


def test_real_field_api_python_mapping_and_submit(sample):
    from apps.itsm.models import Workflow, WorkflowVersion
    from apps.itsm.services.form.fetch import fetch_field, freeze_schema, public_schema
    from apps.itsm.services.ticket.service import TicketService

    ticket, _ = sample
    ticket.team = [1]
    ticket.save()
    api = Integration.objects.create(name="字段工单查询", kind="api", config={"path": "itsm/tickets", "method": "GET"})
    transform = Integration.objects.create(
        name="字段选项映射",
        kind="python",
        config={
            "script": (
                "def transform(rows, params):\n" '    return [{"value": str(row["id"]), "label": row["sn"] + " · " + row["title"]} for row in rows]'
            )
        },
    )
    schema = freeze_schema(
        {
            "fields": [
                {
                    "key": "related",
                    "type": "select",
                    "required": True,
                    "fetch": {
                        "source": "integration",
                        "mode": "options",
                        "integration_id": api.id,
                        "inputs": {"page": 1, "page_size": 20},
                        "list_path": "data.items",
                        "transform_id": transform.id,
                        "value_path": "value",
                        "label_path": "label",
                    },
                }
            ]
        },
        "domain.com",
    )
    workflow = Workflow.objects.create(name="字段真实闭环", key="field-real")
    version = WorkflowVersion.objects.create(
        workflow=workflow, version_no=1, design={"form_schema": schema, "nodes": [{"id": "submit", "type": "submit"}]}
    )
    identity = CallerIdentity("owner", "domain.com", "jwt", team_ids=[1], permission={"itsm": {"ticket-View"}})
    result = fetch_field(schema, "related", {}, identity, context=f"version:{version.id}")
    assert result["options"] == [{"value": str(ticket.id), "label": f"{ticket.sn} · {ticket.title}"}]
    created = TicketService(identity=identity).create(
        version, {"related": str(ticket.id), "_field_receipts": {"related": [result["receipt"]]}}, "owner"
    )
    assert created.form_data["_field_labels"]["related"] == result["options"]
    assert "script" not in str(public_schema(schema))
    with pytest.raises(ValueError):
        fetch_field(schema, "related", {}, CallerIdentity("denied", "domain.com", "jwt", team_ids=[1]), context="denied")
