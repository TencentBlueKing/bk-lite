"""Playbook archive guard helpers."""

from __future__ import annotations

import os
import tarfile
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

PLAYBOOK_ARCHIVE_MAX_SIZE_BYTES = 20 * 1024 * 1024
PLAYBOOK_ARCHIVE_MAX_MEMBERS = 2000
PLAYBOOK_ARCHIVE_MAX_MEMBER_SIZE_BYTES = 5 * 1024 * 1024
PLAYBOOK_ARCHIVE_MAX_EXPANDED_SIZE_BYTES = 50 * 1024 * 1024


@dataclass
class ArchiveInfo:
    archive_type: str
    raw_size: int
    member_count: int
    max_member_size: int
    total_member_size: int


def get_archive_file_size(file_obj) -> int:
    size = getattr(file_obj, "size", None)
    if isinstance(size, int):
        return size

    if hasattr(file_obj, "tell") and hasattr(file_obj, "seek"):
        current = file_obj.tell()
        file_obj.seek(0, os.SEEK_END)
        size = file_obj.tell()
        file_obj.seek(current)
        return size

    raise ValueError("无法确定归档文件大小")


def validate_archive_extension(filename: str) -> None:
    lowered = (filename or "").lower()
    if lowered.endswith((".zip", ".tar.gz", ".tgz")):
        return
    raise ValueError("仅支持 .zip, .tar.gz, .tgz 格式的文件")


@contextmanager
def open_archive(file_obj) -> Generator[tuple[str, zipfile.ZipFile | tarfile.TarFile], None, None]:
    filename = (getattr(file_obj, "name", "") or "").lower()
    file_obj.seek(0)
    if filename.endswith(".zip"):
        with zipfile.ZipFile(file_obj) as archive:
            yield "zip", archive
    elif filename.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=file_obj, mode="r:gz") as archive:
            yield "tar", archive
    else:
        raise ValueError("仅支持 .zip, .tar.gz, .tgz 格式的文件")
    file_obj.seek(0)


def inspect_archive(file_obj) -> ArchiveInfo:
    raw_size = get_archive_file_size(file_obj)
    member_count = 0
    max_member_size = 0
    total_member_size = 0

    with open_archive(file_obj) as (archive_type, archive):
        if archive_type == "zip":
            for member in archive.infolist():
                if member.is_dir():
                    continue
                member_count += 1
                max_member_size = max(max_member_size, member.file_size)
                total_member_size += member.file_size
        else:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                member_count += 1
                max_member_size = max(max_member_size, member.size)
                total_member_size += member.size

    return ArchiveInfo(
        archive_type=archive_type,
        raw_size=raw_size,
        member_count=member_count,
        max_member_size=max_member_size,
        total_member_size=total_member_size,
    )


def enforce_archive_limits(file_obj) -> ArchiveInfo:
    info = inspect_archive(file_obj)
    if info.raw_size > PLAYBOOK_ARCHIVE_MAX_SIZE_BYTES:
        raise ValueError(f"压缩包过大，不支持处理|{info.raw_size}")
    if info.member_count > PLAYBOOK_ARCHIVE_MAX_MEMBERS:
        raise ValueError("压缩包文件数量过多，不支持处理")
    if info.max_member_size > PLAYBOOK_ARCHIVE_MAX_MEMBER_SIZE_BYTES:
        raise ValueError("压缩包内单文件过大，不支持处理")
    if info.total_member_size > PLAYBOOK_ARCHIVE_MAX_EXPANDED_SIZE_BYTES:
        raise ValueError("压缩包解压总量过大，不支持处理")
    return info
