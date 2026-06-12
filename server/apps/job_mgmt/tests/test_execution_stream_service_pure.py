# server/apps/job_mgmt/tests/test_execution_stream_service_pure.py
import json

import pytest

from apps.job_mgmt.services import execution_stream_service as svc

pytestmark = pytest.mark.unit


def test_build_stream_topic():
    assert svc.build_stream_topic(42, "node-abc") == "job.stream.42.node-abc"
    assert svc.build_stream_topic("7", "5") == "job.stream.7.5"


def test_format_sse_event_is_data_line_with_trailing_blank():
    out = svc.format_sse_event({"line": "héllo", "type": "log"})
    assert out.startswith("data: ")
    assert out.endswith("\n\n")
    assert json.loads(out[len("data: "):].strip()) == {"line": "héllo", "type": "log"}


def test_format_sse_event_keeps_unicode_unescaped():
    out = svc.format_sse_event({"line": "中文"})
    assert "中文" in out


def test_parse_target_key_strips_prefix():
    assert svc.parse_target_key("job.stream.42.node-abc", 42) == "node-abc"
    assert svc.parse_target_key("job.stream.42.t.5", 42) == "t.5"


def test_parse_target_key_returns_empty_when_no_match():
    assert svc.parse_target_key("other.subject", 42) == ""


def test_aggregator_emits_every_payload_as_sse():
    agg = svc.ExecutionStreamAggregator(["a", "b"])
    out = agg.process({"target_key": "a", "line": "x"})
    assert out == svc.format_sse_event({"target_key": "a", "line": "x"})


def test_aggregator_not_complete_until_all_targets_done():
    agg = svc.ExecutionStreamAggregator(["a", "b"])
    assert agg.is_complete() is False
    agg.process({"target_key": "a", "type": svc.DONE_TYPE, "status": "success"})
    assert agg.is_complete() is False
    agg.process({"target_key": "b", "type": svc.DONE_TYPE, "status": "failed"})
    assert agg.is_complete() is True


def test_aggregator_done_target_key_is_string_normalized():
    agg = svc.ExecutionStreamAggregator([1, 2])
    agg.process({"target_key": 1, "type": svc.DONE_TYPE, "status": "success"})
    agg.process({"target_key": "2", "type": svc.DONE_TYPE, "status": "success"})
    assert agg.is_complete() is True


def test_aggregator_unknown_done_target_is_ignored_safely():
    agg = svc.ExecutionStreamAggregator(["a"])
    agg.process({"target_key": "zzz", "type": svc.DONE_TYPE, "status": "success"})
    assert agg.is_complete() is False


def test_aggregator_empty_targets_is_immediately_complete():
    agg = svc.ExecutionStreamAggregator([])
    assert agg.is_complete() is True
