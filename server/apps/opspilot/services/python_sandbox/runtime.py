"""Per-run local workspace and subprocess execution, NOT a security sandbox.

The historical PythonSandbox name is retained for callers. Code runs with the
Server's OS identity; file API bounds do not constrain Python or shell execution.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path


class SandboxUnavailable(RuntimeError):
    """The task workspace or local execution process is unavailable."""


_PYTHON_RUNNER = """import ast, pathlib, sys
code = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')
tree = ast.parse(code, mode='exec')
if tree.body and isinstance(tree.body[-1], ast.Expr):
    expr = tree.body[-1].value
    if not (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id == 'print'):
        tree.body[-1] = ast.Expr(value=ast.Call(func=ast.Name(id='print', ctx=ast.Load()), args=[expr], keywords=[]))
        ast.fix_missing_locations(tree)
exec(compile(tree, '<python_execute_direct>', 'exec'), {'__name__': '__main__'})
"""
_MAX_FILE_BYTES = 16 * 1024 * 1024
_MAX_OUTPUT_BYTES = 64 * 1024


class PythonSandbox:
    """Share local files across tools, with fresh child processes per call."""

    def __init__(self, *, attachments=None):
        self._lock = threading.RLock()
        self._execution_lock = threading.Lock()
        self._root = None
        self._process = None
        self._closed = False
        self._attachments = list(attachments or [])

    @property
    def workspace(self) -> str:
        """Create only a private temporary directory, never an execution process."""
        with self._lock:
            if self._closed:
                raise SandboxUnavailable("任务工作区已关闭")
            if self._root is None:
                try:
                    self._root = Path(tempfile.mkdtemp(prefix="opspilot-run-")).resolve()
                    for name in ("skills", "ppt-workspace", "tmp", ".packages", ".local/bin"):
                        (self._root / name).mkdir(parents=True)
                    if self._attachments:
                        from .attachments import ATTACHMENT_READER

                        self.write_workspace_file(
                            str(self._root / "attachments/index.json"), json.dumps(self._attachments, ensure_ascii=False).encode()
                        )
                        self.write_workspace_file(str(self._root / "attachments/read.py"), ATTACHMENT_READER.encode())
                except OSError as exc:
                    raise SandboxUnavailable("无法创建任务工作区") from exc
            return str(self._root)

    def _file_path(self, path: str) -> Path:
        root = Path(self.workspace)
        if not isinstance(path, str):
            raise ValueError("文件路径必须位于当前任务工作目录")
        target = Path(path)
        if not target.is_absolute() or ".." in target.parts or target == root or not target.is_relative_to(root):
            raise ValueError("文件路径必须位于当前任务工作目录")
        if not target.resolve().is_relative_to(root) or target.is_symlink():
            raise ValueError("文件路径不能通过链接离开当前任务工作目录")
        return target

    def write_workspace_file(self, path: str, data: bytes) -> None:
        if not isinstance(data, bytes) or len(data) > _MAX_FILE_BYTES:
            raise ValueError("文件超过工作区传输限制")
        with self._lock:
            target = self._file_path(path)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                with os.fdopen(os.open(target, flags, 0o600), "wb") as stream:
                    stream.write(data)
            except OSError as exc:
                raise SandboxUnavailable("文件写入任务工作区失败") from exc

    def read_workspace_file(self, path: str) -> bytes:
        with self._lock:
            target = self._file_path(path)
            try:
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                with os.fdopen(os.open(target, flags), "rb") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_FILE_BYTES:
                        raise SandboxUnavailable("产物必须是大小不超过 16 MiB 的普通文件")
                    data = stream.read(_MAX_FILE_BYTES + 1)
                    if len(data) > _MAX_FILE_BYTES:
                        raise SandboxUnavailable("产物超过 16 MiB")
                    return data
            except OSError as exc:
                raise SandboxUnavailable("无法读取任务工作区文件") from exc

    def files(self) -> list[str]:
        with self._lock:
            return [str(path) for path in (Path(self.workspace) / "large_tool_results").glob("*") if path.is_file()]

    def _environment(self, extra):
        root = self.workspace
        # Do not automatically hand Server credentials to child processes. This
        # allowlist is convenience hygiene, not an OS access restriction.
        keys = ("PATH", "LANG", "LC_ALL", "SystemRoot", "WINDIR", "PATHEXT", "COMSPEC", "SSL_CERT_FILE", "SSL_CERT_DIR")
        env = {key: os.environ[key] for key in keys if key in os.environ}
        env.update(
            HOME=root,
            TMPDIR=f"{root}/tmp",
            TEMP=f"{root}/tmp",
            TMP=f"{root}/tmp",
            PYTHONIOENCODING="utf-8",
            PYTHONUTF8="1",
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONUNBUFFERED="1",
            PYTHONPATH=f"{root}/.packages",
            PIP_TARGET=f"{root}/.packages",
            PIP_NO_CACHE_DIR="1",
            NPM_CONFIG_PREFIX=f"{root}/.local",
            NPM_CONFIG_CACHE=f"{root}/.cache/npm",
            NPM_CONFIG_UPDATE_NOTIFIER="false",
            UV_CACHE_DIR=f"{root}/.cache/uv",
            OPSPILOT_WORKSPACE=root,
        )
        env["PATH"] = os.pathsep.join([f"{root}/.local/bin", f"{root}/.packages/bin", str(Path(sys.executable).parent), env.get("PATH", os.defpath)])
        env.update(extra or {})
        return env

    @staticmethod
    def _stop_process(process):
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return  # Already exited and has no surviving process group.
        elif process.poll() is None:  # pragma: no cover - Windows deployment
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if process.poll() is None:
                process.kill()

    def _run(self, args, *, timeout, env=None):
        from deepagents.backends.protocol import ExecuteResponse

        if timeout <= 0:
            raise ValueError("timeout must be positive")
        with self._execution_lock:
            with self._lock:
                root = self.workspace
                try:
                    process = subprocess.Popen(
                        args,
                        cwd=root,
                        env=self._environment(env),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        start_new_session=os.name == "posix",
                    )
                except OSError as exc:
                    raise SandboxUnavailable("无法启动本地执行进程") from exc
                self._process = process
            output = bytearray()
            truncated = False

            stop_reading = threading.Event()
            os.set_blocking(process.stdout.fileno(), False)

            def drain():
                nonlocal truncated
                while not stop_reading.is_set():
                    try:
                        chunk = os.read(process.stdout.fileno(), 8192)
                    except BlockingIOError:
                        stop_reading.wait(0.01)
                        continue
                    if not chunk:
                        break
                    remaining = _MAX_OUTPUT_BYTES - len(output)
                    truncated = truncated or len(chunk) > remaining
                    output.extend(chunk[:remaining])

            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            timed_out = False
            try:
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
            finally:
                # Also reap ordinary background descendants after a successful
                # shell exits; an execution call must not leave them running.
                self._stop_process(process)
                process.wait()
                reader.join(timeout=1)
                # A detached descendant can retain stdout; do not hang Server
                # teardown waiting on code that escaped its process group.
                stop_reading.set()
                reader.join()
                process.stdout.close()
                with self._lock:
                    self._process = None
            text = output.decode("utf-8", errors="replace").strip()
            if truncated:
                text += "\n[输出已截断]"
            if timed_out:
                text += "\n执行超时"
            exit_code = 124 if timed_out else process.returncode
            if exit_code:
                text = f"{text}\nExit code: {exit_code}".strip()
            return ExecuteResponse(output=text or "<no output>", exit_code=exit_code, truncated=truncated)

    def execute(self, code: str) -> str:
        # A file avoids the OS argv size limit for generated Python programs.
        with self._lock:
            script = Path(self.workspace) / f".python-{uuid.uuid4().hex}.py"
            try:
                script.write_text(code, encoding="utf-8")
            except OSError as exc:
                raise SandboxUnavailable("无法保存 Python 程序") from exc
        try:
            result = self._run([sys.executable, "-c", _PYTHON_RUNNER, str(script)], timeout=60)
            if result.exit_code:
                return f"Python 执行失败（退出码 {result.exit_code}）：{result.output}"
            return "代码执行完成，但没有输出" if result.output == "<no output>" else result.output
        finally:
            script.unlink(missing_ok=True)

    def execute_command(self, command: str, *, timeout: int = 120, env: dict[str, str] | None = None):
        from deepagents.backends.protocol import ExecuteResponse

        if not isinstance(command, str) or not command.strip():
            return ExecuteResponse(output="命令不能为空", exit_code=1, truncated=False)
        shell = shutil.which("sh")
        if shell is None:
            raise SandboxUnavailable("Server 环境未安装 sh，请安装兼容的 Shell")
        return self._run([shell, "-c", command], timeout=timeout, env=env)

    def close(self):
        with self._lock:
            self._closed = True
            if self._process is not None:
                self._stop_process(self._process)
        # Do not remove files until the active invocation has reaped its process.
        with self._execution_lock, self._lock:
            if self._root is not None:
                if self._root.exists():
                    shutil.rmtree(self._root)
                self._root = None
