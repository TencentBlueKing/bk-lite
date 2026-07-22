# Historical Superpowers change: 2026-07-07-cmdb-collect-v3-phase2

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-07-cmdb-collect-v3-phase2-plan.md

> **状态**：执行计划草案（2026-07-07）｜ **启动条件**：Phase 1 已完成（2/4 完成 + 2/4 残留见 §6）
> **关联 roadmap**：[`2026-07-06-cmdb-collect-v3-roadmap.md`](2026-07-06-cmdb-collect-v3-roadmap.md) §3.4 Phase 2
> **关联 Phase 1 报告**：[`2026-07-07-cmdb-collect-v3-phase1-execution-report.md`](2026-07-07-cmdb-collect-v3-phase1-execution-report.md)
> **配套代码**：`agents/stargazer/tests/collect_fixtures/`
> **配套产物**：`agents/stargazer/tests/fixtures/collect/<model_id>.json`

---

## 0. 文档使用约定（继承 roadmap §0）

1. **「测试结果」字段**：每个对象完成实现 + 真实采集落盘后，对应章节的「测试结果」字段由执行者**手动回填**（fixture 路径、关键字段、pytest 行号）
2. **「能做 / 不能做 / 不做」三档标识**：
   - 🟢 **能做**：对象在 fixture 适配范围 + 镜像可达 + 有可用 collector 代码
   - 🟡 **能做（降级方案）**：原生方案不可行，但有可接受的降级路径
   - 🔴 **不能做**：受物理 / license / 架构硬约束
   - ⚪ **不做（明确不纳入）**：超出本路线图范围
3. **执行约定**（沿用 v2 plan）：
   - 不修改生产链路（`plugins/inputs/<x>/` 内**已存在的商业版脚本可复用但不改**；`server/apps/cmdb/collection/`、`stargazer core` 不动）
   - 不引入新依赖（v3 范围内所有依赖已声明）
   - 落盘 JSON schema 固定（6 字段对齐 v2 spec §4.2）
   - 敏感字段掩码
   - 原子写 + try/finally 容器清理
   - 完成后不自动 commit（由用户本人提交）

---

## 1. 关键事实修正（roadmap 偏差清单）

> Phase 2 启动**前必须**对齐这些事实，否则按 roadmap 原方案会直接撞墙。

### 1.1 redis_sentinel — roadmap 说错的事实

| roadmap §3.4 G2.1 写的 | 仓库实际 | 影响 |
|---|---|---|
| entry_type = `shell` | ✅ 正确 — 复用现有 redis catalog 路径 | 无影响 |
| ports `{6379/tcp: 16380, 26379/tcp: 26380}` | ✅ 大致正确 — sentinel 默认 26379 | 用 16379（避开现有 redis）/ 26379 |
| "复用社区版 redis 镜像 `docker.m.daocloud.io/library/redis:7-alpine`" | ❌ **偏差** — 现有 redis Spec 用的是 `redis:7-alpine`(无 daocloud 前缀);docker daemon 是否自动走镜像加速取决于 `/etc/docker/daemon.json` 配置 | 沿用现有 `redis:7-alpine`(docker SDK 默认走 daemon.json 配置);如有加速问题 fallback 用 `docker.m.daocloud.io/library/redis:7-alpine` |
| `init_script = redis_sentinel_default_discover.sh`（待新建） | ⚠️ **半错** — `plugins/inputs/redis/redis_default_discover.sh` **已存在**(600 行,内置 SENTINEL MASTERS / SENTINEL REPLICAS / CLUSTER NODES 全套采集) | **不新建**专用脚本,直接复用 `redis_default_discover.sh`,用 env vars 触发 sentinel 分支 |

**修正结论**：redis_sentinel **不是"新建脚本",而是"复用现有 redis 脚本 + 改 image 启动参数"**。在容器里同时起 redis-server(6379)+ redis-sentinel(26379),discover 脚本通过 `REDIS_TARGET_PORTS=6379,26379` 自动跑 sentinel 分支。

### 1.2 ibmmq — roadmap 说错的事实

