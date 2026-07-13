# CMDB 采集 Fixture 工具 v3 Phase 3 — 社区版扩展执行计划

> **状态**：执行计划草案（2026-07-07）｜ **前置**:Phase 2 已完成(worktree `feature-cmdb-collect-v3-gap4-validate`)
> **关联 roadmap**：[`2026-07-06-cmdb-collect-v3-roadmap.md`](2026-07-06-cmdb-collect-v3-roadmap.md) §3.1
> **关联 Phase 1 报告**：[`2026-07-07-cmdb-collect-v3-phase1-execution-report.md`](2026-07-07-cmdb-collect-v3-phase1-execution-report.md)
> **关联 Phase 2 报告**：[`2026-07-07-cmdb-collect-v3-phase2-execution-report.md`](2026-07-07-cmdb-collect-v3-phase2-execution-report.md)

---

## 0. 范围（roadmap §3.1 高优先级 7 个）

| 对象 | 类型 | 镜像 | 复杂度 | 备注 |
|---|---|---|---|---|
| `minio` | middleware | `minio/minio:RELEASE.2023-09-30T07-02-29Z` | 🟢 低 | 本地已有镜像,单进程 |
| `zookeeper` | middleware | `zookeeper:3.9`(官方) | 🟡 中 | Java 进程,apt 镜像略慢 |
| `consul` | middleware | `hashicorp/consul:1.16` | 🟢 低 | 单一二进制 |
| `etcd` | middleware | `quay.io/coreos/etcd:v3.5` 或 `bitnami/etcd:3.5` | 🟢 低 | 单一二进制 |
| `memcached` | middleware | `memcached:1.6-alpine` | 🟢 低 | alpine 镜像自带 memcached + netstat |
| `openresty` | middleware | `openresty/openresty:1.21-alpine` | 🟢 低 | alpine 自带 openresty nginx |
| `haproxy` | middleware | `haproxy:2.8-alpine` | 🟢 低 | alpine 自带 haproxy + netstat |

**roadmap §3.1 已将这 7 个列为 🟢 高优先级**,本计划聚焦这 7 个,Phase 4 候选(中等优先级 12+ 对象)延后。

---

## 1. 现状核查（2026-07-07）

### 1.1 现成资源

| 资源 | 状态 |
|---|---|
| `plugins/inputs/<obj>/<obj>_default_discover.sh` | ✅ 7 个全部存在(35-124 行,纯 shell 扫进程模式) |
| 镜像可达性 | ✅ daemon.json 配置阿里云+轩辕加速源,各镜像应该可达 |
| 已有 fixture JSON | ❌ 0 个(全部未跑过) |

### 1.2 脚本风格一致性

| 对象 | 模式 | 入口需求 |
|---|---|---|
| minio | `ps -ef \| grep '[m]inio server'` + readlink /proc/PID/exe + `minio --version` | netstat / procps / ss |
| zookeeper | `ps -ef \| grep zookeeper` + readlink java exe + `zkServer.sh status` | netstat + java |
| consul | `consul members` API 调用 | consul CLI |
| etcd | `etcd --version` + 读 cmdline 提取 config/data/listen URL | procps |
| memcached | `ps` 提取 `-p/-c/-m` 参数 | procps |
| openresty | `ps` 找 nginx master + `readlink` 检查 openresty 标识 + netstat | netstat / procps |
| haproxy | `pgrep -x haproxy` + 读 cmdline 找 `-f` 配置文件 | procps |

**共同点**:都是 ssh 入口 + ubuntu base(同 nginx/tomcat/rabbitmq 模式),需要 `procps` 和 `net-tools` 或 `iproute2`。

---

## 2. 设计决策（继承 Phase 2 plan §0）

### 2.1 入口选型

| 对象 | 入口类型 | image 选型 | 理由 |
|---|---|---|---|
| minio | ssh | `minio/minio:RELEASE.2023-09-30T07-02-29Z` | 本地已有镜像,装 sshd 即可 |
| zookeeper | ssh | `docker.m.daocloud.io/library/ubuntu:22.04` + apt | zookeeper 官方镜像缺 sshd / 缺 `ps` 增强工具 |
| consul | ssh | `hashicorp/consul:1.16` | 单一二进制 + 装 sshd 即可 |
| etcd | ssh | `quay.io/coreos/etcd:v3.5` | 单一二进制 |
| memcached | ssh | `docker.m.daocloud.io/library/ubuntu:22.04` + apt | 镜像精简,apt 装全 |
| openresty | ssh | `openresty/openresty:1.21-alpine` | 镜像自含 openresty |
| haproxy | ssh | `haproxy:2.8-alpine` | alpine 自带 haproxy + iproute2 |

