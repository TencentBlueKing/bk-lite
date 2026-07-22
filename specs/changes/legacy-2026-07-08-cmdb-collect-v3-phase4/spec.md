# Historical Superpowers change: 2026-07-08-cmdb-collect-v3-phase4

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-08-cmdb-collect-v3-phase4-plan.md

> **状态**:执行计划(2026-07-08)｜ **前置**:Phase 1/2/3 已落(worktree `feature-cmdb-collect-v3-gap4-validate`)
> **关联 roadmap**:[`2026-07-06-cmdb-collect-v3-roadmap.md`](2026-07-06-cmdb-collect-v3-roadmap.md) §3.2
> **关联 Phase 3 报告**:[`2026-07-08-cmdb-collect-v3-phase3-execution-report.md`](2026-07-08-cmdb-collect-v3-phase3-execution-report.md)

---

## 0. 范围(roadmap §3.2 全部有 plugin 的 10 个)

| 类型 | 对象 | plugin 行数 | 装包 | 风险 |
|---|---|---|---|---|
| **A. JMX 类 5** | jboss | 53 | apt `wildfly` | 🟢 |
| A. JMX | jetty | 94 | apt `jetty9` | 🟢 |
| A. JMX + 国产 | **tongweb** | 81 | 东方通 tarball | 🟡 |
| A. JMX | weblogic | 93 | Oracle zip,**license** | 🟡 降级 |
| A. JMX | websphere | 61 | IBM zip,**license** | 🟡 降级 |
| **C. 社区版 apt 装 3** | apache | 133 | apt `apache2` | 🟢 |
| C. | squid | 33 | apt `squid` | 🟢 |
| C. | keepalived | 60 | apt `keepalived` | 🟢 |
| **D. 社区版镜像 2** | rocketmq | 60 | apache/rocketmq 镜像 | 🟡 |
| D. | tuxedo | 37 | Oracle Tuxedo 镜像 | 🟡 |

**roadmap §3.2 国产化 8 个无 plugin 排除**:tonglinkq / tonggtp / apusic / inforsuite_as / bes / ihs / gbase8s / oscar / mycat(写 plugin 是独立工作量,Phase 5+ 排期)。

---

## 1. 现状(2026-07-08)

- MODEL_SPECS 14 → 21(Phase 1/2/3 完成)
- 镜像源 aliyun 切换已修(Phase 3)
- bk_host_innerip 模板替换 bug 已在 init/ 副本修复 3 个(memcached/openresty/haproxy)
- **Phase 4 10 个对象需要新修 bk_host_innerip bug**(JMX 类 5 个全有 `{{bk_host_innerip}}`)

---

## 2. 设计决策(继承 Phase 1/2/3 plan §0)

### 2.1 入口选型

所有 10 个对象都走 **SSH 入口 + ubuntu:22.04**(同 Phase 3 模式):
- bootstrap_sshd_in_container 用 `bash -c` 跑 apt,只支持 debian 系
- 统一路径,不动 cli 工具核心
- JMX 类(Java 应用)额外装 openjdk-11-jre-headless

### 2.2 镜像可达性(2026-07-08 待 verify)

| 对象 | 镜像 | 待 verify |
|---|---|---|
| jboss/wildfly | apt `wildfly` | 🟢 apt 路径,稳 |
| jetty | apt `jetty9` | 🟢 apt 路径,稳 |
| tongweb | 东方通 tarball,需下载 | 🟡 镜像/下载源待 verify |
| weblogic | Oracle 官方 zip | 🟡 需账号,降级 |
| websphere | IBM 官方 zip | 🟡 需账号,降级 |
| apache | apt `apache2` | 🟢 apt 路径,稳 |
| squid | apt `squid` | 🟢 apt 路径,稳 |
| keepalived | apt `keepalived` | 🟢 apt 路径,稳 |
| rocketmq | apache/rocketmq 镜像 | 🟡 单 broker 模式 |
| tuxedo | Oracle Tuxedo 镜像 | 🟡 镜像待 verify |

### 2.3 端口分配(避开已有 21 对象)

| 对象 | ssh | 业务端口 |
|---|---|---|
| jboss/wildfly | 12250 | 18080/tomcat 冲突 → 18090 |
| jetty | 12251 | 18091 |
| tongweb | 12252 | 18092 |
| weblogic | 12253 | 18093 |
| websphere | 12254 | 18094, 18095(SSL)|
| apache | 12255 | 18096 |
| squid | 12256 | 18097(http) + 18098(https)|
| keepalived | 12257 | n/a(VRRP 协议) |
| rocketmq | 12258 | 19876(name server) + 19875(broker) |
| tuxedo | 12259 | 19850 |

