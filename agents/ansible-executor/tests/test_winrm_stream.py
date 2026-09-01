import asyncio
import json
import time

import pytest
from service.winrm_stream import _build_command, _build_protocol, run_winrm_stream


class _Protocol:
    def __init__(self):
        self.responses = iter(
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
        assert command == "powershell.exe"
        assert "-EncodedCommand" in arguments
        return "command-1"

    def get_command_output_raw(self, shell_id, command_id):
        assert (shell_id, command_id) == ("shell-1", "command-1")
        return next(self.responses)

    def cleanup_command(self, shell_id, command_id):
        self.cleaned = True

    def close_shell(self, shell_id):
        self.closed = True


@pytest.mark.asyncio
async def test_winrm_stream_reuses_shell_and_publishes_incremental_lines():
    protocol = _Protocol()
    events = []

    async def publisher(subject, payload):
        events.append((subject, json.loads(payload.decode("utf-8"))["line"]))

    code, output, meta = await run_winrm_stream(
        [{"host": "10.10.90.120"}],
        script_content="Write-Output first",
        script_type="powershell",
        timeout=30,
        stream_publish=publisher,
        stream_log_topic="job.stream.31.ansible",
        execution_id="31",
        protocol_factory=lambda credential: protocol,
    )

    assert code == 0
    assert "first\r\nsecond" in output
    assert meta["truncated"] is False
    assert events == [
        ("job.stream.31.ansible", "first"),
        ("job.stream.31.ansible", "second"),
    ]
    assert protocol.cleaned is True
    assert protocol.closed is True


@pytest.mark.parametrize("script_type", ["powershell", "bat"])
def test_winrm_command_keeps_script_out_of_process_arguments(script_type):
    secret = "echo do-not-leak-this-script"
    command, arguments = _build_command(secret, script_type)

    assert command == "powershell.exe"
    assert secret not in " ".join(arguments)
    assert "-EncodedCommand" in arguments


def test_build_protocol_rejects_unsafe_host_before_connecting():
    with pytest.raises(ValueError, match="invalid WinRM host"):
        _build_protocol({"host": "http://example.invalid/path"})


@pytest.mark.asyncio
async def test_winrm_stream_bounds_retained_and_streamed_partial_line():
    protocol = _Protocol()
    protocol.responses = iter([(b"x" * 20, b"", 0, True)])
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
    protocol.responses = iter([("".join(f"line{i}\n" for i in range(100)).encode(), b"", 0, True)])

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
    )

    assert code == 0
    assert "line99" in output
    assert time.monotonic() - started < 0.5
    assert meta["stream_lines_dropped"] > 0