> **统一策略**:ubuntu 22.04 base + ssh 入口(同 Phase 1 nginx/tomcat/rabbitmq/kafka/elasticsearch 模式),镜像自含服务的(zookeeper / openresty / haproxy / consul / etcd / memcached)用对应镜像 + 装 sshd。

### 2.2 端口分配（避开已有 14 对象）

| 对象 | ssh | 业务端口 |
|---|---|---|
| nginx(已有) | 12222 | 18000 |
| mongodb(已有) | 12223 | 17017 |
| rabbitmq(已有) | 12224 | 5673, 15672 |
| tomcat(已有) | 12225 | 18080 |
| elasticsearch(已有) | 12228 | 19200 |
| kafka(已有) | 12229 | 19092 |
| activemq(已有) | 12230 | 31616, 18161 |
| mssql(已有) | 14330 | 14331 |
| dameng(占位) | 12232 | 15236 |
| ibmmq(占位) | 12231 | 11414, 19443 |
| redis_sentinel | n/a(shell) | 16380, 26380 |
| **minio** | **12240** | **19000(S3)+ 19001(admin)** |
| **zookeeper** | **12241** | **12181(client)+ 12888(peer)+ 13888(leader)** |
| **consul** | **12242** | **18500(http)+ 18600(dns)+ 18300-18302(server)** |
| **etcd** | **12243** | **12379(client)+ 12380(peer)** |
| **memcached** | **12244** | **111211** |
| **openresty** | **12245** | **18080-OR(tomcat 冲突 → 18081)** |
| **haproxy** | **12246** | **18081(已被 openresty 用 → 18082)+ 18404(stats)** |

> **冲突解决**:openresty 和 haproxy 都想用 18080/18081,顺延 18082/18083。

### 2.3 init 脚本策略

7 个对象**全部复用** `plugins/inputs/<obj>/<obj>_default_discover.sh`(生产链路脚本,只读)。

需要做的是把这些文件**复制**到 `tests/collect_fixtures/init/`(同 Phase 2 G2.1 redis_sentinel 模式),加头部注释说明同步策略。

---

## 3. 单对象执行细节

### G3.1 minio

**目标**:单实例 minio server,落盘 JSON 含 version / endpoint / access_mode 等字段

**Spec 关键点**:
```python
"minio": Spec(
    model_id="minio",
    image="minio/minio:RELEASE.2023-09-30T07-02-29Z",
    ports={"22/tcp": 12240, "9000/tcp": 19000, "9001/tcp": 19001},
    init_script="minio_default_discover.sh",
    entry_type="ssh",
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps net-tools > /dev/null 2>&1",
        "mkdir -p /run/sshd && echo 'root:testpw' | chpasswd",
        "sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config",
        "/usr/sbin/sshd",
    ),
    start_commands=(
        # MINIO_ROOT_USER + MINIO_ROOT_PASSWORD 是 minio 启动必须的 env
        # 但容器内 USER=minio(uid 1000),装 sshd 要 root → container_user=0:0 + cmd 覆盖
        "MINIO_ROOT_USER=admin MINIO_ROOT_PASSWORD=adminpass123 nohup minio server /data --address ':9000' --console-address ':9001' > /tmp/minio.log 2>&1 &",
        "sleep 3",
    ),
    ready_check={"command": "ss -tln | grep -q ':9000 '", "timeout": 30, "interval": 2.0},
),
```

**风险**:minio 官方镜像 USER=minio,装 sshd 需 root → `container_user="0:0"` + `container_cmd` 覆盖 keepalive。

---

### G3.2 zookeeper

**目标**:单实例 zookeeper server(2181 client + 2888 peer + 3888 leader-election)