> 冲突解决:wildfly/tomcat 都用 8080,顺延 18090;weblogic 9043/7001 顺延 18093/18094 等。

---

## 3. 单对象执行细节

### G4.1 jboss(wildfly)

**目标**:单 wildfly 实例,采集 jvm_xms / jvm_xmx / role / config_file

**Spec 关键点**:
```python
"jboss": Spec(
    model_id="jboss",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12250, "8080/tcp": 18090},
    env={},
    wait_strategy={"type": "ssh", "timeout": 60, "interval": 1.0},
    init_script="jboss_default_discover.sh",
    entry_type="ssh",
    collector_kwargs={"host": "127.0.0.1", "ssh_port": 12250},
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wildfly iproute2 procps net-tools openjdk-11-jre-headless > /tmp/jboss_install.log 2>&1 || (echo 'jboss install failed:'; tail -30 /tmp/jboss_install.log; exit 1)",
    ),
    start_commands=(
        # wildfly 装在 /opt/wildfly,默认 standalone 模式
        "nohup /opt/wildfly/bin/standalone.sh -b 0.0.0.0 > /tmp/wildfly.log 2>&1 &",
        "sleep 15",  # JVM 启动 5-10s
    ),
    ready_check={"command": "ss -tln | grep -q ':8080 '", "timeout": 60, "interval": 2.0},
),
```

**风险**:JVM 启动慢(10-15s),wait_strategy 60s 应该够;wildfly 装好后默认监听 8080 但只 bind 127.0.0.1,需 `-b 0.0.0.0` 显式指定。

---

### G4.2 jetty

**目标**:单 jetty9 实例,采集 jetty_version / port

**Spec 关键点**:
```python
"jetty": Spec(
    model_id="jetty",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12251, "8080/tcp": 18091},
    ...
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq jetty9 iproute2 procps net-tools openjdk-11-jre-headless > /tmp/jetty_install.log 2>&1 || (echo 'jetty install failed:'; tail -30 /tmp/jetty_install.log; exit 1)",
    ),
    start_commands=(
        # jetty9 默认 /etc/jetty9/start.ini 配 8080
        "nohup java -jar /usr/share/jetty9/start.jar > /tmp/jetty.log 2>&1 &",
        "sleep 10",
    ),
    ready_check={"command": "ss -tln | grep -q ':8080 '", "timeout": 60, "interval": 2.0},
),
```

**风险**:jetty9 apt 包默认配置可能没启用 HTTP connector,需手动检查 `/etc/jetty9/jetty-http.xml`。

---

### G4.3 tongweb(国产,东方通)

**目标**:单 tongweb 实例,采集 tongweb 路径 / 端口

**Spec 关键点**:
```python
"tongweb": Spec(
    model_id="tongweb",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12252, "8080/tcp": 18092},
    ...
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq iproute2 procps net-tools openjdk-11-jre-headless unzip > /tmp/tongweb_pre.log 2>&1",
        # 东方通官网下载安装包(需研究 URL;Phase 4 先试东方通国内镜像,失败再降级)
        "mkdir -p /opt/tongweb && cd /opt/tongweb && wget -q --tries=2 --timeout=60 https://mirrors.tuna.tsinghua.edu.cn/tongweb/7.0/tongweb-7.0.zip -O /tmp/tongweb.zip || (echo 'tongweb download failed'; exit 1)",
        "cd /opt/tongweb && unzip -q /tmp/tongweb.zip",
    ),
    start_commands=(
        "nohup /opt/tongweb/bin/startserver.sh > /tmp/tongweb.log 2>&1 &",
        "sleep 15",
    ),
    ready_check={"command": "ss -tln | grep -q ':8080 '", "timeout": 60, "interval": 2.0},
),
```

**风险**:
- 东方通国内下载源待 verify(可能要走 license 申请,或用试用版)
- 启动脚本路径可能不是 startserver.sh(需 verify)
- 容器内 Java 启动慢

---

### G4.4 weblogic(license 降级占位)

**目标**:Orcale WebLogic 12c,采集 domain / port / version

