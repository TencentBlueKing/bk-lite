import os

import pytest

from apps.workflow.services.data_transform import DataTransformError, run_data_transform
from apps.workflow.services.health_summary_sql import health_summary_queries


def test_select_overlays_named_rows_and_json_cells():
    result = run_data_transform(
        {"keep": 1, "summary": {"total": 0}},
        [
            {"name": "summary", "sql": "SELECT json_object('total', 2, 'extra', 'kept')"},
            {"name": "rows", "sql": "SELECT 1 AS n UNION ALL SELECT 2"},
            {"name": "alone", "sql": "SELECT 7 AS n"},
        ],
        5,
    )

    assert result["keep"] == 1
    assert result["summary"] == {"total": 2, "extra": "kept"}
    assert result["rows"] == [{"n": 1}, {"n": 2}]
    assert result["alone"] == {"n": 7}


def test_query_cannot_load_extensions():
    with pytest.raises(DataTransformError, match="只能读取 input 表"):
        run_data_transform({"ok": True}, [{"name": "bad", "sql": "SELECT load_extension('x')"}], 5)


def test_timeout_interrupts_and_removes_the_sqlite_file(monkeypatch):
    created: list[str] = []
    real_mkdtemp = __import__("tempfile").mkdtemp

    def track(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created.append(path)
        return path

    monkeypatch.setattr("apps.workflow.services.data_transform.tempfile.mkdtemp", track)
    with pytest.raises(DataTransformError, match="查询超时"):
        run_data_transform(
            {"ok": True},
            [{"name": "spin", "sql": "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT max(x) FROM c"}],
            1,
        )

    assert created
    assert not os.path.exists(created[0])


def test_health_queries_union_two_job_envelopes():
    windows = {
        "data": [{"status": "SUCCESS", "result": {"collected_at": "2026-01-01 00:00:00", "metrics": [], "host": {}}}],
        "summary": {"total": 1, "succeeded": 1, "failed": 0},
    }
    linux = {
        "data": [{"status": "FAILED", "result": None, "error": "down"}],
        "summary": {"total": 1, "succeeded": 0, "failed": 1},
    }

    result = run_data_transform({"windows": windows, "linux": linux}, health_summary_queries(), 30)

    assert result["summary"]["total"] == 2
    assert result["summary"]["failed"] == 1
    assert result["summary"]["healthy_hosts"] == 1
    assert len(result["data"]) == 2
    assert result["data"][1]["result"]["host"]["hostname"] == ""
