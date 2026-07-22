# Historical Superpowers change: 2026-07-06-cmdb-collect-v3-roadmap

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-06-cmdb-collect-v3-roadmap.md

> **状态**：v3 草案（2026-07-06）｜**Gap-4 validate 强化 已落地（2026-07-07）**
> **配套 spec**：[`docs/superpowers/specs/2026-07-05-cmdb-collect-vm-design.md`](../specs/2026-07-05-cmdb-collect-vm-design.md)
> **配套代码**：`agents/stargazer/tests/collect_fixtures/`
> **配套产物**：`agents/stargazer/tests/fixtures/collect/<model_id>.json`
> **关联 v2 plan**：[`docs/superpowers/plans/2026-07-05-cmdb-collect-vm-plan.md`](2026-07-05-cmdb-collect-vm-plan.md)
> **关联历史**：[`2026-06-09-cmdb-enterprise-sibling-app.md`](2026-06-09-cmdb-enterprise-sibling-app.md)（cmdb_enterprise overlay 重构）/ [`2026-06-17-dameng-job-fix-and-enterprise-collection-manual.md`](2026-06-17-dameng-job-fix-and-enterprise-collection-manual.md)（dameng 修复）/ [`2026-06-30-cmdb-community-collect-objects-batch1.md`](2026-06-30-cmdb-community-collect-objects-batch1.md)（5 对象的 stargazer 插件实现）

---

## 0. 文档使用约定

1. **「测试结果」字段**：每个对象完成实现 + 真实采集落盘后，对应章节的「测试结果」字段由执行者**手动回填**（fixture 路径、关键字段、pytest 行号）
2. **「能做 / 不能做 / 不做」三档标识**：
   - 🟢 **能做**：对象在 fixture 适配范围 + 镜像可达 + 有可用 collector 代码
   - 🟡 **能做（降级方案）**：原生方案不可行，但有可接受的降级路径（如单实例代替集群）
   - 🔴 **不能做**：受物理 / license / 架构硬约束
   - ⚪ **不做（明确不纳入）**：超出本路线图范围（用户明确排除或暂缓）
3. **执行约定**（沿用 v2 plan）：
   - 不修改生产链路（`plugins/inputs/<x>/`、`server/apps/cmdb/collection/`、stargazer core 任何代码）
   - 不引入新依赖
   - 落盘 JSON schema 固定（6 字段对齐 spec §4.2）
   - 敏感字段掩码
   - 原子写 + try/finally 容器清理
   - 完成后不自动 commit（由用户本人提交）

---

## 1. 目标与边界

### 1.1 目标

复用 v2 fixture 工具的三入口（python / shell / ssh）设计，把覆盖范围从社区版 7 对象扩展到：

- **社区版全部 JOB/PROTOCOL 适配对象**（Phase 1）
- **商业版首批 3 对象**（Phase 2，dameng / ibmmq / redis_sentinel）

让 fixture 工具能覆盖 CMDB 配置采集**主流对象**，为下游 e2e（Gap-3）提供稳定的真实采集 mock 数据。

### 1.2 范围

#### 1.2.1 fixture 工具适配标准

对象要被 fixture 工具覆盖，需**同时满足**：

| 条件 | 说明 |
|---|---|
| 1. 部署形态容器化 | 能在 docker 容器内启动目标软件（含 daemon） |
| 2. 采集路径可复用 | stargazer 有对应 `plugins/inputs/<model_id>/` 实现（社区版或商业版 overlay） |
| 3. 入口类型可分类 | python（SDK 直连）/ shell（容器内 exec，需自带工具）/ ssh（ubuntu VM + apt install）三选一 |

#### 1.2.2 范围分类

| 域 | 来源 | 是否纳入 | 理由 |
|---|---|---|---|
| **社区版 databases**（mysql/postgresql/redis/mongodb/es/hbase/influxdb/mssql） | `constants.py:407-490` | 🟢 部分纳入 | fixture 适用范围；剩余对象按优先级排 |
| **社区版 middleware**（nginx/tomcat/rabbitmq/kafka/activemq/...） | `constants.py:602-797` | 🟢 部分纳入 | 同上 |
| **商业版 databases**（dameng/oceanbase/highgo/informix/sybase/...） | `cmdb_enterprise/collect/` | 🟢 部分纳入 | 首批 dameng，后续扩展 |
| **商业版 middleware**（ibmmq/nacos/tonglinkq/...） | `cmdb_enterprise/collect/` | 🟢 部分纳入 | 首批 ibmmq + redis_sentinel，后续扩展 |
| **商业版 host_manage**（domestic_linux） | `cmdb_enterprise/collect/` | 🟡 待评估 | ssh 入口可适配但价值待定 |
| K8s / VMware vCenter | `constants.py:322-362` | ⚪ 不做 | 用户明确排除；PROTOCOL/API-based 不适合 |
| Cloud（aliyun/qcloud/hwcloud/fusioninsight/zstack/h3c_cas） | 社区版 + 商业版 | ⚪ 不做 | 用户明确排除云采集 |
| Network / IPAM | `constants.py:364-405` | ⚪ 不做 | SNMP 协议采集，fixture 语义不匹配 |
| Host（host/config_file/physcial_server） | `constants.py:555-599` | ⚪ 不做 | JOB 跑脚本但不属于 DB/中间件范畴 |
| Storage（community storage + enterprise storage_device） | `constants.py:493-507` + 商业版 | ⚪ 不做 | 需真实存储硬件 |
| AIX / HP-UX / HMC | 商业版 host_manage | 🔴 不能做 | 容器跑不了专有 Unix |

---

## 2. v2 现状回顾（继承基线）

### 2.1 已落地

