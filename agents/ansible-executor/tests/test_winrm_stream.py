import asyncio
import json
import time
from pathlib import Path

import pytest
from service.linux_script_delivery import ScriptDeliveryError
from service.winrm_stream import _build_command, _build_protocol, build_execute_command, prepare_script_bytes, run_winrm_stream


def _is_execute_command(command: str, arguments: list[str]) -> bool:
    joined = " ".join([command, *arguments])
    return command == "cmd.exe" and ("-File" in joined or "-u" in joined or ".cmd" in joined or ".py" in joined or ".ps1" in joined)


class _Protocol:
    def __init__(self):
        self.commands: list[tuple[str, list[str]]] = []
        self.exec_responses = iter(
            [
                (b"first\r\n", b"", -1, False),
                (b"second\r\n", b"", 0, True),
            ]
        )
        self.cleaned = False
        self.closed = False

    def open_shell(self):
        return "shell-1"

    def run_command(self, shell_id, command, arguments):
        assert shell_id == "shell-1"
        self.commands.append((command, list(arguments)))
        if _is_execute_command(command, arguments):
            return "command-exec"
        return f"command-setup-{len(self.commands)}"

    def get_command_output_raw(self, shell_id, command_id):
        assert shell_id == "shell-1"
        if command_id == "command-exec":
            return next(self.exec_responses)
        return b"", b"", 0, True

    def cleanup_command(self, shell_id, command_id):
        self.cleaned = True

    def close_shell(self, shell_id):
        self.closed = True


@pytest.mark.asyncio
async def test_winrm_stream_puts_file_then_streams_short_execute_command(tmp_path, monkeypatch):
    protocol = _Protocol()
    events = []
    copy_calls = []

    async def publisher(subject, payload):
        events.append((subject, json.loads(payload.decode("utf-8"))["line"]))

    def fake_copier(local_path, leaf, script_type, host_credentials):
        copy_calls.append((local_path, leaf, script_type, [item["host"] for item in host_credentials]))
        assert script_type == "powershell"
        assert Path(local_path).is_file()

    monkeypatch.setattr("service.winrm_stream.create_task_workspace", lambda task_id=None: tmp_path / "ws")
    (tmp_path / "ws").mkdir()

    code, output, meta = await run_winrm_stream(
        [{"host": "10.10.90.120", "connection": "winrm"}],
        script_content="Write-Output first",
        script_type="powershell",
        timeout=30,
        stream_publish=publisher,
        stream_log_topic="job.stream.31.ansible",
        execution_id="31",
        protocol_factory=lambda credential: protocol,
        script_copier=fake_copier,
    )

    assert code == 0
    assert copy_calls
    assert "first\r\nsecond" in output
    assert meta["truncated"] is False
    assert events == [
        ("job.stream.31.ansible", "first"),
        ("job.stream.31.ansible", "second"),
    ]
    assert any(_is_execute_command(cmd, args) for cmd, args in protocol.commands)
    assert protocol.cleaned is True
    assert protocol.closed is True


@pytest.mark.asyncio
async def test_winrm_stream_raises_when_put_file_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("service.winrm_stream.create_task_workspace", lambda task_id=None: tmp_path / "ws-fail")
    (tmp_path / "ws-fail").mkdir()

    def fail_copier(*_args, **_kwargs):
        raise ScriptDeliveryError("put boom", ["10.10.90.120"])

    with pytest.raises(ScriptDeliveryError, match="put boom"):
        await run_winrm_stream(
            [{"host": "10.10.90.120", "connection": "winrm"}],
            script_content="Write-Output first",
            script_type="powershell",
            timeout=30,
            stream_publish=lambda *_: asyncio.sleep(0),
            stream_log_topic="job.stream.31.ansible",
            execution_id="31",
            protocol_factory=lambda credential: _Protocol(),
            script_copier=fail_copier,
        )


