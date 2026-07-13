# -*- coding: utf-8 -*-
"""dump.py 单测"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.collect_fixtures.dump import dump, mask_sensitive  # noqa: E402


def test_dump_creates_file_with_required_fields(tmp_path: Path):
    out = dump(
        model_id="mysql",
        raw_stdout={"version": "8.0.36"},
        container_meta={"container_id": "abc123", "image": "mysql:8.0"},
        params={"host": "127.0.0.1", "password": "rootpw"},
        out_dir=tmp_path,
    )
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["model_id"] == "mysql"
    assert data["raw_stdout"] == {"version": "8.0.36"}
    assert "captured_at" in data
    assert data["params"]["password"] == "***"  # 敏感字段已掩码
    assert data["container_meta"]["container_id"] == "abc123"


def test_dump_atomic_write_no_partial_file_on_failure(tmp_path: Path, monkeypatch):
    """确保原子写：失败时不会出现半成品文件。"""
    from tests.collect_fixtures import dump as dump_mod

    # 让 os.fsync 失败 → 触发回滚（json.dump 在新版本 Python 上走 C 路径，
    # 不会经过 json.dumps 的 patch 点；fsync 永远在 Python 层）
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated dump failure")

    monkeypatch.setattr(dump_mod.os, "fsync", _boom)

    with pytest.raises(RuntimeError):
        dump(
            model_id="mysql",
            raw_stdout={"x": 1},
            container_meta={},
            params={},
            out_dir=tmp_path,
        )
    # 不应留下任何 .json 文件（包括半成品 .tmp）
    assert list(tmp_path.glob("*.json")) == []
    assert list(tmp_path.glob("*.json.tmp")) == []


def test_mask_sensitive_replaces_passwords():
    raw = {"password": "rootpw", "secret": "abc", "host": "127.0.0.1"}
    masked = mask_sensitive(raw)
    assert masked["password"] == "***"
    assert masked["secret"] == "***"
    assert masked["host"] == "127.0.0.1"


def test_mask_sensitive_handles_nested_dict():
    raw = {"a": {"password": "x", "b": {"token": "y"}}}
    masked = mask_sensitive(raw)
    assert masked["a"]["password"] == "***"
    assert masked["a"]["b"]["token"] == "***"