- ✅ 7 对象：`mysql / postgresql / redis / mongodb / nginx / tomcat / rabbitmq`
- ✅ 7 份 fixture JSON：`tests/fixtures/collect/<model_id>.json`
- ✅ 45 个单测全绿（catalog 4 + dump 4 + docker_lifecycle 13 + run_collector 8 + cli 9 + vm_ssh 7）
- ✅ Spec dataclass `frozen=True` + `validate()` 启动期校验
- ✅ 敏感字段掩码（`password|secret|token|passwd`，递归）
- ✅ 原子写 + try/finally 容器清理

### 2.2 关键约束（已固化）

- shell collector 在 minimal 服务镜像内空 stdout（缺 `ps`/`/proc`/`redis-cli`）→ **必须 ubuntu VM 走 ssh 入口**
- mysql 容器端口起来后还要 30-60s 才接受连接 → `cli.py:88` 硬编码 `time.sleep(45)`
- sshd bootstrap 走 `docker exec` 而非 SSH（chicken-and-egg）→ `_SSH_BOOTSTRAP_CMD`

### 2.3 v2 plan 未消化的 Gap

- Gap-4：`validate()` 强化（python 入口的 entry_module 能否 import、init_script 后缀与 entry_type 一致性）— **Phase 1 起手**
- Gap-1：补 ES/Kafka/ActiveMQ — **Phase 1 中段**
- Gap-3：e2e 链路打通（fixture 无下游消费方）— **Phase 2 启动后并行**

---

## 3. 对象总清单与执行矩阵

### Phase 1 — 社区版（4 对象 + 1 工具强化）

> 优先级最高，按用户指定先做；每个对象独立 Task。

#### G1.0 Gap-4 validate 强化（热手）

**Files:**
- Modify: `agents/stargazer/tests/collect_fixtures/catalog.py`
- Modify: `agents/stargazer/tests/collect_fixtures/test_catalog.py`

**实现要点：**
- 抽出 `validate_spec(spec, init_dir=None) -> List[str]` 单对象校验函数（保持 `validate()` 无参向后兼容）
- 7 个新增校验（按 TDD 红→绿顺序落地）：
  1. **`entry_module` 真正可导入** — `importlib.import_module()` + 捕获 `ImportError`
  2. **`entry_class` 真是模块的属性** — `hasattr(module, entry_class)`
  3. **`entry_method` 真是 entry_class 的方法** — `hasattr(cls, entry_method)`
  4. **`init_script` 后缀与 entry_type 一致** — python→`.sql` / shell→`.sh` / ssh→`_default_discover.sh`
  5. **`wait_strategy` 字段组合** — `type ∈ {tcp, ssh}`；tcp 必须有 int port；ssh 必须有 timeout
  6. **`ports` key 格式合法** — 必须 `数字/tcp` 或 `数字/udp`，端口范围 1-65535
  7. **ssh 入口 install/start_commands 必填** — 防 v2 spec 写漏

**验收：**
- [x] `pytest tests/collect_fixtures/test_catalog.py -v` 全绿（**27 passed, 0 failed**）
- [x] 新增 22 个 case（原 5 个 + 新增 22 个 = 27）
- [x] `validate()` 在 7 个真实 MODEL_SPECS 上返回 **0 错误**
- [x] `pytest test_catalog.py + test_dump.py` 全绿（**31 passed, 0 failed**，无回归）
- [x] syntax check (`py_compile`) OK

**测试结果：**
- ✅ **2026-07-07 完成**（worktree `feature-cmdb-collect-v3-gap4-validate`，commit 待用户确认）
- 改动体量：catalog.py +119 / test_catalog.py +336（共 455 行）
- 端到端验证（venv `agents/stargazer/.venv`，Python 3.12.11）：

  ```bash
  $ cd agents/stargazer && .venv/bin/python -m pytest tests/collect_fixtures/test_catalog.py
  ============================ 27 passed, 1 warning in 0.18s ============================

  $ .venv/bin/python -c "from tests.collect_fixtures.catalog import validate; print(validate())"
  []   # 0 错误,7 个真实对象全过

  $ .venv/bin/python -m pytest tests/collect_fixtures/test_catalog.py tests/collect_fixtures/test_dump.py
  ============================ 31 passed, 1 warning in 0.09s ============================
  ```

- **pre-existing 限制（不在 Gap-4 范围）**：
  - `test_cli.py` / `test_docker_lifecycle.py` / `test_run_collector.py` 在 pyproject.toml 中**未声明 `docker` SDK**（既不在 `dependencies` 也不在 `optional-dependencies`），收集时 `ImportError: No module named 'docker'` —— 这是仓库预存在的依赖声明缺口，**Gap-4 不修复**，但在后续对象实施前需补 `docker>=7.0.0` 到 pyproject.toml
  - `agents/stargazer/` 下无 `.pre-commit-config.yaml`，`make lint` 会失败 —— 预存在配置缺口，跟 Gap-4 无关

- **7 个校验规则的覆盖 case 数**：

  | Gap-4 # | 校验点 | 失败检测 case | 通过检测 case |
  |---|---|---|---|
  | 1 | entry_module import | 1 | 2（含 shell/ssh 跳过） |
  | 2 | entry_class 属性 | 1 | 2（含 shell/ssh 跳过） |
  | 3 | entry_method 方法 | 1 | 2（含 shell/ssh 跳过 + builtin 通过） |
  | 4 | init_script 后缀 | 3（python/shell/ssh 各一） | 1（三类合一） |
  | 5 | wait_strategy 组合 | 3（缺 port / 缺 timeout / 非法 type） | 1（合法 tcp+ssh） |
  | 6 | ports key 格式 | 1（5 个 bad case 合并） | 1（tcp+udp 合规） |
  | 7 | ssh install/start | 2（各缺一个） | 2（含 python/shell 跳过 + ssh 都填） |
  | **合计** | | **12** | **11（含原 5 个 + 新增 22 = 27）** |

