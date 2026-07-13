# CMDB 采集 Fixture 工具 v3 Phase 5 — 执行报告

> **状态**:执行完成(2026-07-08)｜ **前置**:Phase 1/2/3/4 已落(worktree `feature-cmdb-collect-v3-gap4-validate`)
> **关联 plan**:[`2026-07-08-cmdb-collect-v3-phase5-plan.md`](2026-07-08-cmdb-collect-v3-phase5-plan.md)
> **关联 roadmap**:[`2026-07-06-cmdb-collect-v3-roadmap.md`](2026-07-06-cmdb-collect-v3-roadmap.md) §3

---

## 0. TL;DR

| 维度 | 数据 |
|---|---|
| **新增对象** | 26 个(G5.1 12 + G5.2 11 + G5.3 3) |
| **MODEL_SPECS** | 31 → **57** |
| **新增 plugin** | 10 个 stub(除 influxdb 复用已有) |
| **新增 init 脚本** | 1 个(only mycat) |
| **fixture 落盘** | 0(全部阻塞,等 amd64 CI) |
| **pytest** | 160 → **160 passed**(Phase 1-4 baseline 保持) |
| **关键工具改动** | `Spec` 加 `platform` 字段 / `docker_lifecycle.py` 传 platform / `test_catalog.py` & `test_cli.py` 断言更新 |

**整体策略**:按用户拍板"批量 catalog 化"(推荐 2),1.5 小时完成 roadmap §3 全部 26 个对象 catalog 化,不真跑采集。

---

## 1. 真实跑通情况

| 维度 | 数据 |
|---|---|
| **真实采集跑通** | 0/26(0%) |
| **手动验证 mycat 可启动** | 1/26(amd64 容器内 mycat 启动 + 8066/9066 监听,见 §3.1) |
| **阻塞原因** | amd64 模拟在 arm64 Mac 极慢(同 mssql 阻塞源) |

**为什么 0/26**:Mac arm64 跑 amd64 rosetta 模拟,jdk 安装 5+ 分钟装不完,跟 Phase 1 mssql 同源阻塞。所有 26 个对象 `install_commands` 末尾 `exit 1` 标记阻塞,fixture 不落盘。真实采集留 amd64 CI runner(GitHub Actions ubuntu-22.04)。

---

## 2. 分组执行详情

### 2.1 G5.1 国产化 JOB(12 个)— 全部 catalog 占位

| 对象 | spec | init_script | 阻塞原因 |
|---|---|---|---|
| `mycat` | ✅ | ✅ 写好(等 amd64 CI) | amd64 模拟 + mycat 1.6 无 aarch64 wrapper |
| `ihs` | ✅ | None | IBM license + amd64 模拟 |
| `gbase8s` | ✅ | None | 国产镜像 + amd64 模拟 |
| `oscar` | ✅ | None | 国产镜像 + amd64 模拟 |
| `tonglinkq` | ✅ | None | 东方通 rpm + license + amd64 |
| `tonggtp` | ✅ | None | 东方通 rpm + license + amd64 |
| `apusic` | ✅ | None | 东方通 rpm + license + amd64 |
| `inforsuite_as` | ✅ | None | 中创 rpm + license + amd64 |
| `bes` | ✅ | None | 国产 rpm + 文档少 + license + amd64 |
| `domestic_linux` | ✅ | None | 麒麟/统信/欧拉 dnf 适配 + amd64 |
| `informix` | ✅ | None | IBM docker 镜像 + license + amd64 |
| `sybase` | ✅ | None | SAP docker 镜像 + license + amd64 |

### 2.2 G5.2 protocol 类型(11 个)— catalog + plugin stub

| 对象 | spec | plugin | 阻塞原因 |
|---|---|---|---|
| `influxdb` | ✅ | ✅ 复用已有 | 等 amd64 CI 跑采集 |
| `nacos` | ✅ | ✅ stub | amd64 模拟 + plugin stub |
| `highgo` | ✅ | ✅ stub | amd64 模拟 + plugin stub |
| `tdsql` | ✅ | ✅ stub | amd64 模拟 + plugin stub |
| `ambari` | ✅ | ✅ stub | amd64 模拟 + plugin stub |
| `server_bmc` | ✅ | ✅ stub | amd64 模拟 + plugin stub |
| `oceanbase` | ✅ | ✅ stub | pyobclient SDK + amd64 |
| `tongrds` | ✅ | ✅ stub | 东方通 + amd64 |
| `couchbase` | ✅ | ✅ stub | SDK + license + amd64 |
| `sap_hana` | ✅ | ✅ stub | license 不可达(仅占位) |
| `iris` | ✅ | ✅ stub | driver 缺失(仅占位) |

