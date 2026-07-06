# -*- coding: utf-8 -*-
"""
对象清单 — 声明每个可容器化的数据库/中间件的采集参数。

设计原则：
- 单一数据源：所有对象参数在此声明，其他模块只读不写。
- 不可变：Spec 是 frozen dataclass，避免运行时误改。
- 启动期校验：validate() 在 catalog 加载时调用，配置错误早暴露。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------- Spec 数据类 ----------

@dataclass(frozen=True)
class Spec:
    """单个采集对象的完整描述。"""

    # 原有字段（v1）
    model_id: str
    image: str
    ports: Dict[str, int]  # docker SDK 约定：{"container_port/tcp": host_port}，例如 {"3306/tcp": 13306}
    env: Dict[str, str]
    wait_strategy: Dict[str, Any]  # 例如 {"type": "tcp", "port": 13306, "timeout": 60}
    init_script: Optional[str]  # 相对于 collect_fixtures/init/ 的文件名，或 None
    entry_type: str  # "python" | "shell" | "ssh"
    entry_module: Optional[str] = None  # entry_type=="python" 时必填
    entry_class: Optional[str] = None
    entry_method: str = "list_all_resources"  # python 入口方法名
    collector_kwargs: Dict[str, Any] = field(default_factory=dict)

    # v2 VM SSH 相关字段（仅 entry_type=="ssh" 用）
    vm_privileged: bool = False
    vm_ssh_user: str = "root"
    vm_ssh_password: Optional[str] = None
    install_commands: tuple = ()  # 顺序执行；tuple 可 hash，frozen dataclass 需要
    start_commands: tuple = ()
    ready_check: Optional[Dict[str, Any]] = None


# ---------- 清单（10 个对象：mysql + postgresql 是 python 入口，其余 8 个是 shell 入口） ----------

# 共用 ubuntu 基础安装 + sshd 启动（不依赖 systemd）
_UBUNTU_BASE_INSTALL = (
    "echo 'sshd 已在 bootstrap 阶段装好,这里只装业务服务'",
)

MODEL_SPECS: Dict[str, Spec] = {
    "mysql": Spec(
        model_id="mysql",
        image="mysql:8.0",
        ports={"3306/tcp": 13306},
        env={"MYSQL_ROOT_PASSWORD": "rootpw"},
        wait_strategy={"type": "tcp", "port": 13306, "timeout": 180, "interval": 3},
        init_script="mysql.sql",
        entry_type="python",
        entry_module="plugins.inputs.mysql.mysql_info",
        entry_class="MysqlInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "port": 13306, "user": "root", "password": "rootpw"},
    ),
    "postgresql": Spec(
        model_id="postgresql",
        image="docker.m.daocloud.io/library/postgres:16-alpine",
        ports={"5432/tcp": 15432},
        env={"POSTGRES_PASSWORD": "rootpw"},
        wait_strategy={"type": "tcp", "port": 15432, "timeout": 120},
        init_script="postgresql.sql",
        entry_type="python",
        entry_module="plugins.inputs.postgresql.postgresql_info",
        entry_class="PostgresqlInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "port": 15432, "user": "postgres", "password": "rootpw"},
    ),
    "redis": Spec(
        model_id="redis",
        image="redis:7-alpine",
        ports={"6379/tcp": 16379},
        env={},
        wait_strategy={"type": "tcp", "port": 16379, "timeout": 30},
        init_script="redis_default_discover.sh",
        entry_type="shell",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "port": 16379, "password": ""},
    ),
    # --- VM SSH 入口对象（v2 新增）---
    "nginx": Spec(
        model_id="nginx",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12222, "80/tcp": 18000},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="nginx_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12222},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=("DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx > /dev/null 2>&1",),
        start_commands=("nginx -g 'daemon on;'",),
        ready_check={"command": "ss -tln | grep -q ':80 '", "timeout": 30, "interval": 1.0},
    ),
    "mongodb": Spec(
        model_id="mongodb",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12223, "27017/tcp": 17017},
        env={},
        wait_strategy={"type": "ssh", "timeout": 90, "interval": 1.0},
        init_script="mongodb_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12223},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq gnupg curl net-tools procps > /dev/null 2>&1",
            "curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor",
            "echo 'deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse' | tee /etc/apt/sources.list.d/mongodb-org-7.0.list",
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mongodb-org > /dev/null 2>&1",
            "mkdir -p /var/log/mongodb /var/lib/mongodb",
            "chown -R mongodb:mongodb /var/log/mongodb /var/lib/mongodb",
        ),
        start_commands=("mongod --fork --logpath /var/log/mongodb/mongod.log --dbpath /var/lib/mongodb --bind_ip_all",),
        ready_check={"command": "ss -tln | grep -q ':27017 '", "timeout": 30, "interval": 1.0},
    ),
    "rabbitmq": Spec(
        model_id="rabbitmq",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12224, "5672/tcp": 5673, "15672/tcp": 15672},
        env={},
        wait_strategy={"type": "ssh", "timeout": 90, "interval": 1.0},
        init_script="rabbitmq_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12224},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rabbitmq-server net-tools procps iproute2 > /dev/null 2>&1",
        ),
        start_commands=("rabbitmq-server -detached",),
        ready_check={"command": "ss -tln | grep -q ':5672 '", "timeout": 60, "interval": 1.0},
    ),
    "tomcat": Spec(
        model_id="tomcat",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12225, "8080/tcp": 18080},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="tomcat_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12225},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tomcat9 net-tools procps iproute2 > /dev/null 2>&1",
            "mkdir -p /usr/share/tomcat9/logs /usr/share/tomcat9/work /usr/share/tomcat9/conf",
            "cp -r /etc/tomcat9/. /usr/share/tomcat9/conf/",
        ),
        start_commands=("/usr/share/tomcat9/bin/startup.sh",),
        ready_check={"command": "ss -tln | grep -q ':8080 '", "timeout": 60, "interval": 1.0},
    ),
}


# ---------- 工具函数 ----------

def lookup(model_id: str) -> Spec:
    """获取指定对象的 Spec。"""
    if model_id not in MODEL_SPECS:
        raise KeyError(f"model_id '{model_id}' 不在 MODEL_SPECS 中。可用: {list(MODEL_SPECS)}")
    return MODEL_SPECS[model_id]


def list_models() -> List[str]:
    """返回所有 model_id 列表（已排序）。"""
    return sorted(MODEL_SPECS.keys())


def validate() -> List[str]:
    """校验所有 Spec 配置正确性。返回错误列表（空 = 通过）。"""
    errors: List[str] = []
    init_dir = Path(__file__).parent / "init"

    seen_ports: Dict[int, str] = {}
    for mid, spec in MODEL_SPECS.items():
        if spec.entry_type == "python":
            if not spec.entry_module or not spec.entry_class:
                errors.append(f"{mid}: python 入口必须填 entry_module + entry_class")
        elif spec.entry_type == "shell":
            if not spec.init_script:
                errors.append(f"{mid}: shell 入口必须填 init_script（脚本路径）")
        elif spec.entry_type == "ssh":
            if not spec.vm_ssh_password:
                errors.append(f"{mid}: ssh 入口必须填 vm_ssh_password")
        else:
            errors.append(f"{mid}: 不支持的 entry_type '{spec.entry_type}'")

        # 检查 init_script 文件存在
        if spec.init_script and not (init_dir / spec.init_script).exists():
            errors.append(f"{mid}: init_script 文件不存在: {init_dir / spec.init_script}")

        # 检查端口不冲突（ports 是 {container_port: host_port}，按 host_port 去重）
        for host_port in spec.ports.values():
            if host_port in seen_ports:
                errors.append(
                    f"{mid}: 端口 {host_port} 与 {seen_ports[host_port]} 冲突"
                )
            seen_ports[host_port] = mid

    return errors