"""Disk cache for materialized skill package directories."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any

def _cache_root() -> Path | None:
    cache_root = os.getenv("OPSPILOT_SKILL_MATERIALIZE_CACHE", "")
    if not cache_root.strip():
        return None
    root = Path(cache_root)
    root.mkdir(parents=True, exist_ok=True)
    return root

def build_materialize_cache_key(package: Any) -> str:
    package_id = getattr(package, "id", None) or getattr(package, "pk", None) or "unknown"
    content_hash = getattr(package, "content_hash", None) or getattr(package, "version", None) or ""
    updated_at = getattr(package, "updated_at", None)
    stamp = updated_at.isoformat() if updated_at is not None else "na"
    raw = f"{package_id}:{content_hash}:{stamp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cached_materialize_dir(package: Any) -> Path | None:
    root = _cache_root()
    if root is None:
        return None
    path = root / build_materialize_cache_key(package)
    if path.is_dir() and any(path.iterdir()):
        return path
    return None


def store_materialized_dir(package: Any, source_dir: Path) -> Path | None:
    root = _cache_root()
    if root is None or not source_dir.is_dir():
        return None
    target = root / build_materialize_cache_key(package)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source_dir, target)
    return target


def copy_cached_into(target_dir: Path, cached_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in cached_dir.iterdir():
        dest = target_dir / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