**Spec 关键点**:
```python
"weblogic": Spec(
    model_id="weblogic",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12253, "7001/tcp": 18093, "9001/tcp": 18094},
    ...
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
        "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
        "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
        "/usr/sbin/sshd",
        # 2026-07-08 阻塞:Oracle WebLogic 12c 安装包需 Oracle 账号,license 不可达
        # 后续解锁:用户提供账号或在 amd64 CI runner 跑(同 mssql 模式)
        "echo 'G4.4 weblogic blocked: Oracle WebLogic license not available; see phase4-execution-report 2026-07-08'",
        "exit 1",
    ),
    start_commands=(
        "echo 'placeholder: G4.4 weblogic install_commands 故意 exit 1,此命令不会被执行'",
    ),
    ready_check=None,
),
```

---

### G4.5 websphere(license 降级占位)

**目标**:IBM WebSphere 9,采集 profile / port / version

**Spec 关键点**:
```python
"websphere": Spec(
    model_id="websphere",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12254, "9043/tcp": 18095, "9080/tcp": 18096},
    ...
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
        "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
        "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
        "/usr/sbin/sshd",
        # 2026-07-08 阻塞:IBM WebSphere 安装包需 IBM 账号,license 不可达
        "echo 'G4.5 websphere blocked: IBM WebSphere license not available; see phase4-execution-report 2026-07-08'",
        "exit 1",
    ),
    start_commands=(
        "echo 'placeholder: G4.5 websphere install_commands 故意 exit 1,此命令不会被执行'",
    ),
    ready_check=None,
),
```

---

### G4.6 apache(社区版)

**目标**:apache2 单实例,采集 httpd_version / port

**Spec 关键点**:
```python
"apache": Spec(
    model_id="apache",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12255, "80/tcp": 18097},
    ...
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq apache2 iproute2 procps net-tools > /tmp/apache_install.log 2>&1 || (echo 'apache install failed:'; tail -30 /tmp/apache_install.log; exit 1)",
    ),
    start_commands=(
        "apachectl start",
        "sleep 1",
    ),
    ready_check={"command": "ss -tln | grep -q ':80 '", "timeout": 30, "interval": 1.0},
),
```

**风险**:apache2 ubuntu apt 包默认监听 80,采集脚本应能直接拿到。

---

### G4.7 squid(社区版)

**目标**:squid 单实例,采集 squid_version / port

**Spec 关键点**:
```python
"squid": Spec(
    model_id="squid",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12256, "3128/tcp": 18098},
    ...
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq squid iproute2 procps net-tools > /tmp/squid_install.log 2>&1 || (echo 'squid install failed:'; tail -30 /tmp/squid_install.log; exit 1)",
    ),
    start_commands=(
        "squid -D -d 1",
        "sleep 2",
    ),
    ready_check={"command": "ss -tln | grep -q ':3128 '", "timeout": 30, "interval": 1.0},
),
```

---

### G4.8 keepalived(社区版)

**目标**:keepalived 单实例(VRRP 协议,无传统 listen 端口)

**Spec 关键点**:
```python
"keepalived": Spec(
    model_id="keepalived",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12257},  # keepalived 用 VRRP multicast,无 host 端口
    ...
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq keepalived iproute2 procps net-tools > /tmp/keepalived_install.log 2>&1 || (echo 'keepalived install failed:'; tail -30 /tmp/keepalived_install.log; exit 1)",
    ),
    start_commands=(
        # keepalived 需配置文件,手写一份最小配置
        "printf 'global_defs {\\n    enable_script_security\\n    script_user root\\n}\\nvrrp_script check_script {\\n    script \"/bin/true\"\\n    interval 2\\n}\\nvrrp_instance VI_1 {\\n    state MASTER\\n    interface eth0\\n    virtual_router_id 51\\n    priority 100\\n    advert_int 1\\n    authentication {\\n        auth_type PASS\\n        auth_pass secret\\n    }\\n    virtual_ipaddress {\\n        192.168.1.100\\n    }\\n    track_script {\\n        check_script\\n    }\\n}\\n' > /etc/keepalived/keepalived.conf",
        "nohup keepalived -f /etc/keepalived/keepalived.conf -n -D > /tmp/keepalived.log 2>&1 &",
        "sleep 2",
    ),
    # keepalived 用 VRRP 协议(112 端口 multicast),ss -tln 不显示
    # ready_check 改用 ps 检测进程
    ready_check={"command": "pgrep -x keepalived", "timeout": 30, "interval": 1.0},
),
```

**风险**:keepalived 不是传统 TCP 服务,需用 `pgrep` 验证进程;VRRP multicast 在容器内可能受限(但只要进程存活就够采集)。

---

### G4.9 rocketmq(镜像,可能降级)

**目标**:单 rocketmq broker + nameserver,采集 version / cluster / topic