**Spec 关键点**:
```python
"zookeeper": Spec(
    model_id="zookeeper",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12241, "2181/tcp": 12181, "2888/tcp": 12888, "3888/tcp": 13888},
    init_script="zookeeper_default_discover.sh",
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq zookeeperd iproute2 procps net-tools openjdk-11-jre-headless > /tmp/zk_install.log 2>&1 || (echo 'zk install failed:'; tail -30 /tmp/zk_install.log; exit 1)",
    ),
    start_commands=("/usr/share/zookeeper/bin/zkServer.sh start",),
    ready_check={"command": "/usr/share/zookeeper/bin/zkServer.sh status 2>&1 | grep -q 'Mode: '", "timeout": 60, "interval": 2.0},
),
```

**风险**:apt 装 zookeeperd + openjdk 慢(可能要 2-3 分钟);**镜像走 daocloud 源**。

---

### G3.3 consul

**目标**:单 consul agent(dev mode),落盘 JSON 含 datacenter / members

**Spec 关键点**:
```python
"consul": Spec(
    model_id="consul",
    image="hashicorp/consul:1.16",
    ports={"22/tcp": 12242, "8500/tcp": 18500, "8600/tcp": 18600, "8300/tcp": 18300},
    init_script="consul_default_discover.sh",
    container_user="0:0",  # 装 sshd 需要 root
    container_cmd=(
        "sh -c 'DEBIAN_FRONTEND=noninteractive apt-get update -qq > /dev/null 2>&1; "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server iproute2 procps > /dev/null 2>&1; "
        "mkdir -p /run/sshd && echo \"root:testpw\" | chpasswd; "
        "sed -i \"s/#PermitRootLogin.*/PermitRootLogin yes/\" /etc/ssh/sshd_config; "
        "/usr/sbin/sshd; "
        "consul agent -dev -client=0.0.0.0 -bind=127.0.0.1 > /tmp/consul.log 2>&1 & "
        "while true; do sleep 3600; done'"
    ),
    install_commands=(
        "echo 'placeholder: container_cmd 已装 sshd + 启 consul'",
    ),
    start_commands=(
        "echo 'placeholder: consul 已在 container_cmd 启动'",
    ),
    ready_check={"command": "ss -tln | grep -q ':8500 '", "timeout": 30, "interval": 2.0},
),
```

**风险**:consul dev mode 启动快(~5 秒),API 8500 端口起来即就绪。

---

### G3.4 etcd

**目标**:单 etcd 实例(client + peer),落盘 JSON 含 version / data_dir / listen URLs

**Spec 关键点**:
```python
"etcd": Spec(
    model_id="etcd",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12243, "2379/tcp": 12379, "2380/tcp": 12380},
    init_script="etcd_default_discover.sh",
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq etcd-server iproute2 procps net-tools > /tmp/etcd_install.log 2>&1 || (echo 'etcd install failed:'; tail -30 /tmp/etcd_install.log; exit 1)",
    ),
    start_commands=(
        "nohup etcd --data-dir=/var/lib/etcd --listen-client-urls=http://0.0.0.0:2379 --advertise-client-urls=http://127.0.0.1:2379 --listen-peer-urls=http://0.0.0.0:2380 --initial-advertise-peer-urls=http://127.0.0.1:2380 --initial-cluster=default=http://127.0.0.1:2380 > /tmp/etcd.log 2>&1 &",
        "sleep 3",
    ),
    ready_check={"command": "ss -tln | grep -q ':2379 '", "timeout": 60, "interval": 2.0},
),
```

**风险**:etcd 启动需 5-10 秒,peer URL 必须跟 listen URL 对应。

---

### G3.5 memcached

**目标**:单 memcached 实例(port 11211),落盘 JSON 含 maxconn / cachesize

**Spec 关键点**:
```python
"memcached": Spec(
    model_id="memcached",
    image="docker.m.daocloud.io/library/ubuntu:22.04",
    ports={"22/tcp": 12244, "11211/tcp": 111211},
    init_script="memcached_default_discover.sh",
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq memcached iproute2 procps net-tools > /dev/null 2>&1",
    ),
    start_commands=(
        # memcached 前台启动(避免后台进程在 cli exec_run 结束后被信号杀掉)
        "memcached -m 64 -p 11211 -u memcache -d",
        "sleep 1",
    ),
    ready_check={"command": "ss -tln | grep -q ':11211 '", "timeout": 30, "interval": 1.0},
),
```

**风险**:memcached 默认监听 127.0.0.1,SSH 通过 127.0.0.1 采集 OK。

---

### G3.6 openresty

**目标**:openresty nginx 主进程 + worker,落盘 JSON 含 version / master PID

