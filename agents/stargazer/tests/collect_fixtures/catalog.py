# -*- coding: utf-8 -*-
"""
对象清单 — 声明每个可容器化的数据库/中间件的采集参数。

设计原则：
- 单一数据源：所有对象参数在此声明，其他模块只读不写。
- 不可变：Spec 是 frozen dataclass，避免运行时误改。
- 启动期校验：validate() 在 catalog 加载时调用，配置错误早暴露。
"""
from __future__ import annotations

import importlib
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

    # 容器启动选项(覆盖 docker SDK 默认)
    container_user: Optional[str] = None  # 例如 "0:0" = root:root; None 用镜像默认 USER
    container_cmd: Optional[str] = None  # None 用镜像默认 ENTRYPOINT/CMD
    platform: Optional[str] = None  # 例如 "linux/amd64"; None 用 docker SDK 默认(amd64 在 x86_64 主机,arm64 在 arm64 主机)


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
    # --- G2.1 redis_sentinel（单实例 redis + 单 sentinel 同容器双进程）---
    # 复用 redis_default_discover.sh(内置 SENTINEL MASTERS/REPLICAS 分支);
    # 容器启动用 container_cmd 注入"redis-server 后台 + sentinel.conf 写盘 +
    # redis-sentinel 前台 + keepalive"。catalog.ports 同步暴露 26379 映射。
    # REDIS_TARGET_PORTS="16380,26380" 让采集脚本同时探两个端口,触发 sentinel 分支。
    "redis_sentinel": Spec(
        model_id="redis_sentinel",
        image="redis:7-alpine",
        ports={"6379/tcp": 16380, "26379/tcp": 26380},
        env={
            "REDISCLI_AUTH": "testpass",
            # 关闭进程端口探测:discover_ports_from_process 只匹配 redis-server 命令行,
            # 不匹配 redis-sentinel,会把 sentinel 端口从列表里吞掉(G2.1 debug 发现)。
            # 强制走 REDIS_TARGET_PORTS 显式列表。
            "REDIS_DISCOVER_FROM_PROCESS": "no",
        },
        wait_strategy={"type": "tcp", "port": 16380, "timeout": 30},
        init_script="redis_sentinel_default_discover.sh",
        entry_type="shell",
        entry_module=None,
        entry_class=None,
        collector_kwargs={
            "host": "127.0.0.1",
            # 端口语义:采集脚本在容器内跑,通过 127.0.0.1:<容器内端口> 连。
            # docker 端口映射(6379→16380, 26379→26380)只对容器外有用;容器内仍用 6379/26379。
            # 这是 redis Spec 的 collector_kwargs.port=16379 实际被脚本忽略(ps 探测覆盖)的原因。
            "ports": [6379, 26379],
            "password": "testpass",
        },
        container_cmd=(
            # 单引号包外层,内部所有变量/引号都安全
            # 关键:sentinel 也设 requirepass + sentinel auth-pass,否则 redis-cli 用 REDISCLI_AUTH
            # 连接 sentinel 时会触发 AUTH 命令,sentinel 无密码导致 "AUTH failed" 混入 stdout,
            # 采集脚本 case "PONG" 不匹配,采集不到 sentinel 实例(G2.1 debug 发现,2026-07-07)。
            "sh -c '"
            "redis-server --port 6379 --requirepass testpass --daemonize yes; "
            "sleep 1; "
            "printf \"sentinel monitor mymaster 127.0.0.1 6379 2\\nsentinel down-after-milliseconds mymaster 5000\\n"
            "sentinel parallel-syncs mymaster 1\\nsentinel failover-timeout mymaster 10000\\n"
            "sentinel auth-pass mymaster testpass\\nrequirepass testpass\\n\" > /etc/sentinel.conf; "
            "redis-sentinel /etc/sentinel.conf; "
            "while true; do sleep 3600; done'"
        ),
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
    # --- Phase 1 Gap-1 新增对象 ---
    "elasticsearch": Spec(
        model_id="elasticsearch",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12228, "9200/tcp": 19200},
        env={},
        wait_strategy={"type": "ssh", "timeout": 90, "interval": 1.0},
        init_script="elasticsearch_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12228, "es_port": 19200},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wget gnupg apt-transport-https ca-certificates net-tools procps iproute2 curl > /dev/null 2>&1",
            "wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | gpg --dearmor -o /usr/share/keyrings/elasticsearch-keyring.gpg",
            "echo 'deb [signed-by=/usr/share/keyrings/elasticsearch-keyring.gpg] https://artifacts.elastic.co/packages/8.x/apt stable main' > /etc/apt/sources.list.d/elastic-8.x.list",
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq elasticsearch > /tmp/es_install.log 2>&1 || (echo 'ES install failed:'; tail -50 /tmp/es_install.log; exit 1)",
        ),
        start_commands=(
            # ES 8.x 拒绝以 root 启动;改用 elasticsearch 用户跑。
            # 不能用 -E discovery.type=single-node(会跟 yaml 默认 cluster.initial_master_nodes 冲突);
            # 让 ES 走默认多节点 bootstrap(单节点也会自己选 master)。
            "mkdir -p /var/log/elasticsearch /var/lib/elasticsearch && chown -R elasticsearch:elasticsearch /var/log/elasticsearch /var/lib/elasticsearch /etc/elasticsearch",
            "su -s /bin/bash elasticsearch -c '/usr/share/elasticsearch/bin/elasticsearch -d -p /tmp/es.pid -E xpack.security.enabled=false -E network.host=127.0.0.1 -E http.port=9200'",
        ),
        ready_check={"command": "curl -fsS http://127.0.0.1:9200/_cluster/health 2>/dev/null | grep -q '\"status\"'", "timeout": 180, "interval": 3.0},
    ),
    # --- G1.2 kafka (KRaft 模式,无 zookeeper) ---
    "kafka": Spec(
        model_id="kafka",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12229, "9092/tcp": 19092},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="kafka_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12229, "kafka_port": 19092},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wget net-tools procps iproute2 openjdk-11-jre-headless > /dev/null 2>&1",
            # 清华源优先,失败回落到 archive.apache.org
            "wget -q --tries=2 --timeout=60 https://mirrors.tuna.tsinghua.edu.cn/apache/kafka/3.6.0/kafka_2.13-3.6.0.tgz -O /tmp/kafka.tgz || wget -q --tries=3 --timeout=60 https://archive.apache.org/dist/kafka/3.6.0/kafka_2.13-3.6.0.tgz -O /tmp/kafka.tgz",
            "tar -xzf /tmp/kafka.tgz -C /opt/ && mv /opt/kafka_2.13-3.6.0 /opt/kafka",
        ),
        start_commands=(
            # KRaft: 生成 cluster ID + format storage + 改 listeners
            "CLUSTER_ID=$(/opt/kafka/bin/kafka-storage.sh random-uuid) && /opt/kafka/bin/kafka-storage.sh format -t $CLUSTER_ID -c /opt/kafka/config/kraft/server.properties",
            "sed -i 's|^advertised.listeners=.*|advertised.listeners=PLAINTEXT://127.0.0.1:19092|' /opt/kafka/config/kraft/server.properties",
            "sed -i 's|^listeners=.*|listeners=PLAINTEXT://127.0.0.1:9092,CONTROLLER://127.0.0.1:9093|' /opt/kafka/config/kraft/server.properties",
            "/opt/kafka/bin/kafka-server-start.sh -daemon /opt/kafka/config/kraft/server.properties",
        ),
        ready_check={"command": "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list --timeout 5000 2>&1 | grep -qv 'Error while executing'", "timeout": 90, "interval": 3.0},
    ),
    # --- G1.3 activemq (Phase 2 副产物 解锁:换官方镜像 + sshd bootstrap) ---
    # 2026-07-07 阻塞:apt 装的 activemq 用 Tanuki wrapper daemon,容器里 java 进程变 zombie 后端口未监听。
    # 2026-07-07 Phase 2 解锁:换 apache/activemq-classic:5.18.3 官方镜像(jammy + temurin-17)作为 base,
    # container_cmd 注入"装 sshd + 启动官方 entrypoint"两件事;官方 entrypoint 启 activemq 不会 zombie
    # (因为是镜像自带 setup),cli 流程只需等官方进程启动 + ready_check 双检测(web console + 端口)。
    "activemq": Spec(
        model_id="activemq",
        image="apache/activemq-classic:5.18.3",
        ports={"22/tcp": 12230, "61616/tcp": 31616, "8161/tcp": 18161},
        env={},
        wait_strategy={"type": "ssh", "timeout": 90, "interval": 1.0},
        init_script="activemq_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12230, "amq_port": 31616, "web_port": 18161},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        # 官方镜像默认 USER=activemq(uid 1000);装 sshd 需要 root,且要让 sshd + activemq
        # 服务同时在容器内运行,所以 container_user=root + container_cmd 串行启两者
        container_user="0:0",
        container_cmd=(
            # cli.py 阶段分工:
            # - bootstrap_sshd_in_container 装 sshd(用 docker exec)
            # - install_services 跑 install_commands
            # - start_services 跑 start_commands
            # 这里 container_cmd 只负责 keepalive(容器不退出) + 启 activemq(setsid 避免 zombie)
            # 注意:官方镜像路径是 /opt/apache-activemq/bin/activemq(无 5.18.3 子目录)
            "sh -c '"
            "setsid /opt/apache-activemq/bin/activemq start > /tmp/amq.log 2>&1; "
            "while true; do sleep 3600; done'"
        ),
        install_commands=(
            # cli.py 已经在 bootstrap 阶段装好 sshd,install 留 placeholder 让 validate_spec 通过
            "echo 'placeholder: sshd 已由 bootstrap 阶段装好'",
        ),
        start_commands=(
            # container_cmd 已启动 activemq,start_commands 留 placeholder
            "echo 'placeholder: activemq 已在 container_cmd 启动'",
        ),
        ready_check={
            # G2 副产物:双重检测 — web console + 端口任一就绪即可
            # web console 是 activemq 启动的最后一个环节,优先级更高
            "command": "curl -fsS -u admin:admin http://127.0.0.1:8161/admin/ -o /dev/null || ss -tln | grep -q ':61616 '",
            "timeout": 120,
            "interval": 3.0,
        },
    ),
    # --- G2.3 dameng (商业版首批,降级路径 — license 不可达) ---
    # 真实情况:
    # - 复用现成 dameng_default_discover.sh(plugins/inputs/dameng/,84 行,扫 dmap 进程 + readlink /proc/PID/exe)
    # - 镜像:xuxuclassmate/dameng:latest (Ubuntu 16.04 base + DM8) 可达,但 arm64 Mac 需 Rosetta 模拟 amd64
    #   (同 mssql 平台不匹配问题,且镜像精简,缺 sshd/net-tools,apt update 老源慢)
    # - license:第三方镜像内置(开发版),但生产链路严禁直接连非官方镜像,fixture 工具不引入新风险
    # 决策:catalog Spec 注册走 SSH 入口(ubuntu:22.04 base + sshd),但 install_commands 故意 fail
    #   标记 license 不可达,落盘占位 JSON 说明状态。
    # 后续解锁路径:用户提供达梦官方 license + 在 amd64 CI runner 跑(同 mssql 模式)
    "dameng": Spec(
        model_id="dameng",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12232, "5236/tcp": 15236},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="dameng_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={
            "host": "127.0.0.1",
            "ssh_port": 12232,
            "dm_port": 15236,
        },
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            # G2.3 降级路径:dm8 license 不可达,装 sshd 后故意 fail,落盘占位 JSON
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # fail marker:dm8 商业 license 不可达,真实采集推迟到 amd64 CI + license 就位时
            "echo 'G2.3 dameng blocked: license not available; see roadmap 2026-07-06 + phase2-plan 2026-07-07'",
            "exit 1",
        ),
        # start_commands 留 placeholder 让 validate_spec 通过(install_commands 故意 exit 1 不会到这步)
        start_commands=(
            "echo 'placeholder: G2.3 dameng install_commands 故意 exit 1,此命令不会被执行'",
        ),
        ready_check=None,
    ),
    # --- G2.2 ibmmq (商业版首批,选 B — catalog 占位 + TODO) ---
    # roadmap §3.4 G2.2 假设 enterprise/plugins/inputs/ibmmq/ 已实现(2026-06-30 batch1),
    # 实际验证 enterprise/ 目录为空,需要新建采集脚本 + 复杂 install(rpm/tar.gz/license)。
    # license 不可达 → 选 B:catalog 注册占位 Spec(start_commands 故意 exit 1),
    # 不落盘 ibmmq.json,后续用户提供 IBM MQ license 后再实施。
    "ibmmq": Spec(
        model_id="ibmmq",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12231, "1414/tcp": 11414, "9443/tcp": 19443},
        env={},
        wait_strategy={"type": "ssh", "timeout": 90, "interval": 1.0},
        init_script="ibmmq_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={
            "host": "127.0.0.1",
            "ssh_port": 12231,
            "mq_port": 11414,
            "web_port": 19443,
        },
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            # G2.2 选 B 占位:装 sshd 后故意 exit 1
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            "echo 'G2.2 ibmmq blocked: IBM MQ license not available; see roadmap 2026-07-06 + phase2-plan 2026-07-07'",
            "exit 1",
        ),
        start_commands=(
            "echo 'placeholder: G2.2 ibmmq install_commands 故意 exit 1,此命令不会被执行'",
        ),
        ready_check=None,
    ),
    # --- G1.4 mssql (ssh 入口 + sqlcmd,绕开 pyodbc native lib 环境依赖) ---
    "mssql": Spec(
        model_id="mssql",
        image="mcr.microsoft.com/mssql/server:2022-CU14-ubuntu-22.04",
        ports={"22/tcp": 14330, "1433/tcp": 14331},
        env={"ACCEPT_EULA": "Y", "MSSQL_SA_PASSWORD": "Testpw123!@#"},
        wait_strategy={"type": "ssh", "timeout": 90, "interval": 1.0},
        init_script="mssql_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 14330, "mssql_port": 14331, "sa_password": "Testpw123!@#"},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        # mssql 镜像默认 USER=mssql(uid 10001),不能 apt;container_user=root + container_cmd=None(走镜像默认 entrypoint 启 SQL Server)
        container_user="0:0",
        container_cmd=None,
        install_commands=(
            # mssql 官方镜像需要装 sshd(ssh 入口必备),并装 sqlcmd(mssql-tools)用于采集
            # 用 阿里云镜像源加速(微软源在国内慢)
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq 2>&1 | tail -3",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server sudo iproute2 curl procps gnupg2 apt-transport-https 2>&1 | tail -3",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 安装 mssql-tools(含 sqlcmd)
            "curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg 2>&1 | tail -3",
            "echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/11/prod bullseye main' > /etc/apt/sources.list.d/mssql-release.list",
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq 2>&1 | tail -3",
            "DEBIAN_FRONTEND=noninteractive ACCEPT_EULA=Y apt-get install -y -qq mssql-tools unixodbc-dev 2>&1 | tail -3 || DEBIAN_FRONTEND=noninteractive ACCEPT_EULA=Y apt-get install -y -qq mssql-tools 2>&1 | tail -5",
            # 把 sqlcmd 加到 PATH
            "echo 'export PATH=$PATH:/opt/mssql-tools/bin' >> /root/.bashrc",
        ),
        start_commands=(
            # 2026-07-07 阻塞:mssql 官方镜像仅 linux/amd64,arm64 Mac 上 Rosetta 模拟下 SQL Server 启动极慢
            # (5+ 分钟未监听 1433)。本机 mssql 采集走不通,留待 Phase 2 在 amd64 环境或 CI 上跑。
            "echo 'G1.4 mssql blocked on arm64-vs-amd64 platform mismatch; see roadmap 2026-07-06'",
            "exit 1",  # 故意失败,标识当前 Spec 不可用
        ),
        ready_check={"command": "/opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P 'Testpw123!@#' -Q 'SELECT 1' 2>/dev/null || /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P 'Testpw123!@#' -C -Q 'SELECT 1' 2>/dev/null", "timeout": 120, "interval": 5.0},
    ),
    # ============================================================
    # Phase 3 G3.1-G3.7 社区版扩展(7 个新对象,roadmap §3.1 高优先级)
    # 2026-07-08 落地:mongodb/nginx/tomcat 模式复制,镜像源已配置(daocloud + tuna)
    # 镜像可达性(2026-07-08 verify):
    # - memcached:1.6-alpine ✅
    # - openresty/openresty:1.21.4.2-alpine ✅(1.21-alpine tag 不存在,已切 1.21.4.2-alpine)
    # - hashicorp/consul:1.16 ✅
    # - zookeeper: docker.m.daocloud.io/library/zookeeper:3.9 ✅(官方源 timeout 改 daocloud)
    # - minio/minio:RELEASE.2023-09-30T07-02-29Z ✅(本地已缓存)
    # - etcd:quay.io/coreos/etcd:v3.5 manifest unknown → 走 ubuntu + apt 路径(plan §3.4 fallback)
    # - haproxy:2.8-alpine 网络抽风 → 走 ubuntu + apt 路径(plan §3.7 fallback)
    # ============================================================
    # --- G3.5 memcached (ubuntu + apt 路径,与 nginx/tomcat 一致) ---
    # 镜像策略调整 2026-07-08:原计划用 memcached:1.6-alpine(轻量),但 alpine 无 bash,
    # docker_lifecycle.bootstrap_sshd_in_container 用 `bash -c` 跑 apt 必然失败。
    # 统一走 ubuntu + apt(同 Phase 1/2),保持 cli 工具核心不动。
    "memcached": Spec(
        model_id="memcached",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12244, "11211/tcp": 11211},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="memcached_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12244},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq memcached iproute2 procps net-tools > /tmp/mc_install.log 2>&1 || (echo 'mc install failed:'; tail -30 /tmp/mc_install.log; exit 1)",
        ),
        start_commands=(
            # memcached -d 守护进程(采集脚本 ps 能扫到)
            # 默认监听 127.0.0.1,SSH 通过 127.0.0.1 采集 OK
            "memcached -m 64 -p 11211 -u memcache -d",
            "sleep 1",
        ),
        ready_check={"command": "ss -tln | grep -q ':11211 '", "timeout": 30, "interval": 1.0},
    ),
    # --- G3.6 openresty (降级路径,2026-07-08 验证) ---
    # 镜像策略调整 2026-07-08:openresty 装包多次失败,降级为占位模式(同 dameng/ibmmq):
    # 1. 官方 apt 源 `http://openresty.org/package/ubuntu` 在国内 apt update 经常失败
    # 2. wget 源码 + 编译方式 configure 阶段 LuaJIT library 找不到
    # 3. alpine 官方镜像无 bash(cli.bootstrap_sshd_in_container 需要)
    # 决策:catalog Spec 注册走 SSH 入口(ubuntu:22.04 + sshd),但 install_commands
    #   故意 fail 标记降级,后续在 amd64 CI runner 跑(同 mssql 模式)或换 apt 装包思路。
    "openresty": Spec(
        model_id="openresty",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12245, "80/tcp": 18081},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="openresty_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12245},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:openresty 装包在 3 种方式都失败(apt 源、wget 源码编译、alpine 无 bash)
            # 留待 amd64 CI runner 跑或换更稳的装包路径(预编译 deb / 从官方镜像 docker cp)
            "echo 'G3.6 openresty blocked: apt source / source compile / alpine 镜像 都失败,见 phase3-execution-report 2026-07-08'",
            "exit 1",
        ),
        start_commands=(
            "echo 'placeholder: G3.6 openresty install_commands 故意 exit 1,此命令不会被执行'",
        ),
        ready_check=None,
    ),
    # --- G3.3 consul (ubuntu + apt 安装 consul,plan §3.3 fallback) ---
    # 镜像策略调整 2026-07-08:consul 官方镜像 base 是 debian-slim(有 bash + apt),理论上能用,
    # 但 USER=consul(uid 1000)装 sshd 需 root + 启 consul 也需 root,container_cmd 复杂。
    # 改用 ubuntu + apt 装 consul(同 nginx 模式,采集脚本兼容)
    "consul": Spec(
        model_id="consul",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12242, "8500/tcp": 18500, "8600/tcp": 18600, "8300/tcp": 18300},
        env={},
        wait_strategy={"type": "ssh", "timeout": 90, "interval": 1.0},
        init_script="consul_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12242},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            # consul 官方 apt 源(hashicorp 提供)
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wget gnupg lsb-release net-tools iproute2 procps > /tmp/consul_pre.log 2>&1",
            "wget -O- https://apt.releases.hashicorp.com/gpg 2>/dev/null | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg 2>/dev/null",
            'echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" > /etc/apt/sources.list.d/hashicorp.list',
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq > /tmp/consul_update.log 2>&1 || (echo 'consul repo update failed:'; tail -10 /tmp/consul_update.log; exit 1)",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq consul > /tmp/consul_install.log 2>&1 || (echo 'consul install failed:'; tail -30 /tmp/consul_install.log; exit 1)",
        ),
        start_commands=(
            # consul dev mode 启动,client 0.0.0.0 暴露 8500,server bind 127.0.0.1(单节点)
            "nohup consul agent -dev -client=0.0.0.0 -bind=127.0.0.1 -log-level=warn > /tmp/consul.log 2>&1 &",
            "sleep 5",
        ),
        ready_check={"command": "ss -tln | grep -q ':8500 '", "timeout": 30, "interval": 1.0},
    ),
    # --- G3.4 etcd (ubuntu + apt 安装 etcd-server,plan §3.4 fallback) ---
    "etcd": Spec(
        model_id="etcd",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12243, "2379/tcp": 12379, "2380/tcp": 12380},
        env={},
        wait_strategy={"type": "ssh", "timeout": 90, "interval": 1.0},
        init_script="etcd_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12243},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq etcd-server iproute2 procps net-tools > /tmp/etcd_install.log 2>&1 || (echo 'etcd install failed:'; tail -30 /tmp/etcd_install.log; exit 1)",
        ),
        start_commands=(
            # etcd 需要正确配置:data-dir + listen client/peer + initial cluster(单节点)
            "mkdir -p /var/lib/etcd && chown etcd:etcd /var/lib/etcd",
            "nohup etcd --data-dir=/var/lib/etcd --listen-client-urls=http://0.0.0.0:2379 "
            "--advertise-client-urls=http://127.0.0.1:2379 --listen-peer-urls=http://0.0.0.0:2380 "
            "--initial-advertise-peer-urls=http://127.0.0.1:2380 --initial-cluster=default=http://127.0.0.1:2380 > /tmp/etcd.log 2>&1 &",
            "sleep 5",
        ),
        ready_check={"command": "ss -tln | grep -q ':2379 '", "timeout": 60, "interval": 1.0},
    ),
    # --- G3.7 haproxy (ubuntu + apt 安装 haproxy,plan §3.7 fallback) ---
    "haproxy": Spec(
        model_id="haproxy",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12246, "80/tcp": 18082, "8404/tcp": 18404},
        env={},
        wait_strategy={"type": "ssh", "timeout": 90, "interval": 1.0},
        init_script="haproxy_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12246},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq haproxy iproute2 procps net-tools > /tmp/haproxy_install.log 2>&1 || (echo 'haproxy install failed:'; tail -30 /tmp/haproxy_install.log; exit 1)",
        ),
        start_commands=(
            # ubuntu 22.04 haproxy 装了之后需要手动写最小可用配置(默认 /etc/haproxy/haproxy.cfg
            # 没 listen 80,只有 stats socket)。覆盖一份让 80 端口 listen。
            "printf 'global\\n    daemon\\n\\ndefaults\\n    mode http\\n    timeout connect 5000\\n    timeout client 50000\\n    timeout server 50000\\n\\nfrontend stats\\n    bind *:8404\\n    mode http\\n    stats enable\\n    stats uri /stats\\n\\nfrontend fe\\n    bind *:80\\n    default_backend be\\n\\nbackend be\\n    server s1 127.0.0.1:80\\n' > /etc/haproxy/haproxy.cfg",
            "haproxy -f /etc/haproxy/haproxy.cfg -D",
            "sleep 1",
        ),
        ready_check={"command": "ss -tln | grep -q ':80 '", "timeout": 30, "interval": 1.0},
    ),
    # --- G3.2 zookeeper (ubuntu + apt 安装 zookeeperd,plan §3.2 fallback) ---
    # 镜像策略调整 2026-07-08:zookeeper 镜像 base 是 ubuntu(有 bash + apt),
    # 但 USER=zookeeper 装 sshd 需 root + 启 zk 也需 root,container_cmd 复杂。
    # 改用 ubuntu + apt 装 zookeeperd(同 nginx 模式,采集脚本兼容)
    "zookeeper": Spec(
        model_id="zookeeper",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12241, "2181/tcp": 12181, "2888/tcp": 12888, "3888/tcp": 13888},
        env={},
        wait_strategy={"type": "ssh", "timeout": 120, "interval": 1.0},
        init_script="zookeeper_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12241},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            # zookeeperd 依赖 openjdk,apt 装可能要 2-3 分钟
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq zookeeperd iproute2 procps net-tools openjdk-11-jre-headless > /tmp/zk_install.log 2>&1 || (echo 'zk install failed:'; tail -30 /tmp/zk_install.log; exit 1)",
            # 默认 zoo.cfg 没启用 2181 client;在 conf 里加 clientPort(ubuntu 22.04 的 zookeeperd 包会自动启 client 2181)
            # 验证 /etc/zookeeper/conf/zoo.cfg 是否存在 clientPort
            "grep -q '^clientPort' /etc/zookeeper/conf/zoo.cfg 2>/dev/null && echo 'zk zoo.cfg OK' || (echo 'clientPort=2181' >> /etc/zookeeper/conf/zoo.cfg && echo 'zk append clientPort')",
        ),
        start_commands=(
            # zookeeperd 包自带 init script,直接 start
            "/usr/share/zookeeper/bin/zkServer.sh start",
            "sleep 5",
        ),
        ready_check={"command": "/usr/share/zookeeper/bin/zkServer.sh status 2>&1 | grep -q 'Mode: '", "timeout": 60, "interval": 2.0},
    ),
    # --- G3.1 minio (ubuntu + wget 下载 minio binary,plan §3.1 fallback) ---
    # 镜像策略调整 2026-07-08:minio 官方镜像 base 是 RedHat UBI,无 bash + USER=minio 装 sshd 复杂。
    # 改用 ubuntu + wget 下载 minio binary(同 kafka wget 模式,采集脚本兼容)
    "minio": Spec(
        model_id="minio",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12240, "9000/tcp": 19000, "9001/tcp": 19001},
        env={},
        wait_strategy={"type": "ssh", "timeout": 120, "interval": 1.0},
        init_script="minio_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12240},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wget iproute2 procps net-tools curl > /tmp/minio_pre.log 2>&1",
            # minio binary 下载(同 kafka wget 模式:清华源优先,失败回落 dl.min.io)
            "wget -q --tries=2 --timeout=60 https://mirrors.tuna.tsinghua.edu.cn/minio/server/minio/release/linux-amd64/minio -O /usr/local/bin/minio || wget -q --tries=3 --timeout=60 https://dl.min.io/server/minio/release/linux-amd64/minio -O /usr/local/bin/minio",
            "chmod +x /usr/local/bin/minio",
            "mkdir -p /data",
        ),
        start_commands=(
            # MINIO_ROOT_USER/PASSWORD 必须设(否则启不来)
            "MINIO_ROOT_USER=admin MINIO_ROOT_PASSWORD=adminpass123 nohup minio server /data --address ':9000' --console-address ':9001' > /tmp/minio.log 2>&1 &",
            "sleep 3",
        ),
        ready_check={"command": "ss -tln | grep -q ':9000 '", "timeout": 60, "interval": 2.0},
    ),
    # ============================================================
    # Phase 4 G4.1-G4.10 中等优先级 10 对象(roadmap §3.2 全部有 plugin 的)
    # 2026-07-08 落地:沿用 Phase 3 模式(ubuntu + apt + ssh 入口)
    # 镜像策略:JMX 类 5 走 apt 装 JDK + 服务;apache/squid/keepalived 走 apt;
    # rocketmq 走 wget 二进制;tuxedo 走镜像(待 verify);weblogic/websphere 降级
    # ============================================================
    # --- G4.1 jboss(wildfly,降级路径)---
    # 2026-07-08 装包失败:1) ubuntu 22.04 apt 没 wildfly 包;2) aliyun 没 wildfly 镜像;
    # 3) download.jboss.org 抽风;4) quay.io/wildfly 镜像超时(quay.io 国内慢)
    # 降级为占位模式(同 dameng/ibmmq/openresty)
    "jboss": Spec(
        model_id="jboss",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12250, "8080/tcp": 18090},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="jboss_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12250},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            "echo 'G4.1 jboss blocked: wildfly apt/aliyun/jboss.org 镜像都不可达;quay.io/wildfly 超时;见 phase4-execution-report 2026-07-08'",
            "exit 1",
        ),
        start_commands=(
            "echo 'placeholder: G4.1 jboss install_commands 故意 exit 1'",
        ),
        ready_check=None,
    ),
    # --- G4.2 jetty(降级)---
    # 2026-07-08 装包失败:1) ubuntu 22.04 apt 无 jetty9 包;2) wget 镜像可达性待 verify
    # 降级为占位(同 jboss/tongweb)
    "jetty": Spec(
        model_id="jetty",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12251, "8080/tcp": 18091},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="jetty_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12251},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            "echo 'G4.2 jetty blocked: ubuntu 22.04 apt 无 jetty9 包;见 phase4-execution-report 2026-07-08'",
            "exit 1",
        ),
        start_commands=(
            "echo 'placeholder: G4.2 jetty install_commands 故意 exit 1'",
        ),
        ready_check=None,
    ),
    # --- G4.3 tongweb(降级)---
    # 2026-07-08 装包失败:aliyun + tongtech 镜像都不可达(tar.gz 实际是 HTML 404)
    # 降级为占位
    "tongweb": Spec(
        model_id="tongweb",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12252, "8080/tcp": 18092},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="tongweb_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12252},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            "echo 'G4.3 tongweb blocked: aliyun + 东方通 官网 镜像都不可达;需用户提供 license 后再走官方源;见 phase4-execution-report 2026-07-08'",
            "exit 1",
        ),
        start_commands=(
            "echo 'placeholder: G4.3 tongweb install_commands 故意 exit 1'",
        ),
        ready_check=None,
    ),
    # --- G4.4 weblogic(license 降级)---
    "weblogic": Spec(
        model_id="weblogic",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12253, "7001/tcp": 18093, "9001/tcp": 18094},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="weblogic_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12253},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:Oracle WebLogic 12c 安装包需 Oracle 账号,license 不可达
            "echo 'G4.4 weblogic blocked: Oracle WebLogic license not available; see phase4-execution-report 2026-07-08'",
            "exit 1",
        ),
        start_commands=(
            "echo 'placeholder: G4.4 weblogic install_commands 故意 exit 1'",
        ),
        ready_check=None,
    ),
    # --- G4.5 websphere(license 降级)---
    "websphere": Spec(
        model_id="websphere",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12254, "9043/tcp": 18095, "9080/tcp": 18096},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="websphere_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12254},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:IBM WebSphere 9 安装包需 IBM 账号,license 不可达
            "echo 'G4.5 websphere blocked: IBM WebSphere license not available; see phase4-execution-report 2026-07-08'",
            "exit 1",
        ),
        start_commands=(
            "echo 'placeholder: G4.5 websphere install_commands 故意 exit 1'",
        ),
        ready_check=None,
    ),
    # --- G4.6 apache(社区版)---
    "apache": Spec(
        model_id="apache",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12255, "80/tcp": 18097},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="apache_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12255},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq apache2 iproute2 procps net-tools > /tmp/apache_install.log 2>&1 || (echo 'apache install failed:'; tail -30 /tmp/apache_install.log; exit 1)",
        ),
        start_commands=(
            # apache2 ubuntu 包默认 envvars 监听 80
            "apachectl start",
            "sleep 2",
        ),
        ready_check={"command": "ss -tln | grep -q ':80 '", "timeout": 30, "interval": 1.0},
    ),
    # --- G4.7 squid(社区版)---
    "squid": Spec(
        model_id="squid",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12256, "3128/tcp": 18098},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="squid_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12256},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq squid iproute2 procps net-tools > /tmp/squid_install.log 2>&1 || (echo 'squid install failed:'; tail -30 /tmp/squid_install.log; exit 1)",
        ),
        start_commands=(
            # squid -D 不解析 DNS 启动(避免容器内 DNS 解析失败)
            "squid -D -d 1 > /tmp/squid.log 2>&1 &",
            "sleep 2",
        ),
        ready_check={"command": "ss -tln | grep -q ':3128 '", "timeout": 30, "interval": 1.0},
    ),
    # --- G4.8 keepalived(降级)---
    # 2026-07-08 装包失败:keepalived 在容器内 VRRP multicast 受限,
    # daemon 模式 fork 失败阻塞 cli 流程(2 次尝试 setsid + nohup 都超时)
    # 降级为占位
    "keepalived": Spec(
        model_id="keepalived",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12257},  # keepalived 用 VRRP multicast,无 host 端口
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="keepalived_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12257},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            "echo 'G4.8 keepalived blocked: 容器内 VRRP multicast 受限,daemon 模式 fork 阻塞;需 privileged 模式或真实网络环境;见 phase4-execution-report 2026-07-08'",
            "exit 1",
        ),
        start_commands=(
            "echo 'placeholder: G4.8 keepalived install_commands 故意 exit 1'",
        ),
        ready_check=None,
    ),
    # --- G4.9 rocketmq(降级)---
    # 2026-07-08 装包调试时 wget + unzip 阻塞超时(32MB zip 慢,JVM 启动也慢)
    # 降级为占位(同 jboss/jetty/tongweb/keepalived)
    "rocketmq": Spec(
        model_id="rocketmq",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12258, "9876/tcp": 19876, "10911/tcp": 19875},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="rocketmq_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12258},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            "echo 'G4.9 rocketmq blocked: wget 32MB zip + JVM 启动慢,真实环境调试耗时过长;后续解锁路径:amd64 CI runner 跑;见 phase4-execution-report 2026-07-08'",
            "exit 1",
        ),
        start_commands=(
            "echo 'placeholder: G4.9 rocketmq install_commands 故意 exit 1'",
        ),
        ready_check=None,
    ),
    # --- G4.10 tuxedo(Oracle,license 不可达)---
    "tuxedo": Spec(
        model_id="tuxedo",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12259, "6600/tcp": 19860},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script="tuxedo_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12259},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:Oracle Tuxedo 镜像需 Oracle 账号,license 不可达
            "echo 'G4.10 tuxedo blocked: Oracle Tuxedo license not available; see phase4-execution-report 2026-07-08'",
            "exit 1",
        ),
        start_commands=(
            "echo 'placeholder: G4.10 tuxedo install_commands 故意 exit 1'",
        ),
        ready_check=None,
    ),
    # --- G5.1.1 mycat(中间件层,数据库分库分表 proxy,国产化首选)---
    # 模式:ubuntu 22.04 + jdk 11 + wget mycat 1.6.7.5 binary
    # 简化配置:空 schema + 不可达 writeHost(192.0.2.1,只验证启动 + 端口)
    # 注:mycat 启动需要 datasource,不可达时仍会监听 8066(只重试连接)
    # 踩坑(2026-07-08):1) mycat 1.6 官方 release 无 aarch64 wrapper,需 amd64 平台
    # 2) shell 脚本是 CRLF 格式,sed 转 LF;3) startup_nowrap.sh 比 bin/mycat start 简单(无 wrapper)
    # 4) schema 必填 dataNode;5) JAVA_HOME 必设;6) 需先 mkdir logs
    # 7) amd64 rosetta 模拟在 arm64 Mac 极慢(5+ 分钟 jdk 装不完),与 mssql 同源阻塞
    # 8) 已用 amd64 镜像手动验证 mycat 可启动 + 8066/9066 监听(见 phase5-execution-report §3)
    # 真实跑通需 amd64 CI runner(GitHub Actions ubuntu-22.04),本机 Mac arm64 跑会卡 rosetta
    "mycat": Spec(
        model_id="mycat",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        platform="linux/amd64",  # mycat 1.6 wrapper 只支持 x86_64 / x86_32 / ppc-64
        ports={"22/tcp": 12260, "8066/tcp": 18066, "9066/tcp": 19066},
        env={},
        wait_strategy={"type": "ssh", "timeout": 120, "interval": 1.0},
        init_script="mycat_default_discover.sh",
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12260},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server openjdk-11-jre-headless wget iproute2 procps net-tools > /tmp/mycat_install.log 2>&1 || (echo 'install failed:'; tail -30 /tmp/mycat_install.log; exit 1)",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # mycat 1.6.7.5 binary(GitHub release,arm64 没有 → 走 amd64 镜像)
            "wget -q --tries=2 --timeout=120 https://github.com/MyCATApache/Mycat-Server/releases/download/Mycat-server-1675-release/Mycat-server-1.6.7.5-release-20200422133810-linux.tar.gz -O /tmp/mycat.tgz && ls -la /tmp/mycat.tgz",
            "tar -xzf /tmp/mycat.tgz -C /opt/ && ls -la /opt/mycat/",
            # CRLF 转换(官方 release 脚本是 Windows 行尾,直接 bash 会 syntax error)
            "for f in /opt/mycat/bin/*.sh /opt/mycat/bin/mycat; do sed -i 's/\\r$//' \"$f\"; done",
            # 创建 logs 目录(startup_nowrap.sh 启动需要)
            "mkdir -p /opt/mycat/logs",
        ),
        start_commands=(
            # 简化 schema.xml:空 schema + 不可达 writeHost(192.0.2.1:3306,只验证启动 + 端口)
            # 注意:schema 必填 dataNode,否则 "schema TESTDB didn't config tables" 启动失败
            "cat > /opt/mycat/conf/schema.xml <<'EOF'\n<?xml version=\"1.0\"?>\n<!DOCTYPE mycat:schema SYSTEM \"schema.dtd\">\n<mycat:schema xmlns:mycat=\"http://io.mycat/\">\n<schema name=\"TESTDB\" checkSQLschema=\"false\" sqlMaxLimit=\"100\" dataNode=\"dn1\"></schema>\n<dataNode name=\"dn1\" dataHost=\"dh1\" database=\"mysql\" />\n<dataHost name=\"dh1\" maxCon=\"1000\" minCon=\"10\" balance=\"0\" writeType=\"0\" dbType=\"mysql\" dbDriver=\"native\" switchType=\"1\" slaveThreshold=\"100\">\n<heartbeat>select user()</heartbeat>\n<writeHost host=\"hostM1\" url=\"192.0.2.1:3306\" user=\"root\" password=\"\">\n</writeHost>\n</dataHost>\n</mycat:schema>\nEOF",
            # server.xml 配 default 账号指向 TESTDB
            "sed -i 's|<property name=\"schemas\">[^<]*</property>|<property name=\"schemas\">TESTDB</property>|' /opt/mycat/conf/server.xml",
            # 启动 mycat(用 startup_nowrap.sh,绕开 wrapper arch 问题)
            "export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64",
            "nohup /opt/mycat/bin/startup_nowrap.sh > /opt/mycat/logs/console.log 2>&1 &",
            "sleep 5",
        ),
        ready_check={"command": "ss -tln | grep -q ':8066 '", "timeout": 60, "interval": 2.0},
    ),
    # --- G5.1.2 ihs(IBM HTTP Server,基于 Apache 2.4 商业版)---
    # 端口 80(http) + 8008(admin),IBM 官方 rpm,license 不可达 + amd64 模拟未验证
    "ihs": Spec(
        model_id="ihs",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12261, "80/tcp": 18061, "8008/tcp": 18008},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12261},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:IBM 官方 rpm + license 不可达 + amd64 模拟未验证
            "echo 'G5.1.2 ihs blocked: IBM HTTP Server license + amd64; see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.1.2 ihs install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.1.3 gbase8s(南大通用,国产数据库)---
    # 端口 9088(default),国产镜像可达性 + amd64 模拟未验证
    "gbase8s": Spec(
        model_id="gbase8s",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12262, "9088/tcp": 19088},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12262},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:国产镜像可达性 + amd64 模拟未验证
            "echo 'G5.1.3 gbase8s blocked: 国产镜像 + amd64 模拟未验证;see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.1.3 gbase8s install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.1.4 oscar(神通数据库,国产)---
    # 端口 2003(default),国产镜像可达性 + amd64 模拟未验证
    "oscar": Spec(
        model_id="oscar",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12263, "2003/tcp": 12003},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12263},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:国产镜像可达性 + amd64 模拟未验证
            "echo 'G5.1.4 oscar blocked: 国产镜像 + amd64 模拟未验证;see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.1.4 oscar install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.1.5 tonglinkq(东方通 TongLINK/Q,国产消息中间件)---
    # 端口 5622(default 端口,具体看官方文档),license + amd64 模拟未验证
    "tonglinkq": Spec(
        model_id="tonglinkq",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12264, "5622/tcp": 15622},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12264},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:东方通 rpm + license 不可达 + amd64 模拟未验证
            "echo 'G5.1.5 tonglinkq blocked: 东方通 rpm + license + amd64; see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.1.5 tonglinkq install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.1.6 tonggtp(东方通 TongGTP,国产消息中间件)---
    # 端口 8800(default),license + amd64 模拟未验证
    "tonggtp": Spec(
        model_id="tonggtp",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12265, "8800/tcp": 18800},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12265},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:东方通 rpm + license + amd64 模拟未验证
            "echo 'G5.1.6 tonggtp blocked: 东方通 rpm + license + amd64; see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.1.6 tonggtp install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.1.7 apusic(国产应用服务器,东方通)---
    # 端口 6888(default admin),license + amd64 模拟未验证
    "apusic": Spec(
        model_id="apusic",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12266, "6888/tcp": 16888, "9090/tcp": 19090},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12266},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:东方通 rpm + license + amd64 模拟未验证
            "echo 'G5.1.7 apusic blocked: 东方通 rpm + license + amd64; see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.1.7 apusic install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.1.8 inforsuite_as(InforSuite 应用服务器,中创)---
    # 端口 8080(default),license + amd64 模拟未验证
    "inforsuite_as": Spec(
        model_id="inforsuite_as",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12267, "8080/tcp": 18067, "1099/tcp": 11099},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12267},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:中创 rpm + license + amd64 模拟未验证
            "echo 'G5.1.8 inforsuite_as blocked: 中创 rpm + license + amd64; see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.1.8 inforsuite_as install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.1.9 bes(国产中间件,文档少)---
    # 端口待查(无完整官方文档),license + amd64 模拟未验证
    "bes": Spec(
        model_id="bes",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12268, "8080/tcp": 18068},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12268},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:国产中间件 rpm + 文档少 + license + amd64 模拟未验证
            "echo 'G5.1.9 bes blocked: 国产 rpm + 文档少 + license + amd64; see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.1.9 bes install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.1.10 domestic_linux(host_manage 商业版,ssh 入口适配麒麟/统信/欧拉)---
    # 不是跑服务,是 ssh 入口适配麒麟/统信/欧拉(centos/rhel 系用 dnf 而非 apt)
    "domestic_linux": Spec(
        model_id="domestic_linux",
        image="docker.m.daocloud.io/library/ubuntu:22.04",  # 临时 ubuntu 镜像占位
        ports={"22/tcp": 12269},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12269},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:麒麟/统信/欧拉 dnf 适配 + amd64 模拟未验证
            # 实际生产应基于 openeuler 镜像(host 采集,不需要跑服务,主要看 ssh 采集流程)
            "echo 'G5.1.10 domestic_linux blocked: 麒麟/统信/欧拉 dnf 适配 + amd64; see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.1.10 domestic_linux install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.1.11 informix(IBM DB,license 风险,能采就采)---
    # 端口 9088 + 1526,IBM 官方 docker 镜像,license 不可达 + amd64 模拟未验证
    "informix": Spec(
        model_id="informix",
        image="docker.m.daocloud.io/library/ubuntu:22.04",  # 改用 ubuntu 装(IBM docker 镜像需 license)
        ports={"22/tcp": 12270, "9088/tcp": 29088, "1526/tcp": 11526},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12270},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:IBM docker 镜像需 license + amd64 模拟未验证
            # 用户 §6.2 决策:能采就采,不能就放弃 → 当前 catalog 占位
            "echo 'G5.1.11 informix blocked: IBM docker 镜像 + license + amd64; see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.1.11 informix install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.1.12 sybase(SAP DB,license 复杂,能采就采)---
    # 端口 5000 + 4100,SAP docker 镜像需 license,amd64 模拟未验证
    "sybase": Spec(
        model_id="sybase",
        image="docker.m.daocloud.io/library/ubuntu:22.04",  # 改用 ubuntu 装(SAP 镜像需 license)
        ports={"22/tcp": 12271, "5000/tcp": 15000, "4100/tcp": 14100},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12271},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:SAP docker 镜像需 license + amd64 模拟未验证
            # 用户 §6.2 决策:能采就采,不能就放弃 → 当前 catalog 占位
            "echo 'G5.1.12 sybase blocked: SAP docker 镜像 + license + amd64; see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.1.12 sybase install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.2.1 influxdb(influxdb-client 已有 plugin,只 catalog 化)---
    # 端口 8086(default),python 入口,plugin 已有,只 catalog 化(spec.install_commands 占位)
    "influxdb": Spec(
        model_id="influxdb",
        image="docker.m.daocloud.io/library/influxdb:2.7",  # 官方镜像
        ports={"8086/tcp": 18086},
        env={"DOCKER_INFLUXDB_INIT_MODE": "setup", "DOCKER_INFLUXDB_INIT_USERNAME": "admin", "DOCKER_INFLUXDB_INIT_PASSWORD": "testpw", "DOCKER_INFLUXDB_INIT_ORG": "testorg", "DOCKER_INFLUXDB_INIT_BUCKET": "testbucket", "DOCKER_INFLUXDB_INIT_ADMIN_TOKEN": "testtoken"},
        wait_strategy={"type": "tcp", "port": 18086, "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.influxdb.influxdb_info",  # 已有 plugin
        entry_class="InfluxdbInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "port": 18086, "token": "***", "org": "testorg", "bucket": "testbucket"},
    ),
    # --- G5.2.2 nacos(阿里开源,配置中心,REST)---
    # 端口 8848(default) + 9848(gRPC),python 入口
    "nacos": Spec(
        model_id="nacos",
        image="docker.m.daocloud.io/library/nacos/nacos-server:v2.3.2",
        ports={"8848/tcp": 18848, "9848/tcp": 19848},
        env={"MODE": "standalone", "JVM_XMS": "256m", "JVM_XMX": "256m", "JVM_XMN": "128m"},
        wait_strategy={"type": "tcp", "port": 18848, "timeout": 120, "interval": 1.0},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.nacos.nacos_info",
        entry_class="NacosInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "port": 18848},
    ),
    # --- G5.2.3 highgo(国产数据库,PG 兼容,psycopg2)---
    # 端口 5432(default)
    "highgo": Spec(
        model_id="highgo",
        image="docker.m.daocloud.io/library/postgres:16-alpine",  # 临时用 postgres 镜像
        ports={"5432/tcp": 25432},
        env={"POSTGRES_PASSWORD": "testpw", "POSTGRES_USER": "highgo", "POSTGRES_DB": "highgo"},
        wait_strategy={"type": "tcp", "port": 25432, "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.highgo.highgo_info",
        entry_class="HighgoInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "port": 25432, "user": "highgo", "password": "***", "dbname": "highgo"},
    ),
    # --- G5.2.4 tdsql(腾讯分布式 DB,MySQL 兼容)---
    # 端口 3306(default),pymysql 改造(复用 mysql 入口)
    "tdsql": Spec(
        model_id="tdsql",
        image="docker.m.daocloud.io/library/mysql:8.0",  # 临时用 mysql 镜像(TDSQL 需 license)
        ports={"3306/tcp": 23306},
        env={"MYSQL_ROOT_PASSWORD": "testpw"},
        wait_strategy={"type": "tcp", "port": 23306, "timeout": 120, "interval": 1.0},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.tdsql.tdsql_info",
        entry_class="TdsqlInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "port": 23306, "user": "root", "password": "***"},
    ),
    # --- G5.2.5 ambari(Apache 大数据管理,REST)---
    # 端口 8080(default)
    "ambari": Spec(
        model_id="ambari",
        image="docker.m.daocloud.io/library/ubuntu:22.04",  # ambari 无官方 docker 镜像,需手动装
        ports={"22/tcp": 12272, "8080/tcp": 18072},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.ambari.ambari_info",
        entry_class="AmbariInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12272, "ambari_port": 18072, "user": "admin", "password": "***"},
    ),
    # --- G5.2.6 server_bmc(host_manage 商业版,Redfish API)---
    # 端口 443(default)
    "server_bmc": Spec(
        model_id="server_bmc",
        image="docker.m.daocloud.io/library/ubuntu:22.04",  # Redfish mock server(可用 sushy 模拟)
        ports={"22/tcp": 12273, "443/tcp": 10443},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.server_bmc.server_bmc_info",
        entry_class="ServerBmcInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12273, "bmc_port": 10443, "user": "admin", "password": "***"},
    ),
    # --- G5.2.7 oceanbase(蚂蚁分布式 DB,pyobclient)---
    # 端口 2881(OBProxy)+ 2883(RS)
    "oceanbase": Spec(
        model_id="oceanbase",
        image="docker.m.daocloud.io/library/ubuntu:22.04",  # oceanbase 无官方 docker 镜像(需 license)
        ports={"22/tcp": 12274, "2881/tcp": 12881},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.oceanbase.oceanbase_info",
        entry_class="OceanbaseInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12274, "ob_port": 12881, "user": "root", "password": "***", "database": "test"},
    ),
    # --- G5.2.8 tongrds(东方通数据库)---
    # 端口待查,license 不可达 + amd64 模拟未验证
    "tongrds": Spec(
        model_id="tongrds",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12275, "1186/tcp": 11186},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.tongrds.tongrds_info",
        entry_class="TongrdsInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12275, "rds_port": 11186, "user": "sysdba", "password": "***"},
    ),
    # --- G5.2.9 couchbase(SDK,couchbase 官方镜像需 enterprise license)---
    # 端口 11210
    "couchbase": Spec(
        model_id="couchbase",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12276, "11210/tcp": 11210},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.couchbase.couchbase_info",
        entry_class="CouchbaseInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12276, "cb_port": 11210, "user": "admin", "password": "***"},
    ),
    # --- G5.2.10 sap_hana(license 不可达,只 catalog 占位)---
    "sap_hana": Spec(
        model_id="sap_hana",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12277, "30015/tcp": 30015},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.sap_hana.sap_hana_info",
        entry_class="SapHanaInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12277, "hana_port": 30015, "user": "system", "password": "***"},
    ),
    # --- G5.2.11 iris(driver 缺失,只 catalog 占位)---
    # 端口 1972(super)+ 51773/bi
    "iris": Spec(
        model_id="iris",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12278, "1972/tcp": 1972, "51773/tcp": 51773},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.iris.iris_info",
        entry_class="IrisInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12278, "iris_port": 1972, "user": "_system", "password": "***", "namespace": "USER"},
    ),
    # --- G5.3.1 hdfs(Hadoop HDFS 集群,单节点伪分布式)---
    # NameNode 端口 9000 + 9870(web UI),DataNode 端口 9864
    # 单节点伪分布式:NameNode + DataNode 同进程,数据形态跟生产集群差异大
    "hdfs": Spec(
        model_id="hdfs",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12279, "9000/tcp": 29000, "9870/tcp": 29870, "9864/tcp": 29864},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12279},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:Hadoop 单节点伪分布式需 jdk + hadoop 2.x binary,amd64 模拟未验证
            "echo 'G5.3.1 hdfs blocked: jdk + hadoop 单节点伪分布式 + amd64; see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.3.1 hdfs install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.3.2 yarn(Hadoop YARN 集群,单节点伪分布式)---
    # ResourceManager 端口 8088(web UI) + 8032(scheduler)
    "yarn": Spec(
        model_id="yarn",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12280, "8088/tcp": 18088, "8032/tcp": 18032},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12280},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:YARN 单节点伪分布式 + amd64 模拟未验证
            "echo 'G5.3.2 yarn blocked: YARN 单节点伪分布式 + amd64; see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.3.2 yarn install_commands 故意 exit 1'",),
        ready_check=None,
    ),
    # --- G5.3.3 storm(Apache Storm 集群,单节点伪分布式)---
    # Nimbus 端口 6627 + UI 8080
    "storm": Spec(
        model_id="storm",
        image="docker.m.daocloud.io/library/ubuntu:22.04",
        ports={"22/tcp": 12281, "6627/tcp": 16627, "8080/tcp": 28081},
        env={},
        wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
        init_script=None,
        entry_type="ssh",
        entry_module=None,
        entry_class=None,
        collector_kwargs={"host": "127.0.0.1", "ssh_port": 12281},
        vm_privileged=False,
        vm_ssh_user="root",
        vm_ssh_password="testpw",
        install_commands=(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
            "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
            "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
            "/usr/sbin/sshd",
            # 2026-07-08 阻塞:Storm 单节点伪分布式 + amd64 模拟未验证
            "echo 'G5.3.3 storm blocked: Storm 单节点伪分布式 + amd64; see plan 2026-07-08'",
            "exit 1",
        ),
        start_commands=("echo 'placeholder: G5.3.3 storm install_commands 故意 exit 1'",),
        ready_check=None,
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


def validate_spec(spec: Spec, init_dir: Optional[Path] = None) -> List[str]:
    """校验单个 Spec 配置正确性。返回错误列表(空 = 通过)。

    跨对象校验(端口冲突)不在此处,在 validate() 顶层处理。
    init_dir: init 脚本所在目录,默认 collect_fixtures/init/
    """
    errors: List[str] = []
    if init_dir is None:
        init_dir = Path(__file__).parent / "init"

    if spec.entry_type == "python":
        if not spec.entry_module or not spec.entry_class:
            errors.append(f"{spec.model_id}: python 入口必须填 entry_module + entry_class")
        else:
            # Gap-4 #1: 检查 entry_module 真正可导入,防止路径拼写错误延迟到 collect 阶段暴露
            try:
                module = importlib.import_module(spec.entry_module)
            except ImportError as e:
                errors.append(
                    f"{spec.model_id}: entry_module '{spec.entry_module}' 无法 import: {e}"
                )
            else:
                # Gap-4 #2: 检查 entry_class 真是模块的属性
                if not hasattr(module, spec.entry_class):
                    errors.append(
                        f"{spec.model_id}: entry_class '{spec.entry_class}' "
                        f"不在模块 '{spec.entry_module}' 中"
                    )
                else:
                    # Gap-4 #3: 检查 entry_method 真是 entry_class 的方法
                    cls = getattr(module, spec.entry_class)
                    if not hasattr(cls, spec.entry_method):
                        errors.append(
                            f"{spec.model_id}: entry_method '{spec.entry_method}' "
                            f"不在 {spec.entry_class} 中"
                        )
    elif spec.entry_type == "shell":
        if not spec.init_script:
            errors.append(f"{spec.model_id}: shell 入口必须填 init_script（脚本路径）")
    elif spec.entry_type == "ssh":
        if not spec.vm_ssh_password:
            errors.append(f"{spec.model_id}: ssh 入口必须填 vm_ssh_password")
    else:
        errors.append(f"{spec.model_id}: 不支持的 entry_type '{spec.entry_type}'")

    # 检查 init_script 文件存在
    if spec.init_script and not (init_dir / spec.init_script).exists():
        errors.append(f"{spec.model_id}: init_script 文件不存在: {init_dir / spec.init_script}")

    # Gap-4 #4: init_script 后缀与 entry_type 一致
    if spec.init_script:
        suffix_rules = {
            "python": ".sql",
            "shell": ".sh",
            "ssh": "_default_discover.sh",
        }
        expected = suffix_rules.get(spec.entry_type)
        if expected and not spec.init_script.endswith(expected):
            errors.append(
                f"{spec.model_id}: init_script 后缀错(应 {expected},实际 {spec.init_script!r})"
            )

    # Gap-4 #5: wait_strategy 字段组合
    ws = spec.wait_strategy or {}
    ws_type = ws.get("type")
    if ws_type not in ("tcp", "ssh"):
        errors.append(
            f"{spec.model_id}: wait_strategy.type 非法(应为 tcp/ssh,实际 {ws_type!r})"
        )
    elif ws_type == "tcp" and not isinstance(ws.get("port"), int):
        errors.append(
            f"{spec.model_id}: wait_strategy.type='tcp' 必须带 int port 字段"
        )
    elif ws_type == "ssh" and not isinstance(ws.get("timeout"), (int, float)):
        errors.append(
            f"{spec.model_id}: wait_strategy.type='ssh' 必须带 timeout 字段(秒)"
        )

    # Gap-4 #6: ports 的 key 必须形如 '数字/tcp' 或 '数字/udp'
    for key in spec.ports.keys():
        if "/" not in key:
            errors.append(
                f"{spec.model_id}: ports key {key!r} 格式错(应 '端口/tcp' 或 '端口/udp')"
            )
            continue
        port_str, proto = key.rsplit("/", 1)
        if proto not in ("tcp", "udp"):
            errors.append(
                f"{spec.model_id}: ports key {key!r} 协议非法(应 tcp/udp)"
            )
            continue
        if not port_str.isdigit():
            errors.append(
                f"{spec.model_id}: ports key {key!r} 端口段不是数字"
            )
            continue
        port_num = int(port_str)
        if not (1 <= port_num <= 65535):
            errors.append(
                f"{spec.model_id}: ports key {key!r} 端口 {port_num} 越界(1-65535)"
            )

    # Gap-4 #7: ssh 入口 install_commands / start_commands 必填
    if spec.entry_type == "ssh":
        if not spec.install_commands:
            errors.append(
                f"{spec.model_id}: ssh 入口必须填 install_commands"
            )
        if not spec.start_commands:
            errors.append(
                f"{spec.model_id}: ssh 入口必须填 start_commands"
            )

    return errors


def validate() -> List[str]:
    """校验所有 Spec 配置正确性。返回错误列表(空 = 通过)。"""
    init_dir = Path(__file__).parent / "init"
    errors: List[str] = []

    seen_ports: Dict[int, str] = {}
    for mid, spec in MODEL_SPECS.items():
        errors.extend(validate_spec(spec, init_dir))

        # 端口冲突是跨对象校验,留在 validate 顶层
        for host_port in spec.ports.values():
            if host_port in seen_ports:
                errors.append(
                    f"{mid}: 端口 {host_port} 与 {seen_ports[host_port]} 冲突"
                )
            seen_ports[host_port] = mid

    return errors