**Spec 关键点**:
```python
"rocketmq": Spec(
    model_id="rocketmq",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12258, "9876/tcp": 19876, "10911/tcp": 19875},
    ...
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wget iproute2 procps net-tools openjdk-11-jre-headless unzip > /tmp/rocketmq_pre.log 2>&1 || (echo 'rocketmq pre install failed:'; tail -30 /tmp/rocketmq_pre.log; exit 1)",
        # rocketmq 4.x 二进制(同 kafka wget 模式,清华源优先)
        "wget -q --tries=2 --timeout=120 https://mirrors.tuna.tsinghua.edu.cn/apache/rocketmq/4.9.7/rocketmq-all-4.9.7-bin-release.zip -O /tmp/rocketmq.zip || wget -q --tries=3 --timeout=120 https://archive.apache.org/dist/rocketmq/4.9.7/rocketmq-all-4.9.7-bin-release.zip -O /tmp/rocketmq.zip",
        "unzip -q /tmp/rocketmq.zip -d /opt/ && mv /opt/rocketmq-all-4.9.7-bin-release /opt/rocketmq",
    ),
    start_commands=(
        # rocketmq 单 broker 模式需配 broker + nameserver
        "nohup /opt/rocketmq/bin/mqnamesrv > /tmp/mqnamesrv.log 2>&1 &",
        "sleep 5",
        "nohup /opt/rocketmq/bin/mqbroker -n 127.0.0.1:9876 > /tmp/mqbroker.log 2>&1 &",
        "sleep 10",
    ),
    ready_check={"command": "ss -tln | grep -q ':9876 '", "timeout": 60, "interval": 2.0},
),
```

**风险**:rocketmq 启动 10-20s,JVM 启动慢;broker 可能因 OOM 失败(需调小内存:`-Xms256m -Xmx256m`)。

---

### G4.10 tuxedo(镜像,可能降级)

**目标**:Oracle Tuxedo,采集 TUXDIR / 端口

**Spec 关键点**:
```python
"tuxedo": Spec(
    model_id="tuxedo",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12259, "6600/tcp": 19860},
    ...
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wget iproute2 procps net-tools > /tmp/tuxedo_pre.log 2>&1",
        # Oracle Tuxedo 镜像:oracle/tuxedo:21.0
        # 需研究镜像可达性(可能需 Oracle 账号)
        "wget -q --tries=2 --timeout=120 https://example.com/tuxedo.tar.gz -O /tmp/tuxedo.tar.gz || (echo 'tuxedo download failed; mirror not verified'; exit 1)",
        "tar -xzf /tmp/tuxedo.tar.gz -C /opt/",
    ),
    start_commands=(
        "nohup /opt/tuxedo/bin/tuxedo > /tmp/tuxedo.log 2>&1 &",
        "sleep 5",
    ),
    ready_check={"command": "ss -tln | grep -q ':6600 '", "timeout": 30, "interval": 2.0},
),
```

**风险**:Oracle Tuxedo 镜像**需 Oracle 账号**,2026-07-08 极可能降级;具体镜像 URL 待 verify。

---

## 4. 执行顺序

| 顺序 | 对象 | 估时 | 阻塞风险 |
|---|---|---|---|
| 1 | G4.1 jboss | 5-10 分钟 | 🟡 JVM 启动慢 |
| 2 | G4.6 apache | 2-3 分钟 | 🟢 单进程 |
| 3 | G4.7 squid | 2-3 分钟 | 🟢 单进程 |
| 4 | G4.8 keepalived | 2-3 分钟 | 🟡 VRRP 特殊 |
| 5 | G4.2 jetty | 5-8 分钟 | 🟡 JVM |
| 6 | G4.3 tongweb | 5-10 分钟 | 🟡 国产手装 |
| 7 | G4.9 rocketmq | 5-10 分钟 | 🟡 JVM 内存 |
| 8 | G4.4 weblogic | 1-2 分钟 | 🟡 降级占位 |
| 9 | G4.5 websphere | 1-2 分钟 | 🟡 降级占位 |
| 10 | G4.10 tuxedo | 1-5 分钟 | 🟡 镜像待 verify |

**总时间盒**:
- 串行:30-50 分钟
- --parallel 3:20-30 分钟

---

## 5. 验收(Phase 4 整体)

### 5.1 必达

- [ ] **新增落盘 JSON**:10 个(8 真实 + 2 降级占位)
- [ ] **catalog 增条**:10 个,MODEL_SPECS 21 → **31**
- [ ] **pytest 全绿**:`pytest tests/collect_fixtures/ -n 4` 130+ passed(Phase 3 129 增)
- [ ] **validate() 通过**:31 个对象 0 错误
- [ ] **roadmap 回填**:G4.1-G4.10 测试结果字段填完

