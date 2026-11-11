"""Skill sandbox backend and environment helpers extracted from node.py."""
from __future__ import annotations

import asyncio

from asgiref.sync import sync_to_async
from langchain_core.callbacks import adispatch_custom_event

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.entity import ExtraConfig
from apps.opspilot.services.ppt_master_runtime import (
    begin_ppt_run,
    discard_ppt_run,
    is_ppt_master_package,
    packages_include_ppt_master,
    publish_latest_export,
)


class SkillSandboxMixin:
    """Configure the task container and publish skill artifacts."""

    def _build_skill_backend_and_sources(self, graph_request, packages=None, *, sandbox=None):
        """Materialize skills in the run container. Never fall back to host execution."""
        from apps.opspilot.services.python_sandbox.runtime import SandboxUnavailable
        from apps.opspilot.services.python_sandbox.skill_backend import ContainerSkillBackend

        if packages is None:
            packages = self._resolve_skill_packages(graph_request)
        if not packages:
            return None, [], None
        if sandbox is None:
            raise SandboxUnavailable("技能执行需要任务容器")
        params, secrets = self._load_skill_package_runtime_params(graph_request, packages)
        ppt_workspace = begin_ppt_run(graph_request) if packages_include_ppt_master(packages) else None
        try:
            backend = ContainerSkillBackend(sandbox, params_by_package=params, secret_values=secrets, ppt_workspace=ppt_workspace)
            for package in packages:
                from apps.opspilot.services.python_sandbox.provisioning import materialize_container_skill

                materialize_container_skill(package, sandbox)
                from apps.opspilot.services.skill_package.materializer import sanitize_skill_name
                from apps.opspilot.utils.skill_package_params import format_skillenv

                name = sanitize_skill_name(package.get("package_id") or package.get("name"))
                if params.get(name):
                    sandbox.write_workspace_file(f"/workspace/skills/{name}/.skillenv", format_skillenv(params[name]).encode())
            backend.set_packages(packages)
        except BaseException:
            if ppt_workspace is not None:
                discard_ppt_run(graph_request)
            raise
        return backend, ["/workspace/skills/"], str(ppt_workspace) if ppt_workspace else None

    @staticmethod
    async def _publish_ppt_master_export(graph_request, prior_filenames, config=None, sandbox=None) -> None:
        if sandbox is not None:
            from apps.opspilot.services.ppt_master_runtime import current_ppt_run
            from apps.opspilot.services.python_sandbox.ppt import sync_ppt_workspace

            workspace = current_ppt_run(graph_request)
            if workspace is not None:
                await asyncio.to_thread(sync_ppt_workspace, sandbox, workspace)
        # 登记附件会写数据库。ASGI 请求里直接调用会抛 SynchronousOnlyOperation，下载卡片就出不来。
        await sync_to_async(publish_latest_export, thread_sensitive=True)(graph_request, prior_filenames)
        event = getattr(graph_request, "_ppt_download_event", None)
        if not isinstance(event, dict) or config is None:
            return
        try:
            await adispatch_custom_event("report_file_download", event, config=config)
        except Exception as exc:
            logger.warning("ppt download event failed error_type=%s", type(exc).__name__)

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

        仅供旧本地后端的独立调用方使用；正式智能体运行路径不再调用本函数。
        统一容器的依赖安装由 ContainerSkillBackend._install_dependencies 负责。

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
            if not isinstance(pkg, dict) or is_ppt_master_package(pkg):
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
            if not isinstance(pkg, dict) or is_ppt_master_package(pkg):
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
            if not isinstance(pkg, dict) or is_ppt_master_package(pkg):
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
            # 子进程 Python 默认也用 UTF-8。父进程读管道的解码在 utf8_local_shell。
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
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
    def _cleanup_sandbox(sandbox_dir: str | None) -> None:
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