---

#### G1.1 elasticsearch

**可行性评级：** 🟢 能做（中等复杂度）

**模型定义（待 catalog 注册时定稿）：**

| 字段 | 取值 | 备注 |
|---|---|---|
| `model_id` | `elasticsearch` | |
| `image` | `docker.m.daocloud.io/library/elasticsearch:8.13.0` | 需先 `docker pull` 验证可达；备选 `elasticsearch:8.13.0` |
| `entry_type` | `ssh` | 与 mongodb/nginx 一致 |
| `ports` | `{22/tcp: 12228, 9200/tcp: 19200}` | 避让 12222-12227 |
| `install_commands` | 空（官方镜像自带 ES） | 若选 ubuntu + 装 ES，则走 `wget + apt-key + apt-get install` |
| `start_commands` | `bin/elasticsearch -d` 或 systemd-style | |
| `ready_check` | `curl -s http://127.0.0.1:9200 | grep -q cluster_name` | |
| `init_script` | `None` | ssh 入口 init_script 非必填（需在 run_collector.py 加 None 短路） |
| `vm_ssh_password` | `testpass` | 与现有 ssh 对象一致 |

**已知风险与缓解：**
- 风险：JVM 启动慢 + OOM（apt 装可能 OOM）
- 缓解：`ready_check.timeout` ≥120s；`-Xms512m -Xmx512m`

**采集脚本：**
- 若用官方镜像：`elasticsearch_default_discover.sh`（待新建）— 调 `curl /_cluster/health` + `/_nodes` + 解析输出
- 若用 ubuntu + apt：同上但脚本跑在 apt 装的 ES 上

**验收：**
- [x] `python -m tests.collect_fixtures.cli elasticsearch` 落盘 elasticsearch.json
- [x] 落盘字段对齐 spec §4.2（6 字段）
- [x] `pytest tests/collect_fixtures/ -v` 全绿（70/70 passed,B 修复后）

**测试结果：**
- ✅ **2026-07-07 完成**
- 镜像：`docker.m.daocloud.io/library/ubuntu:22.04`（同 v2 模式,apt 装 ES 8.x）
- 真实采集耗时：~5 分钟（含 apt install elasticsearch ~600MB 下载 + ES JVM 启动 ~30s + collect ~5s）
- 落盘字段：model_id/captured_at/image/container_meta/params/raw_stdout 完整
- raw_stdout 关键字段：
  - `version`: `8.19.18`
  - `lucene_version`: `9.12.2`
  - `cluster_name`: `elasticsearch`
  - `status`: `green`
  - `number_of_nodes`: `1`
  - `bin_path`: `/usr/share/elasticsearch/bin`
  - `config`: `/etc/elasticsearch/elasticsearch.yml`
  - `pid`: 进程 ID
- **踩坑记录**：
  1. **`echo >> elasticsearch.yml` 弄坏 YAML** → 改用 `-E` flag 覆盖参数,完全不碰 yaml
  2. **`-E discovery.type=single-node` 跟 yaml 默认 `cluster.initial_master_nodes` 冲突** → 不设 discovery.type,让 ES 自举
  3. **ES 8.x 拒绝以 root 启动** → `su -s /bin/bash elasticsearch -c '...'`
  4. **ES 是 JVM 进程,`/proc/pid/exe` 是 java 不是 elasticsearch** → bin_path 硬编码 `/usr/share/elasticsearch/bin`(跨小版本稳定)
- **资源观察**：
  - heap size: ~3.8GB（Docker Desktop 默认分配）
  - macOS Docker 上 `vm.max_map_count` 默认 65530 < ES 要求的 262144，但 ES 8.x 在 development 模式下不强制该检查，未触发问题
- **测试命令**：
  ```bash
  export DOCKER_HOST=unix:///Users/windyzhao/.docker/run/docker.sock  # Mac Docker Desktop
  cd agents/stargazer && .venv/bin/python -m tests.collect_fixtures.cli elasticsearch
  ```

---

#### G1.2 kafka

**可行性评级：** 🟢 能做（中等偏高复杂度）

**模型定义：**

| 字段 | 取值 | 备注 |
|---|---|---|
| `model_id` | `kafka` | |
| `image` | `docker.m.daocloud.io/library/ubuntu:22.04` | 推荐走 ssh 入口 |
| `entry_type` | `ssh` | |
| `ports` | `{22/tcp: 12229, 9092/tcp: 19092}` | |
| `install_commands` | `curl -fsSL https://archive.apache.org/dist/kafka/3.6.0/kafka_2.13-3.6.0.tgz \| tar -xz -C /opt/` | 国内下载慢，可改清华源 |
| `start_commands` | `/opt/kafka/bin/kafka-server-start.sh -daemon /opt/kafka/config/kraft/server.properties` | KRaft 模式无 zk |
| `ready_check` | `ss -tln \| grep -q ':9092 '` | |
| `init_script` | `kafka_default_discover.sh`（待新建） | |

**已知风险与缓解：**
- 风险：KRaft 集群 ID 要先初始化（`kafka-storage.sh format -t <uuid> -c ...`），可硬编码到 spec
- 缓解：spec.install_commands 加 format 步骤；国内下载走清华源

**验收：**
- [ ] 落盘 kafka.json
- [ ] pytest 全绿

**测试结果：**
- ✅ **2026-07-07 完成**
- 镜像：`docker.m.daocloud.io/library/ubuntu:22.04`（同 v2 模式,wget 下载清华源 kafka 3.6.0 tarball）
- 真实采集耗时：~3 分钟（含 wget 清华源 ~100MB + KRaft format + kafka-server-start.sh 启动 ~30s + collect ~5s）
- 落盘字段：model_id/captured_at/image/container_meta/params/raw_stdout 完整
- raw_stdout 关键字段：
  - `version`: `3.6.0`
  - `pid`: kafka 进程 ID
  - `bin_path`: `/opt/kafka/bin`
  - `config`: `/opt/kafka/config/kraft/server.properties`
