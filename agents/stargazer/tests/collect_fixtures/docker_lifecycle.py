# -*- coding: utf-8 -*-
"""
Docker 容器生命周期管理：start / wait_ready / exec_init / remove。

设计原则：
- try/finally 强制清理：所有 start 之后必须有对应 remove（业务侧负责）。
- docker_client 可注入：单测用 MagicMock，生产用 docker.from_env()。
- 不捕获 NotFound 等"已删除"错误：容器可能已被 --rm 自动清理。
"""
from __future__ import annotations

import io
import socket
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import docker
import docker.errors

from tests.collect_fixtures.catalog import Spec
from tests.collect_fixtures.vm_ssh import VMSSH


@dataclass
class ContainerHandle:
    """一个被启动的容器句柄。"""

    model_id: str
    container: Any  # docker.models.containers.Container（用 Any 避免循环 import）


def _get_docker_client(docker_client=None):
    """默认从环境拿 docker client，允许单测注入 fake。"""
    if docker_client is not None:
        return docker_client
    return docker.from_env()


def start_container(spec: Spec, docker_client=None, privileged: bool = False) -> ContainerHandle:
    """拉起一个 spec 描述的容器，返回 handle。"""
    client = _get_docker_client(docker_client)
    # ubuntu minimal 镜像默认 CMD 立即退出,需要 keepalive 让容器持续运行
    # 直到 install_services 跑完 / remove 触发
    keepalive_cmd = "bash -c 'while true; do sleep 3600; done'"
    container = client.containers.run(
        image=spec.image,
        command=keepalive_cmd,
        detach=True,
        environment=spec.env,
        ports=spec.ports,
        privileged=privileged,  # 新增：v2 SSH VM 需要（虽然本项目 v2 不强求）
        remove=True,  # 进程退出即清理，防御忘记 remove 的情况
    )
    return ContainerHandle(model_id=spec.model_id, container=container)


def remove(handle: ContainerHandle) -> None:
    """销毁容器。已删除时（NotFound）静默成功。"""
    try:
        handle.container.remove(force=True)
    except docker.errors.NotFound:
        pass


# ---------- TCP 探测（可被单测 monkeypatch） ----------
def _tcp_probe(host: str, port: int, timeout: float = 1.0) -> None:
    """尝试 TCP 连接；成功返回 None，失败 raise。"""
    with socket.create_connection((host, port), timeout=timeout):
        pass


# ---------- 读取 init 脚本（可被单测 monkeypatch） ----------
def _read_init_script(spec: Spec) -> str:
    """从 init/<script> 读脚本内容。"""
    script_path = Path(__file__).parent / "init" / spec.init_script
    return script_path.read_text(encoding="utf-8")


def wait_ready(handle: ContainerHandle, spec: Spec) -> None:
    """轮询 wait_strategy 直到就绪或超时。"""
    strategy = spec.wait_strategy
    timeout = float(strategy.get("timeout", 60))
    interval = float(strategy.get("interval", 1.0))
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            if strategy["type"] == "tcp":
                _tcp_probe("127.0.0.1", int(strategy["port"]))
                return  # 端口可连 = 就绪
            else:
                raise NotImplementedError(
                    f"不支持的 wait_strategy.type: {strategy['type']}（仅 'tcp'）"
                )
        except (ConnectionRefusedError, OSError):
            time.sleep(interval)

    raise TimeoutError(f"容器 {spec.model_id} 在 {timeout}s 内未就绪（image={spec.image}）")


def exec_init(handle: ContainerHandle, spec: Spec) -> None:
    """把 init_script 通过 put_archive + exec_run 注入到容器内执行。

    只对 python 入口生效（mysql/postgresql 用 sql 灌种子数据）。
    shell 入口的 init_script 实际是采集脚本，由 run_collector 在容器内执行，
    不在这里触发（由 cli.py 通过 `entry_type != "shell"` 条件负责跳过日志打印）。
    """
    if not spec.init_script:
        return
    # shell 入口的 init_script 是采集脚本而非种子数据脚本,留给 run_collector 执行
    if spec.entry_type == "shell":
        return

    sql_text = _read_init_script(spec)
    _exec_sql_via_container(handle, spec, sql_text)


def _exec_sql_via_container(handle: ContainerHandle, spec: Spec, sql_text: str) -> None:
    """通过 put_archive + exec_run 把 sql 喂进容器执行（兼容 mysql/postgresql）。"""
    # 在容器内固定路径
    if spec.model_id == "mysql":
        remote_path = "/tmp/init.sql"
        # 用 -h 127.0.0.1 强制 TCP,避免 socket 不存在
        run_cmd = ["sh", "-c", f"mysql -h 127.0.0.1 -uroot -p$MYSQL_ROOT_PASSWORD < {remote_path}"]
    elif spec.model_id == "postgresql":
        remote_path = "/tmp/init.sql"
        run_cmd = ["sh", "-c", f"psql -U postgres -f {remote_path}"]
    else:
        raise NotImplementedError(
            f"model_id '{spec.model_id}' 的 init 脚本执行方式未实现"
        )

    # 把 sql 文本打包成 tar
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        data = sql_text.encode("utf-8")
        info = tarfile.TarInfo(name="init.sql")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    tar_buf.seek(0)

    put_result = handle.container.put_archive("/tmp", tar_buf.read())
    if not put_result:
        raise RuntimeError(f"put_archive 上传 init 脚本失败（model={spec.model_id}）")

    result = handle.container.exec_run(run_cmd)
    # docker SDK 7.x 返回 ExecResult dataclass; 旧版本返回 tuple
    if hasattr(result, "exit_code"):
        exit_code = result.exit_code
        output = result.output
    else:
        exit_code, output = result[0], result[1]

    if exit_code != 0:
        raise RuntimeError(
            f"init 脚本执行失败（model={spec.model_id}）: exit={exit_code} output={output!r}"
        )


