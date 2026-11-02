import asyncio

import pytest
from service.ansible_runner import AdhocRequest
from service.mixed_python_stream import run_mixed_python_script_stream


@pytest.mark.asyncio
async def test_mixed_python_stream_runs_linux_and_windows_in_parallel(monkeypatch, tmp_path):
    started = asyncio.Event()
    release = asyncio.Event()
    order: list[str] = []

    def fake_prepare(request):
        assert request.module == "raw"
        assert len(request.host_credentials) == 1
        assert request.host_credentials[0]["host"] == "192.168.1.10"
        return ["ansible", "all"], tmp_path

    async def fake_linux(*_args, **_kwargs):
        order.append("linux-start")
        started.set()
        await release.wait()
        order.append("linux-end")
        return (
            0,
            "192.168.1.10 | CHANGED | rc=0 >>\nok\n",
            {"truncated": False, "output_bytes_total": 2, "output_bytes_retained": 2, "output_max_bytes": 10},
        )

    windows_kwargs: dict = {}

    async def fake_windows_capture(*_args, **kwargs):
        windows_kwargs.update(kwargs)
        await started.wait()
        order.append("windows-start")
        release.set()
        order.append("windows-end")
        return (
            0,
            "10.10.90.120 | CHANGED | rc=0 >>\nok\n",
            {"truncated": False, "output_bytes_total": 2, "output_bytes_retained": 2, "output_max_bytes": 10, "stream_line_chunks": 1},
        )

    monkeypatch.setattr("service.mixed_python_stream.prepare_adhoc_execution", fake_prepare)
    monkeypatch.setattr("service.mixed_python_stream.run_remote_shell_stream", fake_linux)
    monkeypatch.setattr("service.mixed_python_stream.run_winrm_stream", fake_windows_capture)

    request = AdhocRequest(
        module="bklite_mixed_python",
        module_args="print('hi')",
        execute_timeout=30,
        task_id="mixed-1",
        extra_vars={"bklite_python_interpreter": "python3"},
        host_credentials=[
            {"host": "192.168.1.10", "connection": "ssh"},
            {"host": "10.10.90.120", "connection": "winrm"},
        ],
        stream_remote_output=True,
        stream_remote_type="python",
    )
    code, output, meta, workspace = await run_mixed_python_script_stream(
        request,
        stream_publish=lambda *_: asyncio.sleep(0),
        stream_log_topic="job.stream.1.ansible",
        execution_id="1",
    )

    assert code == 0
    assert workspace == tmp_path
    assert "192.168.1.10" in output and "10.10.90.120" in output
    assert order == ["linux-start", "windows-start", "windows-end", "linux-end"]
    assert windows_kwargs["script_type"] == "python"
    assert windows_kwargs["windows_interpreter"] == "python"
    assert meta["output_bytes_total"] == 4
    assert meta["stream_line_chunks"] == 1


@pytest.mark.asyncio
async def test_mixed_python_stream_merges_partial_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "service.mixed_python_stream.prepare_adhoc_execution",
        lambda request: (["ansible", "all"], tmp_path),
    )

    async def fake_linux(*_args, **_kwargs):
        return 0, "linux | CHANGED | rc=0 >>\nok\n", {"truncated": False, "output_bytes_total": 1, "output_bytes_retained": 1, "output_max_bytes": 8}

    async def fake_windows(*_args, **_kwargs):
        return 1, "win | FAILED | rc=1 >>\nbad\n", {"truncated": False, "output_bytes_total": 1, "output_bytes_retained": 1, "output_max_bytes": 8}

    monkeypatch.setattr("service.mixed_python_stream.run_remote_shell_stream", fake_linux)
    monkeypatch.setattr("service.mixed_python_stream.run_winrm_stream", fake_windows)

    request = AdhocRequest(
        module="bklite_mixed_python",
        module_args="print(1)",
        execute_timeout=30,
        host_credentials=[
            {"host": "linux", "connection": "ssh"},
            {"host": "win", "connection": "winrm"},
        ],
    )
    code, output, _meta, _workspace = await run_mixed_python_script_stream(request)
    assert code == 1
    assert "linux |" in output and "win |" in output