### 2.3 G5.3 集群降级(3 个)— catalog 占位

| 对象 | spec | init_script | 阻塞原因 |
|---|---|---|---|
| `hdfs` | ✅ | None | Hadoop 单节点伪分布式 + amd64 |
| `yarn` | ✅ | None | YARN 单节点伪分布式 + amd64 |
| `storm` | ✅ | None | Storm 单节点伪分布式 + amd64 |

---

## 3. G5.1.1 mycat 手动验证证据(amd64 容器内)

> **价值**:虽然 cli 真跑阻塞(amd64 rosetta 5+ 分钟装不完 jdk),但**手动用 `docker run --platform linux/amd64` 启容器**,mycat 1.6.7.5 完整可启动 + 8066/9066 监听,验证了 spec 设计 + install_commands 流程正确。

### 3.1 启动流程(实测)

```bash
# 启容器
docker run -d --name mycat_test --platform linux/amd64 -p 22060:22 \
  docker.m.daocloud.io/library/ubuntu:22.04 sleep 1200

# bootstrap:切源 + 装 jdk + wget mycat
docker exec mycat_test bash -c "
  sed -i 's|//ports.ubuntu.com/ubuntu-ports|//mirrors.aliyun.com/ubuntu-ports|g' /etc/apt/sources.list
  apt-get update -qq
  apt-get install -y -qq openjdk-11-jre-headless wget iproute2 procps net-tools
  wget --tries=3 --timeout=180 \
    https://github.com/MyCATApache/Mycat-Server/releases/download/Mycat-server-1675-release/Mycat-server-1.6.7.5-release-20200422133810-linux.tar.gz \
    -O /tmp/mycat.tgz
  tar -xzf /tmp/mycat.tgz -C /opt/
  # CRLF 转换(官方 release 脚本是 Windows 行尾)
  for f in /opt/mycat/bin/*.sh /opt/mycat/bin/mycat; do
    sed -i 's/\r$//' \"\$f\"
  done
  mkdir -p /opt/mycat/logs
"

# 配置 schema.xml(简化 + 不可达 writeHost 192.0.2.1:3306)
# server.xml 配 default schema=TESTDB
# 启动(用 startup_nowrap.sh 绕开 wrapper arch 问题)
docker exec mycat_test bash -c "
  export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
  nohup /opt/mycat/bin/startup_nowrap.sh > /opt/mycat/logs/console.log 2>&1 &
  sleep 30
"
```

### 3.2 启动日志(关键行)

```
2026-07-08 08:34:35 INFO (MycatServer.startup) - $_MyCatManager is started and listening on 9066
2026-07-08 08:34:35 INFO (MycatServer.startup) - $_MyCatServer is started and listening on 8066
2026-07-08 08:34:35 INFO (PhysicalDBPool.initSource) - init backend mysql source, create connections total 10 for hostM1 index :0
2026-07-08 08:34:35 INFO (PhysicalDatasource.getConnection) - no idle connection in pool, create new connection for hostM1 of schema mysql
```

> **关键证据**:mycat 启动成功后,business logic 才尝试连接 backend `192.0.2.1:3306`(不可达),但端口 8066/9066 已正常监听 — 这就是 fixture 工具可以"只验证启动 + 端口"的核心机制。

### 3.3 端口验证

```
ss -tln | grep -E '8066|9066'
LISTEN 0 100 *:9066 *:*
LISTEN 0 100 *:8066 *:*
```

### 3.4 关键 gotcha(踩坑列表)

| 坑 | 现象 | 解决 |
|---|---|---|
| mycat 1.6 wrapper 无 aarch64 | `Unable to locate wrapper-linux-aarch64-64` | spec 加 `platform="linux/amd64"` + cli 改 `containers.run(platform=spec.platform)` |
| 官方 release shell 脚本 CRLF | `line 58: syntax error near $'\r'` | `for f in /opt/mycat/bin/*.sh /opt/mycat/bin/mycat; do sed -i 's/\r$//' "$f"; done` |
| `nohup bin/startup_nowrap.sh` 找不到 | `failed to run command 'bin/...': No such file or directory` | 改绝对路径 `nohup /opt/mycat/bin/startup_nowrap.sh` |
| schema TESTDB 无 table 启动失败 | `ConfigException: schema TESTDB didn't config tables` | schema 加 `dataNode="dn1"` |
| logs 目录不存在 | `cannot create /opt/mycat/logs/console.log: Directory nonexistent` | `mkdir -p /opt/mycat/logs` |
| JAVA_HOME 未设 | `JAVA_HOME environment variable is not set` | `export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64` |
| bin/mycat start 选 wrapper arch 失败 | 同 aarch64 坑 | 改用 `startup_nowrap.sh`(不走 wrapper) |

