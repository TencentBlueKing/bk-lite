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
        self._validate_command(rewritten, original=command)
        self._ensure_sandbox_dirs(rewritten)
        return self._inner.execute(rewritten, timeout=timeout)

    async def aexecute(self, command: str, *, timeout: int | None = None) -> Any:
        rewritten = rewrite_sandbox_paths(command, self._sandbox_dir, self._skills_root)
        self._validate_command(rewritten, original=command)
        self._ensure_sandbox_dirs(rewritten)
        return await self._inner.aexecute(rewritten, timeout=timeout)

    # 沙箱安全：可执行命令白名单(防止 LLM 误操作 host)。
    # 当前 sandbox 是 LocalShellBackend(virtual_mode),execute 直接跑 host shell,
    # 白名单是 P0 短期方案,Phase 1 NATS worker + Docker 沙箱是长期方案。
    # 安全约定:任何需要出网的命令(curl / wget / ssh / scp / rsync / nc)
    # 都不在白名单;对应的网络行为由工具函数显式提供(参考 SSRFValidator)。
    _ALLOWED_COMMANDS = frozenset({
        # 文件/文本
        "ls", "cat", "head", "tail", "grep", "find", "wc", "echo", "pwd",
        "less", "more", "file", "stat", "diff", "sort", "uniq", "cut",
        "tr", "tee", "xargs", "tee",
        # 目录/文件操作(受限,见 _BLOCKED_PATTERNS 里的 rm 限制)
        "mkdir", "touch", "mv", "cp", "ln", "rm", "chmod", "chown",
        # 解压/归档
        "tar", "unzip", "zip", "gzip", "gunzip", "zcat",
        # Python / Node 工具链
        "python3", "python", "pip", "pip3", "uv", "uvx",
        "node", "npm", "npx", "node-gyp",
        # 浏览器 / 文档工具
        "agent-browser", "ab", "playwright", "chromium", "google-chrome",
        "pdftotext", "pdfinfo", "pdftoppm", "qpdf", "wkhtmltopdf",
        "pdf2htmlEX", "mutool", "pandoc",
        # k8s
        "kubectl", "helm", "kustomize", "kubectx", "kubens",
        # 网络工具(curl/wget/ssh 等)显式不在白名单。
        # 真正出网需求由业务工具(uvx / git / npm)或 SSRF 校验过的 fetch 工具处理。
        # 其他常用
        "git", "tar", "date", "echo", "true", "false", "test", "[",
        "which", "whereis", "type",
    })
    # 黑名单正则(任何匹配都拒绝)
    # 收紧后比 L3 shell_tools 严:L3 只禁纯命令词,这层连管道 / 替换 / 展开一起拦。
    _BLOCKED_PATTERNS = (
        r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|-rf|-fr)\s+/\s*",  # rm -rf /
        r"\brm\s+-rf\s+/",
        r"\brm\s+-rf\s+~",            # rm -rf ~
        r"\brm\s+-rf\s+\$HOME",
        r"\brm\s+-rf\s+/\*",
        r"\bdd\s+",
        r"\bmkfs(\.\w+)?\s+",
        r"\bformat\s+",
        r"\bshutdown\s+",
        r"\breboot\s+",
        r"\bpoweroff\s+",
        r"\bhalt\s+",
        r"\bsudo\s+",
        r"\bsu\s+",
        r"\bssh\s+",                   # 远程爆破
        r"\bscp\s+",
        r"\brsync\s+",
        r"\bnc\s+",                    # netcat
        r"\|\s*sh\b",
        r"\|\s*bash\b",
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"\bsource\s+",
        r"\bchmod\s+(-R\s+)?777\b",
        r"\bchown\s+(-R\s+)?root\b",
        r"\buseradd\b",
        r"\buserdel\b",
        r"\bgroupadd\b",
        r"\bpasswd\s+",
        r"\bvisudo\b",
        r"\biptables\b",
        r"\bip\s+route\b",
        r"\bifconfig\b",
        r"\bmount\s+",
        r"\bumount\s+",
        r"\bswapon\s+",
        r"\bmkfs\.ext",
        r"\b>/dev/sd",
        r"\bcrontab\s+",
        r"\bat\s+now\b",              # at 立即执行
        # S4 防御:网络工具原命令被 _ALLOWED_COMMANDS 拿掉,这里再做一次
        # 黑名单兜底防止 LLM 通过管道 `cat|curl` / `echo|curl` 之类绕开
        r"\bcurl\b",
        r"\bwget\b",
        # M6 防御:路径展开绕开路径白名单(原正则只查 /xxx,LLM 写 ~/.ssh/id_rsa
        # / $HOME/.aws/credentials / `cat $(echo /etc/passwd)` 都不触发)
        r"\$\(",                      # 命令替换 $(...) 任何出现都拦
        r"`[^`]*`",                   # 反引号命令替换
        r"(?:^|\s)~/[^\s'\"]*",       # ~/path 任意字符(隐藏文件 / 任意位置展开)
        r"\$HOME\b",                  # $HOME 环境变量展开
        r"\$\{[A-Z_][A-Z0-9_]*\}",   # ${HOME} ${PATH} 形式
        r"(?:^|\s|\|)\$[A-Z_][A-Z0-9_]*\b",  # $PATH $USER $SECRET 等无大括号形式
    )

    def _validate_command(self, rewritten_command: str, original: str) -> None:
        """命令安全校验:黑名单 + 白名单 + 路径沙箱。

        参数:
            rewritten_command: rewrite_sandbox_paths 重写后的命令(实际给 host 跑)
            original: LLM 原始写的命令(只含虚拟路径 /skills/ /tmp/)

        校验策略:
        - 黑名单查 original(防 LLM 用 curl|wget 等绕过白名单路径访问 host)
        - 首命令白名单查 rewritten 的首 token
        - 路径沙箱查 original(只允许 /skills/ /tmp/ 等虚拟根,不是物理 sandbox 路径)
        """
        # 1. 黑名单(防 LLM 用 sed/awk/python -c 等绕过)
        for pattern in self._BLOCKED_PATTERNS:
            if re.search(pattern, original) or re.search(pattern, rewritten_command):
                raise PermissionError(
                    f"[sandbox] 命令被黑名单拦截(模式 {pattern!r}): {original!r}"
                )

        # 2. 首命令白名单(查 rewritten 的首 token,去除路径前缀)
        stripped = rewritten_command.strip()
        if not stripped:
            raise PermissionError("[sandbox] 空命令")
        first_token = stripped.split()[0]
        first_cmd = first_token.rsplit("/", 1)[-1]
        # 处理 env/sudo/time 等前缀
        skip_prefixes = {"env", "command", "sudo", "time", "nice", "nohup", "xargs"}
        tokens = stripped.split()
        idx = 0
        while first_cmd in skip_prefixes and idx + 1 < len(tokens):
            idx += 1
            first_cmd = tokens[idx].rsplit("/", 1)[-1]
        # 跳过 env KEY=VAL 这种赋值
        while "=" in first_cmd and idx + 1 < len(tokens):
            idx += 1
            first_cmd = tokens[idx].rsplit("/", 1)[-1]

        if first_cmd not in self._ALLOWED_COMMANDS:
            raise PermissionError(
                f"[sandbox] 命令 {first_cmd!r} 不在白名单。"
                f"允许的命令: {sorted(self._ALLOWED_COMMANDS)}"
            )

        # 3. 路径沙箱(只查原 command,防止 LLM 访问 host 路径)
        # 允许: /skills/xxx, /tmp/xxx(虚拟根,会被重写到 sandbox_dir),
        # /dev/null, /dev/stdout, /dev/stderr, 纯环境变量赋值, 注释
        # M9 修复:删 /proc/self/(可读 host 进程 environ 拿 SECRET_KEY/DB_PASSWORD)、
        # /dev/fd/(可反推进程打开文件)、/dev/shm/(跨进程共享内存泄露)。整个 /proc
        # 前缀都不在白名单,堵死 /proc/cpuinfo /proc/meminfo /proc/net/tcp 等。
        allowed_path_prefixes = (
            "/skills/", "/tmp/", "/dev/null", "/dev/stdout",
            "/dev/stderr",
        )
        for match in re.finditer(r"(?:^|\s)(/[^\s'\"]+)", original):
            path = match.group(1)
            if not any(path.startswith(p) for p in allowed_path_prefixes):
                    raise PermissionError(
                        f"[sandbox] 拒绝 host 路径 {path!r}。"
                        f"只允许 {allowed_path_prefixes} 下的路径。"
                    )

        # 4. SSRF 兜底:扫命令字符串里所有 http(s):// URL,用 LLM 端点宽松模式
        # 校验(只挡云元数据,内网 / localhost 由 ops-system-mgmt 的内网白名单统一管)。
        # 即便 _ALLOWED_COMMANDS 拿掉了 curl/wget,LLM 还能走
        # `python3 -c "import urllib.request; ..."` 这类绕道,黑名单拦不住,这里兜底。
        # 严格 validate() 模式对 skill 沙箱太死板(企业 k8s、localhost 服务、内部 HTTP
        # 都会拒),用 validate_llm_endpoint 只挡云元数据,把"内网能不能走"留给系统
        # 白名单(apps/system_mgmt/viewsets/network_white_list_viewset.py + 缓存
        # apps/system_mgmt/utils/network_whitelist_cache.py)统一管。
        # deep_wrapper_node 是 async,但 _validate_command 是同步调用,
        # validate_llm_endpoint 内部用 socket.getaddrinfo 同步,host 解析在
        # 50ms 以内,可接受;Phase 1 容器化时再考虑包 to_thread。
        from apps.core.utils.ssrf_validator import SSRFValidator, SSRFError
        for url in re.findall(r"https?://[^\s'\"|;&<>]+", original):
            try:
                SSRFValidator.validate_llm_endpoint(url)
            except SSRFError as e:
                raise PermissionError(
                    f"[sandbox] 网络目标被 SSRF 拦截: {url!r}({e})"
                ) from e

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