@pytest.mark.parametrize("script_type", ["powershell", "bat", "python"])
def test_winrm_execute_command_keeps_script_out_of_process_arguments(script_type):
    secret = "echo do-not-leak-this-script"
    command, arguments = build_execute_command("abc123", script_type, windows_interpreter="python")
    joined = " ".join([command, *arguments])
    assert secret not in joined
    assert command == "cmd.exe"
    assert ".bklite-stream-abc123." in joined


def test_winrm_python_execute_uses_windows_interpreter_and_temp_py():
    command, arguments = build_execute_command("deadbeef", "python", windows_interpreter="python")
    assert command == "cmd.exe"
    joined = " ".join(arguments)
    assert "python -u" in joined
    assert ".bklite-stream-deadbeef.py" in joined


def test_winrm_powershell_utf8_lives_in_uploaded_script():
    prepared = prepare_script_bytes("Write-Output '距上次补丁天数'", "powershell").decode("utf-8-sig")
    assert "Encoding]::UTF8" in prepared
    assert "$OutputEncoding" in prepared
    assert prepared.index("$OutputEncoding") < prepared.index("距上次补丁天数")
    command, arguments = build_execute_command("abc123", "powershell")
    assert command == "cmd.exe"
    assert "-File" in " ".join(arguments)


def test_prepare_script_bytes_rejects_more_than_512_kib():
    with pytest.raises(ValueError, match=r"Windows script exceeds 512 KiB limit"):
        prepare_script_bytes("x" * (512 * 1024 + 1), "python")


def test_build_command_compat_returns_short_execute_only():
    command, arguments = _build_command("print(1)", "python", windows_interpreter="python", token="compat")
    joined = " ".join([command, *arguments])
    assert "print(1)" not in joined
    assert ".bklite-stream-compat.py" in joined


def test_build_protocol_rejects_unsafe_host_before_connecting():
    with pytest.raises(ValueError, match="invalid WinRM host"):
        _build_protocol({"host": "http://example.invalid/path"})


@pytest.mark.asyncio
async def test_winrm_stream_bounds_retained_and_streamed_partial_line():
    protocol = _Protocol()
    protocol.exec_responses = iter([(b"x" * 20, b"", 0, True)])
    lines = []

    async def publisher(_subject, payload):
        lines.append(json.loads(payload.decode("utf-8"))["line"])

    code, output, meta = await run_winrm_stream(
        [{"host": "10.10.90.120"}],
        script_content="Write-Output ignored",
        script_type="powershell",
        timeout=30,
        stream_publish=publisher,
        stream_log_topic="job.stream.32.ansible",
        execution_id="32",
        max_output_bytes=10,
        protocol_factory=lambda credential: protocol,
        skip_put_file=True,
        copy_token="boundtoken",
    )

    assert code == 0
    assert "xxxxxxxxxx" in output
    assert "x" * 11 not in output
    assert lines == ["x" * 20]
    assert meta["truncated"] is True
    assert meta["output_bytes_total"] == 20
    assert meta["output_bytes_retained"] == 10


@pytest.mark.asyncio
async def test_winrm_stream_slow_publisher_does_not_block_output_receive():
    protocol = _Protocol()
    protocol.exec_responses = iter([("".join(f"line{i}\n" for i in range(100)).encode(), b"", 0, True)])

    async def slow_publisher(_subject, _payload):
        await asyncio.sleep(0.05)

    started = time.monotonic()
    code, output, meta = await run_winrm_stream(
        [{"host": "10.10.90.120"}],
        script_content="Write-Output ignored",
        script_type="powershell",
        timeout=1,
        stream_publish=slow_publisher,
        stream_log_topic="job.stream.33.ansible",
        execution_id="33",
        stream_queue_size=4,
        stream_batch_size=2,
        stream_flush_timeout=0.05,
        protocol_factory=lambda credential: protocol,
        skip_put_file=True,
        copy_token="slowtoken",
    )

    assert code == 0
    assert "line99" in output
    assert time.monotonic() - started < 0.5
    assert meta["stream_lines_dropped"] > 0
