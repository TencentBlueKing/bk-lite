"""PathRewritingBackend:在 execute 命令字符串里重写 ``/skills/...`` 与 ``/tmp/...`` 虚拟路径。

背景:
    deepagents ``LocalShellBackend`` 在 ``virtual_mode=True`` 时,只重写文件系统
    操作(read/write/ls/glob/grep)的路径,``execute`` 走 ``subprocess.run`` 把
    命令字符串直接传给宿主 shell,**不做任何路径重写**。
    这意味着当 LLM 写 ``python /skills/pdf/create_pdf.py`` 时:
      - cwd 是物理 sandbox_dir(如 ``/var/folders/.../run-XXX``),不是 ``/``
      - shell 找绝对路径 ``/skills/...`` 在文件系统根下不存在 → "No such file"
      - LLM 多次重试失败,最终 fallback 到自己直接调 Python 生成

    **L3 跨工具一致性问题:** 即便 ``/skills/...`` 通过 PathRewritingBackend 解决,
    LLM 还可能写 ``/tmp/<file>`` 这类沙箱外路径。deepagents virtual_mode 会把
    ``read_file('/tmp/...')`` 重写为 ``sandbox_dir/tmp/...``,但 ``execute`` 不会。
    两者路径域不一致 → "execute 写入成功,read_file 找不到"(同 sandbox 内)。

解决:
    ``PathRewritingBackend.execute`` / ``aexecute`` 接收 LLM 写的命令字符串,
    用正则把:
      - ``/skills/<path>`` → ``sandbox_dir/skills/<path>``
      - ``/tmp/<path>``   → ``sandbox_dir/tmp/<path>``(L3 扩展,与 virtual_mode 对齐)
    其他方法(read/write/ls/glob/grep)透传给底层 LocalShellBackend,后者已经
    正确处理 virtual_mode。

Phase 0 引入,Phase 1 NATS worker / 容器沙箱上线后可废弃。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from deepagents.backends.protocol import BackendProtocol, SandboxBackendProtocol

logger = logging.getLogger("apps.opspilot.skill_executor.path_rewriting_backend")

# 匹配 ``/skills/`` 开头、连续路径字符(不含 shell 特殊字符)的子串
_SKILLS_PATH_PATTERN = re.compile(r"/skills/[^\s'\"\|;&<>(){}\\`$?!*]*")
# L3 扩展:匹配 ``/tmp/`` 开头、连续路径字符(不含 shell 特殊字符)
_TMP_PATH_PATTERN = re.compile(r"/tmp/[^\s'\"\|;&<>(){}\\`$?!*]*")


def rewrite_skill_paths(command: str, sandbox_dir: Path, skills_root: str = "/skills") -> str:
    """把 command 字符串里以 ``/skills/`` 开头的路径 token 替换为物理路径。

    Args:
        command: LLM 写的 shell 命令字符串。
        sandbox_dir: 一次性沙箱物理根目录(传给 ``LocalShellBackend(root_dir=...)`` 的值)。
        skills_root: 虚拟根,默认 ``/skills``。

    Returns:
        替换后的命令字符串。其他 token(shell 控制符、参数值等)原样保留。
    """
    if not command:
        return command

    skills_prefix = skills_root.rstrip("/") + "/"
    if skills_prefix not in command:
        return command

    physical_prefix = str(sandbox_dir) + "/skills"
    rewritten = _SKILLS_PATH_PATTERN.sub(
        lambda match: physical_prefix + match.group(0)[len(skills_root) :],
        command,
    )
    if rewritten != command:
        logger.debug(
            "技能虚拟路径重写:\n  原: %s\n  新: %s",
            command,
            rewritten,
        )
    return rewritten


def rewrite_sandbox_paths(command: str, sandbox_dir: Path, skills_root: str = "/skills") -> str:
    """重写 execute 命令字符串中的多个沙箱外路径,让 execute 与 virtual_mode 路径域一致。

    L3 扩展:除 ``/skills/`` 外,也重写 ``/tmp/`` 让 execute 写入的临时文件能被
    read_file / ls / glob 在同一虚拟根看到。
    """
    if not command:
        return command

    rewritten = command
    skills_prefix = skills_root.rstrip("/") + "/"
    if skills_prefix in rewritten:
        physical_prefix = str(sandbox_dir) + "/skills"
        rewritten = _SKILLS_PATH_PATTERN.sub(
            lambda match: physical_prefix + match.group(0)[len(skills_root) :],
            rewritten,
        )

    if "/tmp/" in rewritten:
        physical_tmp = str(sandbox_dir) + "/tmp"
        rewritten = _TMP_PATH_PATTERN.sub(
            lambda match: physical_tmp + match.group(0)[len("/tmp") :],
            rewritten,
        )

    if rewritten != command:
        logger.debug(
            "沙箱虚拟路径重写:\n  原: %s\n  新: %s",
            command,
            rewritten,
        )
    return rewritten


class PathRewritingBackend(SandboxBackendProtocol):
    """包装 deepagents ``LocalShellBackend``(或任何 SandboxBackendProtocol),
    在 ``execute`` / ``aexecute`` 调用前重写 ``/skills/`` 虚拟路径。

    继承 ``SandboxBackendProtocol``(它已继承 BackendProtocol)是 deepagents 的硬要求:
      - ``_resolve_backend`` 用 ``isinstance(BackendProtocol)`` 校验,失败会把它当 callable 调而抛错
      - FilesystemMiddleware 用 ``SandboxBackendProtocol`` 校验决定是否注册 ``execute`` 工具,
        不继承则 LLM 拿不到 execute,只能 read_file/write_file

    其他方法(read/write/ls/glob/grep/upload_files/download_files/...)透传给底层
    backend,因为 deepagents ``LocalShellBackend`` 已经正确处理 virtual_mode。
    """

    def __init__(
        self,
        inner: Any,
        sandbox_dir: str | Path,
        skills_root: str = "/skills",
    ) -> None:
        self._inner = inner
        self._sandbox_dir = Path(sandbox_dir)
        self._skills_root = skills_root

    @property
    def id(self) -> str:
        """透传底层 backend 的 sandbox id(deepagents SandboxBackendProtocol 要求)。"""
        return getattr(self._inner, "id", f"path-rewriting-{id(self._inner)}")

    # ------------------------------------------------------------------
    # 重写的执行方法
    # ------------------------------------------------------------------

    def execute(self, command: str, *, timeout: int | None = None) -> Any:
        rewritten = rewrite_sandbox_paths(command, self._sandbox_dir, self._skills_root)
        self._ensure_sandbox_dirs(rewritten)
        return self._inner.execute(rewritten, timeout=timeout)

    async def aexecute(self, command: str, *, timeout: int | None = None) -> Any:
        rewritten = rewrite_sandbox_paths(command, self._sandbox_dir, self._skills_root)
        self._ensure_sandbox_dirs(rewritten)
        return await self._inner.aexecute(rewritten, timeout=timeout)

    def _ensure_sandbox_dirs(self, rewritten_command: str) -> None:
        """提前 mkdir sandbox_dir 下可能被写到的子目录,避免 open() 因父目录不存在而失败。

        L3 修复:PathRewriting 重写 /tmp/<path> → sandbox_dir/tmp/<path> 后,
        sandbox_dir/tmp 可能不存在,Python ``open()`` 会 FileNotFoundError。
        这里从 rewritten_command 提取所有 ``<sandbox>/<sub>`` 前缀并 mkdir -p。
        """
        sandbox_str = str(self._sandbox_dir)
        for match in re.finditer(re.escape(sandbox_str) + r"/[^\s'\"\|;&<>()]+", rewritten_command):
            path = Path(match.group(0))
            # 只 mkdir 已有父级在 sandbox 下、当前还不存在的中间目录
            try:
                if not path.exists():
                    parent = path.parent
                    # 只往下 mkdir 到 sandbox 下,避免意外触碰 sandbox 外
                    if str(parent).startswith(sandbox_str) and not parent.exists():
                        parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                # 目录创建失败(如权限)交给后续 execute 自然报错,这里不阻断
                pass

    # ------------------------------------------------------------------
    # 透传给底层 backend(deepagents 已处理 virtual_mode)
    # ------------------------------------------------------------------

    def write(self, file_path: str, content: str) -> Any:
        return self._inner.write(file_path, content)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> Any:
        return self._inner.read(file_path, offset=offset, limit=limit)

    def ls(self, path: str) -> Any:
        return self._inner.ls(path)

    def glob(self, pattern: str, path: str | None = None) -> Any:
        return self._inner.glob(pattern, path=path)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._inner.grep(pattern, path=path, glob=glob, **kwargs)

    def ls_info(self, path: str) -> Any:
        return getattr(self._inner, "ls_info", lambda p: self._inner.ls(p))(path)

    def glob_info(self, pattern: str, path: str = "/") -> Any:
        return getattr(self._inner, "glob_info", lambda pat, p="/": self._inner.glob(pat, path=p))(pattern, path)

    def grep_raw(self, *args: Any, **kwargs: Any) -> Any:
        return getattr(self._inner, "grep_raw", lambda *a, **k: self._inner.grep(*a, **k))(*args, **kwargs)

    def upload_files(self, files: list[tuple[str, bytes]]) -> Any:
        return self._inner.upload_files(files)

    def download_files(self, paths: list[str]) -> Any:
        return self._inner.download_files(paths)