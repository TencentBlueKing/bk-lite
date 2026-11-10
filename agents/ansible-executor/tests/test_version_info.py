import importlib.util
from pathlib import Path

import pytest

import version_info
import version_stamp
from version_info import PRODUCT_VERSION, bake_version_stamp, current_version_line, resolve_git_sha, restore_version_stamp


def test_product_version_is_checked_in():
    assert PRODUCT_VERSION == "1.0.0"
    source = Path(version_info.__file__).read_text(encoding="utf-8")
    assert 'PRODUCT_VERSION = "1.0.0"' in source


def test_resolve_git_sha_prefers_checkout_and_falls_back_to_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANSIBLE_EXECUTOR_GIT_SHA", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    monkeypatch.setattr(version_info, "_git_head", lambda _root: "ABCDEF0123456789ABCDEF0123456789ABCDEF01")
    assert resolve_git_sha(tmp_path) == "abcdef0123456789abcdef0123456789abcdef01"

    monkeypatch.setattr(version_info, "_git_head", lambda _root: None)
    assert resolve_git_sha(tmp_path) == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    monkeypatch.setenv("ANSIBLE_EXECUTOR_GIT_SHA", "short")
    assert resolve_git_sha(tmp_path) == "unknown"


def test_bake_writes_constants_and_restore_puts_the_original_bytes_back(tmp_path: Path, monkeypatch):
    stamp = tmp_path / "version_stamp.py"
    original = b"GIT_SHA = 'unknown'\n"
    stamp.write_bytes(original)
    monkeypatch.setattr(version_info, "resolve_git_sha", lambda _root: "0123456789abcdef0123456789abcdef01234567")
    monkeypatch.setattr(version_info, "utc_timestamp", lambda: "2026-11-10T01:49:00Z")

    saved = bake_version_stamp(tmp_path)
    spec = importlib.util.spec_from_file_location("baked_version_stamp", stamp)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert saved == original
    assert module.GIT_SHA == "0123456789abcdef0123456789abcdef01234567"
    assert module.BUILD_TIMESTAMP == "2026-11-10T01:49:00Z"
    assert not hasattr(module, "ENCODE_ADHOC_MODULE_ARGS")
    assert not hasattr(module, "LINUX_SCRIPT_DELIVERY")
    restore_version_stamp(tmp_path, saved)
    assert stamp.read_bytes() == original


def test_bake_does_not_touch_the_stamp_when_the_sha_is_unknown(tmp_path: Path, monkeypatch):
    stamp = tmp_path / "version_stamp.py"
    stamp.write_bytes(b"original\n")
    monkeypatch.setattr(version_info, "resolve_git_sha", lambda _root: "unknown")
    with pytest.raises(RuntimeError, match="git SHA"):
        bake_version_stamp(tmp_path)
    assert stamp.read_bytes() == b"original\n"


def test_frozen_binary_uses_baked_constants_only(monkeypatch):
    monkeypatch.setattr(version_info.sys, "frozen", True, raising=False)
    monkeypatch.setenv("ANSIBLE_EXECUTOR_GIT_SHA", "ffffffffffffffffffffffffffffffffffffffff")
    monkeypatch.setattr(version_stamp, "GIT_SHA", "0123456789abcdef0123456789abcdef01234567")
    monkeypatch.setattr(version_stamp, "BUILD_TIMESTAMP", "2026-11-10T01:49:00Z")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("packaged version must use baked constants")

    monkeypatch.setattr(version_info, "resolve_git_sha", forbidden)
    assert current_version_line() == ("ansible-executor version=1.0.0 git=0123456789abcdef0123456789abcdef01234567 built=2026-11-10T01:49:00Z")


def test_source_checkout_fills_unknown_sha_and_keeps_build_time_unknown(monkeypatch):
    monkeypatch.setattr(version_stamp, "GIT_SHA", "unknown")
    monkeypatch.setattr(version_stamp, "BUILD_TIMESTAMP", "unknown")
    monkeypatch.setattr(version_info, "resolve_git_sha", lambda _root: "0123456789abcdef0123456789abcdef01234567")
    line = current_version_line()
    assert line == "ansible-executor version=1.0.0 git=0123456789abcdef0123456789abcdef01234567 built=unknown"
    assert "encode_adhoc_module_args" not in line
    assert "linux_script_delivery" not in line
