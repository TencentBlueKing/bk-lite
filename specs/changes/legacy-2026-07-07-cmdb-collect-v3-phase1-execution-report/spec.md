# Historical Superpowers change: 2026-07-07-cmdb-collect-v3-phase1-execution-report

Status: done

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-07-cmdb-collect-v3-phase1-execution-report.md

> **生成日期**：2026-07-07
> **执行人**：Mavis (claude-opus-4)
> **配套路线图**：[2026-07-06-cmdb-collect-v3-roadmap.md](2026-07-06-cmdb-collect-v3-roadmap.md)
> **代码分支**：`feature-cmdb-collect-v3-gap4-validate`（worktree 在 `.worktrees/feature-cmdb-collect-v3-gap4-validate/`）
> **运行环境**：macOS arm64 (Apple Silicon),Docker Desktop + orbstack socket,Python 3.12

---

## 0. 总结一句话

**Phase 1 计划 4 个对象中,2 个 ✅ 完成 + 2 个 🔴 阻塞**。完成的（elasticsearch / kafka）落盘了真实 fixture JSON,阻塞的（activemq / mssql）有明确原因和后续方案。期间顺手修了 3 个预存在限制（Gap-4 validate 强化 + docker SDK 缺失 + unixodbc 安装）。

---

## 1. 工具侧改动（按时间顺序）

### 1.1 Gap-4 `validate()` 强化（2026-07-07 早段完成）

| 项 | 状态 | 证据 |
|---|---|---|
| 抽出 `validate_spec(spec, init_dir=None)` 单对象校验函数 | ✅ | `agents/stargazer/tests/collect_fixtures/catalog.py:198` |
| 7 个新增校验规则 | ✅ | entry_module import / entry_class 属性 / entry_method 方法 / init_script 后缀一致性 / wait_strategy 字段组合 / ports key 格式 / ssh install+start_commands 必填 |
| 单元测试 | ✅ | **27 passed, 0 failed**(原 5 + 新 22) |
| 端到端 `validate()` 在 7 个真实对象上 | ✅ | **0 errors** |

详见路线图 `§G1.0 Gap-4 validate 强化`。

### 1.2 预存在修复 B：docker SDK 依赖补齐

| 项 | 状态 | 证据 |
|---|---|---|
| 加 `docker>=7.0.0` 到 `pyproject.toml` 的 `dependencies` | ✅ | `pyproject.toml:42`（带注释说明 + 3 个 smoke test） |
| 安装并验证 | ✅ | docker SDK 7.1.0 装好,3 个 smoke test 通过 |
| 全套测试套件 | ✅ | **70 passed, 0 failed**（含 24 个 docker-using 测试,完整套件从 31 → 70） |

### 1.3 顺手加：Spec 容器启动选项

mssql 镜像默认 USER=mssql 不能 apt,新增 2 个 Spec 字段（向后兼容）:

| 字段 | 默认 | 用途 |
|---|---|---|
| `container_user` | `None` | 覆盖镜像 USER,如 `"0:0"` = root:root |
| `container_cmd` | `None` | 覆盖镜像 ENTRYPOINT/CMD,None 时 ubuntu minimal 用 keepalive 循环 |

`docker_lifecycle.start_container` 同步支持。详见路线图 G1.4 mssql 阻塞说明。

### 1.4 顺手装：unixodbc（mssql pyodbc 需要）

```bash
brew install unixodbc   # 2.3.14 装好,libodbc.2.dylib 在 /opt/homebrew/opt/unixodbc/lib/
```

`pyodbc 5.2.0` 加载正常,但还需要 Microsoft ODBC Driver 17（`msodbcsql17`,需 `brew trust microsoft/mssql-release` 用户授权）才能连 MSSQL → 触发了 ssh 入口降级方案。

---

## 2. 对象执行结果（4 个）

### ✅ G1.1 elasticsearch

**镜像**：`docker.m.daocloud.io/library/ubuntu:22.04`（apt 装 ES 8.x,同 v2 模式）
**入口**：ssh
**fixture**：`tests/fixtures/collect/elasticsearch.json` 已落盘
**耗时**：~5 分钟（含 apt install elasticsearch ~600MB 下载 + ES JVM 启动 ~30s + collect ~5s）

**落盘字段**（raw_stdout 16 字段，关键几个）：
```json
{
  "version": "8.19.18",
  "lucene_version": "9.12.2",
  "cluster_name": "elasticsearch",
  "status": "green",
  "number_of_nodes": "1",
  "bin_path": "/usr/share/elasticsearch/bin",
  "config": "/etc/elasticsearch/elasticsearch.yml",
  "pid": "4434"
}
```

**踩坑记录**（4 个，路线图里有完整叙述）：
1. `echo >> elasticsearch.yml` 弄坏 YAML → 改用 `-E` flag 覆盖
2. `-E discovery.type=single-node` 跟 yaml 默认 `cluster.initial_master_nodes` 冲突 → 不设 discovery.type,让 ES 自举
3. ES 8.x 拒绝以 root 启动 → `su -s /bin/bash elasticsearch -c '...'`
4. ES 是 JVM 进程,`/proc/pid/exe` 是 java → bin_path 硬编码 launcher 路径

