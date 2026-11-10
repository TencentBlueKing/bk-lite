"""识别 ansible-executor 二进制的版本行。

产品版本写在本文件，随源码入库。PyInstaller spec 只把 git SHA 和构建时间
写进 ``version_stamp.py``。源码直接运行时，unknown 的 SHA 改为当前 HEAD，
构建时间保持 unknown。
"""

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PRODUCT_VERSION = "1.0.0"

_SHA_RE = re.compile(r"[0-9a-f]{40}")
_STAMP_NAME = "version_stamp.py"


@dataclass(frozen=True)
class BuildIdentity:
    git_sha: str
    build_timestamp: str


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


def resolve_build_identity(source_root: Path) -> BuildIdentity:
    root = Path(source_root)
    return BuildIdentity(git_sha=resolve_git_sha(root), build_timestamp=utc_timestamp())


def format_version_line(git_sha: str, build_timestamp: str) -> str:
    return f"ansible-executor version={PRODUCT_VERSION} git={git_sha} built={build_timestamp}"


def current_version_line() -> str:
    import version_stamp

    git_sha = version_stamp.GIT_SHA
    build_timestamp = version_stamp.BUILD_TIMESTAMP
    if not getattr(sys, "frozen", False) and git_sha == "unknown":
        git_sha = resolve_git_sha(Path(__file__).resolve().parent)
    return format_version_line(git_sha, build_timestamp)


def render_version_stamp_source(identity: BuildIdentity) -> str:
    return "\n".join(
        [
            '"""Baked by the ansible-executor PyInstaller spec. Do not edit."""',
            f"GIT_SHA = {identity.git_sha!r}",
            f"BUILD_TIMESTAMP = {identity.build_timestamp!r}",
            "",
        ]
    )


def bake_version_stamp(source_root: Path) -> bytes:
    """把 git SHA 和构建时间写进打包树，返回原文件字节供调用方恢复。"""
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
