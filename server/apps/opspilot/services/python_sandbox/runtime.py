"""Isolated, per-run Python workspace backed by a Docker container."""
from __future__ import annotations

import base64
import os
import threading
import uuid

import docker


class SandboxUnavailable(RuntimeError):
    """The isolated runtime could not safely execute the request."""


# The code is passed as an argument, never interpolated into a shell command.
_PYTHON_RUNNER = """import ast, base64, sys
code = base64.b64decode(sys.argv[1]).decode("utf-8")
tree = ast.parse(code, mode="exec")
if tree.body and isinstance(tree.body[-1], ast.Expr):
    expr = tree.body[-1].value
    if not (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id == "print"):
        tree.body[-1] = ast.Expr(value=ast.Call(func=ast.Name(id="print", ctx=ast.Load()), args=[expr], keywords=[]))
        ast.fix_missing_locations(tree)
exec(compile(tree, "<python_execute_direct>", "exec"), {"__name__": "__main__"})
"""


class PythonSandbox:
    """One container and workspace per agent run; no host directories are mounted."""

    def __init__(self, *, client=None, image=None, attachments=None):
        self._client = client
        self._image = image or os.getenv("OPSPILOT_PYTHON_SANDBOX_IMAGE", "bk-lite-python-sandbox:latest")
        self._container = None
        self._lock = threading.RLock()
        self._files = []
        self._closed = False
        self._attachments = list(attachments or [])

    def _ensure_container(self):
        if self._closed:
            raise SandboxUnavailable("Python 沙箱已关闭")
        if self._container is not None:
            return self._container
        try:
            client = self._client or docker.from_env(timeout=135)
            self._client = client
            self._container = client.containers.run(
                self._image,
                ["sleep", "3600"],
                detach=True,
                auto_remove=True,
                user="65534:65534",
                working_dir="/workspace",
                tmpfs={"/workspace": "rw,exec,size=256m,uid=65534,gid=65534,mode=700", "/tmp": "rw,exec,size=128m,uid=65534,gid=65534,mode=700"},
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit="1g",
                nano_cpus=1_000_000_000,
                pids_limit=128,
                environment={"HOME": "/workspace", "TMPDIR": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
                labels={"bk-lite.opspilot.python-sandbox": "true"},
                **({"network": os.environ["OPSPILOT_SANDBOX_NETWORK"]} if os.getenv("OPSPILOT_SANDBOX_NETWORK") else {}),
            )
            initialized = self._container.exec_run(["mkdir", "-p", "/workspace/skills", "/workspace/ppt-workspace"])
            if initialized.exit_code:
                raise SandboxUnavailable("沙箱工作目录初始化失败")
        except Exception as exc:
            raise SandboxUnavailable("Python 隔离环境不可用，请检查 Docker 和沙箱镜像配置") from exc
        if self._attachments:
            self._write_attachment_catalog()
        return self._container

    def _write_attachment_catalog(self):
        import json

        from .attachments import ATTACHMENT_READER

        self.write_workspace_file("/workspace/attachments/index.json", json.dumps(self._attachments, ensure_ascii=False).encode())
        self.write_workspace_file("/workspace/attachments/read.py", ATTACHMENT_READER.encode())

    def store_result(self, text: str) -> str:
        data = text.encode("utf-8")
        name = f"tool-result-{uuid.uuid4().hex}.txt"
        with self._lock:
            container = self._ensure_container()
            path = f"/workspace/{name}"
            try:
                # Docker's archive API can target the image layer rather than a
                # tmpfs mount. Write through a process inside the container so
                # the visible workspace is always the destination.
                for offset in range(0, len(data), 48 * 1024):
                    chunk = base64.b64encode(data[offset : offset + 48 * 1024]).decode("ascii")
                    result = container.exec_run(
                        ["python", "-c", "import base64,sys;open(sys.argv[1], 'ab').write(base64.b64decode(sys.argv[2]))", path, chunk],
                        workdir="/workspace",
                    )
                    if result.exit_code != 0:
                        raise SandboxUnavailable("工具结果写入 Python 沙箱失败")
            except SandboxUnavailable:
                raise
            except Exception as exc:
                raise SandboxUnavailable("工具结果写入 Python 沙箱失败") from exc
            self._files.append(path)
            return path

    def write_workspace_file(self, path: str, data: bytes) -> None:
        """Copy one bounded file into the container workspace, never onto the host."""
        import posixpath

        if not isinstance(data, bytes) or len(data) > 16 * 1024 * 1024:
            raise ValueError("文件超过沙箱传输限制")
        if not isinstance(path, str) or not path.startswith("/workspace/") or posixpath.normpath(path) != path:
            raise ValueError("文件路径必须位于沙箱工作目录")
        script = (
            "import base64,os,sys; p=sys.argv[1]; root='/workspace/'; "
            "parent=os.path.dirname(p); "
            "assert os.path.realpath(parent).startswith(root) or os.path.realpath(parent)==root[:-1]; "
            "os.makedirs(parent,exist_ok=True); "
            "assert os.path.realpath(parent).startswith(root) or os.path.realpath(parent)==root[:-1]; "
            "fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|("
            "os.O_TRUNC if sys.argv[3]=='1' else os.O_APPEND),0o600); "
            "os.write(fd,base64.b64decode(sys.argv[2])); os.close(fd)"
        )
        with self._lock:
            container = self._ensure_container()
            try:
                for offset in range(0, max(len(data), 1), 48 * 1024):
                    chunk = base64.b64encode(data[offset : offset + 48 * 1024]).decode("ascii")
                    result = container.exec_run(["python", "-c", script, path, chunk, "1" if offset == 0 else "0"])
                    if result.exit_code != 0:
                        raise SandboxUnavailable("文件写入沙箱失败")
            except SandboxUnavailable:
                raise
            except Exception as exc:
                raise SandboxUnavailable("文件写入沙箱失败") from exc

    def read_workspace_file(self, path: str) -> bytes:
        """Read a bounded regular file from this run's workspace."""
        import posixpath

        if not isinstance(path, str) or not path.startswith("/workspace/") or posixpath.normpath(path) != path:
            raise ValueError("文件路径必须位于沙箱工作目录")
        script = (
            "import base64,os,stat,sys; p=sys.argv[1]; "
            "assert os.path.realpath(p).startswith('/workspace/'); "
            "fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW); st=os.fstat(fd); "
            "assert stat.S_ISREG(st.st_mode) and st.st_size<=16777216; "
            "f=os.fdopen(fd,'rb'); sys.stdout.buffer.write(base64.b64encode(f.read(16777217)))"
        )
        with self._lock:
            container = self._ensure_container()
            try:
                result = container.exec_run(["python", "-c", script, path])
                if result.exit_code != 0:
                    raise SandboxUnavailable("无法读取沙箱文件")
                return base64.b64decode(result.output, validate=True)
            except SandboxUnavailable:
                raise
            except Exception as exc:
                raise SandboxUnavailable("无法读取沙箱文件") from exc

    def files(self) -> list[str]:
        with self._lock:
            return list(self._files)

    def execute(self, code: str) -> str:
        encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
        with self._lock:
            container = self._ensure_container()
            try:
                created = container.client.api.exec_create(
                    container.id,
                    ["timeout", "-s", "KILL", "60", "python", "-c", _PYTHON_RUNNER, encoded],
                    workdir="/workspace",
                )
                stream = container.client.api.exec_start(created["Id"], stream=True)
                chunks = []
                remaining = 64 * 1024
                truncated = False
                for chunk in stream:
                    if len(chunk) > remaining:
                        truncated = True
                    if remaining > 0:
                        chunks.append(chunk[:remaining])
                        remaining -= len(chunk[:remaining])
                output = b"".join(chunks).decode("utf-8", errors="replace").strip()
                if truncated:
                    output += "\n[输出已截断]"
                exit_code = container.client.api.exec_inspect(created["Id"])["ExitCode"]
                if exit_code != 0:
                    return f"Python 执行失败（退出码 {exit_code}）：{output}"
                return output or "代码执行完成，但没有输出"
            except Exception as exc:
                raise SandboxUnavailable("Python 沙箱执行失败") from exc

    def execute_command(self, command: str, *, timeout: int = 120, env: dict[str, str] | None = None):
        """Execute a skill command in the same container as Python and tool results."""
        from deepagents.backends.protocol import ExecuteResponse

        if not isinstance(command, str) or not command.strip():
            return ExecuteResponse(output="命令不能为空", exit_code=1, truncated=False)
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        with self._lock:
            container = self._ensure_container()
            try:
                created = container.client.api.exec_create(
                    container.id,
                    ["timeout", "-s", "KILL", str(timeout), "sh", "-c", command],
                    workdir="/workspace",
                    environment=env or {},
                )
                stream = container.client.api.exec_start(created["Id"], stream=True)
                chunks = []
                remaining = 64 * 1024
                truncated = False
                for chunk in stream:
                    if len(chunk) > remaining:
                        truncated = True
                    if remaining > 0:
                        kept = chunk[:remaining]
                        chunks.append(kept)
                        remaining -= len(kept)
                output = b"".join(chunks).decode("utf-8", errors="replace").strip()
                if truncated:
                    output += "\n[输出已截断]"
                exit_code = container.client.api.exec_inspect(created["Id"])["ExitCode"]
                if exit_code:
                    output = f"{output}\nExit code: {exit_code}".strip()
                return ExecuteResponse(output=output or "<no output>", exit_code=exit_code, truncated=truncated)
            except Exception as exc:
                raise SandboxUnavailable("技能容器执行失败") from exc

    def close(self):
        with self._lock:
            self._closed = True
            if self._container is not None:
                try:
                    self._container.remove(force=True)
                finally:
                    self._container = None
