"""Skill sandbox backend and environment helpers extracted from node.py."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.entity import ExtraConfig


class SkillSandboxMixin:
    """Mixin for ToolsNodes; extracted without behavior change."""

    def _build_skill_backend_and_sources(self, graph_request):
        """把启用的 SkillPackage 物化到「一次性沙箱目录」，返回 (backend, sources, sandbox_dir)。

        采用 deepagents 自带的 ``LocalShellBackend``：它既是 ``FilesystemBackend``
        （读写技能文件），又实现 ``SandboxBackendProtocol``（提供 ``execute`` shell
        工具）。技能即「CLI 自运行」：SKILL.md 里直接写 ``uvx ...`` / ``npx ...`` /
        二进制命令，由模型通过 ``execute`` 在 shell 里跑，不依赖业务工具接线。

        加固（人造沙箱，best-effort 隔离，非容器级强隔离），见实现注释：
          1. 每次运行新建临时目录、用完即弃（调用方在 finally 中 rmtree）；
          2. virtual_mode=True：文件工具关进沙箱，不能读写宿主任意路径；
          3. inherit_env=False + 精简白名单：不把宿主 DB 密码/密钥泄露给技能 shell。
        sandbox_dir 交给调用方清理。best-effort：无技能或失败返回 (None, [], None)。

        **backend 替换方向(Phase 1):** 当前 backend 是 ``LocalShellBackend``,
        ``execute`` 仍跑真实宿主 shell,绝对路径可访问宿主(非强隔离)。
        Phase 1 将按 deepagents ``SandboxBackendProtocol`` 接口替换为
        NATS worker / 容器沙箱实现,本函数调用方不变(materializer 接口
        向后兼容,通过 feature flag 切换 backend)。
        """
        packages = self._resolve_skill_packages(graph_request)
        if not packages:
            return None, [], None
        backend = None
        sources = []
        sandbox_dir = None
        try:
            import os
            import tempfile

            from deepagents.backends import LocalShellBackend

            from apps.opspilot.services.skill_executor import PathRewritingBackend
            from apps.opspilot.services.skill_package.materializer import materialize_skill_package, sanitize_skill_name
            from apps.opspilot.utils.skill_package_params import format_skillenv

            base = self._skill_sandbox_base()
            os.makedirs(base, exist_ok=True)
            # 一次性沙箱目录：run-XXXX，用完即弃（由调用方在 finally 中清理）
            sandbox_dir = tempfile.mkdtemp(prefix="run-", dir=base)
            skills_dir = os.path.join(sandbox_dir, "skills")
            os.makedirs(skills_dir, exist_ok=True)

            # 加固说明：
            #   - virtual_mode=True：沙箱目录即虚拟根，read/write/ls/glob/grep 关在沙箱内。
            #   - inherit_env=False + 精简白名单：杜绝 Django 进程 DB 密码/密钥外泄；
            #     TMPDIR 也指向沙箱，临时文件不外溢。
            #   - execute 的 cwd 即沙箱目录；技能命令用相对路径，产物随沙箱销毁。
            # 局限：execute 跑真实宿主 shell，绝对路径仍可访问宿主，非强隔离；要强隔离
            #   需换 NATS executor / 容器沙箱（替换 SandboxBackendProtocol 即可）。
            #
            # Phase 0 路径解析修复:deepagents 0.5.x 的 virtual_mode 不重写
            # execute 命令字符串里的绝对路径(/skills/...)。
            # PathRewritingBackend 在 execute 前正则替换 /skills/ → 物理 sandbox_dir/skills/。
            params_by_dir, secret_values = self._load_skill_package_runtime_params(graph_request, packages)
            injected = {name: sorted(env.keys()) for name, env in (params_by_dir or {}).items() if env}
            if injected:
                logger.info("技能包运行时参数已加载: %s", injected)
            else:
                logger.warning("技能包运行时参数为空，脚本将读不到 AD_HOST 等变量")
            inner_backend = LocalShellBackend(
                root_dir=sandbox_dir,
                virtual_mode=True,
                inherit_env=False,
                env=self._sandbox_env(sandbox_dir),
            )
            backend = PathRewritingBackend(
                inner=inner_backend,
                sandbox_dir=sandbox_dir,
                skills_root="/skills",
                on_skill_access=self._make_lazy_skill_deps_callback(packages),
                params_by_package=params_by_dir,
                secret_values=secret_values,
            )
            # 不在建沙箱时预装依赖:寒暄/未用技能时不应 pip install。
            # 依赖在 read/execute 真正碰到 /skills/<name>/ 时按需安装。
            # virtual_mode 下，物化到虚拟根的 /skills/ 即落在 sandbox_dir/skills/
            for pkg in packages:
                try:
                    materialize_skill_package(pkg, backend, skills_root="/skills")
                except Exception as me:  # 幂等：已存在/单包失败不影响其它技能
                    import traceback

                    logger.warning(
                        "技能物化失败(%s): %s\n%s",
                        pkg.get("name") if isinstance(pkg, dict) else pkg,
                        me,
                        traceback.format_exc(),
                    )
            for pkg in packages:
                if not isinstance(pkg, dict):
                    continue
                dir_name = sanitize_skill_name(pkg.get("package_id") or pkg.get("name"))
                env = params_by_dir.get(dir_name) or {}
                if not env:
                    continue
                skillenv_path = f"/skills/{dir_name}/.skillenv"
                try:
                    backend.write(skillenv_path, format_skillenv(env))
                    chmod = getattr(backend, "chmod", None)
                    if callable(chmod):
                        chmod(skillenv_path, 0o600)
                except Exception as env_exc:
                    logger.warning("写入 .skillenv 失败(%s): %r", dir_name, env_exc)
            sources = ["/skills/"]
            return backend, sources, sandbox_dir
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("技能 backend 构建失败，跳过 skills: %r", e)
            self._cleanup_sandbox(sandbox_dir)
            return None, [], None

    @classmethod
    def _make_lazy_skill_deps_callback(cls, packages: list):
        """返回「访问 /skills/<name>/ 时按需装依赖」的回调。

        与渐进披露一致:只物化目录元数据不够触发 pip;模型 read_file SKILL.md
        或 execute 技能脚本时才装对应包依赖。
        """
        from apps.opspilot.services.skill_package.materializer import sanitize_skill_name

        by_dir_name: dict[str, dict] = {}
        for pkg in packages:
            if not isinstance(pkg, dict):
                continue
            dir_name = sanitize_skill_name(pkg.get("package_id") or pkg.get("name"))
            by_dir_name[dir_name] = pkg

        ensured: set[str] = set()

        def _on_skill_access(names) -> None:
            pending: list[dict] = []
            for name in names or []:
                key = str(name or "").strip().lower()
                if not key or key in ensured:
                    continue
                pkg = by_dir_name.get(key)
                if pkg is None:
                    continue
                ensured.add(key)
                pending.append(pkg)
            if pending:
                cls._ensure_skill_deps(pending)

        return _on_skill_access

    @staticmethod
    def _ensure_skill_deps(packages: list) -> None:  # noqa: C901
        """根据**被访问的**技能包,确保 host Python 装了对应的 Python 库。

        当前 sandbox 是 LocalShellBackend(virtual_mode),execute 跑在 host,
        共享 host 的 sys.path,所以装 host 即可。Phase 1 切到独立容器沙箱后,
        这个函数会变成往镜像里塞依赖,而不是往 host 装。

        调用时机:PathRewritingBackend 在 read/execute 碰到 /skills/<name>/ 时
        按需触发;建沙箱阶段不再预装。
        """
        import importlib.util
        import re
        import subprocess
        import sys
        from pathlib import Path

        # 三层依赖发现:
        # Layer 1: deps_map(opspilot 预设,常用技能包的兜底)
        # Layer 2: 技能包自带的 requirements.txt / package.json(标准文件)
        # Layer 3: skill.yaml 里的 runtime.python_packages 字段(扩展字段)
        #
        # 这三层互补,优先 Layer 1 → 2 → 3 任一命中即用。
        # 长期方向:让 GitHub 技能包自己声明依赖,deps_map 退化为可选兜底。

        deps_map = {
            "pdf": ["reportlab", "pypdf", "pdfplumber", "pypdfium2"],
            "xlsx": ["openpyxl", "pandas"],
            "docx": ["python-docx"],
            "pptx": ["python-pptx"],
            "kubernetes-specialist": ["kubernetes", "pyyaml"],
            # agent-browser 是 Node CLI,全局 npm 装好即可。
            "agent-browser": [],
        }

        needed: set[str] = set()

        # Layer 1: deps_map 兜底(按 package_id / name 的目录名匹配)
        from apps.opspilot.services.skill_package.materializer import sanitize_skill_name

        for pkg in packages:
            if not isinstance(pkg, dict):
                continue
            keys = {
                sanitize_skill_name(pkg.get("package_id")),
                sanitize_skill_name(pkg.get("name")),
                str(pkg.get("name") or "").lower(),
                str(pkg.get("package_id") or "").lower(),
            }
            for key in keys:
                if key in deps_map:
                    needed.update(deps_map[key])
                    break

        # Layer 2: 扫描技能包根目录的标准依赖文件
        # requirements.txt(PEP 标准) / package.json(Node.js 标准)
        for pkg in packages:
            if not isinstance(pkg, dict):
                continue
            extracted_root = pkg.get("extracted_root")
            if not isinstance(extracted_root, Path):
                continue
            # requirements.txt
            req_txt = extracted_root / "requirements.txt"
            if req_txt.is_file():
                for line in req_txt.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        # 去掉版本约束(>=,==,<=,~=,!=,>,<,[], extras)
                        pkg_name = re.split(r"[<>=!~;\[]", line, 1)[0].strip()
                        if pkg_name:
                            needed.add(pkg_name)
                logger.warning(f"[sandbox-deps] 从 {req_txt} 检测到 Python 依赖")
            # package.json(只取 dependencies 和 devDependencies)
            pkg_json = extracted_root / "package.json"
            if pkg_json.is_file():
                try:
                    import json

                    pkg_meta = json.loads(pkg_json.read_text(encoding="utf-8"))
                    for section in ("dependencies", "devDependencies"):
                        deps = pkg_meta.get(section) or {}
                        if isinstance(deps, dict):
                            needed.update(deps.keys())
                            logger.warning(f"[sandbox-deps] 从 {pkg_json} 检测到 Node 依赖: {list(deps.keys())}")
                except Exception as json_err:
                    logger.warning(f"[sandbox-deps] 解析 {pkg_json} 失败: {json_err}")

        # Layer 3: skill.yaml 显式声明的 runtime.python_packages(扩展字段,优先级最高)
        for pkg in packages:
            if not isinstance(pkg, dict):
                continue
            declared = pkg.get("required_python_packages") or []
            if declared:
                needed.update(declared)
                logger.warning(f"[sandbox-deps] 从 skill.yaml 声明读到 Python 依赖: {declared}")

        # 过滤掉已经装好的。
        missing: list[str] = []
        for dep in sorted(needed):
            # importlib.util.find_spec 比真正 import 快,且不抛副作用。
            mod_name = dep.replace("-", "_").split("[")[0]
            if importlib.util.find_spec(mod_name) is None:
                missing.append(dep)

        if not missing:
            return

        logger.warning(f"[sandbox-deps] 缺失依赖: {missing},开始 pip install...")
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    # host Python 环境的 SSL CA bundle 不全,
                    # 加 --trusted-host 绕过 PyPI HTTPS 验证。
                    "--trusted-host",
                    "pypi.org",
                    "--trusted-host",
                    "files.pythonhosted.org",
                    *missing,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                logger.warning(f"[sandbox-deps] 装好: {missing}")
            else:
                logger.warning(f"[sandbox-deps] pip install 失败(returncode={result.returncode}): " f"{result.stderr[:300]}")
        except subprocess.TimeoutExpired:
            logger.warning(f"[sandbox-deps] pip install 超时: {missing}")
        except Exception as e:
            logger.warning(f"[sandbox-deps] pip install 异常: {e!r}")

    @staticmethod
    def _skill_sandbox_base() -> str:
        """一次性技能沙箱的父目录（每次运行在其下新建临时子目录）。"""
        import os
        import tempfile

        return os.getenv("OPSPILOT_SKILL_LOCAL_ROOT", os.path.join(tempfile.gettempdir(), "opspilot-sandbox"))

    _SANDBOX_PATH_PROBES = (
        "python3",
        "python",
        "pip",
        "pip3",
        "uv",
        "uvx",
        "node",
        "npm",
        "npx",
        "agent-browser",
        "ab",
        "playwright",
        "chromium",
        "markitdown",
        "pdftotext",
        "qpdf",
        "wkhtmltopdf",
        "pypdf",
        "pymupdf",
        "pdfplumber",
        "reportlab",
        "kubectl",
        "helm",
        "kustomize",
        "git",
        "curl",
        "jq",
        "rg",
    )

    @staticmethod
    def _discover_sandbox_path() -> str:
        """扫描 host 上已装的工具,把它们的 bin 目录合并成一个 PATH 字符串。

        解决 LLM 在 sandbox 内调 `markitdown` / `pip` / `python3` 等工具时
        找不到的问题 — 不用每次都猜安装路径。

        Returns:
            合并后的 PATH 字符串(``os.pathsep`` 分隔,无重复)。
        """
        import os
        import shutil
        import sys

        host_path = os.environ.get("PATH", "")
        path_sep = os.pathsep
        if not host_path:
            host_path = "/usr/local/bin:/usr/bin:/bin" if os.name != "nt" else ""
        host_parts = [p for p in host_path.split(path_sep) if p]
        bins: list[str] = []
        runtime_bins = [
            os.path.dirname(sys.executable),
            os.path.dirname(os.path.realpath(sys.executable)),
        ]

        for cmd in SkillSandboxMixin._SANDBOX_PATH_PROBES:
            try:
                resolved = shutil.which(cmd)
            except OSError:
                continue
            if not resolved:
                continue
            bin_dir = os.path.dirname(resolved)
            if bin_dir and bin_dir not in host_parts and bin_dir not in bins:
                bins.append(bin_dir)

        # 合并 host PATH + 探测 bins,用 dict.fromkeys 保序去重(host PATH 本身可能有重复段)
        # 当前服务的 venv 必须优先于父进程 PATH。否则从精简环境启动时会命中
        # /usr/bin/python3，并与服务 venv 的依赖形成跨 Python 版本混用。
        merged_list = runtime_bins + host_parts + bins
        merged_unique = list(dict.fromkeys(p for p in merged_list if p))
        return path_sep.join(merged_unique)

    _WINDOWS_SOCKET_ENV_KEYS = (
        "SystemRoot",
        "SYSTEMROOT",
        "SystemDrive",
        "SYSTEMDRIVE",
        "windir",
        "WINDIR",
        "PATHEXT",
        "ComSpec",
        "COMSPEC",
        "USERPROFILE",
        "USERNAME",
        "APPDATA",
        "LOCALAPPDATA",
        "TEMP",
        "TMP",
    )

    @staticmethod
    def _sandbox_env(sandbox_dir: str) -> dict:
        """技能 shell 的环境配置 — PATH 最大化,HOME/TMPDIR 隔离,敏感变量不携带。

        设计原则:
          - **PATH 扩展**: 用 shutil.which 探测 host 用户级 Python 工具(pip / uv / markitdown 等),
            任何工具的 bin 目录自动加入 sandbox PATH。LLM 不必反复试不同路径,
            一次能找到工具。分隔符用 ``os.pathsep``(Windows `;` / Linux `:`)，
            不能写死冒号,否则 `C:\\Windows\\system32` 会被拆碎。
          - **HOME 隔离到 sandbox_dir**: 避免 `~/.cache/pip` 等用户配置污染 host HOME,
            sandbox 销毁后清理。
          - **TMPDIR 隔离到 sandbox_dir**: subprocess 写 /tmp 时落沙箱内,
            跟 L3b 的 /tmp 重写 + PathRewritingBackend 配合。
          - **不携带敏感变量**: SECRET_KEY / DB_PASSWORD / NATS_TOKEN 等
            不出现在 sandbox 子进程环境中,即使工具泄漏也不会泄露。
          - **Windows 套接字**: 透传 SystemRoot / windir / PATHEXT / ComSpec,
            否则 ldap3 建 socket 会 WinError 10106。
        """
        import os

        env = {
            "PATH": SkillSandboxMixin._discover_sandbox_path(),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", os.environ.get("LANG", "C.UTF-8")),
            "TMPDIR": sandbox_dir,  # 临时文件落在沙箱内,用完即弃
            "HOME": sandbox_dir,  # 用户配置也隔离(PATH 透传但 HOME 不透)
            # kubectl 默认读 ~/.kube/config,但 sandbox 把 HOME 隔离到 sandbox_dir,
            # 找不到 kubeconfig。显式传 KUBECONFIG(host 环境变量,LLM 调 kubectl 才能连 k8s)。
            "KUBECONFIG": os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config")),
        }
        # Windows 环境变量名大小写不敏感;同时写入 SystemRoot/SYSTEMROOT
        # 在部分 CreateProcess 路径上会异常。按规范名去重,只保留一份。
        preferred_windows_keys = {
            "systemroot": "SystemRoot",
            "systemdrive": "SystemDrive",
            "windir": "windir",
            "pathext": "PATHEXT",
            "comspec": "ComSpec",
            "userprofile": "USERPROFILE",
            "username": "USERNAME",
            "appdata": "APPDATA",
            "localappdata": "LOCALAPPDATA",
            "temp": "TEMP",
            "tmp": "TMP",
        }
        for key in SkillSandboxMixin._WINDOWS_SOCKET_ENV_KEYS:
            value = os.environ.get(key)
            if not value:
                continue
            canon = preferred_windows_keys.get(key.lower(), key)
            env.setdefault(canon, value)
        system_root = env.get("SystemRoot")
        if system_root:
            system32 = os.path.join(system_root, "system32")
            parts = [p for p in env["PATH"].split(os.pathsep) if p]
            if system32 not in parts:
                parts.append(system32)
                env["PATH"] = os.pathsep.join(parts)
            # 临时目录仍落沙箱,避免子进程写到宿主 %TEMP%。
            env["TEMP"] = sandbox_dir
            env["TMP"] = sandbox_dir
        return env

    @staticmethod
    def _cleanup_sandbox(sandbox_dir: Optional[str]) -> None:
        """删除一次性沙箱目录（用完即弃）；失败仅记录，不影响主流程。"""
        if not sandbox_dir:
            return
        import shutil

        try:
            shutil.rmtree(sandbox_dir, ignore_errors=True)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("沙箱清理失败(%s): %r", sandbox_dir, e)

    @staticmethod
    def _skill_bucket_name() -> str:
        """技能文件所在的私有桶（沿用项目私有桶约定）。"""
        import os

        return os.getenv("OPSPILOT_SKILL_BUCKET", "munchkin-private")

    @classmethod
    def _load_skill_package_runtime_params(cls, graph_request, packages) -> tuple[dict, list]:
        """解密技能包参数并映射到沙箱目录名。明文只留在本进程内存。"""
        from apps.opspilot.utils.skill_package_params import map_params_to_skill_dirs, resolve_package_params

        ec = ExtraConfig.from_raw(getattr(graph_request, "extra_config", None))
        overlay = getattr(ec, "skill_package_params_overlay", None)
        skill_id = getattr(ec, "skill_id", None)

        def _load():
            params_by_id, secrets_by_id = resolve_package_params(skill_id, overlay=overlay)
            return map_params_to_skill_dirs(packages, params_by_id, secrets_by_id)

        try:
            asyncio.get_running_loop()
            in_async = True
        except RuntimeError:
            in_async = False
        if in_async:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(_load).result()
        return _load()

    @staticmethod
    def _resolve_skill_packages(graph_request) -> list:
        """从 request.extra_config 解析本次启用的技能包（已 hydrate 的 dict 列表）。"""
        try:
            import asyncio

            from apps.opspilot.services.skill_package.runtime import hydrate_skill_packages, normalize_skill_packages

            ec = ExtraConfig.from_raw(getattr(graph_request, "extra_config", None))
            raw = list(getattr(ec, "matched_skill_packages", None) or [])
            # 兜底:matched_skill_packages 是 trigger 匹配后 top-N,前端可能漏传。
            # 退回到 enabled_skill_packages(用户显式选中的技能包全集,用于 backend 物化)。
            if not raw:
                raw = list(getattr(ec, "enabled_skill_packages", None) or [])
            if not raw:
                return []
            # LangGraph node 跑在 async 上下文,ORM 查询会抛
            # "You cannot call this from an async context"。
            # 用 ThreadPoolExecutor 把 hydrate 跑在独立线程里,
            # 线程不在 async 上下文,可以正常同步 ORM。
            try:
                asyncio.get_running_loop()
                in_async = True
            except RuntimeError:
                in_async = False
            if in_async:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(hydrate_skill_packages, normalize_skill_packages(raw))
                    return future.result()
            return hydrate_skill_packages(normalize_skill_packages(raw))
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("技能包解析失败: %r", e)
            return []


# Backward-compat module-level aliases (tests patch chain.node.*)
_build_skill_backend_and_sources = SkillSandboxMixin._build_skill_backend_and_sources
_cleanup_sandbox = SkillSandboxMixin._cleanup_sandbox
_discover_sandbox_path = SkillSandboxMixin._discover_sandbox_path
_ensure_skill_deps = SkillSandboxMixin._ensure_skill_deps
_load_skill_package_runtime_params = SkillSandboxMixin._load_skill_package_runtime_params
_make_lazy_skill_deps_callback = SkillSandboxMixin._make_lazy_skill_deps_callback
_resolve_skill_packages = SkillSandboxMixin._resolve_skill_packages
_sandbox_env = SkillSandboxMixin._sandbox_env
_skill_bucket_name = SkillSandboxMixin._skill_bucket_name
_skill_sandbox_base = SkillSandboxMixin._skill_sandbox_base
