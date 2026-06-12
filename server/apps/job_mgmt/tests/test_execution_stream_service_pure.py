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
