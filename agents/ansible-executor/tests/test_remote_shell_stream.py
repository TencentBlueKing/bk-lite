import asyncio
import base64
import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from service.linux_script_delivery import LINUX_SCRIPT_MAX_BYTES, ScriptDeliveryError
from service.remote_shell_stream import _build_remote_commands, _parse_poll_body, run_remote_shell_stream


def _ansible_result(host: str, body: str) -> str:
    return f"{host} | CHANGED | rc=0 >>\n{body}"


def _with_prepare(*responses):
    return iter([(0, _ansible_result("192.0.2.10", "ok"), {}), *responses])


def _stage_script(script: str, shell: str, max_output_bytes: int):
    prepare, launch, poll, stop, remote_dir, script_path = _build_remote_commands(shell, max_output_bytes)
    assert script not in prepare
    assert script not in launch
    prepared = subprocess.run(["/bin/sh", "-c", prepare], check=False, capture_output=True, text=True, timeout=10)
    assert prepared.returncode == 0, prepared.stderr
    Path(script_path).write_text(script, encoding="utf-8")
    return launch, poll, stop, remote_dir


def _poll_body(chunk: bytes, status: str) -> str:
    encoded = base64.b64encode(chunk).decode("ascii")
    return f"__BKLITE_STREAM_CHUNK__\n{encoded}\n__BKLITE_STREAM_STATUS__\n{status}"