# ---------- VM SSH 相关阶段（v2 新增）----------

def _extract_ssh_port(handle: ContainerHandle) -> int:
    """从容器 attrs 拿 ssh 映射到 host 的端口。"""
    # 容器刚启动时 attrs 可能没刷新,先 reload
    try:
        handle.container.reload()
    except Exception:
        pass
    attrs = handle.container.attrs or {}
    ports = attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
    for container_port, mappings in ports.items():
        if container_port.startswith("22"):
            if mappings:
                return int(mappings[0].get("HostPort", 22))
    return 22


def wait_ssh_ready(handle: ContainerHandle, spec: Spec, ssh_password: str) -> None:
    """轮询 SSH 端口直到 sshd 接受连接。"""
    strategy = spec.wait_strategy
    timeout = float(strategy.get("timeout", 60))
    interval = float(strategy.get("interval", 1.0))
    deadline = time.monotonic() + timeout
    port = _extract_ssh_port(handle)
    last_err = None
    while time.monotonic() < deadline:
        ssh = VMSSH(host="127.0.0.1", port=port, user=spec.vm_ssh_user, password=ssh_password)
        try:
            ssh.connect()
            ssh.close()
            return
        except Exception as e:
            last_err = e
            try:
                ssh.close()
            except Exception:
                pass
            time.sleep(interval)
    raise TimeoutError(
        f"SSH 在 {timeout}s 内未就绪（model={spec.model_id}）: {last_err}"
    )


# sshd bootstrap 的固定命令（容器是 minimal ubuntu,需要先装 sshd 才能 SSH）
# 注意：必须用 ; 分隔而非换行,因 docker exec + bash -c 对多行 script 支持不可靠
_SSH_BOOTSTRAP_CMD = (
    "set -e; "
    "export DEBIAN_FRONTEND=noninteractive; "
    "apt-get update -qq; "
    "apt-get install -y -qq openssh-server sudo iproute2 curl > /dev/null 2>&1; "
    "echo 'root:{password}' | chpasswd; "
    "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config; "
    "sed -i 's/^#*PermitEmptyPasswords.*/PermitEmptyPasswords no/' /etc/ssh/sshd_config; "
    "sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config; "
    "sed -i 's/^#*KbdInteractiveAuthentication.*/KbdInteractiveAuthentication no/' /etc/ssh/sshd_config; "
    "mkdir -p /run/sshd; "
    "ssh-keygen -A > /dev/null 2>&1; "
    "/usr/sbin/sshd; "
    "sleep 1; "
    "echo BOOTSTRAP_DONE"
)


def bootstrap_sshd_in_container(handle: ContainerHandle, spec: Spec) -> None:
    """在容器内（用 docker exec,非 SSH）装 sshd + 配置 + 启动,使得后续 SSH 可用。

    SSH 入口的 chicken-and-egg：sshd 没装前 SSH 不能用。
    这里用 docker exec_run 直接在容器内跑 bootstrap 命令,装好 sshd。
    """
    cmd = _SSH_BOOTSTRAP_CMD.format(password=spec.vm_ssh_password)
    result = handle.container.exec_run(cmd=["bash", "-c", cmd])
    if hasattr(result, "exit_code"):
        exit_code = result.exit_code
        output = result.output
    else:
        exit_code = result[0].get("ExitCode", 0) if isinstance(result[0], dict) else result[0]
        output = result[1]
    if exit_code != 0:
        raise RuntimeError(
            f"sshd bootstrap failed (model={spec.model_id}): "
            f"exit={exit_code} output={output!r}"
        )


def install_services(handle: ContainerHandle, spec: Spec, ssh_password: str) -> None:
    """SSH 进 VM 顺序执行 spec.install_commands。"""
    if not spec.install_commands:
        return
    port = _extract_ssh_port(handle)
    ssh = VMSSH(host="127.0.0.1", port=port, user=spec.vm_ssh_user, password=ssh_password)
    ssh.connect()
    try:
        for cmd in spec.install_commands:
            ssh.exec(cmd, check=True, timeout=600)  # apt install 可能很慢
    finally:
        ssh.close()


def start_services(handle: ContainerHandle, spec: Spec, ssh_password: str) -> None:
    """SSH 进 VM 顺序执行 spec.start_commands。"""
    if not spec.start_commands:
        return
    port = _extract_ssh_port(handle)
    ssh = VMSSH(host="127.0.0.1", port=port, user=spec.vm_ssh_user, password=ssh_password)
    ssh.connect()
    try:
        for cmd in spec.start_commands:
            ssh.exec(cmd, check=True)
    finally:
        ssh.close()


def wait_service_ready(handle: ContainerHandle, spec: Spec, ssh_password: str) -> None:
    """轮询 spec.ready_check.command 直到 exit_code==0。"""
    check = spec.ready_check or {}
    cmd = check.get("command")
    if not cmd:
        return
    timeout = float(check.get("timeout", 60))
    interval = float(check.get("interval", 1.0))
    deadline = time.monotonic() + timeout
    port = _extract_ssh_port(handle)
    ssh = VMSSH(host="127.0.0.1", port=port, user=spec.vm_ssh_user, password=ssh_password)
    ssh.connect()
    try:
        while time.monotonic() < deadline:
            r = ssh.exec(cmd, check=False)
            if r["exit_code"] == 0:
                return
            time.sleep(interval)
        raise TimeoutError(
            f"服务在 {timeout}s 内未就绪（model={spec.model_id}）: {cmd!r}"
        )
    finally:
        ssh.close()
