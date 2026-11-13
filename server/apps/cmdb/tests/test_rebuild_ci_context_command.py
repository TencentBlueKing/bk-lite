import logging
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.models.ci_context import CmdbCiContextPending
from apps.cmdb.services.ci_context_policy import APPLICATION_MODEL
from apps.core.logger import SafeLogException

pytestmark = pytest.mark.django_db

COMMAND = "apps.cmdb.management.commands.rebuild_ci_context"
SERVICE = "apps.cmdb.services.ci_context"
PAGE_SIZE = 200
SECRET = "SECRET-sentinel"


class PagingGraph:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        return False

    def query_entity(self, label, params, page=None, fields=None, include_count=True):
        self.calls.append(
            {
                "label": label,
                "params": params,
                "page": page,
                "fields": fields,
                "include_count": include_count,
            }
        )
        skip = (page or {}).get("skip", 0)
        return self.pages.get(skip, []), 0


def _patch_graph(monkeypatch, pages):
    graph = PagingGraph(pages)
    monkeypatch.setattr(f"{SERVICE}.GraphClient", lambda *args, **kwargs: graph)
    return graph


def _patch_recompute(monkeypatch, calls, fail_uuid=None, raised=None):
    def recompute(inst_uuid):
        calls.append(inst_uuid)
        if fail_uuid is not None and inst_uuid == fail_uuid:
            error = RuntimeError(SECRET)
            if raised is not None:
                raised["error"] = error
            raise error

    monkeypatch.setattr(f"{SERVICE}.recompute_application", recompute)


def test_default_pages_two_batches_and_recomputes_each_uuid(monkeypatch):
    first = [f"app-{index:03d}" for index in range(PAGE_SIZE)]
    second = ["app-200"]
    pages = {
        0: [{"inst_uuid": inst_uuid} for inst_uuid in first],
        PAGE_SIZE: [{"inst_uuid": inst_uuid} for inst_uuid in second],
    }
    graph = _patch_graph(monkeypatch, pages)
    recomputed = []
    _patch_recompute(monkeypatch, recomputed)
    stdout = StringIO()

    call_command("rebuild_ci_context", stdout=stdout)

    assert graph.closed is True
    assert [call["page"] for call in graph.calls] == [
        {"skip": 0, "limit": PAGE_SIZE},
        {"skip": PAGE_SIZE, "limit": PAGE_SIZE},
    ]
    assert all(call["label"] == INSTANCE for call in graph.calls)
    assert all(call["params"] == [{"field": "model_id", "type": "str=", "value": APPLICATION_MODEL}] for call in graph.calls)
    assert all(call["fields"] == ["inst_uuid"] for call in graph.calls)
    assert all(call["include_count"] is False for call in graph.calls)
    assert recomputed == first + second
    assert stdout.getvalue().strip() == "ci_context rebuild finished recomputed=201"
    assert CmdbCiContextPending.objects.count() == 0


def test_empty_graph_recomputes_nothing(monkeypatch):
    graph = _patch_graph(monkeypatch, {})
    recomputed = []
    _patch_recompute(monkeypatch, recomputed)
    stdout = StringIO()

    call_command("rebuild_ci_context", stdout=stdout)

    assert len(graph.calls) == 1
    assert graph.calls[0]["page"] == {"skip": 0, "limit": PAGE_SIZE}
    assert recomputed == []
    assert stdout.getvalue().strip() == "ci_context rebuild finished recomputed=0"


def test_model_asst_id_recomputes_roots_only(monkeypatch):
    def forbid_graph(*_args, **_kwargs):
        raise AssertionError("model-asst mode must not page applications")

    seen = []

    def roots(model_asst_id):
        seen.append(model_asst_id)
        return ["app-root-1", "app-root-2"]

    monkeypatch.setattr(f"{SERVICE}.GraphClient", forbid_graph)
    monkeypatch.setattr(f"{COMMAND}._roots_for_model_asst", roots)
    recomputed = []
    monkeypatch.setattr(f"{COMMAND}.recompute_application", lambda inst_uuid: recomputed.append(inst_uuid) or recomputed[-1])
    stdout = StringIO()

    call_command("rebuild_ci_context", "--model-asst-id=application_run_host", stdout=stdout)

    assert seen == ["application_run_host"]
    assert recomputed == ["app-root-1", "app-root-2"]
    assert stdout.getvalue().strip() == "ci_context rebuild finished recomputed=2"


def test_failed_recompute_continues_and_exits_with_command_error(monkeypatch, caplog):
    pages = {0: [{"inst_uuid": "app-a"}, {"inst_uuid": "app-b"}, {"inst_uuid": "app-c"}]}
    _patch_graph(monkeypatch, pages)
    recomputed = []
    raised = {}
    _patch_recompute(monkeypatch, recomputed, fail_uuid="app-b", raised=raised)
    caplog.set_level(logging.ERROR, logger="cmdb")

    with pytest.raises(CommandError, match="ci_context rebuild failed recomputed=2 failed=1"):
        call_command("rebuild_ci_context")

    assert recomputed == ["app-a", "app-b", "app-c"]
    records = [record for record in caplog.records if record.name == "cmdb" and record.levelno >= logging.ERROR]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=ci_context_rebuild_failed inst_uuid=%s failed_stage=%s error_type=%s"
    assert record.args == ("app-b", "recompute_application", "RuntimeError")
    assert record.getMessage() == "event=ci_context_rebuild_failed inst_uuid=app-b failed_stage=recompute_application error_type=RuntimeError"
    error = raised["error"]
    assert error.args == (SECRET,)
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[2] is error.__traceback__
    formatted = logging.Formatter().format(record)
    assert SECRET not in record.getMessage()
    assert SECRET not in formatted
    assert CmdbCiContextPending.objects.count() == 0
