"""Process-level timeout for transform runner."""

from __future__ import annotations

from app.process_exec import run_transform_in_process


def test_run_transform_in_process_kills_on_timeout():
    outcome = run_transform_in_process(
        "def transform(rows, params):\n    while True:\n        pass\n",
        [{"a": 1}],
        {},
        timeout_seconds=0.8,
    )
    assert outcome["ok"] is False
    assert outcome["code"] == "transform_timeout"


def test_run_transform_in_process_returns_large_result_without_false_timeout():
    rows = [{"payload": "x" * 7000} for _ in range(1000)]

    outcome = run_transform_in_process(
        "def transform(rows, params):\n    return rows\n",
        rows,
        {},
        timeout_seconds=5,
    )

    assert outcome["ok"] is True
    assert outcome["rows"] == rows