@pytest.mark.asyncio
async def test_remote_shell_stream_decouples_polling_and_batches_in_order():
    events: list[str] = []
    responses = _with_prepare(
        (0, _ansible_result("192.0.2.10", "__BKLITE_STREAM_STARTED__"), {}),
        (0, _ansible_result("192.0.2.10", _poll_body(b"first\n", "RUNNING")), {}),
        (0, _ansible_result("192.0.2.10", _poll_body(b"second\n", "0")), {}),
        (0, _ansible_result("192.0.2.10", "cleaned"), {}),
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
    assert events.count("command-returned") == 5
    assert events.index("sleep") < next(index for index, event in enumerate(events) if event.startswith("publish:"))
    published = [event.rsplit(":", 1)[-1] for event in events if event.startswith("publish:")]
    assert "\n".join(published).splitlines() == ["first", "second"]


@pytest.mark.asyncio
async def test_remote_shell_stream_slow_publisher_does_not_consume_command_budget():
    lines = "".join(f"line{i}\n" for i in range(100)).encode()
    responses = _with_prepare(
        (0, _ansible_result("192.0.2.10", "__BKLITE_STREAM_STARTED__"), {}),
        (0, _ansible_result("192.0.2.10", _poll_body(lines, "0")), {}),
        (0, _ansible_result("192.0.2.10", "cleaned"), {}),
    )

    async def command_runner(_command, _timeout, **_kwargs):
        return next(responses)

    async def slow_publisher(_subject, _payload):
        await asyncio.sleep(0.05)

    started = time.monotonic()
    code, output, meta = await run_remote_shell_stream(
        ["ansible", "all", "-i", "inventory", "-m", "shell", "-a", "ignored"],
        script_content="echo ignored",
        shell_executable="/bin/bash",
        timeout=1,
        stream_publish=slow_publisher,
        stream_log_topic="job.stream.25.ansible",
        execution_id="25",
        poll_interval=0,
        command_runner=command_runner,
        stream_queue_size=4,
        stream_batch_size=2,
        stream_flush_timeout=0.05,
    )

    assert code == 0
    assert "line99" in output
    assert time.monotonic() - started < 0.5
    assert meta["stream_lines_dropped"] > 0


@pytest.mark.asyncio
async def test_remote_shell_stream_keeps_script_out_of_process_arguments():
    commands: list[list[str]] = []
    responses = _with_prepare(
        (0, _ansible_result("192.0.2.10", "__BKLITE_STREAM_STARTED__"), {}),
        (0, _ansible_result("192.0.2.10", _poll_body(b"done\n", "0")), {}),
        (0, _ansible_result("192.0.2.10", "cleaned"), {}),
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
    for command in commands:
        module_index = command.index("-m")
        args_index = command.index("-a")
        assert command[module_index + 1] == "raw"
        assert "_raw_params" in json.loads(command[args_index + 1])
    raw_params = [json.loads(command[command.index("-a") + 1])["_raw_params"] for command in commands]
    launch_params = next(item for item in raw_params if "setsid -f /bin/sh" in item)
    assert "setsid -f true" in launch_params
    assert "setsid /bin/sh" in launch_params
    assert "test -s " in launch_params
    assert secret_script not in launch_params
    assert all("printf %s" not in item or secret_script not in item for item in raw_params)


def test_remote_shell_start_finishes_script_when_setsid_has_no_fork_flag(tmp_path):
    """目标机 setsid 不支持 -f 时，启动命令仍要把用户脚本跑到结束。"""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    setsid = fake_bin / "setsid"
    setsid.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import os, sys",
                "args = sys.argv[1:]",
                "if args and args[0] == '-f':",
                "    sys.stderr.write('setsid: invalid option -- f\\n')",
                "    raise SystemExit(1)",
                "os.setsid()",
                "os.execvp(args[0], args)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    setsid.chmod(0o755)
    script = "printf 'hello world\\n'"
    start_command, poll_command, stop_command, remote_dir = _stage_script(script, "/bin/sh", 1024)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    chunks: list[bytes] = []
    try:
        started = subprocess.run(
            ["/bin/sh", "-c", start_command],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        assert started.returncode == 0, started.stderr
        assert "__BKLITE_STREAM_STARTED__" in started.stdout

        status = "RUNNING"
        deadline = time.monotonic() + 10
        while status == "RUNNING" and time.monotonic() < deadline:
            polled = subprocess.run(
                ["/bin/sh", "-c", poll_command],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
            )
            assert polled.returncode == 0, polled.stderr
            chunk, status = _parse_poll_body(polled.stdout)
            chunks.append(chunk)
            if status == "RUNNING":
                time.sleep(0.05)

        assert status == "0"
        assert b"hello world" in b"".join(chunks)
    finally:
        subprocess.run(["/bin/sh", "-c", stop_command], check=False, capture_output=True, text=True, timeout=10, env=env)

    assert not Path(remote_dir).exists()


def test_remote_shell_commands_cap_target_file_and_clean_workspace():
    script = "printf '0123456789abcdefghij\\n'"
    start_command, poll_command, stop_command, remote_dir = _stage_script(script, "/bin/sh", 10)
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


@pytest.mark.asyncio
async def test_remote_shell_stream_aborts_empty_poll_loop_before_full_timeout():
    """Ansible exit=0 但无主机结果时，不得空转直到整段 timeout。"""
    responses = _with_prepare(
        (0, _ansible_result("192.0.2.10", "__BKLITE_STREAM_STARTED__"), {}),
        (0, "Shared connection to 192.0.2.10 closed.\n", {}),
        (0, "Shared connection to 192.0.2.10 closed.\n", {}),
        (0, "Shared connection to 192.0.2.10 closed.\n", {}),
        (0, "cleaned", {}),
    )
    calls = {"n": 0}

    async def command_runner(_command, _timeout, **_kwargs):
        calls["n"] += 1
        return next(responses)

    async def publisher(_subject: str, _payload: bytes) -> None:
        return None

    async def no_sleep(_seconds: float) -> None:
        return None

    started = time.monotonic()
    code, output, _meta = await run_remote_shell_stream(
        ["ansible", "all", "-i", "inventory", "-m", "shell", "-a", "ignored"],
        script_content="echo hello",
        shell_executable="/bin/sh",
        timeout=30,
        stream_publish=publisher,
        stream_log_topic="job.stream.26.ansible",
        execution_id="26",
        poll_interval=0,
        command_runner=command_runner,
        sleep=no_sleep,
    )
    elapsed = time.monotonic() - started

    assert code == 1
    assert "no host result" in output
    assert calls["n"] == 6  # prepare + start + 3 empty polls + stop
    assert elapsed < 2


def _base_command() -> list[str]:
    return ["ansible", "all", "-i", "inventory", "-m", "shell", "-a", "ignored"]


@pytest.mark.asyncio
async def test_remote_shell_stream_rejects_script_over_512_kib_before_any_command(tmp_path):
    calls = {"n": 0}

    async def command_runner(*_args, **_kwargs):
        calls["n"] += 1
        raise AssertionError("oversize script must not reach ansible")

    script = "你" * 200_000
    with pytest.raises(ScriptDeliveryError) as raised:
        await run_remote_shell_stream(
            _base_command(),
            script_content=script,
            shell_executable="/bin/sh",
            timeout=30,
            stream_publish=_noop_publish,
            stream_log_topic="job.stream.limit.ansible",
            execution_id="limit",
            command_runner=command_runner,
            host_credentials=[{"host": "192.0.2.10"}],
            workspace=tmp_path,
        )

    assert calls["n"] == 0
    assert len(script.encode("utf-8")) == 600_000
    assert "512 KiB" in str(raised.value)
    assert "600000" in str(raised.value)
    assert "192.0.2.10 | FAILED | rc=1 >>" in raised.value.host_output
    assert not (tmp_path / "remote-shell-script").exists()


@pytest.mark.asyncio
async def test_remote_shell_stream_copies_large_script_instead_of_embedding_it(tmp_path):
    script = "A" * 100_000
    commands: list[list[str]] = []
    copied: dict[str, object] = {}
    responses = _with_prepare(
        (0, _ansible_result("192.0.2.10", "__BKLITE_STREAM_STARTED__"), {}),
        (0, _ansible_result("192.0.2.10", _poll_body(b"done\n", "0")), {}),
        (0, _ansible_result("192.0.2.10", "cleaned"), {}),
    )

    async def command_runner(command, timeout, **kwargs):
        del timeout, kwargs
        commands.append(command)
        return next(responses)

    def transfer(local_path, remote_path, credentials, workspace):
        local_file = Path(local_path)
        copied["mode"] = local_file.stat().st_mode & 0o777
        copied["body"] = local_file.read_text(encoding="utf-8")
        copied["remote"] = remote_path
        copied["hosts"] = [item["host"] for item in credentials]
        copied["workspace"] = workspace

    await run_remote_shell_stream(
        _base_command(),
        script_content=script,
        shell_executable="/bin/bash",
        timeout=30,
        stream_publish=_noop_publish,
        stream_log_topic="job.stream.large.ansible",
        execution_id="large",
        poll_interval=0,
        command_runner=command_runner,
        sleep=_noop_sleep,
        host_credentials=[{"host": "192.0.2.10", "user": "root"}],
        workspace=tmp_path,
        script_transfer=transfer,
    )

    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    assert copied["body"] == script
    assert copied["mode"] == 0o600
    assert str(copied["remote"]).endswith("/script")
    assert copied["hosts"] == ["192.0.2.10"]
    assert all(script not in argument and encoded not in argument for command in commands for argument in command)
    assert not (tmp_path / "remote-shell-script").exists()
    assert len(script) > 96_078
    assert len(script.encode("utf-8")) < LINUX_SCRIPT_MAX_BYTES


@pytest.mark.asyncio
async def test_remote_shell_stream_copy_failure_does_not_fall_back_to_arguments(tmp_path):
    script = "B" * 100_000
    commands: list[list[str]] = []
    responses = iter(
        [
            (0, _ansible_result("192.0.2.10", "ok"), {}),
            (0, _ansible_result("192.0.2.10", "cleaned"), {}),
        ]
    )

    async def command_runner(command, timeout, **kwargs):
        del timeout, kwargs
        commands.append(command)
        return next(responses)

    def transfer(_local_path, _remote_path, _credentials, _workspace):
        raise RuntimeError("unit-test-password-must-not-leak")

    with pytest.raises(ScriptDeliveryError) as raised:
        await run_remote_shell_stream(
            _base_command(),
            script_content=script,
            shell_executable="/bin/sh",
            timeout=30,
            stream_publish=_noop_publish,
            stream_log_topic="job.stream.copy.ansible",
            execution_id="copy",
            command_runner=command_runner,
            host_credentials=[{"host": "192.0.2.10", "password": "unit-test-password-must-not-leak"}],
            workspace=tmp_path,
            script_transfer=transfer,
        )

    joined = "\n".join(" ".join(command) for command in commands)
    assert "setsid" not in joined
    assert script not in joined
    assert "unit-test-password-must-not-leak" not in str(raised.value)
    assert "SFTP and scp are unavailable" in str(raised.value)
    assert "rm -rf " in joined
    assert not (tmp_path / "remote-shell-script").exists()


async def _noop_publish(_subject: str, _payload: bytes) -> None:
    return None


async def _noop_sleep(_seconds: float) -> None:
    return None