---

### ✅ G1.2 kafka

**镜像**：`docker.m.daocloud.io/library/ubuntu:22.04`（wget 下载清华源 kafka 3.6.0 tarball）
**入口**：ssh
**fixture**：`tests/fixtures/collect/kafka.json` 已落盘
**耗时**：~3 分钟（含 wget ~100MB + KRaft format + kafka-server-start.sh ~30s + collect ~5s）

**落盘字段**（关键几个）：
```json
{
  "version": "3.6.0",
  "pid": "6345",
  "bin_path": "/opt/kafka/bin",
  "config": "/opt/kafka/config/kraft/server.properties",
  "cluster_id": "(unparsed)",
  "broker_count": "0",
  "topics": "(empty or query failed)"
}
```

**踩坑记录**：
1. ready_check `ss -tln` 太宽松（端口监听 ≠ broker ready）→ 改成 `kafka-topics.sh --list` 检测
2. cluster_id / broker_count / topics 是 placeholder —— KRaft 单节点 metadata quorum 输出格式与脚本 grep 不匹配。**fixture 已落盘,schema 完整,字段真实采集值(部分为 placeholder)**

**TODO（Phase 2 优化）**：改进 `kafka_default_discover.sh` 的 grep 模式,真实提取 cluster_id / broker_count / topics。

---

### 🔴 G1.3 activemq（阻塞）

**失败现象**：
- **方案 A（ubuntu:22.04 + apt 装 activemq）**：apt 包用 Tanuki wrapper daemon,容器里 java 进程变 zombie,61616 端口未监听；`activemq.xml` 不在默认搜索路径（`/etc/activemq/instances-available/main/`,需 symlink 到 `/etc/activemq/instances-enabled/` + cp 到 ACTIVEMQ_BASE）
- **方案 B（官方 `apache/activemq-classic:5.18.3`）**：activemq 在容器内确实跑（手动 docker exec 验证,8161/61616 都监听）,但 **cli 流程的 ready_check 始终失败**。试过 `ss -tln` / `python3 socket.connect`（镜像无 python3）/ `curl http://8161/`（webconsole 返回 401,curl `-fsS` 当失败）/ `echo READY`（连 echo 都失败）。**推测 cli 的 SSH exec 与官方轻量基础镜像（jammy + temurin-17-jre）有交互问题**

**catalog Spec 现状**：保留 ubuntu:22.04 + apt 路线,start_commands 故意 `exit 1` 标记阻塞,validate() 仍通过

**建议方案（Phase 2）**：
- 优先：把 activemq 的 ready_check 改成 **curl + 进程双重检测**（webconsole 必然在完全启动后才响应 401）
- 备选：用 `rmohr/activemq` 等预设 sshd+curl 的测试镜像
- 备选：放弃 ssh 入口,改用 python 入口直接调 `stomp.py` 连 61613（STOMP 协议）

---

### 🔴 G1.4 mssql（阻塞）

**失败现象**：
- **方案 A（python 入口 + pyodbc）**：`brew install unixodbc` 装好,pyodbc 5.2.0 能加载,但本机没装 Microsoft ODBC Driver 17（`brew install msodbcsql17` 需 `brew trust microsoft/mssql-release` 用户授权）
- **方案 B（ssh 入口 + sqlcmd，已降级到此方案）**：mssql 官方镜像 `mcr.microsoft.com/mssql/server:2022-CU14-ubuntu-22.04` 只有 linux/amd64,arm64 Mac 用 Rosetta 模拟,**SQL Server 启动 5+ 分钟仍未监听 1433**

**catalog Spec 现状**：保留 ssh 入口设计 + `container_user="0:0"` + `container_cmd=None`,start_commands 故意 `exit 1` 标记阻塞,validate() 仍通过

**建议方案（Phase 2）**：
- **优先**：在 amd64 CI runner（GitHub Actions `ubuntu-22.04`）跑 mssql 真实采集
- 备选：用户在 amd64 Linux 工作站（非 Mac）单独跑 G1.4
- 备选：放弃 mssql,改用社区版支持的 `db2` / `oracle` / `postgresql`（已有 fixture）做端到端验证

---

## 3. 验证证据（verification-before-completion）

### 3.1 单测套件

| 阶段 | 命令 | 结果 |
|---|---|---|
| Gap-4 完成后 | `pytest tests/collect_fixtures/test_catalog.py` | **27 passed** |
| Gap-4 完成后 | `pytest test_catalog + test_dump` | **31 passed, 0 failed** |
| 4 个对象 Spec 加完后 | `pytest tests/collect_fixtures/test_catalog.py` | **38 passed, 0 failed** |
| B 修复后（加 docker SDK） | `pytest tests/collect_fixtures/` | **70 passed, 0 failed** |

### 3.2 端到端真实采集

