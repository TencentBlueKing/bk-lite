"""Normalize uploaded source paths without turning folders into Wiki directories."""

import hashlib
import re
import unicodedata
from pathlib import PurePosixPath

from apps.opspilot.models import WikiDirectory


class MaterialSourceError(ValueError):
    pass


def normalize_source_relative_path(value, *, fallback_name=""):
    raw = unicodedata.normalize("NFKC", str(value or fallback_name or "")).strip().replace("\\", "/")
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise MaterialSourceError("source_relative_path 必须是相对路径")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise MaterialSourceError("source_relative_path 包含非法路径段")
    normalized = path.as_posix()
    if len(normalized) > 1024:
        raise MaterialSourceError("source_relative_path 超过 1024 字符")
    return normalized


def source_metadata(knowledge_base, *, source_relative_path, fallback_name="", classification_root_id=None):
    path = normalize_source_relative_path(source_relative_path, fallback_name=fallback_name)
    folder = PurePosixPath(path).parent.as_posix()
    if folder == ".":
        folder = ""
    directory = None
    if classification_root_id not in (None, ""):
        try:
            directory_id = int(classification_root_id)
        except (TypeError, ValueError) as error:
            raise MaterialSourceError("classification_root_id 必须为整数") from error
        directory = WikiDirectory.objects.filter(
            pk=directory_id,
            knowledge_base=knowledge_base,
            status="active",
        ).first()
        if directory is None:
            raise MaterialSourceError("classification root 不存在或不属于当前知识库")
    identity_source = f"{knowledge_base.pk}:{path.casefold()}".encode("utf-8")
    return {
        "source_relative_path": path,
        "source_folder_path": folder,
        "source_identity": hashlib.sha256(identity_source).hexdigest(),
        "classification_root": directory,
    }


__all__ = ["MaterialSourceError", "normalize_source_relative_path", "source_metadata"]
