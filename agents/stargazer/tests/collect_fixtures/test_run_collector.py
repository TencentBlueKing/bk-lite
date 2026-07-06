# -*- coding: utf-8 -*-
"""run_collector.py 单测（用 fake collector 模块）"""

import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.collect_fixtures.catalog import Spec  # noqa: E402
from tests.collect_fixtures.docker_lifecycle import ContainerHandle  # noqa: E402
from tests.collect_fixtures.run_collector import (  # noqa: E402
    collect_once,
    CollectorImportError,
)


def _spec(entry_type="python", entry_method="list_all_resources", entry_module="fake.module",
          entry_class="FakeCollector", init_script=None):
    return Spec(
        model_id="mysql",
        image="mysql:8.0",
        ports={"3306/tcp": 13306},
        env={},
        wait_strategy={"type": "tcp", "port": 13306, "timeout": 60},
        init_script=init_script,
        entry_type=entry_type,
        entry_module=entry_module,
        entry_class=entry_class,
        entry_method=entry_method,
        collector_kwargs={"host": "127.0.0.1"},
    )


def test_collect_once_python_loads_class_and_calls_list_all_resources():
    """python 入口：动态加载 collector 类，构造，调 list_all_resources()。"""
    fake_class = MagicMock()
    fake_instance = MagicMock()
    fake_instance.list_all_resources.return_value = {"version": "8.0.36"}
    fake_class.return_value = fake_instance

    fake_module = MagicMock()
    fake_module.FakeCollector = fake_class
    sys.modules["fake.module"] = fake_module

    try:
        spec = _spec()
        result = collect_once(spec)

        assert result == {"version": "8.0.36"}
        fake_class.assert_called_once_with({"host": "127.0.0.1"})
        fake_instance.list_all_resources.assert_called_once()
    finally:
        sys.modules.pop("fake.module", None)


def test_collect_once_python_uses_custom_entry_method():
    """python 入口方法名可配（默认 list_all_resources，但有些 collector 用 collect()）。"""
    fake_class = MagicMock()
    fake_instance = MagicMock()
    fake_instance.collect.return_value = {"x": 1}
    fake_class.return_value = fake_instance

    fake_module = MagicMock()
    fake_module.FakeCollector = fake_class
    sys.modules["fake.module"] = fake_module

    try:
        spec = _spec(entry_method="collect")
        result = collect_once(spec)

        assert result == {"x": 1}
        fake_instance.collect.assert_called_once()
        fake_instance.list_all_resources.assert_not_called()
    finally:
        sys.modules.pop("fake.module", None)


def test_collect_once_python_raises_on_import_failure():
    sys.modules.pop("does.not.exist", None)
    spec = _spec(entry_module="does.not.exist")
    with pytest.raises(CollectorImportError, match="无法导入"):
        collect_once(spec)


def test_collect_once_shell_runs_script_via_container_exec():
    """shell 入口：在容器内 exec_run(*_default_discover.sh) + 捕获 stdout。"""
    fake_container = MagicMock()
    fake_container.exec_run.return_value = ({"ExitCode": 0}, b'{"redis_version":"7.2"}')
    fake_container.put_archive.return_value = True
    handle = ContainerHandle(model_id="redis", container=fake_container)

    spec = _spec(entry_type="shell", init_script="redis_default_discover.sh")

    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write("#!/bin/sh\necho hello")
        tmp_script = Path(f.name)

    try:
        from tests.collect_fixtures import run_collector as rc_mod
        original = rc_mod._resolve_shell_script_path
        rc_mod._resolve_shell_script_path = lambda s: tmp_script
        try:
            result = collect_once(spec, handle=handle)
        finally:
            rc_mod._resolve_shell_script_path = original

        # 期望: put_archive 上传 + exec_run 执行
        fake_container.put_archive.assert_called_once()
        fake_container.exec_run.assert_called_once()
        call = fake_container.exec_run.call_args
        cmd = call.args[0] if call.args else call.kwargs["cmd"]
        assert cmd[0] in ("sh", "bash")
        # 容器内路径
        assert "/tmp/" in cmd[1]
        assert result == {"redis_version": "7.2"}
    finally:
        tmp_script.unlink()


def test_collect_once_shell_returns_dict_on_json_stdout():
    """stdout 是 JSON 字符串时，parse 成 dict 返回。"""
    fake_container = MagicMock()
    fake_container.exec_run.return_value = (
        {"ExitCode": 0},
        b'{"version": "8.0.36", "databases": []}',
    )
    fake_container.put_archive.return_value = True
    handle = ContainerHandle(model_id="mysql", container=fake_container)
    spec = _spec(entry_type="shell", init_script="mysql_default_discover.sh")

    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write("#!/bin/sh")
        tmp_script = Path(f.name)
    try:
        from tests.collect_fixtures import run_collector as rc_mod
        original = rc_mod._resolve_shell_script_path
        rc_mod._resolve_shell_script_path = lambda s: tmp_script
        try:
            result = collect_once(spec, handle=handle)
        finally:
            rc_mod._resolve_shell_script_path = original
        assert result == {"version": "8.0.36", "databases": []}
    finally:
        tmp_script.unlink()