| roadmap §3.4 G2.2 写的 | 仓库实际 | 影响 |
|---|---|---|
| "商业版 overlay 中 `agents/stargazer/enterprise/plugins/inputs/ibmmq/` 必须存在（含 `plugin.yml` + `ibmmq_default_discover.sh`）—— 已在 2026-06-30 batch1 中实现" | ❌ **错误** — `agents/stargazer/enterprise/` **目录不存在**(`enterprise/` 在 worktree 和仓库根都是空目录) | roadmap 假设的"已有脚本"不存在,**需要新建** |
| "IBM MQ 9.x 开发者免费版可下载" | ⚠️ 需用户本人 IBMid 下载(license 协议) | **license 必须由用户提供**;脚本里只放 wget URL,**不提交 license 文件** |

**修正结论**：ibmmq **需要新建 collector 脚本**(参考 `redis_default_discover.sh` 的纯 shell 风格,扫 `ps`/`dspmq` 命令输出)。**license 决策是 G2.2 启动的前置条件,需要用户拍板**(见 §3.2)。

### 1.3 dameng — roadmap 说错的事实

| roadmap §3.4 G2.3 写的 | 仓库实际 | 影响 |
|---|---|---|
| "商业版 overlay 中 `agents/stargazer/enterprise/plugins/inputs/dameng/` 必须存在" | ❌ **错误** — `enterprise/` 是空的;**但** `agents/stargazer/plugins/inputs/dameng/dameng_default_discover.sh` **已存在**(84 行真实业务脚本) | 比 roadmap 假设的更好 — 脚本在 stargazer 主仓,不是 overlay |
| `image = dm8:latest`(达梦官方 docker 镜像) | ⚠️ 待验证 — 达梦官方镜像不在 daocloud;需 `docker pull dm8:dmd8_v2.0.1` 之类精确 tag;**license 在容器内手动注入** | image 标签需在 Phase 2 启动时 `docker search dameng` 验证;**license 必须用户提供**(试用 license 30 天过期) |
| "2026-06-17 修复后是 JOB/DB 类型" | ✅ 正确 | 无影响 |

**修正结论**：dameng **复用现有 `dameng_default_discover.sh`**,只补 catalog ssh 入口 Spec;**license 必须用户提供**(与 ibmmq 同性质)。

### 1.4 其他 Phase 2 启动前需澄清的事实

- **fixtures 目录**:`tests/fixtures/collect/` 当前有 9 个 JSON(mysql/postgresql/redis/mongodb/nginx/rabbitmq/tomcat/elasticsearch/kafka),新增 3 个商业版 = 12 个目标产物。
- **CI runner**:roadmap §4 提到"amd64 CI runner(GitHub Actions `ubuntu-22.04`)",Phase 2 默认在本机跑;**只有 redis_sentinel / dameng(amd64 镜像)有 arm64 风险**时,才走 CI。

---

## 2. Phase 2 对象矩阵

> 按 fixture 改造量从小到大排,优先低风险拿成果。

| ID | 对象 | 入口类型 | 复杂度 | license 风险 | 可行性 | 估时 |
|---|---|---|---|---|---|---|
| G2.1 | redis_sentinel | shell(复用 redis) | 🟢 低 | 无 | 🟢 能做 | 1-2h |
| G2.3 | dameng | ssh(复用脚本) | 🟡 中 | ⚠️ 中(试用 30 天) | 🟡 能做(降级:本机无 license 时落盘空 JSON + 注释说明) | 3-4h |
| G2.2 | ibmmq | ssh(需新建脚本 + 复杂 install) | 🔴 高 | 🔴 高(IBMid license) | 🟡 能做(降级:license 不就位时推迟到 Phase 3) | 6-8h 或延后 |
| 副产物 | activemq | ssh | 🟡 中(ready_check 优化) | 无 | 🟡 解锁 | 1-2h |
| 副产物 | mssql | ssh(amd64 only) | 🟡 中(平台差异) | 无 | 🟡 CI-only | 1-2h |

**Phase 2 必做**:G2.1(redis_sentinel)、G2.3(dameng 本机版)
**Phase 2 强烈建议**:activemq / mssql 阻塞解除(改用 amd64 CI 路径,或本机降级方案)
**Phase 2 选做**:ibmmq(依赖 license 获取)