| 对象 | 命令 | 结果 | fixture 路径 |
|---|---|---|---|
| elasticsearch | `cli elasticsearch` | ✅ 落盘 16 字段 | `tests/fixtures/collect/elasticsearch.json` |
| kafka | `cli kafka` | ✅ 落盘 13 字段 | `tests/fixtures/collect/kafka.json` |
| activemq | `cli activemq` | 🔴 ready_check 超时 | (未落盘) |
| mssql | `cli mssql` | 🔴 amd64 模拟性能问题 | (未落盘) |

### 3.3 验证脚本（fixture 字段完整性）

每个落盘的 JSON 都满足：
- ✅ model_id / captured_at / image / container_meta / params / raw_stdout 6 字段齐全
- ✅ `dump.mask_sensitive` 自动掩码 password / secret / token / passwd
- ✅ 原子写（失败不留半文件）

---

## 4. 改动清单（worktree `feature-cmdb-collect-v3-gap4-validate`）

### 4.1 新增 / 修改文件

```
agents/stargazer/
├── pyproject.toml                                          (M)  加 docker>=7.0.0
├── tests/collect_fixtures/
│   ├── catalog.py                                          (M)  +ES/Kafka/AMQ/MSSQL 4 Spec + validate_spec() 函数 + 7 个 Gap-4 校验 + 2 字段
│   ├── test_catalog.py                                     (M)  +27 测试 (Gap-4 #1-#7) + 7 对象存在性测试 = 38 tests
│   ├── test_docker_sdk_smoke.py                            (A)  +3 docker SDK 守护测试
│   ├── docker_lifecycle.py                                 (M)  start_container 支持 user / cmd
│   └── init/
│       ├── elasticsearch_default_discover.sh               (A)
│       ├── kafka_default_discover.sh                       (A)
│       ├── activemq_default_discover.sh                    (A)
│       ├── mssql_default_discover.sh                       (A)
│       └── mssql.sql                                       (A)  旧版,现已被 inline SQL 替代
```

### 4.2 文档

```
docs/superpowers/plans/
├── 2026-07-06-cmdb-collect-v3-roadmap.md                   (M)  4 个对象章节 + 测试结果回填
└── 2026-07-07-cmdb-collect-v3-phase1-execution-report.md   (A)  本文档
```

---

## 5. 当前状态总账

| 维度 | 数量 |
|---|---|
| **v2 baseline** | 7 对象（mysql/postgresql/redis/mongodb/nginx/tomcat/rabbitmq）|
| **Phase 1 新增** | 4 对象目标（ES / Kafka / ActiveMQ / mssql）|
| **Phase 1 完成** | 2 对象（ES / Kafka）✅ |
| **Phase 1 阻塞** | 2 对象（ActiveMQ / mssql）🔴,有明确后续方案 |
| **fixture JSON 总数** | 7 (v2) + 2 (Phase 1) = 9 个 |
| **单测总数** | 70 passed (含 Gap-4 增强 + 4 对象 catalog + docker SDK smoke) |
| **Gap-4 校验规则** | 7 条新规则 |

---

## 6. 下一步建议（Phase 2 准备）

按 v3 路线图,Phase 1 完成后启动 Phase 2（商业版首批 3 对象:redis_sentinel / ibmmq / dameng）。

**Phase 2 启动前必须解决的事**：

1. **🟡 在 amd64 CI runner 上补完 mssql e2e**（建议 GH Actions ubuntu-22.04,落盘 `mssql.json` 后 PR 进 main）
2. **🟡 解 activemq cli 交互问题**（改 ready_check 为 curl + 进程双重,或换 rmohr/activemq 镜像）
3. **🟢 优化 kafka discover 脚本**（cluster_id / broker_count / topics 真实提取,替换 placeholder）

**Phase 2 启动时建议同步**：

4. 跑全量测试套件（`pytest tests/collect_fixtures/ -v`）确认基线干净
5. 在 CI 加 fixture 采集 job（amd64 runner,e2e 全跑一遍）,防止未来回归
6. 路线图头部状态头更新到 `Phase 1 完成 + Phase 2 启动`

---

## 7. 验收 checklist

- [x] B 修复（docker SDK）单测 + 端到端 OK
- [x] Gap-4 7 个校验规则单测 + 端到端 OK
- [x] G1.1 elasticsearch e2e fixture 落盘
- [x] G1.2 kafka e2e fixture 落盘
- [x] G1.3 activemq 阻塞原因文档化 + Spec 标记
- [x] G1.4 mssql 阻塞原因文档化 + Spec 标记
- [x] 路线图回填（4 个对象章节"测试结果"字段）
- [x] 本汇总报告生成

**未完成项**：G1.3 activemq 和 G1.4 mssql 的真实 fixture 落盘（已标记为 Phase 2 任务）。

---

> 配套路线图：[2026-07-06-cmdb-collect-v3-roadmap.md](2026-07-06-cmdb-collect-v3-roadmap.md)（每个对象的"测试结果"字段已回填）
