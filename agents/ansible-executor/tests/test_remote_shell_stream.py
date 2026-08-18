import base64
import json
import subprocess
import time
from pathlib import Path

import pytest
from service.remote_shell_stream import _build_remote_commands, _parse_poll_body, run_remote_shell_stream


def _ansible_result(host: str, body: str) -> str:
    return f"{host} | CHANGED | rc=0 >>\n{body}"


def _poll_body(chunk: bytes, status: str) -> str:
    encoded = base64.b64encode(chunk).decode("ascii")
    return f"__BKLITE_STREAM_CHUNK__\n{encoded}\n__BKLITE_STREAM_STATUS__\n{status}"


@pytest.mark.asyncio
async def test_remote_shell_stream_publishes_each_poll_before_command_finishes():
    events: list[str] = []
    responses = iter(
        [
            (0, _ansible_result("192.0.2.10", "__BKLITE_STREAM_STARTED__"), {}),
            (0, _ansible_result("192.0.2.10", _poll_body(b"first\n", "RUNNING")), {}),
            (0, _ansible_result("192.0.2.10", _poll_body(b"second\n", "0")), {}),
            (0, _ansible_result("192.0.2.10", "cleaned"), {}),
        ]
    )

    async def command_runner(command, timeout, **kwargs):
        del command, timeout, kwargs
        response = next(responses)
        events.append("command-returned")
        return response

    async def publisher(subject: str, payload: bytes) -> None:
        data = json.loads(payload.decode("utf-8"))
        events.append(f"publish:{subject}:{data['line']}")

    async def no_sleep(_seconds: float) -> None:
        events.append("sleep")

    code, output, output_meta = await run_remote_shell_stream(
        ["python", "main.py", "--internal-ansible-cli", "adhoc", "--", "all", "-i", "inventory", "-m", "shell", "-a", "ignored", "-vvv"],
        script_content="echo secret-script-body",
        shell_executable="/bin/bash",
        timeout=30,
        stream_publish=publisher,
        stream_log_topic="job.stream.23.ansible",
        execution_id="23",
        poll_interval=0,
        command_runner=command_runner,
        sleep=no_sleep,
    )

    assert code == 0
    assert "first\nsecond" in output
    assert output_meta["truncated"] is False
    assert events == [
        "command-returned",
        "command-returned",
        "publish:job.stream.23.ansible:first",
        "sleep",
        "command-returned",
        "publish:job.stream.23.ansible:second",
        "command-returned",
    ]


@pytest.mark.asyncio
async def test_remote_shell_stream_keeps_script_out_of_process_arguments():
    commands: list[list[str]] = []
    responses = iter(
        [
            (0, _ansible_result("192.0.2.10", "__BKLITE_STREAM_STARTED__"), {}),
            (0, _ansible_result("192.0.2.10", _poll_body(b"done\n", "0")), {}),
            (0, _ansible_result("192.0.2.10", "cleaned"), {}),
        ]
    )

    async def command_runner(command, timeout, **kwargs):
        del timeout, kwargs
        commands.append(command)
        return next(responses)

    async def publisher(_subject: str, _payload: bytes) -> None:
        return None

    async def no_sleep(_seconds: float) -> None:
        return None

    secret_script = "echo do-not-leak-this-script"
    await run_remote_shell_stream(
        ["ansible", "all", "-i", "inventory", "-m", "shell", "-a", "ignored", "-vvv"],
        script_content=secret_script,
        shell_executable="/bin/bash",
        timeout=30,
        stream_publish=publisher,
        stream_log_topic="job.stream.24.ansible",
        execution_id="24",
        poll_interval=0,
        command_runner=command_runner,
        sleep=no_sleep,
    )

    assert commands
    assert all(secret_script not in argument for command in commands for argument in command)
    assert any("setsid -f" in argument for argument in commands[0])


def test_remote_shell_commands_cap_target_file_and_clean_workspace():
    start_command, poll_command, stop_command, remote_dir = _build_remote_commands(
        "printf '0123456789abcdefghij\\n'",
        "/bin/sh",
        10,
    )
    chunks: list[bytes] = []

    try:
        started = subprocess.run(
            ["/bin/sh", "-c", start_command],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert started.returncode == 0, started.stderr

        status = "RUNNING"
        deadline = time.monotonic() + 10
        while status == "RUNNING" and time.monotonic() < deadline:
            polled = subprocess.run(
                ["/bin/sh", "-c", poll_command],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert polled.returncode == 0, polled.stderr
            chunk, status = _parse_poll_body(polled.stdout)
            chunks.append(chunk)
            if status == "RUNNING":
                time.sleep(0.05)

        assert status == "0"
        output = b"".join(chunks)
        assert output.startswith(b"0123456789")
        assert b"abcdefghij" not in output
        assert b"[output truncated]" in output
    finally:
        subprocess.run(
            ["/bin/sh", "-c", stop_command],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

    assert not Path(remote_dir).exists()
