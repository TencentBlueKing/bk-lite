# -*- coding: utf-8 -*-
"""cli.py 单测（用 fake 容器 + fake collector）"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.collect_fixtures import cli as cli_mod  # noqa: E402


def test_list_prints_sorted_models(capsys):
    rc = cli_mod.main(["--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "mysql" in out
    lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("可用")]
    assert lines == sorted(lines)


def test_dispatch_mysql_calls_full_pipeline(monkeypatch):
    """单对象模式：cli 应按顺序调 start/wait/exec/collect/dump/remove。"""
    fake_handle = MagicMock()
    fake_handle.container.short_id = "cid123"

    fake_raw = {"version": "8.0.36"}

    calls = []

    def fake_start(spec, docker_client=None, privileged=False):
        calls.append("start")
        return fake_handle

    def fake_wait(handle, spec):
        calls.append("wait")

    def fake_exec(handle, spec):
        calls.append("exec")

    def fake_collect(spec, handle=None):
        calls.append("collect")
        return fake_raw

    def fake_dump(model_id, raw_stdout, container_meta, params, out_dir=None):
        calls.append("dump")
        return Path(f"/tmp/{model_id}.json")

    def fake_remove(handle):
        calls.append("remove")

    monkeypatch.setattr(cli_mod, "start_container", fake_start)
    monkeypatch.setattr(cli_mod, "wait_ready", fake_wait)
    monkeypatch.setattr(cli_mod, "exec_init", fake_exec)
    monkeypatch.setattr(cli_mod, "collect_once", fake_collect)
    monkeypatch.setattr(cli_mod, "dump", fake_dump)
    monkeypatch.setattr(cli_mod, "remove", fake_remove)

    rc = cli_mod.main(["mysql"])

    assert rc == 0
    assert calls == ["start", "wait", "exec", "collect", "dump", "remove"]


def test_dispatch_removes_container_even_on_collect_failure(monkeypatch):
    """collect 抛异常时,仍要 remove 容器（try/finally）。"""
    fake_handle = MagicMock()
    fake_handle.container.short_id = "cid123"

    removed = []

    def fake_start(spec, docker_client=None, privileged=False):
        return fake_handle

    def fake_remove(handle):
        removed.append(handle)

    def fake_collect(spec, handle=None):
        raise RuntimeError("采集失败")

    monkeypatch.setattr(cli_mod, "start_container", fake_start)
    monkeypatch.setattr(cli_mod, "wait_ready", lambda h, s: None)
    monkeypatch.setattr(cli_mod, "exec_init", lambda h, s: None)
    monkeypatch.setattr(cli_mod, "collect_once", fake_collect)
    monkeypatch.setattr(cli_mod, "dump", lambda **k: Path("/tmp/x.json"))
    monkeypatch.setattr(cli_mod, "remove", fake_remove)

    rc = cli_mod.main(["mysql"])

    assert rc != 0
    assert removed == [fake_handle]


def test_dispatch_unknown_model_returns_error():
    rc = cli_mod.main(["not_a_real_model"])
    assert rc == 2


def test_no_args_prints_help_and_returns_error():
    rc = cli_mod.main([])
    assert rc == 2


def test_dispatch_passes_handle_to_shell_collector(monkeypatch):
    """shell 入口时,collect_once 必须接收 handle。"""
    fake_handle = MagicMock()
    fake_handle.container.short_id = "cid123"

    calls = []

    def fake_collect(spec, handle=None):
        calls.append(("collect", handle))
        return {"x": 1}

    monkeypatch.setattr(cli_mod, "start_container", lambda spec, docker_client=None, privileged=False: fake_handle)
    monkeypatch.setattr(cli_mod, "wait_ready", lambda h, s: None)
    monkeypatch.setattr(cli_mod, "exec_init", lambda h, s: None)
    monkeypatch.setattr(cli_mod, "collect_once", fake_collect)
    monkeypatch.setattr(cli_mod, "dump", lambda **k: Path("/tmp/x.json"))
    monkeypatch.setattr(cli_mod, "remove", lambda h: None)

    # catalog 暂时只有 mysql (python 入口), 这里手动加个 shell 的临时 model 测试
    from tests.collect_fixtures.catalog import MODEL_SPECS, Spec
    import dataclasses
    MODEL_SPECS["__test_shell__"] = dataclasses.replace(
        next(iter(MODEL_SPECS.values())),
        model_id="__test_shell__",
        entry_type="shell",
        entry_module=None,
        entry_class=None,
        init_script="__test__.sh",
    )
    try:
        rc = cli_mod.main(["__test_shell__"])
        assert rc == 0
        assert calls == [("collect", fake_handle)]  # handle 传给 collect
    finally:
        del MODEL_SPECS["__test_shell__"]


def test_dispatch_ssh_model_calls_full_pipeline(monkeypatch):
    """ssh 入口模式：start → bootstrap_sshd(docker exec) → wait_ssh → install → start_services → wait_service_ready → collect_ssh → dump → remove"""
    from tests.collect_fixtures.docker_lifecycle import ContainerHandle

    fake_handle = ContainerHandle(model_id="nginx", container=MagicMock())
    calls = []
    def fake_start(spec, docker_client=None, privileged=False):
        calls.append(("start", privileged))
        return fake_handle
    def fake_bootstrap_sshd(handle, spec):
        calls.append("bootstrap_sshd")
    def fake_wait_ssh(handle, spec, ssh_password):
        calls.append("wait_ssh")
    def fake_install(handle, spec, ssh_password):
        calls.append("install")
    def fake_start_services(handle, spec, ssh_password):
        calls.append("start_services")
    def fake_wait_service(handle, spec, ssh_password):
        calls.append("wait_service_ready")
    def fake_collect(spec, handle=None):
        calls.append("collect_ssh")
        return {"version": "1.18"}
    def fake_dump(model_id, raw_stdout, container_meta, params, out_dir=None):
        calls.append("dump")
        return Path(f"/tmp/{model_id}.json")
    def fake_remove(handle):
        calls.append("remove")

    monkeypatch.setattr(cli_mod, "start_container", fake_start)
    monkeypatch.setattr(cli_mod, "bootstrap_sshd_in_container", fake_bootstrap_sshd)
    monkeypatch.setattr(cli_mod, "wait_ssh_ready", fake_wait_ssh)
    monkeypatch.setattr(cli_mod, "install_services", fake_install)
    monkeypatch.setattr(cli_mod, "start_services", fake_start_services)
    monkeypatch.setattr(cli_mod, "wait_service_ready", fake_wait_service)
    monkeypatch.setattr(cli_mod, "collect_once", fake_collect)
    monkeypatch.setattr(cli_mod, "dump", fake_dump)
    monkeypatch.setattr(cli_mod, "remove", fake_remove)

    # 在 catalog 临时塞一个 ssh 条目
    from tests.collect_fixtures.catalog import MODEL_SPECS, Spec
    from dataclasses import replace as _replace
    base = next(iter(MODEL_SPECS.values()))
    MODEL_SPECS["__test_ssh__"] = _replace(
        base,
        model_id="__test_ssh__",
        entry_type="ssh",
        vm_ssh_password="x",
        install_commands=("apt-get update",),
        start_commands=("nginx",),
        ready_check={"command": "true", "timeout": 5},
    )
    try:
        rc = cli_mod.main(["__test_ssh__"])
        assert rc == 0
        # 关键顺序: start → bootstrap_sshd → wait_ssh → install → start_services → wait_service_ready → collect_ssh → dump → remove
        assert calls == [
            ("start", False),
            "bootstrap_sshd",
            "wait_ssh",
            "install",
            "start_services",
            "wait_service_ready",
            "collect_ssh",
            "dump",
            "remove",
        ]
    finally:
        del MODEL_SPECS["__test_ssh__"]


def test_dispatch_removes_container_on_install_failure(monkeypatch):
    """install_services 抛异常时,仍要 remove 容器（try/finally）。"""
    from tests.collect_fixtures.docker_lifecycle import ContainerHandle
    fake_handle = ContainerHandle(model_id="nginx", container=MagicMock())
    removed = []

    monkeypatch.setattr(cli_mod, "start_container", lambda spec, docker_client=None, privileged=False: fake_handle)
    monkeypatch.setattr(cli_mod, "bootstrap_sshd_in_container", lambda h, s: None)
    monkeypatch.setattr(cli_mod, "wait_ssh_ready", lambda h, s, p: None)
    def _raise_install(h, s, p):
        raise RuntimeError("apt 失败")
    monkeypatch.setattr(cli_mod, "install_services", _raise_install)
    monkeypatch.setattr(cli_mod, "remove", lambda h: removed.append(h))

    from tests.collect_fixtures.catalog import MODEL_SPECS, Spec
    from dataclasses import replace as _replace
    base = next(iter(MODEL_SPECS.values()))
    MODEL_SPECS["__test_ssh2__"] = _replace(
        base,
        model_id="__test_ssh2__",
        entry_type="ssh",
        vm_ssh_password="x",
        install_commands=("apt-get update",),
    )
    try:
        rc = cli_mod.main(["__test_ssh2__"])
        assert rc != 0
        assert removed == [fake_handle]  # 容器已被销毁
    finally:
        del MODEL_SPECS["__test_ssh2__"]