---

## 3. 三个对象的详细执行步骤

### G2.1 redis_sentinel(必做,低风险)

#### 3.1.1 目标

跑通"容器内同时起 redis-server + redis-sentinel"的单节点 sentinel 模式,落盘 `redis_sentinel.json`,验证 `redis_default_discover.sh` 的 sentinel 分支输出 master_name / master_ip / replica_ips 等字段。

#### 3.1.2 实施步骤

1. **写 init 脚本**:`tests/collect_fixtures/init/redis_sentinel_default_discover.sh`
   - 内容:从 catalog env 注入 `REDIS_TARGET_HOST=127.0.0.1` + `REDIS_TARGET_PORTS=6379,26379` + `REDISCLI_AUTH=testpass`,然后执行 `redis_default_discover.sh`
   - 逻辑:实际是个 thin wrapper,不重写采集逻辑

2. **catalog Spec 新增**:`catalog.py` 加 `redis_sentinel` 条目
   - `entry_type = "shell"`(同 redis)
   - `ports = {"6379/tcp": 16380, "26379/tcp": 26380}`(复用 redis 镜像,加 sentinel 端口)
   - `init_script = "redis_sentinel_default_discover.sh"`
   - `collector_kwargs = {"host": "127.0.0.1", "port": 16380, "password": "testpass"}`
   - **关键**:容器启动需双进程:`REDIS_ARGS=--requirepass testpass` + sentinel 配置启动

3. **改造 docker_lifecycle.py**:如果现有 `start_container` 不支持容器启动后注入自定义进程命令(redis sentinel 需要在 redis-server 启动后再启 sentinel),加一个 `container_cmd` override 已存在(Phase 1 已加),直接用
   - 启动容器时 `command=["sh", "-c", "redis-server --requirepass testpass --daemonize yes && redis-sentinel /etc/sentinel.conf"]`
   - sentinel.conf 需在容器内预置:通过 init_script 或 mount

4. **写测试**:`test_catalog.py` 加 redis_sentinel Spec 校验 case + `test_dump.py` 加 redis_sentinel dump 验证(可 mock 容器跑)

5. **真实采集落盘**:`cli.py redis_sentinel` → `redis_sentinel.json`
   - 容器镜像:redis:7-alpine(沿用现有)
   - 验证 JSON 含 `topo_mode == "sentinel"`、`cluster_uuid` 非空、`master` 字段存在

6. **回填测试结果**:本节「测试结果」字段

#### 3.1.3 已知风险与缓解

| 风险 | 缓解 |
|---|---|
| sentinel 启动顺序敏感(必须先 redis-server) | init_script 里 `sleep 2` 后再启 sentinel |
| redis_default_discover.sh 已存在 600 行,改动风险大 | **不修改**它,只在 catalog 层注入 env vars 触发 sentinel 分支 |
| arm64 macOS 上 redis 镜像无兼容问题(redis 是纯 Go-less) | 无 |

#### 3.1.4 验收

- [ ] `pytest tests/collect_fixtures/test_catalog.py tests/collect_fixtures/test_dump.py -v` 全绿(45 → 预计 47-49 passed)
- [ ] `validate()` 在 12 个 MODEL_SPECS 上返回 0 错误
- [ ] `tests/fixtures/collect/redis_sentinel.json` 落盘,含 `topo_mode=sentinel` 字段
- [ ] pytest 全跑 `pytest tests/collect_fixtures/ -v` 49+ passed,无回归

---

### G2.3 dameng(必做,中风险)

#### 3.3.1 目标

复用现有 `plugins/inputs/dameng/dameng_default_discover.sh`,在 ubuntu:22.04 VM + apt 装 dm8 + license 注入,跑一次真实采集,落盘 `dameng.json`。

#### 3.3.2 实施步骤

1. **license 获取前置**(用户任务):
   - 用户在达梦官网下载试用 license(`.dmhk` 文件)
   - 放到 `tests/collect_fixtures/init/dameng_license.dmhk`(仅本地,不入库)
   - 用 base64 嵌入 `init/dameng_default_discover.sh`(已存在的业务脚本)+ Spec 的 `install_commands` 注入容器

