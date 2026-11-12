"""DeepAgents filesystem and shell backend backed by the local task workspace."""
from __future__ import annotations

import asyncio
import importlib.util
import re
import shlex
import uuid
from pathlib import Path

from deepagents.backends.protocol import FileDownloadResponse, FileUploadResponse
from deepagents.backends.sandbox import BaseSandbox

from apps.opspilot.services.python_sandbox.runtime import SandboxUnavailable
from apps.opspilot.services.skill_executor.path_rewriting_backend import extract_skill_names_from_text


class LocalSkillBackend(BaseSandbox):
    """Skill commands and file operations use the same sandbox as Python."""

    def __init__(self, sandbox, *, params_by_package=None, secret_values=None, ppt_workspace=None):
        self.sandbox = sandbox
        self._id = uuid.uuid4().hex
        self._params_by_package = params_by_package or {}
        self._ppt_workspace = str(ppt_workspace) if ppt_workspace else ""
        self._packages = {}
        self._installed = set()
        self._secrets = [value for value in (secret_values or []) if value]

    @property
    def id(self) -> str:
        return self._id

    def execute(self, command: str, *, timeout: int | None = None):
        # Skill manifests conventionally refer to /skills; both aliases point
        # into this task's local workspace.
        command = re.sub(r"(?<![\w/.-])/skills(?=/|(?=[\s'\"]|$))", self.sandbox.workspace + "/skills", command)
        command = re.sub(r"(?<![\w/.-])/ppt-workspace(?=/|[\s\'\"]|$)", self.sandbox.workspace + "/ppt-workspace", command)
        if self._ppt_workspace:
            command = command.replace(self._ppt_workspace, self.sandbox.workspace + "/ppt-workspace")
        names = extract_skill_names_from_text(command, self.sandbox.workspace + "/skills")
        for name in names:
            self._install_dependencies(name)
        env = self._params_by_package.get(names[0], {}) if len(names) == 1 else {}
        result = self.sandbox.execute_command(command, timeout=timeout if timeout is not None else 120, env=env)
        for secret in sorted(self._secrets, key=len, reverse=True):
            result.output = result.output.replace(secret, "***")
        return result

    def set_packages(self, packages):
        from apps.opspilot.services.skill_package.materializer import sanitize_skill_name

        self._packages = {sanitize_skill_name(p.get("package_id") or p.get("name")): p for p in packages if isinstance(p, dict)}

    def _install_dependencies(self, name):
        if name in self._installed or name not in self._packages:
            return
        package = self._packages[name]
        root = shlex.quote(f"{self.sandbox.workspace}/skills/{name}")
        declared = package.get("required_python_packages") or []
        installer = "python -m pip install" if importlib.util.find_spec("pip") else 'uv pip install --target "$PIP_TARGET"'
        commands = [
            f"if [ -f {root}/requirements.txt ]; then {installer} -r {root}/requirements.txt; fi",
            f"if [ -f {root}/package.json ]; then cd {root} && npm install; fi",
        ]
        if declared:
            commands.append(installer + " " + " ".join(shlex.quote(str(dep)) for dep in declared))
        result = self.sandbox.execute_command(" && ".join(commands), timeout=120)
        if result.exit_code:
            raise SandboxUnavailable("技能依赖安装失败，请检查沙箱网络和依赖声明")
        self._installed.add(name)

    def _file_path(self, path):
        if not path or path in ("/", "."):
            return self.sandbox.workspace
        for alias in ("/skills", "/ppt-workspace"):
            if path == alias or path.startswith(alias + "/"):
                return self.sandbox.workspace + path
        if self._ppt_workspace and (path == self._ppt_workspace or path.startswith(self._ppt_workspace + "/")):
            return self.sandbox.workspace + "/ppt-workspace" + path[len(self._ppt_workspace) :]
        return path if Path(path).is_absolute() else self.sandbox.workspace + "/" + path

    # Resolve aliases before BaseSandbox encodes paths into its commands. Keep
    # its bounded/paginated file protocol and execution-output secret redaction.
    def ls(self, path):
        return super().ls(self._file_path(path))

    async def als(self, path):
        return await asyncio.to_thread(self.ls, path)

    def read(self, file_path, offset=0, limit=2000):
        return super().read(self._file_path(file_path), offset, limit)

    async def aread(self, file_path, offset=0, limit=2000):
        return await asyncio.to_thread(self.read, file_path, offset, limit)

    def write(self, file_path, content):
        return super().write(self._file_path(file_path), content)

    async def awrite(self, file_path, content):
        return await asyncio.to_thread(self.write, file_path, content)

    def edit(self, file_path, old_string, new_string, replace_all=False):
        return super().edit(self._file_path(file_path), old_string, new_string, replace_all)

    async def aedit(self, file_path, old_string, new_string, replace_all=False):
        return await asyncio.to_thread(self.edit, file_path, old_string, new_string, replace_all)

    def grep(self, pattern, path=None, glob=None):
        return super().grep(pattern, self._file_path(path), glob)

    async def agrep(self, pattern, path=None, glob=None):
        return await asyncio.to_thread(self.grep, pattern, path, glob)

    def glob(self, pattern, path=None):
        return super().glob(pattern, self._file_path(path))

    async def aglob(self, pattern, path=None):
        return await asyncio.to_thread(self.glob, pattern, path)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses = []
        for path, data in files:
            try:
                self.sandbox.write_workspace_file(self._file_path(path), data)
                responses.append(FileUploadResponse(path=path))
            except (ValueError, SandboxUnavailable):
                responses.append(FileUploadResponse(path=path, error="permission_denied"))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses = []
        for path in paths:
            try:
                content = self.sandbox.read_workspace_file(self._file_path(path))
                responses.append(FileDownloadResponse(path=path, content=content))
            except (ValueError, SandboxUnavailable):
                responses.append(FileDownloadResponse(path=path, error="file_not_found"))
        return responses
