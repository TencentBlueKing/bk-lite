import importlib.util
from pathlib import Path

import pytest

import version_info
import version_stamp
from version_info import bake_version_stamp, current_version_line, detect_capabilities, resolve_git_sha, restore_version_stamp


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_tree(root: Path, *, encode: bool = True, delivery: bool = True) -> None:
    raw_params = '{"_raw_params": module_args}' if encode else "module_args"
    _write(
        root / "service" / "ansible_runner.py",
        f"def encode_adhoc_module_args(module, module_args):\n    return {raw_params}\n",
    )
    if delivery:
        delivery_source = "def copy_script_to_hosts(script, remote, credentials, directory):\n    return None\n"
    else:
        delivery_source = "def unused():\n    return None\n"
    _write(root / "service" / "linux_script_delivery.py", delivery_source)
    reference = "transfer = copy_script_to_hosts" if delivery else "transfer = None"
    _write(
        root / "service" / "remote_shell_stream.py",
        f"from service.linux_script_delivery import copy_script_to_hosts\ndef run_remote_shell_stream():\n    {reference}\n",
    )


def test_this_tree_reports_shipped_capabilities():
    encode, delivery = detect_capabilities(Path(__file__).resolve().parent.parent)
    assert (encode, delivery) == ("yes", "yes")


def test_capability_flags_follow_the_tree(tmp_path: Path):
    _write_tree(tmp_path)
    assert detect_capabilities(tmp_path) == ("yes", "yes")
    _write_tree(tmp_path, encode=False, delivery=False)
    assert detect_capabilities(tmp_path) == ("no", "no")


def test_resolve_git_sha_prefers_checkout_and_falls_back_to_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANSIBLE_EXECUTOR_GIT_SHA", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    monkeypatch.setattr(version_info, "_git_head", lambda _root: "ABCDEF0123456789ABCDEF0123456789ABCDEF01")
    assert resolve_git_sha(tmp_path) == "abcdef0123456789abcdef0123456789abcdef01"

    monkeypatch.setattr(version_info, "_git_head", lambda _root: None)
    assert resolve_git_sha(tmp_path) == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    monkeypatch.setenv("ANSIBLE_EXECUTOR_GIT_SHA", "short")
    assert resolve_git_sha(tmp_path) == "unknown"


def test_bake_writes_constants_and_restore_puts_the_original_bytes_back(tmp_path: Path, monkeypatch):
    _write_tree(tmp_path)
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
    assert module.ENCODE_ADHOC_MODULE_ARGS == "yes"
    assert module.LINUX_SCRIPT_DELIVERY == "yes"
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
    monkeypatch.setattr(version_stamp, "ENCODE_ADHOC_MODULE_ARGS", "yes")
    monkeypatch.setattr(version_stamp, "LINUX_SCRIPT_DELIVERY", "yes")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("packaged version must use baked constants")

    monkeypatch.setattr(version_info, "resolve_git_sha", forbidden)
    monkeypatch.setattr(version_info, "detect_capabilities", forbidden)
    assert current_version_line() == (
        "ansible-executor git=0123456789abcdef0123456789abcdef01234567 "
        "built=2026-11-10T01:49:00Z encode_adhoc_module_args=yes linux_script_delivery=yes"
    )


def test_source_checkout_fills_unknown_fields_and_keeps_build_time_unknown(monkeypatch):
    for name, value in (
        ("GIT_SHA", "unknown"),
        ("BUILD_TIMESTAMP", "unknown"),
        ("ENCODE_ADHOC_MODULE_ARGS", "unknown"),
        ("LINUX_SCRIPT_DELIVERY", "unknown"),
    ):
        monkeypatch.setattr(version_stamp, name, value)
    monkeypatch.setattr(version_info, "resolve_git_sha", lambda _root: "0123456789abcdef0123456789abcdef01234567")
    monkeypatch.setattr(version_info, "detect_capabilities", lambda _root: ("yes", "no"))
    assert current_version_line() == (
        "ansible-executor git=0123456789abcdef0123456789abcdef01234567 built=unknown encode_adhoc_module_args=yes linux_script_delivery=no"
    )
