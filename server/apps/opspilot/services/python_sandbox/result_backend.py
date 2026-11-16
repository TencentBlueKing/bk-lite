"""将 Deep Agents 原生结果文件路由到当前任务工作区，不授予执行权限。"""

from pathlib import Path

from deepagents.backends.composite import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import BackendProtocol, EditResult, GlobResult, GrepResult, LsResult, ReadResult, WriteResult

from .runtime import SandboxUnavailable

RESULT_PATH = "/large_tool_results/"
RESULT_READ_TOOLS = frozenset({"read_file", "grep"})


def is_result_read(call):
    name = call.get("name")
    args = call.get("args") or {}
    path = args.get("file_path") if name == "read_file" else args.get("path")
    return name in RESULT_READ_TOOLS and isinstance(path, str) and path.startswith(RESULT_PATH) and ".." not in Path(path).parts


class RunResultBackend(BackendProtocol):
    """原生文件读写/检索实现，加上任务关闭与路径检查。"""

    def __init__(self, sandbox):
        self.sandbox = sandbox
        self.root = Path(sandbox.workspace) / "large_tool_results"
        self.root.mkdir(exist_ok=True)
        self.backend = FilesystemBackend(root_dir=self.root, virtual_mode=True)

    def _check(self, path):
        path = path or "/"
        if ".." in Path(path).parts or "~" in path:
            raise ValueError("结果文件路径无效")
        target = self.root / path.lstrip("/")
        self.sandbox._file_path(str(target))
        if not target.resolve().is_relative_to(self.root):
            raise ValueError("只能访问本次任务的结果文件")

    def _call(self, method, result_type, path, *args, **kwargs):
        with self.sandbox._lock:
            try:
                self._check(path)
            except (ValueError, SandboxUnavailable):
                return result_type(error="结果文件不可用或不属于当前任务")
            return getattr(self.backend, method)(*args, **kwargs)

    def read(self, file_path, offset=0, limit=2000):
        return self._call("read", ReadResult, file_path, file_path, offset, limit)

    def grep(self, pattern, path=None, glob=None):
        return self._call("grep", GrepResult, path, pattern, path, glob)

    def ls(self, path):
        return self._call("ls", LsResult, path, path)

    def glob(self, pattern, path=None):
        return self._call("glob", GlobResult, path, pattern, path)

    def write(self, file_path, content):
        return self._call("write", WriteResult, file_path, file_path, content)

    def edit(self, file_path, old_string, new_string, replace_all=False):
        return EditResult(error="工具结果只读")


def build_result_backend(sandbox, skill_backend=None):
    results = RunResultBackend(sandbox)
    return CompositeBackend(default=skill_backend or results, routes={RESULT_PATH: results})