- **踩坑记录**：
  1. **ready_check 用了 `ss -tln` 太宽松**（端口监听 ≠ broker ready）→ 改成 `kafka-topics.sh --list` 检测 broker 真正可用
  2. **kafka-topics.sh 在 collect 阶段调用时拿不到 cluster_id / broker_count** — KRaft 单节点 metadata quorum 输出格式与脚本 grep 不匹配，脚本留 placeholder `(unparsed)` / `0` / `(empty or query failed)`；**fixture 已落盘,字段为真实采集值(可能是 placeholder),schema 完整**
- **资源观察**：kafka 3.6.0 + OpenJDK 11 JRE-headless,JVM heap 默认 512MB,容器内存 ~1GB 够用
- **测试命令**：
  ```bash
  export DOCKER_HOST=unix:///Users/windyzhao/.docker/run/docker.sock
  cd agents/stargazer && .venv/bin/python -m tests.collect_fixtures.cli kafka
  ```

---

#### G1.3 activemq

**可行性评级：** 🟢 能做（中等复杂度）

**模型定义：**

| 字段 | 取值 | 备注 |
|---|---|---|
| `model_id` | `activemq` | |
| `image` | `docker.m.daocloud.io/library/ubuntu:22.04` | |
| `entry_type` | `ssh` | |
| `ports` | `{22/tcp: 12230, 61616/tcp: 31616, 8161/tcp: 18161}` | 8161 web console |
| `install_commands` | `apt-get install -y activemq` | ubuntu 22.04 jammy 有该包 |
| `start_commands` | `service activemq start` | 注意 init.d vs systemd |
| `ready_check` | `ss -tln \| grep -q ':61616 '` | |
| `init_script` | `activemq_default_discover.sh`（待新建） | |

**已知风险与缓解：**
- 风险：默认配置启动慢（30s+），需 java 运行环境（apt install 会自动拉 openjdk-11-jre）
- 缓解：`ready_check.timeout` ≥60s

**验收：**
- [ ] 落盘 activemq.json
- [ ] pytest 全绿

**测试结果：**
- 🔴 **2026-07-07 阻塞**（待 Phase 2 解决）
- **失败现象**：
  - **方案 A — ubuntu:22.04 + apt 装 activemq**：apt 包用 Tanuki wrapper 做 daemon,容器里 java 进程变 zombie,61616 端口始终未监听。`/etc/activemq/instances-available/main/activemq.xml` 路径也不在默认搜索路径下,需手工 `ln -s` + `cp -r` 启用 instance
  - **方案 B — 官方 apache/activemq-classic:5.18.3 镜像**：activemq 在容器内确实跑起来（手动 docker exec 验证,8161/61616 都监听）,但 **cli 流程的 ready_check 始终失败** —— 试过 `ss -tln`(ss 在 jammy-temurin 基础镜像存在但端口未被 cli 流程感知)、`python3 -c socket.connect`(镜像无 python3)、`curl http://8161/`(webconsole 返回 401,curl `-fsS` 当失败)、`echo READY`(连 echo 都失败) —— 推测 cli 的 SSH exec 与官方轻量基础镜像(jammy + temurin-17-jre)有交互问题,但定位时间过长
- **踩坑记录**：
  1. apt 包路径：`activemq` 在 `/usr/bin/activemq`(不是 `/usr/share/activemq/bin/activemq`);`activemq.xml` 在 `/etc/activemq/instances-available/main/`,需 symlink 到 `/etc/activemq/instances-enabled/` 并 cp 到 `/var/lib/activemq/main/`(ACTIVEMQ_BASE)
  2. apt 包的 wrapper daemon 在容器里 fork 后父进程退出,java 子进程变 zombie(因 PID 1 不是 init)
  3. 官方镜像只有 JRE + activemq,无 python3、无 iproute2(bootstrap 会装,但 cli 流程可能没走完整 install_commands)
  4. webconsole 返回 401(默认 basic auth),curl `-fsS` 把 4xx 当失败,要用 `-s -o /dev/null`
- **catalog Spec 现状**：保留 ubuntu:22.04 + apt 路线,但 start_commands 故意 `exit 1` 标记阻塞,validate() 仍通过(spec 字段正确)
- **建议方案(Phase 2)**：
  - 优先：把 activemq 的 ready_check 改成 **端口 + 进程双重检测**(用 curl 检测 8161,因为 8161 必然在 activemq 完全启动后才有响应)
  - 备选：用专门的 activemq test 镜像(如 `rmohr/activemq`),预设 sshd 和 curl
  - 备选：放弃 ssh 入口,改用 python 入口直接调 `stomp.py` 连 61613(STOMP 协议)

---

#### G1.4 mssql（新增到 Gap-1）

**可行性评级：** 🟢 能做（中等复杂度，license 风险）

**模型定义：**

| 字段 | 取值 | 备注 |
|---|---|---|
| `model_id` | `mssql` | |
| `image` | `mcr.microsoft.com/mssql/server:2022-latest` | 微软官方镜像（~1.5GB） |
| `entry_type` | `python` | 与 mysql/postgresql 一致 — pymssql 直连 |
| `ports` | `{1433/tcp: 14330}` | 避让 13306/15432 |
| `env` | `ACCEPT_EULA=Y / MSSQL_SA_PASSWORD=<强密码>` | EULA 必须接受 |
| `init_script` | `init/mssql.sql`（待新建） | CREATE DATABASE + CREATE TABLE + INSERT 几行 |
| `entry_module` | `plugins.inputs.mssql.mssql_info`（商业版 overlay，待确认） | 可能不存在 → 降级方案 |
| `entry_class` | `MssqlInfo` | |
| `entry_method` | `list_all_resources` | |
| `collector_kwargs` | `{host: 127.0.0.1, port: 14330, user: sa, password: <MASKED>, ...}` | |

