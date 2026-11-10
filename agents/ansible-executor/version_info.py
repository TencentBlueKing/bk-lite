"""识别 ansible-executor 二进制的版本行。

打包时由 PyInstaller spec 把 git SHA、构建时间和能力标记写进
``version_stamp.py``。源码直接运行时，unknown 的 SHA 与能力标记改为
查看当前树；构建时间只在打包时写入。
"""

import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_SHA_RE = re.compile(r"[0-9a-f]{40}")
_STAMP_NAME = "version_stamp.py"


@dataclass(frozen=True)
class BuildIdentity:
    git_sha: str
    build_timestamp: str
    encode_adhoc_module_args: str
    linux_script_delivery: str


def utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head(source_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-c", "safe.directory=*", "-C", str(source_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    sha = completed.stdout.strip().lower()
    if completed.returncode != 0 or not _SHA_RE.fullmatch(sha):
        return None
    return sha


def resolve_git_sha(source_root: Path) -> str:
    """优先用当前树的 HEAD。脱离 git 的打包副本再读 ``ANSIBLE_EXECUTOR_GIT_SHA``。"""
    checkout = _git_head(source_root)
    if checkout and _SHA_RE.fullmatch(checkout.lower()):
        return checkout.lower()
    override = os.environ.get("ANSIBLE_EXECUTOR_GIT_SHA", "").strip().lower()
    if _SHA_RE.fullmatch(override):
        return override
    return "unknown"


def _drop_loaded_stamp(path: Path) -> None:
    loaded = sys.modules.get("version_stamp")
    loaded_file = getattr(loaded, "__file__", None)
    if loaded_file and Path(loaded_file).resolve() == path.resolve():
        sys.modules.pop("version_stamp", None)


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return None


def _function(tree: ast.AST, name: str) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _has_constant(node: ast.AST, value: str) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and child.value == value:
            return True
    return False


def _imports_name(tree: ast.AST, module: str, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module and any(alias.name == name for alias in node.names):
            return True
    return False


def _references_name(node: ast.AST, name: str) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == name:
            return True
    return False


def _flag(present: bool) -> str:
    return "yes" if present else "no"


def detect_capabilities(source_root: Path) -> tuple[str, str]:
    """从当前树判断已有能力，不改变运行行为。

    ``encode_adhoc_module_args``：raw 模块参数会写成 JSON ``_raw_params``。
    ``linux_script_delivery``：远程脚本走文件投递，而不是塞进命令参数。
    """
    root = Path(source_root)
    runner = _parse(root / "service" / "ansible_runner.py")
    encode = False
    if runner is not None:
        function = _function(runner, "encode_adhoc_module_args")
        encode = function is not None and _has_constant(function, "_raw_params")

    delivery_tree = _parse(root / "service" / "linux_script_delivery.py")
    remote_tree = _parse(root / "service" / "remote_shell_stream.py")
    delivery = False
    if delivery_tree is not None and remote_tree is not None:
        copy_script = _function(delivery_tree, "copy_script_to_hosts")
        remote_stream = _function(remote_tree, "run_remote_shell_stream")
        delivery = (
            copy_script is not None
            and remote_stream is not None
            and _imports_name(remote_tree, "service.linux_script_delivery", "copy_script_to_hosts")
            and _references_name(remote_stream, "copy_script_to_hosts")
        )
    return _flag(encode), _flag(delivery)


def resolve_build_identity(source_root: Path) -> BuildIdentity:
    root = Path(source_root)
    encode, delivery = detect_capabilities(root)
    return BuildIdentity(
        git_sha=resolve_git_sha(root),
        build_timestamp=utc_timestamp(),
        encode_adhoc_module_args=encode,
        linux_script_delivery=delivery,
    )


def format_version_line(identity: BuildIdentity) -> str:
    return (
        f"ansible-executor git={identity.git_sha} built={identity.build_timestamp} "
        f"encode_adhoc_module_args={identity.encode_adhoc_module_args} "
        f"linux_script_delivery={identity.linux_script_delivery}"
    )


def current_version_line() -> str:
    import version_stamp

    git_sha = version_stamp.GIT_SHA
    build_timestamp = version_stamp.BUILD_TIMESTAMP
    encode = version_stamp.ENCODE_ADHOC_MODULE_ARGS
    delivery = version_stamp.LINUX_SCRIPT_DELIVERY
    if not getattr(sys, "frozen", False):
        root = Path(__file__).resolve().parent
        if git_sha == "unknown":
            git_sha = resolve_git_sha(root)
        if encode == "unknown" or delivery == "unknown":
            live_encode, live_delivery = detect_capabilities(root)
            if encode == "unknown":
                encode = live_encode
            if delivery == "unknown":
                delivery = live_delivery
    return format_version_line(
        BuildIdentity(
            git_sha=git_sha,
            build_timestamp=build_timestamp,
            encode_adhoc_module_args=encode,
            linux_script_delivery=delivery,
        )
    )


def render_version_stamp_source(identity: BuildIdentity) -> str:
    return "\n".join(
        [
            '"""Baked by the ansible-executor PyInstaller spec. Do not edit."""',
            f"GIT_SHA = {identity.git_sha!r}",
            f"BUILD_TIMESTAMP = {identity.build_timestamp!r}",
            f"ENCODE_ADHOC_MODULE_ARGS = {identity.encode_adhoc_module_args!r}",
            f"LINUX_SCRIPT_DELIVERY = {identity.linux_script_delivery!r}",
            "",
        ]
    )


def bake_version_stamp(source_root: Path) -> bytes:
    """把版本常量写进打包树，返回原文件字节供调用方恢复。"""
    root = Path(source_root)
    path = root / _STAMP_NAME
    original = path.read_bytes() if path.is_file() else b""
    identity = resolve_build_identity(root)
    if identity.git_sha == "unknown":
        raise RuntimeError("Unable to resolve source git SHA to bake into ansible-executor")
    path.write_bytes(render_version_stamp_source(identity).encode("utf-8"))
    _drop_loaded_stamp(path)
    return original


def restore_version_stamp(source_root: Path, original: bytes) -> None:
    path = Path(source_root) / _STAMP_NAME
    if original:
        path.write_bytes(original)
    elif path.exists():
        path.unlink()
    _drop_loaded_stamp(path)
