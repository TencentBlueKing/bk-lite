"""Materialize bounded skill packages directly into the run's local directory."""
from pathlib import Path

from deepagents.backends.protocol import FileUploadResponse, WriteResult

from apps.opspilot.services.skill_package.materializer import materialize_skill_package

from .runtime import SandboxUnavailable


class _WorkspaceWriter:
    def __init__(self, sandbox):
        self.sandbox = sandbox
        self.size = 0
        self.count = 0
        self.failed = False

    def write(self, path, content):
        self.upload_files([(path, content.encode("utf-8"))])
        return WriteResult(path=path)

    def upload_files(self, files):
        results = []
        for path, data in files:
            try:
                self.size += len(data)
                self.count += 1
                if self.size > 128 * 1024 * 1024 or self.count > 20000:
                    raise ValueError("Skill package exceeds transfer limits")
                self.sandbox.write_workspace_file(path, data)
                results.append(FileUploadResponse(path=path))
            except (ValueError, SandboxUnavailable):
                self.failed = True
                raise
        return results

    def chmod(self, path, mode):
        self.sandbox._file_path(path).chmod(mode)


def materialize_local_skill(package, sandbox):
    writer = _WorkspaceWriter(sandbox)
    paths = materialize_skill_package(package, writer, skills_root=str(Path(sandbox.workspace) / "skills"))
    if writer.failed:
        raise SandboxUnavailable("技能包写入任务工作区失败")
    return paths