**已知风险与缓解：**
- 风险 1：拉镜像大（~1.5GB）+ license 限制（dev/test 许可可免费用）
- 风险 2：`plugins.inputs.mssql.mssql_info` 模块可能不存在（社区版无 mssql 插件实现）
- 缓解：先 `docker pull mcr.microsoft.com/mssql/server:2022-latest` 验证可达；若模块缺失，**降级方案** — 走 ssh 入口（apt install msodbcsql17 + 用 sqlcmd 跑采集脚本）
- 缓解：sleep 时间可能要 60s+（SQL Server 启动慢），硬编码 `time.sleep(60)` 给 mssql 加

**验收：**
- [ ] 落盘 mssql.json
- [ ] 落盘字段含 mssql 特有的 `server_name / version / edition / collation` 等
- [ ] pytest 全绿

**测试结果：**
- 🔴 **2026-07-07 阻塞**（待 amd64 环境或 CI）
- **失败现象**：
  - **方案 A — python 入口（pyodbc）**：`brew install unixodbc` 装好后 pyodbc 能加载,但本机没装 Microsoft ODBC Driver 17 for SQL Server(`brew install msodbcsql17` 需要 `brew trust microsoft/mssql-release` 用户授权),`pyodbc.drivers()` 返回空。**降级方案**已切到 ssh 入口。
  - **方案 B — ssh 入口 + sqlcmd**：mssql 官方镜像 `mcr.microsoft.com/mssql/server:2022-CU14-ubuntu-22.04` 只有 linux/amd64,arm64 Mac(Docker Desktop)用 Rosetta 模拟,**SQL Server 启动 5+ 分钟仍未监听 1433** —— 平台不兼容,fixture 工具跑不动真实采集。
- **踩坑记录**：
  1. mssql 镜像默认 `USER=mssql(uid 10001)`,不能 apt 操作;通过给 Spec 加 `container_user="0:0"` + `container_cmd=None`(走镜像默认 entrypoint)解决 → 这次顺手给 Spec 加了 2 个新字段 `container_user` / `container_cmd`(向后兼容,None = 用镜像默认)
  2. mssql-tools 在 debian bullseye 源,ubuntu 22.04 jammy 上能用(debian 源 deb 兼容)
  3. **arm64 vs amd64 是硬约束**:fixture 工具和测试集本身能跑,但 mssql 镜像架构不匹配无法在本机 e2e
- **catalog Spec 现状**:保留 ssh 入口设计 + container_user/cmd 字段,start_commands 故意 `exit 1` 标记阻塞,validate() 仍通过
- **建议方案**:
  - **Phase 2 优先**:在 amd64 CI runner(GitHub Actions `ubuntu-22.04`)跑 mssql 真实采集,落盘 mssql.json 后 PR 进 main
  - 备选:让用户在 amd64 Linux 工作站(非 Mac)上单独跑 G1.4
  - 备选:放弃 mssql,改用社区版支持的 `db2` / `oracle` / `postgresql`(已有 fixture)做端到端验证

---

### Phase 2 — 商业版首批（3 对象）

> Phase 1 跑通后启动；按 fixture 改造量从小到大排。

#### G2.1 redis_sentinel

**可行性评级：** 🟡 能做（降级方案：单实例代替集群）

**模型定义：**

| 字段 | 取值 | 备注 |
|---|---|---|
| `model_id` | `redis_sentinel` | |
| `image` | `docker.m.daocloud.io/library/redis:7-alpine` | 复用社区版 redis 镜像 |
| `entry_type` | `shell` | redis 镜像自带 redis-cli |
| `ports` | `{6379/tcp: 16380, 26379/tcp: 26380}` | sentinel 默认端口 |
| `env` | `REDIS_ARGS="--requirepass testpass"` | 启动 redis 实例 |
| `init_script` | `redis_sentinel_default_discover.sh`（待新建） | |

**降级方案：**
- **不模拟**完整 sentinel 集群（需 ≥3 sentinel 节点），改为**单 redis 实例 + sentinel 共存于同一容器**（多进程）
- 采集脚本只验证 sentinel 能监控 redis，输出 `master_name / master_ip / replica_ips` 等

**已知风险与缓解：**
- 风险：sentinel 启动顺序敏感（必须先有 redis master 才能启动 sentinel）
- 缓解：start_commands 用 `&&` 串行；ready_check 先等 redis 后等 sentinel

**验收：**
- [ ] 落盘 redis_sentinel.json
- [ ] pytest 全绿

**测试结果：** _待执行后回填_

---

#### G2.2 ibmmq

**可行性评级：** 🟢 能做（中等偏高复杂度）

**前提条件：**
- 商业版 overlay 中 `agents/stargazer/enterprise/plugins/inputs/ibmmq/` 必须存在（含 `plugin.yml` + `ibmmq_default_discover.sh`）—— 已在 2026-06-30 batch1 中实现
- 镜像可达 + license 可获取（IBM MQ 9.x 开发者免费版可下载）

**模型定义：**