### 5.2 加分

- [ ] `cli --all --parallel 3` 真实跑 31 对象,成功率 ≥ 80%
- [ ] test_catalog.py 加 10×3 = 30 个新 case

---

## 6. 不在 Phase 4 范围(明确)

| 项 | 范围 |
|---|---|
| 国产化 8 个无 plugin 对象 | ⚪ Phase 5+ 排期(写 plugin 是独立工作量) |
| protocol 类型(nacos / oceanbase / highgo / ...)| ⚪ Phase 5+,需新增 python 入口分支 |
| HDFS/YARN/Storm 集群降级 | ⚪ Phase 5+ |
| K8s / VMware / 云采集 / 存储 / 网络 / 主机 | ⚪ 用户明确排除 |
| 生产链路改动(plugins/inputs/、server/apps/cmdb/collection/、stargazer core) | 🔴 红线,Phase 4 不动 |

---

## 7. 决策清单(已 user 拍板)

| # | 问题 | 决策 |
|---|---|---|
| 1 | Phase 4 范围? | ✅ **10 个全做**(A 5 + C 3 + D 2) |
| 2 | 国产化 8 个无 plugin? | ⚪ **不做,Phase 5+ 排期** |
| 3 | weblogic/websphere license? | 🟡 **降级占位** |
| 4 | 单跑先验还是直接并发? | 🟡 **单跑 jboss 验证 Java 应用模板,再并发跑剩下 9** |

---

## 8. 测试结果回填区(执行后由 Agent 手动回填)

### G4.1 jboss 测试结果
_待 G4.1 完成后回填_

### G4.2 jetty 测试结果
_待 G4.2 完成后回填_

### G4.3 tongweb 测试结果
_待 G4.3 完成后回填_

### G4.4 weblogic 测试结果
_待 G4.4 完成后回填_

### G4.5 websphere 测试结果
_待 G4.5 完成后回填_

### G4.6 apache 测试结果
_待 G4.6 完成后回填_

### G4.7 squid 测试结果
_待 G4.7 完成后回填_

### G4.8 keepalived 测试结果
_待 G4.8 完成后回填_

### G4.9 rocketmq 测试结果
_待 G4.9 完成后回填_

### G4.10 tuxedo 测试结果
_待 G4.10 完成后回填_

---

## 9. 完成后产物清单

> Phase 4 整体完成后交付:

- **代码改动**:`agents/stargazer/tests/collect_fixtures/catalog.py`(+10 Spec)/ `init/*.sh`(10 个复制 + bk_host_innerip 修复)/ `test_catalog.py`(30 新 case)
- **落盘 fixture**:`tests/fixtures/collect/{jboss,jetty,tongweb,weblogic,websphere,apache,squid,keepalived,rocketmq,tuxedo}.json`
- **roadmap 更新**:`docs/superpowers/plans/2026-07-06-cmdb-collect-v3-roadmap.md` G4.x 测试结果回填
- **本计划收口**:本文档末尾追加「Phase 4 执行报告」段落
- **worktree**:等你 review,决定 commit + 合并 / 删 / 改

---

## 附录 A:10 对象关键信息速查表

| 对象 | 镜像 | ssh | 业务端口 | 依赖工具 | 启动模式 |
|---|---|---|---|---|---|
| jboss | ubuntu:22.04 | 12250 | 18090 | openjdk-11 + wildfly | start + 15s wait |
| jetty | ubuntu:22.04 | 12251 | 18091 | openjdk-11 + jetty9 | start + 10s wait |
| tongweb | ubuntu:22.04 | 12252 | 18092 | openjdk-11 + 东方通 tarball | start + 15s wait |
| weblogic | ubuntu:22.04(降级) | 12253 | 18093/18094 | Oracle 账号 | 降级占位 |
| websphere | ubuntu:22.04(降级) | 12254 | 18095/18096 | IBM 账号 | 降级占位 |
| apache | ubuntu:22.04 | 12255 | 18097 | apache2 | apachectl start |
| squid | ubuntu:22.04 | 12256 | 18098 | squid | squid -D -d 1 |
| keepalived | ubuntu:22.04 | 12257 | n/a(VRRP)| keepalived | keepalived -n -D |
| rocketmq | ubuntu:22.04 | 12258 | 19875/19876 | openjdk-11 + rocketmq | mqnamesrv + mqbroker |
| tuxedo | ubuntu:22.04 | 12259 | 19860 | Oracle Tuxedo 镜像 | tuxedo start |
