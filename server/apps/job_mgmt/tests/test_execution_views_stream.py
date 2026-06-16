# server/apps/job_mgmt/tests/test_execution_views_stream.py
import asyncio
import json
from unittest.mock import patch

import pytest
from django.http import StreamingHttpResponse

from apps.job_mgmt.constants import ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import JobExecution

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _grant_permission(authenticated_user):
    """SSE 端点用 @HasPermission("job_record-View") 鉴权；测试用户提权为超管放行。"""
    authenticated_user.is_superuser = True
    return authenticated_user


def _collect(resp):
    async def _run():
        return [c.decode() if isinstance(c, bytes) else c async for c in resp.streaming_content]
    return asyncio.run(_run())


def _make_execution(status, results=None):
    return JobExecution.objects.create(
        name="t", job_type=JobType.SCRIPT, status=status,
        target_source=TargetSource.MANUAL,
        target_list=[{"target_id": 5, "name": "h1", "ip": "1.1.1.1"}],
        execution_results=results or [], team=[1],
        created_by="testuser", updated_by="testuser",
    )


def test_stream_terminal_execution_returns_snapshot(api_client):
    execution = _make_execution(
        ExecutionStatus.SUCCESS,
        results=[{"target_key": "5", "stdout": "done-out", "stderr": ""}],
    )
    url = f"/api/v1/job_mgmt/api/execution/{execution.id}/stream/"
    resp = api_client.get(url)
    assert isinstance(resp, StreamingHttpResponse)
    assert resp["Content-Type"].startswith("text/event-stream")
    chunks = _collect(resp)
    assert any("done-out" in c for c in chunks)
    assert chunks[-1] == "data: [DONE]\n\n"


def test_stream_running_execution_uses_live_generator(api_client):
    execution = _make_execution(ExecutionStatus.RUNNING)

    async def _fake_gen(*_a, **_k):
        yield "data: {\"line\": \"live\"}\n\n"
        yield "data: [DONE]\n\n"

    with patch("apps.job_mgmt.views.execution.stream_execution_events", side_effect=lambda *a, **k: _fake_gen()), \
         patch("apps.job_mgmt.views.execution.ensure_stream_sync") as mock_ensure:
        url = f"/api/v1/job_mgmt/api/execution/{execution.id}/stream/"
        resp = api_client.get(url)
        assert isinstance(resp, StreamingHttpResponse)
        chunks = _collect(resp)

    mock_ensure.assert_called_once()
    assert any("live" in c for c in chunks)


def test_stream_running_execution_survives_ensure_stream_failure(api_client):
    execution = _make_execution(ExecutionStatus.RUNNING)

    async def _fake_gen(*_a, **_k):
        yield "data: [DONE]\n\n"

    with patch("apps.job_mgmt.views.execution.stream_execution_events", side_effect=lambda *a, **k: _fake_gen()), \
         patch("apps.job_mgmt.views.execution.ensure_stream_sync", side_effect=Exception("js down")):
        url = f"/api/v1/job_mgmt/api/execution/{execution.id}/stream/"
        resp = api_client.get(url)
        assert isinstance(resp, StreamingHttpResponse)  # 不抛 500
        _collect(resp)


def test_stream_sets_sse_headers(api_client):
    execution = _make_execution(ExecutionStatus.SUCCESS, results=[])
    url = f"/api/v1/job_mgmt/api/execution/{execution.id}/stream/"
    resp = api_client.get(url)
    assert resp["Cache-Control"] == "no-cache"
    assert resp["X-Accel-Buffering"] == "no"