2. **如果 license 不可得**(降级路径):
   - 跳过真实采集,只做"假启动 + 落盘空 JSON + 注释说明"
   - 注释清楚"license 缺失,需用户手动跑"
   - catalog Spec 仍正常注册,validate() 通过

3. **catalog Spec 新增**:`catalog.py` 加 `dameng` 条目
   - `entry_type = "ssh"`(ubuntu VM + 装 dm8)
   - `ports = {"22/tcp": 12232, "5236/tcp": 15236}`(DM 默认端口)
   - `init_script = "dameng_default_discover.sh"`(从 `plugins/inputs/dameng/` 复制到 `tests/collect_fixtures/init/`)
   - `install_commands = (apt-get install dm8 + license 注入)`
   - `start_commands = (/opt/dmdbms/bin/dmserver ...)`
   - `ready_check = (disql sysdba/<password> -e "SELECT 1" exit_code==0)`

4. **写测试**:catalog 校验 + dump 校验(may skip if 容器跑不起来)

5. **真实采集落盘**(license 就位时):`cli.py dameng` → `dameng.json`

6. **回填测试结果**:本节「测试结果」字段

#### 3.3.3 已知风险与缓解

| 风险 | 缓解 |
|---|---|
| 达梦 docker 镜像不在 daocloud | 用户手动 `docker pull dameng/dm8:dmd8_v2.0.1` 验证可达;失败时 Spec 注释标"待用户拉镜像" |
| license 必须,试用 30 天过期 | license 文件不入库;Spec 启动时若检测到 license 缺失,落盘带 `"license_status": "missing"` 的 JSON 并标注 TODO |
| `dmPython` 适配复杂 | **不走 python 入口**,走 ssh 入口 + 复用已有 `dameng_default_discover.sh` |

#### 3.3.4 验收

- [ ] 镜像可达验证通过(或注释说明)
- [ ] license 注入成功(或降级路径文档化)
- [ ] `pytest` 全绿(无回归)
- [ ] `tests/fixtures/collect/dameng.json` 落盘(若 license 就位)或带 TODO 的空 JSON

---

### G2.2 ibmmq(选做,高风险)

#### 3.2.1 前置条件(用户拍板)

**选项 A**:用户能拿到 IBM MQ 9.x 试用 license(需 IBMid 注册) → 实施 G2.2 完整版
**选项 B**:用户暂不拿 license → G2.2 推迟到 Phase 3,本 Phase 只登记 catalog 占位 + TODO 注释

#### 3.2.2 选项 A 实施步骤(license 就位时)

1. **新建 collector 脚本**:`tests/collect_fixtures/init/ibmmq_default_discover.sh`(仿 `dameng_default_discover.sh` 风格)
   - 扫 `dspmq` 输出 → 提取 qmgr_name / port / version
   - 扫 `ps` 找 `runmqlsr` 进程 → 提取 listener 信息
   - 输出 JSON:inst_name / ip_addr / qmgr_name / port / version / install_path

2. **catalog Spec 新增**:`catalog.py` 加 `ibmmq` 条目
   - `entry_type = "ssh"`
   - `ports = {"22/tcp": 12231, 1414/tcp: 11414, 9443/tcp": 19443}`
   - `init_script = "ibmmq_default_discover.sh"`
   - `install_commands = (download MQ tar.gz + mqlicense.sh -accept + rpm -ivh)`
   - `start_commands = (runmqsc <create_qm> + strmqm <qm>)`
   - `ready_check = (runmqsc ... DISPLAY CHSTATUS exit_code==0)`

3. **license 嵌入**:tar.gz 内含 license zip;**不提交**,在容器内 wget + accept

4. **写测试 + 真实采集 + 落盘**:`ibmmq.json`

#### 3.2.3 选项 B(catalog 占位 + TODO)

1. catalog 加 `ibmmq` 条目,`start_commands` 故意 `exit 1`(同 activemq/mssql 模式)
2. 加注释 "等待 license 就位,见 §G2.2 选项 B 决策"
3. 不落盘 JSON