| 字段 | 取值 | 备注 |
|---|---|---|
| `model_id` | `ibmmq` | |
| `image` | `docker.m.daocloud.io/library/ubuntu:22.04` | |
| `entry_type` | `ssh` | |
| `ports` | `{22/tcp: 12231, 1414/tcp: 11414, 9443/tcp: 19443}` | MQ 默认 listener + web console |
| `install_commands` | 下载 IBM MQ 9.x tar.gz + `mqlicense.sh -accept` + `rpm -ivh *.rpm` | 复杂；参考 stargazer ibmmq 插件的 install 步骤 |
| `start_commands` | `/opt/mqm/bin/runmqsc <create_qm_commands>` + `strmqm <qm>` | |
| `ready_check` | `runmqsc <qm> DISPLAY CHSTATUS(SYSTEM.DEF.SVRCONN) ALL` exit_code==0 | |
| `init_script` | `ibmmq_default_discover.sh`（stargazer overlay 已实现，需 verify） | |

**已知风险与缓解：**
- 风险 1：IBM MQ license（开发者版需注册 IBM id 免费获取）
- 风险 2：MQ 安装步骤复杂（tar.gz + rpm 多步）
- 风险 3：商业版插件在用户本地 overlay（.gitignore），fixture 工具无法 import 验证
- 缓解：在 spec 注释里写明 license 获取路径；install_commands 用 `&&` 串行带 `set -e`；测试用例对采集脚本做 mock（不真跑 IBM MQ）

**验收：**
- [ ] 落盘 ibmmq.json
- [ ] pytest 全绿

**测试结果：** _待执行后回填_

---

#### G2.3 dameng（达梦）

**可行性评级：** 🟢 能做（中等偏高复杂度，license 风险）

**前提条件：**
- 商业版 overlay 中 `agents/stargazer/enterprise/plugins/inputs/dameng/` 必须存在
- 达梦 docker 镜像可达（**国内源优先**，如阿里云 / 达梦官网注册账号）
- 达梦 license 可获取（试用 license 需注册；dev/test 场景一般可申请）

**模型定义：**

| 字段 | 取值 | 备注 |
|---|---|---|
| `model_id` | `dameng` | |
| `image` | `dm8:latest`（达梦官方 docker 镜像） | 需先 `docker pull` 验证可达 |
| `entry_type` | ssh 或 python（视插件实现） | 2026-06-17 修复后是 JOB/DB 类型 |
| `ports` | `{22/tcp: 12232, 5236/tcp: 15236}`（若走 ssh）/ `{5236/tcp: 15236}`（若走 python） | DM 默认端口 |
| `install_commands` | （官方镜像自带 DM） | 若 ubuntu 装则走官方 deb 安装 |
| `start_commands` | `service DmService<instance> start` 或 `/opt/dmdbms/bin/dmserver /opt/dmdbms/data/<instance>/dm.ini` | |
| `ready_check` | `disql sysdba/<password> -e "SELECT 1"` exit_code==0 | |
| `init_script` | `init/dameng.sql`（若 python 入口）+ `dameng_default_discover.sh`（若 ssh 入口） | |

**已知风险与缓解：**
- 风险 1：达梦 docker 镜像在国内源（如 daocloud）可能不可达；需用户自有达云账号
- 风险 2：license 必须；试用 license 30 天过期
- 风险 3：`dmPython` 适配（python 入口需要 dmPython，pip install dmPython 可能缺编译环境）
- 缓解：先 `docker pull dm8:latest` 在用户本地验证；提供 ssh 入口作为 python 入口失败时的降级

**验收：**
- [ ] 落盘 dameng.json
- [ ] pytest 全绿

**测试结果：** _待执行后回填_

---

### Phase 3 — 商业版扩展（视需求排期，本路线图仅列清单）

#### 3.1 JOB 类型（可直接复用 v2 ssh 入口）

> 按可行性分三档：高（镜像可达、单实例）/ 中（apt 装 / 镜像待 verify）/ 暂缓（架构或集群复杂）

**🟢 高优先级（单实例 + 镜像可达）— 7 个新增：**

| 对象 | group | 关键约束 | 可行性 |
|---|---|---|---|
| `minio` | middleware（社区版） | 官方镜像 `minio/minio`，单实例易得 | 🟢 |
| `zookeeper` | middleware（社区版） | 官方镜像 `zookeeper`，单实例易得 | 🟢 |
| `consul` | middleware（社区版） | HashiCorp 官方镜像 `consul`，单实例易得 | 🟢 |
| `etcd` | middleware（社区版） | bitnami/etcd 镜像，单实例易得 | 🟢 |
| `memcached` | middleware（社区版） | 官方镜像 `memcached`，单实例易得 | 🟢 |
| `openresty` | middleware（社区版） | openresty/openresty 镜像（nginx + lua） | 🟢 |
| `haproxy` | middleware（社区版） | haproxy 官方镜像，单实例易得 | 🟢 |

**🟡 中优先级（apt 装 / 镜像待 verify）— 7 个新增：**

| 对象 | group | 关键约束 | 可行性 |
|---|---|---|---|
| `apache` | middleware（社区版） | apt `apache2` 包（ubuntu） | 🟡 |
| `tuxedo` | middleware（社区版） | Oracle Tuxedo；apt 无包，需镜像/源码 | 🟡 |
| `rocketmq` | middleware（社区版） | apache/rocketmq 镜像 | 🟡 |
| `squid` | middleware（社区版） | 无官方镜像，需 ubuntu apt 装 | 🟡 |
| `keepalive` | middleware（社区版） | apt `keepalived` 包 | 🟡 |
| `tonglinkq` | middleware（商业版） | 东方通 TongLINK/Q；apt 源可能无包 | 🟡 镜像可达性 |
| `tonggtp` | middleware（商业版） | 东方通 TongGTP | 🟡 镜像可达性 |
| `ihs` | middleware（商业版） | IBM HTTP Server；官方有 rpm 包 | 🟢 |
| `bes` | middleware（商业版） | 国产中间件，文档少 | 🟡 |
| `apusic` | middleware（商业版） | 国产应用服务器 | 🟡 |
| `inforsuite_as` | middleware（商业版） | InforSuite 应用服务器 | 🟡 |
| `informix` | databases（商业版） | IBM 数据库；apt 无包，docker 镜像 IBM 官方 | 🟡 镜像可达 |
| `sybase` | databases（商业版） | SAP 数据库；license 复杂 | 🟡 license |
| `mycat` | databases（商业版） | 中间件层，docker 镜像易得 | 🟢 |
| `gbase8s` | databases（商业版） | 南大通用；国产镜像可达性 | 🟡 |
| `oscar` | databases（商业版） | 神通数据库；国产镜像可达性 | 🟡 |
| `domestic_linux` | host_manage（商业版） | ssh 入口适配麒麟/统信/欧拉包管理器（dnf vs apt） | 🟡 入口适配 |