**Spec 关键点**:
```python
"openresty": Spec(
    model_id="openresty",
    image="openresty/openresty:1.21-alpine",
    ports={"22/tcp": 12245, "80/tcp": 18081},
    init_script="openresty_default_discover.sh",
    container_user="0:0",  # alpine 镜像默认 root,但装 sshd 可能需要再 root
    container_cmd=(
        "sh -c 'apk add --no-cache openssh-server iproute2 procps curl > /dev/null 2>&1; "
        "mkdir -p /run/sshd && echo \"root:testpw\" | chpasswd; "
        "sed -i \"s/#PermitRootLogin.*/PermitRootLogin yes/\" /etc/ssh/sshd_config; "
        "/usr/sbin/sshd; "
        "openresty -p /opt/app -c /usr/local/openresty/nginx/conf/nginx.conf 2>&1 || nginx -g \"daemon on;\"; "
        "while true; do sleep 3600; done'"
    ),
    install_commands=("echo 'placeholder'",),
    start_commands=("echo 'placeholder'",),
    ready_check={"command": "ss -tln | grep -q ':80 '", "timeout": 30, "interval": 2.0},
),
```

**风险**:openresty 官方镜像配置目录路径可能不同(`/usr/local/openresty/nginx/conf/nginx.conf`),需要 verify。

---

### G3.7 haproxy

**目标**:haproxy 守护进程,落盘 JSON 含 version / config_file

**Spec 关键点**:
```python
"haproxy": Spec(
    model_id="haproxy",
    image="docker.m.daocloud.io/library/ubuntu:22.04",  # alpine haproxy 镜像精简,装 sshd 麻烦
    ports={"22/tcp": 12246, "80/tcp": 18082, "8404/tcp": 18404},
    init_script="haproxy_default_discover.sh",
    install_commands=(
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq haproxy iproute2 procps net-tools > /dev/null 2>&1",
        # haproxy 默认配置需 enable
        "sed -i 's/ENABLED=0/ENABLED=1/' /etc/default/haproxy",
    ),
    start_commands=("haproxy -f /etc/haproxy/haproxy.cfg -D",),
    ready_check={"command": "ss -tln | grep -q ':80 '", "timeout": 30, "interval": 1.0},
),
```

**风险**:haproxy ubuntu 22.04 默认配置文件可能没 listen 80,需要自定义 haproxy.cfg 或者改端口。

---

## 4. 执行顺序与时间盒

> **强建议顺序**:**G3.5 memcached → G3.6 openresty → G3.3 consul → G3.4 etcd → G3.7 haproxy → G3.2 zookeeper → G3.1 minio**
> 理由:apt 装慢的对象(zookeeper/minio)放最后;单一二进制 + 镜像自含服务(consul/etcd/haproxy/openresty/memcached)放前面快速拿结果。

| 顺序 | 对象 | 估时 | 阻塞风险 |
|---|---|---|---|
| 1 | G3.5 memcached | 5-10 分钟 | 🟢 低(单进程 + 镜像轻) |
| 2 | G3.6 openresty | 5-10 分钟 | 🟡 中(镜像路径要 verify) |
| 3 | G3.3 consul | 5-10 分钟 | 🟢 低(单二进制 + dev mode) |
| 4 | G3.4 etcd | 5-10 分钟 | 🟢 低(单二进制) |
| 5 | G3.7 haproxy | 5-10 分钟 | 🟡 中(ubuntu 配置可能需调) |
| 6 | G3.2 zookeeper | 10-15 分钟 | 🟡 中(java + apt 慢) |
| 7 | G3.1 minio | 5-10 分钟 | 🟡 中(USER=minio + sshd 冲突) |

**总时间盒**:Phase 3 完整做 ≈ 45-75 分钟(串行)
**并发加速**:`cli --all --parallel 3` ≈ 25-40 分钟(本机 arm64 + daemon.json 加速源已配置)

---

## 5. 验收(Phase 3 整体)

### 5.1 必达

- [ ] **新增落盘 JSON**:7 个(minio / zookeeper / consul / etcd / memcached / openresty / haproxy)
- [ ] **catalog 增条**:7 个,MODEL_SPECS 从 14 → **21**(完整覆盖社区版 + 商业版首批)
- [ ] **pytest 全绿**:`pytest tests/collect_fixtures/ -n auto` 130+ passed(从 Phase 2 107 增)
- [ ] **validate() 通过**:21 个对象 0 错误
- [ ] **roadmap 回填**:G3.1-G3.7 测试结果字段填完