#### 3.2.4 验收

- 选项 A:同 dameng
- 选项 B:catalog validate 通过 + 阻塞明确标注

---

## 4. 单对象执行模板(继承 v2 + Phase 1)

> 每个对象实现 + 测试时按此模板组织。

### 4.1 文件清单(每个对象)

| 文件 | 操作 | 说明 |
|---|---|---|
| `tests/collect_fixtures/init/<model>_default_discover.sh` | 新建或复制 | init 脚本(ssh/shell 入口用) |
| `tests/collect_fixtures/catalog.py` | 修改 | 加 Spec 条目 |
| `tests/collect_fixtures/test_catalog.py` | 修改 | 加 Spec 校验 case |
| `tests/collect_fixtures/test_dump.py` | 修改(maybe) | 加 dump 验证(may skip if mock) |
| `agents/stargazer/tests/fixtures/collect/<model_id>.json` | 新建(落盘) | 真实采集结果 |
| `docs/superpowers/plans/2026-07-06-cmdb-collect-v3-roadmap.md` | 修改 | 回填「测试结果」字段 |
| `agents/stargazer/plugins/inputs/<model_id>/` | **不动**(复用已有脚本) | 生产链路隔离 |

### 4.2 端口分配(避免 catalog validate 冲突)

| 对象 | ssh/22 | 业务端口 |
|---|---|---|
| nginx(已有) | 12222 | 18000 |
| mongodb(已有) | 12223 | 17017 |
| rabbitmq(已有) | 12224 | 5673, 15672 |
| tomcat(已有) | 12225 | 18080 |
| elasticsearch(已有) | 12228 | 19200 |
| kafka(已有) | 12229 | 19092 |
| activemq(已有) | 12230 | 31616, 18161 |
| mssql(已有) | 14330 | 14331 |
| **redis_sentinel** | n/a(shell) | **16380, 26380** |
| **dameng** | **12232** | **15236** |
| **ibmmq** | **12231** | **11414, 19443** |

### 4.3 Spec dataclass 字段使用约定(继承 Phase 1)