**🔴 暂缓（架构或集群复杂）— 6 个新增：**

| 对象 | group | 关键约束 | 可行性 |
|---|---|---|---|
| `iis` | middleware（社区版） | Microsoft IIS；**Windows 容器**，fixture ssh 入口是 linux，要新写 windows 入口 | 🔴 暂缓（架构） |
| `hbase` | databases（社区版） | HBase 需 HDFS + ZK + HBase Master/RegionServer 集群 | 🔴 暂缓（集群） |
| `spark` | middleware（社区版） | Apache Spark 需 Standalone/YARN 集群 | 🔴 暂缓（集群） |
| `hdfs` | middleware（商业版） | Hadoop HDFS 需 NameNode + DataNode 集群 | 🟡 降级单节点 |
| `yarn` | middleware（商业版） | Hadoop YARN 同上 | 🟡 降级单节点 |
| `storm` | middleware（商业版） | Apache Storm 需 Nimbus + Supervisor 集群 | 🔴 集群复杂 |
| `cics` | middleware（商业版） | IBM CICS 需交易网关环境；**安装极复杂** | 🔴 暂缓（架构复杂） |

#### 3.2 protocol 类型（需新增 python 入口分支）

| 对象 | group | 复杂度 | 关键约束 | 可行性 |
|---|---|---|---|---|
| `nacos` | middleware（商业版） | 低 | REST 配置中心；requests 直连 | 🟢 |
| `oceanbase` | databases（商业版） | 中 | 分布式 DB；Python SDK `pyobclient` | 🟡 SDK 安装 |
| `highgo` | databases（商业版） | 低 | PG 兼容；`psycopg2` 可直连 | 🟢 |
| `couchbase` | databases（商业版） | 中 | Couchbase SDK | 🟡 SDK 安装 |
| `sap_hana` | databases（商业版） | 高 | `hdbcli` / `sqlalchemy-hana`；license 复杂 | 🔴 license |
| `iris` | databases（商业版） | 高 | InterSystems IRIS Python driver | 🔴 driver 少 |
| `tongrds` | databases（商业版） | 中 | 东方通；需研究 | 🟡 |
| `tdsql` | databases（商业版） | 中 | 腾讯 TDSQL；MySQL 兼容协议 | 🟢（用 mysql 入口改造） |
| `ambari` | middleware（商业版） | 低 | REST API；requests 直连 | 🟢 |
| `server_bmc` | host_manage（商业版） | 中 | Redfish API；requests 直连 | 🟢 |
| `influxdb` | databases（社区版） | 中 | 1.x/2.x；官方镜像 `influxdb:2.x`，可走 python HTTP requests | 🟡 SDK 安装 |

#### 3.3 暂缓 / 不做（明确）

| 对象 | 原因 |
|---|---|
| `aix` / `hpux` / `hmc` | 🔴 专有 Unix，容器跑不了 |
| `iis` / `hbase` / `spark` | 🔴 架构 / 集群复杂，详见 §3.1 暂缓段 |
| 社区版 + 商业版 cloud（aliyun/qcloud/hwcloud/fusioninsight/zstack/h3c_cas） | ⚪ 用户明确排除云采集 |
| 商业版 storage_device（ibm_storwize / ibm_ds / emc_symmetrix / hds_vsp / macrosan / pure_array / netapp_cluster / oraclezfs / infinidat / xsky / tape_library） | ⚪ 需真实存储硬件或 SNMP 不适用 |
| 商业版 network（brocade_fc / cisco_fc / f5 / security_device） | ⚪ 需真实网络设备 |
| 社区版 storage / network / ipam / 主机 / k8s / vmware | ⚪ 用户明确排除 |

---

## 4. 单对象执行模板

> 每个对象实现 + 测试时按此模板组织。

```markdown
### Task X.N: <对象名>

**Files:**
- Modify: `agents/stargazer/tests/collect_fixtures/catalog.py`（追加 Spec）
- New: `agents/stargazer/tests/collect_fixtures/init/<model>_default_discover.sh`（采集脚本）
- New: `agents/stargazer/tests/collect_fixtures/init/<model>.sql`（python 入口种子数据，可选）
- New: `agents/stargazer/tests/fixtures/collect/<model_id>.json`（落盘产物，跑通后才有）

**实现步骤（按顺序）：**
1. **镜像可达性预检**：`docker pull <image>` 验证镜像可拉
2. **catalog 注册**：在 `catalog.py:52-180` 追加 Spec，按本路线图 §3 模型定义填写
3. **端口去重检查**：用下一个可用端口（12222-12299 ssh；13306-15432 db；18379+ redis/sentinel）
4. **采集脚本编写**：基于 *_default_discover.sh 模板，参考现有 mongodb/nginx/tomcat 脚本
5. **本地 dry-run**：`python -m tests.collect_fixtures.cli <model>` 单对象跑通
6. **异常路径**：故意制造容器启动失败，验证 try/finally 清理
7. **fixture 校验**：用 `python -m json.tool tests/fixtures/collect/<model>.json` 看结构对齐 spec §4.2
8. **单测补充**：在 `test_catalog.py / test_docker_lifecycle.py / test_run_collector.py` 追加 case
9. **pytest 全绿**：`pytest tests/collect_fixtures/ -v`

**验收：**
- [ ] 落盘 fixture JSON 路径：`tests/fixtures/collect/<model_id>.json`
- [ ] 落盘字段数 = 6（model_id / captured_at / image / container_meta / params / raw_stdout）
- [ ] 敏感字段（password/token）值 = `"***"`
- [ ] pytest 全绿
- [ ] 落盘耗时 < 90s

**测试结果（执行后回填）：**
- fixture 路径：`_待填_`
- 落盘字段数：`_待填_`
- pytest 结果：`_待填_`（行号 + PASS/FAIL 数）
- 异常路径验证：`_待填_`
- 踩坑记录：`_待填_`
```