### 5.2 加分

- [ ] `cli --all --parallel 3` 真实跑 21 对象,成功率 ≥ 80%(剩余失败 = license 阻塞 + amd64)
- [ ] test_catalog.py 加 7×3 = 21 个新 case

---

## 6. 不在 Phase 3 范围(明确)

| 项 | 范围 |
|---|---|
| Phase 4 候选 12+ 中优先级对象 | ⚪ Phase 4 排期,本次不动 |
| protocol 类型(nacos / oceanbase / highgo / ...) | ⚪ Phase 5+,需新增 python 入口分支 |
| 暂缓对象(iis / hbase / spark / hdfs / yarn / storm / cics) | ⚪ 持续暂缓 |
| K8s / VMware / 云采集 / 存储 / 网络 / 主机 | ⚪ 用户明确排除 |
| 生产链路改动(plugins/inputs/、server/apps/cmdb/collection/、stargazer core) | 🔴 红线,Phase 3 不动 |

---

## 7. 决策清单(等用户拍板)

| # | 问题 | 默认 | 备选 |
|---|---|---|---|
| 1 | Phase 3 7 对象是否都做? | ✅ 全做 | 选 1-2 个先验证模板再扩 |
| 2 | openresty 用官方镜像还是 ubuntu + apt 装? | 🟡 官方镜像(verify 路径) | ubuntu + apt 装 |
| 3 | haproxy 用 alpine 还是 ubuntu? | 🟡 ubuntu(避免 alpine sshd 装麻烦) | alpine 镜像 |
| 4 | minio 装 sshd + USER 冲突解决方案? | ✅ `container_user="0:0"` + container_cmd | 用 ubuntu + apt 装 minio |
| 5 | 单跑验证还是直接并发 --parallel 3? | 🟡 单跑先验 1-2 个,确认 Spec 稳了再并发 | 直接并发 |

---

## 8. 测试结果回填区(执行后由 Agent 手动回填)

### G3.1 minio 测试结果

_待 G3.1 完成后回填_

### G3.2 zookeeper 测试结果

_待 G3.2 完成后回填_

### G3.3 consul 测试结果

_待 G3.3 完成后回填_

### G3.4 etcd 测试结果

_待 G3.4 完成后回填_

### G3.5 memcached 测试结果

_待 G3.5 完成后回填_

### G3.6 openresty 测试结果

_待 G3.6 完成后回填_

### G3.7 haproxy 测试结果

_待 G3.7 完成后回填_

---

## 9. 完成后产物清单

> Phase 3 整体完成后交付:

- **代码改动**:`agents/stargazer/tests/collect_fixtures/catalog.py`(+7 Spec)/ `init/*.sh`(7 个复制)/ `test_catalog.py`(21 新 case)
- **落盘 fixture**:`tests/fixtures/collect/{minio,zookeeper,consul,etcd,memcached,openresty,haproxy}.json`
- **roadmap 更新**:`docs/superpowers/plans/2026-07-06-cmdb-collect-v3-roadmap.md` G3.x 测试结果回填
- **本计划收口**:本文档末尾追加「Phase 3 执行报告」段落
- **worktree**:等你 review,决定 commit + 合并 / 删 / 改

---

## 附录 A:7 对象关键信息速查表

| 对象 | 镜像 | ssh | 业务端口 | 依赖工具 | 启动模式 |
|---|---|---|---|---|---|
| minio | `minio/minio:RELEASE.2023-09-30T07-02-30T07-02-29Z` | 12240 | 19000, 19001 | procps | container_cmd + start |
| zookeeper | `ubuntu:22.04` | 12241 | 12181, 12888, 13888 | openjdk-11 + zookeeperd | start command |
| consul | `hashicorp/consul:1.16` | 12242 | 18500, 18600, 18300-18302 | consul binary | container_cmd + dev mode |
| etcd | `ubuntu:22.04` | 12243 | 12379, 12380 | etcd-server | start command + nohup |
| memcached | `ubuntu:22.04` | 12244 | 111211 | memcached | start command + daemon |
| openresty | `openresty/openresty:1.21-alpine` | 12245 | 18081 | openresty | container_cmd |
| haproxy | `ubuntu:22.04` | 12246 | 18082, 18404 | haproxy | start command + daemon |