- `entry_type = "ssh"`:必填 `install_commands` / `start_commands` / `ready_check` / `vm_ssh_password`
- `entry_type = "shell"`:必填 `init_script`(.sh 后缀)
- `container_user` / `container_cmd`:仅当官方镜像 USER 不是 root / ENTRYPOINT 不可用时用(redis / mysql 不用,mssql 用)
- 端口必须 `数字/tcp` 格式(Phase 1 Gap-4 #6 已校验)

---

## 5. 执行顺序与时间盒

> **强建议顺序**:**G2.1 → G2.3 → G2.2 → 副产物**;每个对象独立 commit。

| 顺序 | 对象 | 估时 | 阻塞风险 |
|---|---|---|---|
| 1 | G2.1 redis_sentinel | 1-2h | 🟢 低(复用 redis 脚本) |
| 2 | G2.3 dameng | 3-4h(若 license 就位) | 🟡 中(license 决策) |
| 3 | G2.2 ibmmq | 6-8h 或 0.5h(选 B) | 🔴 高(license + 复杂 install) |
| 4 | 副产物 activemq 优化 | 1-2h | 🟡 ready_check 改造 |
| 5 | 副产物 mssql amd64 CI 化 | 1-2h | 🟡 CI 配置 |

**总时间盒**:Phase 2 完整做 ≈ 12-18h(选 A)或 6-8h(选 B)

---

## 6. Phase 1 残留处理(顺手做)

### 6.1 G1.3 activemq 阻塞解除

**现状**(roadmap §3.3):apt 装的 activemq 在容器里 java 进程变 zombie,端口未监听;官方 `apache/activemq-classic:5.18.3` 镜像 cli 流程 ready_check 失败。

**解锁方案**(roadmap 已建议):
1. 改 ready_check 为**双重检测**:`curl -fsS http://localhost:8161/admin/ || ss -tln | grep -q :61616`(端口 + web console 任一就绪即可)
2. 容器内启动后用 `nohup` + `setsid` 让 java 进程脱离 cli 进程的进程组(避免 cli exec 后 java 变 zombie)

**fallback**(若双重检测仍不通):把 activemq 移到 amd64 CI runner 跑(同 mssql 路径)。

### 6.2 G1.4 mssql 阻塞解除

**现状**:mssql 官方镜像仅 linux/amd64,arm64 Mac 上 Rosetta 模拟启动极慢(5+ 分钟)。

**解锁方案**:
1. **首选**:在 `.github/workflows/cmdb-collect-v3.yml` 加 job,ubuntu-22.04 runner 上跑 mssql 真实采集,artifact 上传 `mssql.json`
2. **fallback**:本机跳过 mssql,catalog Spec 保留 `start_commands = exit 1` 标记阻塞,等 CI 就位后跑

### 6.3 副产物优先级

- activemq 优先(本机能解决,无需 CI)
- mssql 推到 CI(本机 arm64 硬约束)

---

## 7. 验收(Phase 2 整体)

### 7.1 必达

- [ ] **新增落盘 JSON**:3 个(`redis_sentinel.json` / `dameng.json` / `ibmmq.json`(可选))
- [ ] **catalog 增条**:`redis_sentinel` / `dameng` / `ibmmq`(可选),MODEL_SPECS 从 11 → 13(14)
- [ ] **pytest 全绿**:`pytest tests/collect_fixtures/ -v` 49+ passed(从 Phase 1 的 45 增)
- [ ] **validate() 通过**:`from tests.collect_fixtures.catalog import validate; print(validate())` 返回 `[]`
- [ ] **roadmap 回填**:G2.1/G2.2/G2.3 三节「测试结果」字段填完

### 7.2 加分

- [ ] **Phase 1 残留解锁**:activemq 本机落盘 + mssql CI 化(任一即可)
- [ ] **fixture 总数**:从 9 → 12(或 13 含 mssql)
- [ ] **测试覆盖**:从 45 → 50+ passed

---

## 8. 不在 Phase 2 范围(明确)

| 项 | 范围 |
|---|---|
| Phase 3 商业版扩展(minio / zookeeper / consul / etcd / memcached / openresty / haproxy / 7 个中优先级商业版) | ⚪ Phase 3 排期,本次不动 |
| protocol 类型(nacos / oceanbase / highgo / ...)| ⚪ Phase 3+,需新增 python 入口分支 |
| 暂缓对象(iis / hbase / spark / hdfs / yarn / storm / cics) | ⚪ 架构 / 集群复杂,持续暂缓 |
| 生产链路改动(`plugins/inputs/` 已有商业版脚本、`server/apps/cmdb/collection/`、stargazer core) | 🔴 红线,Phase 2 不动 |
| 自定义 fixture 字段(非 spec §4.2 定义的 6 字段) | 🔴 红线 |

---

## 9. 测试结果回填区(执行后由 Agent 手动回填)

### G2.1 redis_sentinel 测试结果

✅ **2026-07-07 完成**(worktree `feature-cmdb-collect-v3-gap4-validate`,未 commit)

- **catalog 改动**:`agents/stargazer/tests/collect_fixtures/catalog.py` 加 `redis_sentinel` Spec(11 → 12 对象)
- **新增脚本**:`agents/stargazer/tests/collect_fixtures/init/redis_sentinel_default_discover.sh`(600 行,镜像自 `plugins/inputs/redis/redis_default_discover.sh`)
- **run_collector 改造**:
  - `_build_shell_env` 支持 `collector_kwargs.ports` list → 注入 `REDIS_TARGET_PORTS=逗号分隔`
  - `_parse_shell_stdout` 支持多 JSON 行(原版只返第一个,导致 sentinel port 被吞)
- **container_cmd 改造**:单容器内同跑 redis-server(后台) + sentinel.conf 写盘 + redis-sentinel(前台) + keepalive
- **fixture 产物**:`tests/fixtures/collect/redis_sentinel.json`(2 个 instance:master + sentinel,共享 cluster_uuid)
- **测试新增**:9 个 G2.1 case(test_catalog.py 47 → 54,+7) + 3 个 `_build_shell_env` 改造 case
- **总测试**:`pytest tests/collect_fixtures/ -v` **91 passed, 0 failed**(Phase 1 45 → Phase 2 G2.1 91)

**关键 debug 经验(已写入 init 脚本头部注释)**:
1. `set -u` + 直接 `$X` 展开 → 脚本 fail,改 `${X:-fallback}`
2. sentinel 没设密码 + `REDISCLI_AUTH` 触发 redis-cli 发 AUTH → "AUTH failed" 混入 stdout,采集失败。**修复**:container_cmd 里给 sentinel 也加 `requirepass` + `sentinel auth-pass`
3. `discover_ports_from_process` 默认开启,只匹配 `redis-server` 命令行不匹配 `redis-sentinel`,把 sentinel 端口吞掉。**修复**:`REDIS_DISCOVER_FROM_PROCESS=no`
4. alpine busybox sh 的 `done | sort -nu` 在命令替换下丢行(parse_ports 只返第一行)。**修复**:重写 parse_ports 用 `for part in $spec`(本副本改,不动主脚本)
5. SDK 7.x 的 exec_run 看不到 env vars 是否生效,DEBUG 行被 `_parse_shell_stdout` 当噪音丢,需写 `/tmp/debug.log` 文件验证

### G2.3 dameng 测试结果

🟡 **2026-07-07 降级路径完成**(license 不可达)

- **catalog 改动**:加 `dameng` Spec(12 → 13 对象),ssh 入口,install_commands 故意 exit 1
- **新增脚本**:`init/dameng_default_discover.sh`(复制自 `plugins/inputs/dameng/dameng_default_discover.sh`,镜像副本)
- **fixture 产物**:`tests/fixtures/collect/dameng.json`(占位 JSON,license_status: missing,含 next_steps 和 references)
- **测试新增**:7 个 G2.3 case(test_catalog.py 54 → 60,+7 含 LICENSE BLOCK MARKER 等)

**降级决策**:
- 真实情况:`xuxuclassmate/dameng:latest` 镜像可达但 arm64 Mac 需 Rosetta 模拟 amd64,镜像精简缺 sshd/net-tools,apt update 老源慢
- license 不可达(用户决策)
- fixture 工具不引入新风险(不连非官方生产镜像)

**解锁路径**:用户提供达梦官方 license + 在 amd64 CI runner 跑(类似 mssql 模式,见 §6.2)。

### G2.2 ibmmq 测试结果

🟡 **2026-07-07 选 B 完成**(license 不可达,catalog 占位 + TODO)

- **catalog 改动**:加 `ibmmq` Spec(13 → 14 对象),ssh 入口,install_commands 故意 exit 1
- **新增脚本**:`init/ibmmq_default_discover.sh`(占位脚本,echo placeholder JSON)
- **fixture 产物**:`tests/fixtures/collect/ibmmq.json`(占位 JSON,含 phase2_decision 和完整 next_steps)
- **测试新增**:6 个 G2.2 case(test_catalog.py 60 → 66,+6)

**roadmap 偏差已修正**:roadmap §3.4 G2.2 假设 `enterprise/plugins/inputs/ibmmq/` 已实现,实际验证 `enterprise/` 目录为空。需要新建采集脚本 + 复杂 install(rpm/tar.gz/license)。

### Phase 1 残留测试结果

#### G1.3 activemq 测试结果

✅ **2026-07-07 解锁完成**(Phase 2 副产物)

- **catalog 改动**:换 `apache/activemq-classic:5.18.3` 官方镜像(原 ubuntu 22.04 + apt 装包失败)
- **container_cmd 改造**:`setsid /opt/apache-activemq/bin/activemq start`(用 setsid 避免 cli 进程组僵尸)
- **ready_check 改造**:双重检测 `curl -fsS -u admin:admin http://127.0.0.1:8161/admin/ -o /dev/null || ss -tln | grep -q ':61616 '`
- **container_user**: `0:0`(root,装 sshd 必需)
- **fixture 产物**:`tests/fixtures/collect/activemq.json`(13 字段,port=61616,listening_ports=1883,5672,61613,61616,8161)

#### G1.4 mssql 测试结果

🟡 **2026-07-07 amd64 CI workflow 完成**

- **新增 workflow**:`.github/workflows/cmdb-collect-v3-mssql.yml`
- **触发方式**:`workflow_dispatch`(手动,因 mssql 镜像大、跑得慢)
- **runner**:`ubuntu-22.04`(amd64,mssql 镜像架构匹配)
- **步骤**:checkout → setup python 3.12 → install uv → uv venv + pip install -e → 跑 cli mssql → upload artifact
- **artifact**:`mssql-fixture-json`(30 天 retention)
- **catalog Spec 保持阻塞**(arm64 Mac 上仍 exit 1,标记本地无法跑)

**后续**:用户在 amd64 CI 上手动跑通后,落盘 mssql.json 可 PR 进 main。

---

## 10. 决策清单(等用户拍板)

> 启动 Phase 2 实施前需要用户确认的 5 个问题。

| # | 问题 | 默认方案 | 备选 |
|---|---|---|---|
| 1 | G2.1 redis_sentinel 是否按"复用 redis_default_discover.sh + 容器双进程"方案做? | ✅ 是 | 新建专用 redis_sentinel 脚本(成本高,不推荐) |
| 2 | G2.3 dameng 的达梦 license 你能否拿到? | ✅ 能拿到试用 license | ❌ 拿不到 → 走降级路径(空 JSON + TODO) |
| 3 | G2.2 ibmmq 的 IBM MQ license 你能否拿到? | 🟡 选 B(catalog 占位) | ✅ 选 A(实施完整版,license 自备) |
| 4 | activemq ready_check 改造在本机做? | ✅ 是(改双重检测) | 推到 CI(不推荐,本机应可解) |
| 5 | mssql 走 GitHub Actions amd64 runner? | ✅ 是(配 workflow) | 本机跳过,等 CI 自然就位 |

---

## 11. 完成后产物清单

> Phase 2 整体完成后(无论决策结果)交付:

- **代码改动**:`agents/stargazer/tests/collect_fixtures/catalog.py` / `init/*.sh` / `test_catalog.py`(增量,不动 catalog 主体)
- **落盘 fixture**:`tests/fixtures/collect/{redis_sentinel,dameng,ibmmq}.json`(任一可空)
- **roadmap 更新**:`docs/superpowers/plans/2026-07-06-cmdb-collect-v3-roadmap.md` Phase 2 节「测试结果」回填
- **本计划收口**:本文档末尾追加「Phase 2 执行报告」段落
- **worktree**:等你 review,决定 commit + 合并 / 删 / 改

---

## 附录 A:roadmap §3.4 原始设计对照表

> 本表给"roadmap 写了什么 vs Phase 2 plan 改成什么"的快速对照,便于你 review 时看差异。

| 对象 | roadmap 设计 | Phase 2 plan 设计 | 差异原因 |
|---|---|---|---|
| redis_sentinel entry_type | shell | shell | ✅ 一致 |
| redis_sentinel init_script | 新建 redis_sentinel_default_discover.sh | **复用** redis_default_discover.sh | redis_default_discover.sh 600 行已内置 sentinel 分支 |
| ibmmq 脚本 | 假设 enterprise overlay 已有 | **新建** enterprise 目录 + 脚本 | enterprise/ 目录实际是空的,roadmap 假设不成立 |
| dameng 脚本 | 假设 enterprise overlay 已有 | **复用** plugins/inputs/dameng/dameng_default_discover.sh | 脚本已在 stargazer 主仓,不在 enterprise overlay |
| dameng image | dm8:latest | dm8:dmd8_v2.0.1(待 verify) | roadmap 标签不精确,Phase 2 启动时 docker search 验证 |
| ibmmq license | "开发者免费版可下载" | **用户拍板选 A/B** | license 协议需用户确认 |
| dameng license | (未明确) | 同 ibmmq | 同上 |
| 端口分配 | 未明确 | §4.2 表格化 | 避免 catalog validate 冲突 |