---

## 4. 工具改动

### 4.1 `Spec` 数据类加 `platform` 字段

```python
@dataclass(frozen=True)
class Spec:
    ...
    container_user: Optional[str] = None
    container_cmd: Optional[str] = None
    platform: Optional[str] = None  # 例如 "linux/amd64"; None = docker SDK 默认
```

### 4.2 `docker_lifecycle.py` 传 platform

```python
container = client.containers.run(
    image=spec.image,
    command=cmd,
    detach=True,
    environment=spec.env,
    ports=spec.ports,
    privileged=privileged,
    user=user,
    platform=spec.platform,  # NEW
    remove=True,
)
```

### 4.3 test 断言更新

- `test_catalog.py::test_phase4_objects_total_count_is_10`:31 → 57
- `test_cli.py::test_all_parallel_uses_thread_pool`:31 → 57
- `test_cli.py::test_all_parallel_one_runs_serially`:31 → 57

---

## 5. pytest 全量

```bash
cd agents/stargazer && .venv/bin/python -m pytest tests/collect_fixtures/
============================= 160 passed, 1 warning in 91.52s (0:01:31) ==============================
```

**160 case 全绿**,Phase 1-4 baseline 保持。

---

## 6. 关键 gotcha 总结(给后续 Phase 6+ 参考)

1. **amd64 模拟在 arm64 Mac 极慢** — mycat / mssql / ihs / 国产中间件 binary 都需要 amd64,rosetta 模拟 5+ 分钟装不完 jdk
2. **真要跑这些对象的真实采集** → amd64 CI runner(GitHub Actions ubuntu-22.04)
3. **国产化 binary 大都只支持 x86_64** — 留 platform 字段,spec 写 `platform="linux/amd64"`,容器内模拟
4. **mycat 1.6 启动需要 5+ 必要条件**(CRLF/JAVA_HOME/logs/dataNode/startup_nowrap.sh)— mycat_default_discover.sh 已写好,等 amd64 CI 跑通
5. **plugin stub 模式**:15 行,`__init__` 存 kwargs,`list_all_resources` 返回 `[]` + warning 日志,validate() 通过但实际不采

---

## 7. Phase 5 状态总结

| 维度 | 数据 |
|---|---|
| 范围 | 26 个对象(G5.1 12 + G5.2 11 + G5.3 3) |
| 完成度 | catalog 化 100%(26/26),fixture 落盘 0/26(等 amd64 CI) |
| 工作量 | 1.5 小时(含调研、踩坑、修代码、pytest 验证) |
| 真实采集 | 0/26(全部阻塞,等 CI) |
| 阻塞统一原因 | amd64 模拟在 arm64 Mac 极慢 + 国产化 binary 无 aarch64 |

**下一步候选**:
1. **commit + merge Phase 1-4 + Phase 5**(31→57 catalog,160 pytest,1 个 G5.1.1 init 脚本,10 个 plugin stub)
2. **继续 Phase 5.1.1 真实采集** → 改 amd64 CI runner(用户决定是否走 CI)
3. **暂停**,worktree 留着,用户来

---

## 8. 关联文档索引

| 类型 | 文档 |
|---|---|
| Phase 5 plan | `docs/superpowers/plans/2026-07-08-cmdb-collect-v3-phase5-plan.md` |
| roadmap | `docs/superpowers/plans/2026-07-06-cmdb-collect-v3-roadmap.md` |
| spec 设计 | `docs/superpowers/specs/2026-07-05-cmdb-collect-vm-design.md` |
| Phase 1-4 plan | `docs/superpowers/plans/2026-07-07-cmdb-collect-v3-phase{1,2,3,4}-plan.md` |
| Phase 1-4 报告 | `docs/superpowers/plans/2026-07-{07,08}-cmdb-collect-v3-phase{1,2,3,4}-execution-report.md` |
| catalog 代码 | `agents/stargazer/tests/collect_fixtures/catalog.py` |
| 工具改动 | `agents/stargazer/tests/collect_fixtures/docker_lifecycle.py` |
| mycat init 脚本 | `agents/stargazer/tests/collect_fixtures/init/mycat_default_discover.sh` |
| plugin stubs | `agents/stargazer/plugins/inputs/{nacos,highgo,tdsql,ambari,server_bmc,oceanbase,tongrds,couchbase,sap_hana,iris}/<obj>_info.py` |
