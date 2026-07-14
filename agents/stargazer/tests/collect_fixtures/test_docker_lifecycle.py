# -*- coding: utf-8 -*-
"""docker_lifecycle.py 单测（用 fake DockerClient 注入）"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.collect_fixtures.catalog import Spec  # noqa: E402
from tests.collect_fixtures.docker_lifecycle import (  # noqa: E402
    ContainerHandle,
    exec_init,
    install_services,
    remove,
    start_container,
    start_services,
    wait_ready,
    wait_service_ready,
    wait_ssh_ready,
)


def _spec():
    return Spec(
        model_id="mysql",
        image="mysql:8.0",
        ports={"3306/tcp": 13306},
        env={"MYSQL_ROOT_PASSWORD": "rootpw"},
        wait_strategy={"type": "tcp", "port": 13306, "timeout": 5},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.mysql.mysql_info",
        entry_class="MysqlInfo",
    )


def test_start_container_returns_handle_and_calls_run():
    fake_container = MagicMock()
    fake_container.id = "cid123"
    fake_container.short_id = "cid123"

    fake_client = MagicMock()
    fake_client.containers.run.return_value = fake_container

    handle = start_container(_spec(), docker_client=fake_client)

    assert isinstance(handle, ContainerHandle)
    assert handle.container is fake_container
    assert handle.model_id == "mysql"

    fake_client.containers.run.assert_called_once()
    kwargs = fake_client.containers.run.call_args.kwargs
    assert kwargs["image"] == "mysql:8.0"
    assert kwargs["detach"] is True
    assert kwargs["environment"] == {"MYSQL_ROOT_PASSWORD": "rootpw"}
    assert kwargs["ports"] == {"3306/tcp": 13306}
    assert kwargs["remove"] is True  # 容器退出即清理


def test_remove_calls_container_remove():
    fake_container = MagicMock()
    handle = ContainerHandle(model_id="mysql", container=fake_container)

    remove(handle)

    fake_container.remove.assert_called_once_with(force=True)


def test_remove_swallows_already_removed():
    """容器已被 --rm 自动清理时，remove() 不应抛异常。"""
    import docker.errors

    fake_container = MagicMock()
    fake_container.remove.side_effect = docker.errors.NotFound("not found")
    handle = ContainerHandle(model_id="mysql", container=fake_container)

    # 不应抛异常
    remove(handle)


def test_wait_ready_tcp_succeeds_when_port_open():
    """TCP wait 策略：端口可连接即视为就绪。"""
    import dataclasses

    fake_container = MagicMock()
    handle = ContainerHandle(model_id="mysql", container=fake_container)

    spec = dataclasses.replace(
        _spec(),
        wait_strategy={"type": "tcp", "port": 13306, "timeout": 5, "interval": 0.1},
    )

    call_count = {"n": 0}

    def fake_open(host, port, timeout=1.0):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise ConnectionRefusedError("not ready yet")
        return None

    from tests.collect_fixtures import docker_lifecycle as dl_mod

    original = dl_mod._tcp_probe
    dl_mod._tcp_probe = fake_open
    try:
        wait_ready(handle, spec)
    finally:
        dl_mod._tcp_probe = original

    assert call_count["n"] >= 3  # 至少重试了 3 次


def test_wait_ready_tcp_raises_on_timeout():
    import dataclasses

    fake_container = MagicMock()
    handle = ContainerHandle(model_id="mysql", container=fake_container)
    spec = dataclasses.replace(
        _spec(),
        wait_strategy={"type": "tcp", "port": 13306, "timeout": 0.2, "interval": 0.05},
    )

    from tests.collect_fixtures import docker_lifecycle as dl_mod

    def always_fail(*args, **kwargs):
        raise ConnectionRefusedError("nope")

    original = dl_mod._tcp_probe
    dl_mod._tcp_probe = always_fail
    try:
        with pytest.raises(TimeoutError, match="容器.*未就绪"):
            wait_ready(handle, spec)
    finally:
        dl_mod._tcp_probe = original


def test_exec_init_runs_sql_via_tar_and_exec():
    """init_script 通过 put_archive + exec_run 注入并执行。"""
    import dataclasses
    import tempfile

    fake_container = MagicMock()
    fake_container.exec_run.return_value = MagicMock(exit_code=0, output=b"")
    fake_container.put_archive.return_value = True
    handle = ContainerHandle(model_id="mysql", container=fake_container)

    spec = dataclasses.replace(_spec(), init_script="mysql.sql")

    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
        f.write("SELECT 1;")
        tmp_path = Path(f.name)

    try:
        from tests.collect_fixtures import docker_lifecycle as dl_mod

        original = dl_mod._read_init_script
        dl_mod._read_init_script = lambda s: tmp_path.read_text(encoding="utf-8")
        try:
            exec_init(handle, spec)
        finally:
            dl_mod._read_init_script = original

        # 期望: put_archive 一次 + exec_run 至少一次
        fake_container.put_archive.assert_called_once()
        assert fake_container.exec_run.called
    finally:
        tmp_path.unlink()


# --- Task 3 新增测试 ---


def _ssh_spec(**overrides):
    """构造一个最小可用的 ssh Spec，用于 docker_lifecycle v2 测试。"""
    from dataclasses import replace as _replace
    from tests.collect_fixtures.catalog import Spec
    base = Spec(
        model_id="nginx",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12222, "80/tcp": 18000},
        env={},
        wait_strategy={"type": "ssh", "timeout": 0.3, "interval": 0.05},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
    )
    return _replace(base, **overrides)


def test_start_container_passes_privileged():
    """start_container 加 privileged 参数透传给 docker.containers.run。"""
    fake_container = MagicMock()
    fake_container.short_id = "cid"
    fake_client = MagicMock()
    fake_client.containers.run.return_value = fake_container

    spec = _ssh_spec()
    handle = start_container(spec, docker_client=fake_client, privileged=True)

    kwargs = fake_client.containers.run.call_args.kwargs
    assert kwargs["privileged"] is True


def test_wait_ssh_ready_succeeds_when_ssh_responds(monkeypatch):
    """wait_ssh_ready 通过 VMSSH 试连接。"""
    from tests.collect_fixtures.docker_lifecycle import ContainerHandle
    fake_container = MagicMock()
    fake_container.short_id = "cid"
    fake_container.attrs = {"NetworkSettings": {"Ports": {"22/tcp": [{"HostPort": "12222"}]}}}
    handle = ContainerHandle(model_id="nginx", container=fake_container)
    spec = _ssh_spec()

    fake_ssh = MagicMock()
    fake_ssh.connect = MagicMock()  # 不抛 = OK
    monkeypatch.setattr("tests.collect_fixtures.docker_lifecycle.VMSSH", lambda **k: fake_ssh)

    wait_ssh_ready(handle, spec, ssh_password="x")
    fake_ssh.connect.assert_called_once()


def test_wait_ssh_ready_retries_then_raises(monkeypatch):
    from tests.collect_fixtures.docker_lifecycle import ContainerHandle
    fake_container = MagicMock()
    fake_container.short_id = "cid"
    fake_container.attrs = {"NetworkSettings": {"Ports": {"22/tcp": [{"HostPort": "12222"}]}}}
    handle = ContainerHandle(model_id="nginx", container=fake_container)
    spec = _ssh_spec(wait_strategy={"type": "ssh", "timeout": 0.3, "interval": 0.05})

    fake_ssh = MagicMock()
    fake_ssh.connect = MagicMock(side_effect=ConnectionError("nope"))
    monkeypatch.setattr("tests.collect_fixtures.docker_lifecycle.VMSSH", lambda **k: fake_ssh)

    with pytest.raises(TimeoutError, match="SSH.*未就绪"):
        wait_ssh_ready(handle, spec, ssh_password="x")


def test_install_services_runs_commands_via_ssh(monkeypatch):
    """install_services 走 SSH 顺序执行所有 install_commands。"""
    from tests.collect_fixtures.docker_lifecycle import ContainerHandle
    fake_container = MagicMock()
    fake_container.attrs = {"NetworkSettings": {"Ports": {"22/tcp": [{"HostPort": "12222"}]}}}
    handle = ContainerHandle(model_id="nginx", container=fake_container)
    spec = _ssh_spec(install_commands=("apt-get update", "apt-get install -y nginx"))

    calls = []

    def fake_exec(cmd, check=True, timeout=None):
        calls.append(cmd)
        return {"stdout": "", "stderr": "", "exit_code": 0}

    fake_ssh = MagicMock()
    fake_ssh.exec = fake_exec
    monkeypatch.setattr("tests.collect_fixtures.docker_lifecycle.VMSSH", lambda **k: fake_ssh)

    install_services(handle, spec, ssh_password="x")

    # Phase 3 增强(2026-07-08):install 前先 sed 切 ubuntu 源到 aliyun
    # 所以第一条 call 是 sed(if file),然后才是用户 install_commands
    assert len(calls) == 3
    assert "mirrors.aliyun.com" in calls[0]  # sed 切源
    assert calls[1] == "apt-get update"
    assert calls[2] == "apt-get install -y nginx"


def test_start_services_runs_commands_via_ssh(monkeypatch):
    from tests.collect_fixtures.docker_lifecycle import ContainerHandle
    fake_container = MagicMock()
    fake_container.attrs = {"NetworkSettings": {"Ports": {"22/tcp": [{"HostPort": "12222"}]}}}
    handle = ContainerHandle(model_id="nginx", container=fake_container)
    spec = _ssh_spec(start_commands=("nginx -g 'daemon on;'",))

    calls = []

    def fake_exec(cmd, check=True, timeout=None):
        calls.append(cmd)
        return {"stdout": "", "stderr": "", "exit_code": 0}

    fake_ssh = MagicMock()
    fake_ssh.exec = fake_exec
    monkeypatch.setattr("tests.collect_fixtures.docker_lifecycle.VMSSH", lambda **k: fake_ssh)

    start_services(handle, spec, ssh_password="x")
    assert calls == list(spec.start_commands)


def test_wait_service_ready_polls_ssh_command(monkeypatch):
    """ready_check.command 在 VM 上执行,直到返回 exit_code==0。"""
    from tests.collect_fixtures.docker_lifecycle import ContainerHandle
    fake_container = MagicMock()
    fake_container.attrs = {"NetworkSettings": {"Ports": {"22/tcp": [{"HostPort": "12222"}]}}}
    handle = ContainerHandle(model_id="nginx", container=fake_container)
    spec = _ssh_spec(ready_check={"command": "ss -tln | grep -q :80", "timeout": 0.3, "interval": 0.05})

    fake_ssh = MagicMock()
    counter = {"n": 0}

    def fake_exec(cmd, check=False, timeout=None):
        counter["n"] += 1
        if counter["n"] < 3:
            return {"stdout": "", "stderr": "", "exit_code": 1}
        return {"stdout": "LISTEN", "stderr": "", "exit_code": 0}

    fake_ssh.exec = fake_exec
    monkeypatch.setattr("tests.collect_fixtures.docker_lifecycle.VMSSH", lambda **k: fake_ssh)

    wait_service_ready(handle, spec, ssh_password="x")
    assert counter["n"] >= 3


def test_wait_service_ready_raises_on_timeout(monkeypatch):
    from tests.collect_fixtures.docker_lifecycle import ContainerHandle
    fake_container = MagicMock()
    fake_container.attrs = {"NetworkSettings": {"Ports": {"22/tcp": [{"HostPort": "12222"}]}}}
    handle = ContainerHandle(model_id="nginx", container=fake_container)
    spec = _ssh_spec(ready_check={"command": "false", "timeout": 0.2, "interval": 0.05})

    fake_ssh = MagicMock()

    def fake_exec(cmd, check=False, timeout=None):
        return {"stdout": "", "stderr": "", "exit_code": 1}

    fake_ssh.exec = fake_exec
    monkeypatch.setattr("tests.collect_fixtures.docker_lifecycle.VMSSH", lambda **k: fake_ssh)

    with pytest.raises(TimeoutError, match="服务.*未就绪"):
        wait_service_ready(handle, spec, ssh_password="x")
