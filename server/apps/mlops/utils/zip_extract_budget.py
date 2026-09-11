"""图片数据集发布 ZIP 解压预算：按实际写出字节与成员数计数。"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

from apps.core.logger import mlops_logger as logger

ZIP_EXTRACT_CHUNK_SIZE = 64 * 1024

ENV_MODE = "MLOPS_DATASET_ZIP_BUDGET_MODE"
ENV_MAX_MEMBERS = "MLOPS_DATASET_ZIP_MAX_MEMBERS"
ENV_MAX_MEMBER_BYTES = "MLOPS_DATASET_ZIP_MAX_MEMBER_BYTES"
ENV_MAX_TOTAL_BYTES = "MLOPS_DATASET_ZIP_MAX_TOTAL_BYTES"

DEFAULT_MODE = "enforce"
DEFAULT_MAX_MEMBERS = 50_000
DEFAULT_MAX_MEMBER_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024

_ALLOWED_MODES = {"observe", "enforce"}


class ZipExtractBudgetExceeded(ValueError):
    """ZIP 解压超出成员数或实际写出字节预算。"""

    def __init__(self, kind: str, actual: int, limit: int, member: str = ""):
        self.kind = kind
        self.actual = actual
        self.limit = limit
        self.member = member
        super().__init__(
            f"dataset zip extract budget exceeded kind={kind} actual={actual} limit={limit} member={member}"
        )


class ZipExtractUnsafePath(ValueError):
    """ZIP 成员路径逃逸或非法。"""


class ZipExtractBudget:
    """跨 train/val/test 共用的解压预算。"""

    def __init__(self, *, mode: str, max_members: int, max_member_bytes: int, max_total_bytes: int):
        self.mode = mode
        self.max_members = max_members
        self.max_member_bytes = max_member_bytes
        self.max_total_bytes = max_total_bytes
        self.member_count = 0
        self.total_bytes = 0
        self._logged: set[tuple[str, str]] = set()

    @classmethod
    def from_env(cls) -> ZipExtractBudget:
        mode_raw = (os.getenv(ENV_MODE, DEFAULT_MODE) or DEFAULT_MODE).strip().lower()
        if mode_raw not in _ALLOWED_MODES:
            logger.warning(
                "event=dataset_zip_budget_invalid_mode value=%s fallback=%s",
                mode_raw,
                DEFAULT_MODE,
            )
            mode_raw = DEFAULT_MODE
        return cls(
            mode=mode_raw,
            max_members=_env_positive_int(ENV_MAX_MEMBERS, DEFAULT_MAX_MEMBERS),
            max_member_bytes=_env_positive_int(ENV_MAX_MEMBER_BYTES, DEFAULT_MAX_MEMBER_BYTES),
            max_total_bytes=_env_positive_int(ENV_MAX_TOTAL_BYTES, DEFAULT_MAX_TOTAL_BYTES),
        )

    def note_member(self, member: str) -> None:
        next_count = self.member_count + 1
        self._check("members", next_count, self.max_members, member)
        self.member_count = next_count

    def note_written_bytes(self, written: int, member: str) -> None:
        self._check("member_bytes", written, self.max_member_bytes, member)
        self._check("total_bytes", self.total_bytes + written, self.max_total_bytes, member)

    def commit_written_bytes(self, written: int) -> None:
        self.total_bytes += written

    def _check(self, kind: str, actual: int, limit: int, member: str) -> None:
        if actual <= limit:
            return
        key = (kind, member)
        if key not in self._logged:
            self._logged.add(key)
            logger.warning(
                "event=dataset_zip_budget_exceeded kind=%s mode=%s actual=%s limit=%s member=%s",
                kind,
                self.mode,
                actual,
                limit,
                member,
            )
        if self.mode == "enforce":
            raise ZipExtractBudgetExceeded(kind, actual, limit, member)


def extract_zip_with_budget(zip_path: str | Path, dest_dir: str | Path, budget: ZipExtractBudget) -> None:
    """按块解压 ZIP，累计实际写出字节；enforce 超额时清理目标目录并抛错。"""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            for info in archive.infolist():
                member_name = info.filename or ""
                target = _resolve_member_path(dest_resolved, member_name)
                budget.note_member(member_name)
                if info.is_dir() or member_name.endswith("/") or member_name.endswith("\\"):
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                # ZipExtFile 按 ZipInfo.file_size 截断；预算只认实际写出字节，打开前去掉该截断。
                info.file_size = _uncapped_file_size(info.file_size, budget)
                with archive.open(info, "r") as source, open(target, "wb") as output:
                    while True:
                        chunk = source.read(ZIP_EXTRACT_CHUNK_SIZE)
                        if not chunk:
                            break
                        written += len(chunk)
                        budget.note_written_bytes(written, member_name)
                        output.write(chunk)
                budget.commit_written_bytes(written)
    except Exception:
        _clear_extracted_tree(dest_resolved)
        raise


def _uncapped_file_size(declared_size: int, budget: ZipExtractBudget) -> int:
    declared = max(int(declared_size or 0), 0)
    if budget.mode != "enforce":
        return max(declared, (1 << 62) - 1)
    remaining_total = max(0, budget.max_total_bytes - budget.total_bytes)
    read_cap = min(budget.max_member_bytes, remaining_total) + ZIP_EXTRACT_CHUNK_SIZE
    return max(declared, read_cap)


def _env_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("event=dataset_zip_budget_invalid_int env=%s fallback=%s", name, default)
        return default
    if value <= 0:
        logger.warning("event=dataset_zip_budget_invalid_int env=%s fallback=%s", name, default)
        return default
    return value


def _resolve_member_path(dest_resolved: Path, member_name: str) -> Path:
    if not member_name or "\x00" in member_name:
        raise ZipExtractUnsafePath("dataset zip member path is empty or contains NUL")
    normalized = member_name.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("//"):
        raise ZipExtractUnsafePath(f"dataset zip member path is absolute member={member_name}")
    if len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/":
        raise ZipExtractUnsafePath(f"dataset zip member path is absolute member={member_name}")
    target = (dest_resolved / normalized).resolve()
    if not target.is_relative_to(dest_resolved):
        raise ZipExtractUnsafePath(f"dataset zip member path escapes dest member={member_name}")
    return target


def _clear_extracted_tree(dest: Path) -> None:
    if not dest.exists() or not dest.is_dir():
        return
    for child in dest.iterdir():
        try:
            if child.is_symlink() or child.is_file():
                child.unlink()
            else:
                shutil.rmtree(child)
        except OSError:
            logger.warning("event=dataset_zip_extract_cleanup_failed path=%s", child)