def test_collect_once_shell_raises_on_non_zero_exit():
    fake_container = MagicMock()
    fake_container.exec_run.return_value = ({"ExitCode": 1}, b"some error output")
    fake_container.put_archive.return_value = True
    handle = ContainerHandle(model_id="redis", container=fake_container)
    spec = _spec(entry_type="shell", init_script="redis_default_discover.sh")

    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write("#!/bin/sh")
        tmp_script = Path(f.name)
    try:
        from tests.collect_fixtures import run_collector as rc_mod
        original = rc_mod._resolve_shell_script_path
        rc_mod._resolve_shell_script_path = lambda s: tmp_script
        with pytest.raises(RuntimeError, match="shell 脚本执行失败"):
            collect_once(spec, handle=handle)
    finally:
        tmp_script.unlink()


# --- Task 5 新增 ssh 入口测试 ---

def test_collect_once_ssh_runs_script_via_vm_ssh(monkeypatch, tmp_path):
    """ssh 入口：通过 VMSSH 上传脚本 + 执行 + 捕获 stdout。"""
    from tests.collect_fixtures.docker_lifecycle import ContainerHandle

    fake_container = MagicMock()
    fake_container.short_id = "cid"
    fake_container.attrs = {"NetworkSettings": {"Ports": {"22/tcp": [{"HostPort": "12222"}]}}}
    handle = ContainerHandle(model_id="nginx", container=fake_container)

    spec = _spec(entry_type="ssh")
    spec = replace(spec, init_script="nginx_default_discover.sh", vm_ssh_password="testpw")

    # 准备一个临时脚本供 _resolve_shell_script_path monkey-patch
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write("#!/bin/bash\necho nginx_output")
        tmp_script = Path(f.name)

    # monkey-patch VMSSH
    fake_ssh_instance = MagicMock()
    fake_ssh_instance.exec.return_value = {"stdout": '{"version":"1.18.0"}', "stderr": "", "exit_code": 0}
    fake_ssh_class = MagicMock(return_value=fake_ssh_instance)
    monkeypatch.setattr("tests.collect_fixtures.run_collector.VMSSH", fake_ssh_class)

    # monkey-patch _upload_script_via_ssh 跳过实际传输
    from tests.collect_fixtures import run_collector as rc_mod
    original_resolve = rc_mod._resolve_shell_script_path
    rc_mod._resolve_shell_script_path = lambda s: tmp_script
    rc_mod._upload_script_via_ssh = lambda ssh, local, remote: None

    try:
        result = collect_once(spec, handle=handle)
    finally:
        rc_mod._resolve_shell_script_path = original_resolve
        tmp_script.unlink()

    assert result == {"version": "1.18.0"}
    # 验证 SSH 命令包含 'bash /tmp/...'
    last_call = fake_ssh_instance.exec.call_args_list[-1]
    assert "/tmp/" in last_call.args[0]


def test_collect_once_ssh_raises_on_non_zero_exit(monkeypatch, tmp_path):
    fake_container = MagicMock()
    fake_container.attrs = {"NetworkSettings": {"Ports": {"22/tcp": [{"HostPort": "12222"}]}}}
    handle = ContainerHandle(model_id="nginx", container=fake_container)
    spec = _spec(entry_type="ssh")
    spec = replace(spec, vm_ssh_password="testpw")

    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write("#!/bin/bash\nexit 1")
        tmp_script = Path(f.name)

    fake_ssh_instance = MagicMock()
    fake_ssh_instance.exec.return_value = {"stdout": "", "stderr": "boom", "exit_code": 1}
    fake_ssh_class = MagicMock(return_value=fake_ssh_instance)
    monkeypatch.setattr("tests.collect_fixtures.run_collector.VMSSH", fake_ssh_class)

    from tests.collect_fixtures import run_collector as rc_mod
    original_resolve = rc_mod._resolve_shell_script_path
    rc_mod._resolve_shell_script_path = lambda s: tmp_script
    rc_mod._upload_script_via_ssh = lambda ssh, local, remote: None

    try:
        with pytest.raises(RuntimeError, match="ssh 脚本执行失败"):
            collect_once(spec, handle=handle)
    finally:
        rc_mod._resolve_shell_script_path = original_resolve
        tmp_script.unlink()