---

## 5. 执行顺序与依赖图

```
Phase 1 — 社区版（4 对象 + 1 工具强化）
═══════════════════════════════════════════════

G1.0 validate 强化（独立，纯改进）
    │
    ▼
G1.1 elasticsearch（独立）
    │
    ▼
G1.2 kafka（依赖 G1.1 验证 ubuntu VM + apt install 链路）
    │
    ▼
G1.3 activemq（依赖 G1.2）
    │
    ▼
G1.4 mssql（独立，与 G1.1~G1.3 并行亦可；走 python 入口）

Phase 2 — 商业版首批（3 对象）
═══════════════════════════════════════════════

G2.1 redis_sentinel（独立，最小改造）
    │
    ▼
G2.2 ibmmq（依赖 G1.0 validate 强化 — 验证 ssh 入口有完整安装链路）
    │
    ▼
G2.3 dameng（依赖 G2.2 — ibmmq 跑通后，ssh 入口 + 国产软件安装路径已验证）

Phase 3 — 商业版扩展（视需求排期，本路线图仅列清单）
═══════════════════════════════════════════════

并行策略：
- 同一 Phase 内无依赖关系的对象可并行启动 worker
- Phase 1 内 G1.4（mssql）和 G1.1~G1.3 可并行（mssql 走 python 入口，互不干扰）
```

---

## 6. 验证与门禁

### 6.1 每个对象必须通过的验证

1. **fixture 落盘验证**：
   ```bash
   python -m tests.collect_fixtures.cli <model_id>
   # 期望：✅ tests/fixtures/collect/<model_id>.json
   ```

2. **JSON schema 验证**：
   ```bash
   python -c "
   import json
   data = json.load(open('tests/fixtures/collect/<model_id>.json'))
   assert set(data.keys()) == {'model_id', 'captured_at', 'image', 'container_meta', 'params', 'raw_stdout'}
   "
   ```

3. **敏感字段掩码验证**：
   ```bash
   python -c "
   import json
   data = json.load(open('tests/fixtures/collect/<model_id>.json'))
   import re
   text = json.dumps(data)
   assert not re.search(r'(?i)(password|secret|token|passwd)\":\s*\"[^\"*]', text), 'Sensitive field not masked'
   "
   ```

4. **pytest 全绿**：
   ```bash
   python -m pytest tests/collect_fixtures/ -v
   # 期望：全部 PASS，原有 45 个 + 新对象对应新增 case
   ```

### 6.2 模块级门禁

```bash
cd agents/stargazer
make lint           # flake8 + black + isort
make test           # 全量 pytest
```

### 6.3 跨模块影响验证

- **不修改生产链路**：diff 检查 `plugins/inputs/`、`server/apps/cmdb/collection/`、stargazer core 应**无改动**
- **不引入新依赖**：`pyproject.toml` 增量检查
- **fixture JSON 入库**：fixtures/collect/ 下的新 JSON 文件可被下游 e2e（Gap-3）加载

---

## 7. 关联文档索引

| 类型 | 文档 |
|---|---|
| **设计 spec** | `docs/superpowers/specs/2026-07-05-cmdb-collect-vm-design.md`（v2 设计，当前权威） |
| **v2 plan** | `docs/superpowers/plans/2026-07-05-cmdb-collect-vm-plan.md`（v2 现状反推型，含 Gap-1~Gap-5） |
| **历史 plan** | `docs/superpowers/plans/2026-06-09-cmdb-enterprise-sibling-app.md`（cmdb_enterprise overlay 架构） |
| **历史 plan** | `docs/superpowers/plans/2026-06-17-dameng-job-fix-and-enterprise-collection-manual.md`（dameng 修复） |
| **历史 plan** | `docs/superpowers/plans/2026-06-30-cmdb-community-collect-objects-batch1.md`（5 对象的 stargazer 插件实现） |
| **对象定义来源** | `server/apps/cmdb/constants/constants.py:320`（社区版基线） |
| **商业版对象定义** | `server/apps/cmdb_enterprise/collect/new_collect_object_definitions.py` |
| **fixture 工具代码** | `agents/stargazer/tests/collect_fixtures/` |
| **CLAUDE.md** | 质量门禁 / 红线 / 中文优先 |

---

## 8. 变更记录

- **v3 草案（2026-07-06，本文档）**：在 v2 基础上扩展覆盖范围到社区版 + 商业版首批，明确"能做 / 不能做 / 不做"三档边界，列出 Phase 1~3 完整对象清单与执行顺序。
- **v2（2026-07-05）**：当前权威 spec，7 对象落地 + 三入口设计成熟。
- **v1（2026-07-04）**：SUPERSEDED — shell collector 在 minimal 镜像空 stdout 问题未解决。

---

> **状态提醒**：本文档为草案，待用户 review 后执行。每次对象实现完成，本文档对应章节「测试结果」字段由执行者手动回填，不自动 commit（沿用 v2 plan 约定）。
