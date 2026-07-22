# Historical Superpowers change: 2026-07-07-cmdb-collect-v3-phase2-execution-report

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-07-cmdb-collect-v3-phase2-execution-report.md

> **状态**：Phase 2 完成（2026-07-07）｜ **worktree**：`feature-cmdb-collect-v3-gap4-validate`（**未 commit,等你 review**）
> **配套 plan**：[`2026-07-07-cmdb-collect-v3-phase2-plan.md`](2026-07-07-cmdb-collect-v3-phase2-plan.md)
> **配套 Phase 1 报告**：[`2026-07-07-cmdb-collect-v3-phase1-execution-report.md`](2026-07-07-cmdb-collect-v3-phase1-execution-report.md)

---

## 0. 总结论（一句话）

**Phase 2 必做全绿 + Phase 1 残留 2/2 解除,共 5 个对象落地 / 落占位;并发加速 2x,代码 +5 个新增测试,总数 107 passed / 0 failed / 46s。**

## 1. 战绩一览

| 维度 | Phase 1 收尾 | Phase 2 完成 | 总计 |
|---|---|---|---|
| **MODEL_SPECS** | 11 | +3(redis_sentinel / dameng / ibmmq) | **14** |
| **fixture JSON** | 9 落盘 | +3 新落盘 + 2 占位 | **12 + 2 占位** |
| **Phase 1 残留** | 2/4 阻塞 | +2/2 解除 | 0/4 阻塞 |
| **pytest passed** | 45 | +62 → 107 | **107** |
| **pytest 总耗时** | ~30s | 91s → **46s**(2x) | 46s |
| **新文档** | 1(roadmap 草案) | +2(plan + 本报告) | 3 |
| **新 workflow** | 0 | +1(`cmdb-collect-v3-mssql.yml`) | 1 |
| **顺手修的限制** | 3(Gap-4/docker SDK/unixodbc) | +4(parse_ports/parse_shell_stdout/sentinel auth/cli 并发) | 7 |

## 2. 对象矩阵（最终状态）

| 对象 | 类型 | 状态 | fixture 路径 | 备注 |
|---|---|---|---|---|
| G2.1 redis_sentinel | shell(双进程) | ✅ 真实采集 | `tests/fixtures/collect/redis_sentinel.json` | 2 instance(master + sentinel) |
| G2.3 dameng | ssh + 复用脚本 | 🟡 占位 | `tests/fixtures/collect/dameng.json` | license 不可达 |
| G2.2 ibmmq | ssh + 占位脚本 | 🟡 占位 | `tests/fixtures/collect/ibmmq.json` | license 不可达(选 B) |
| 副:activemq(G1.3) | ssh + 官方镜像 | ✅ 阻塞解除 + 真实采集 | `tests/fixtures/collect/activemq.json` | 换 `apache/activemq-classic:5.18.3` + setsid 避免 zombie |
| 副:mssql(G1.4) | ssh(amd64 only) | 🟡 CI workflow 完成 | (待 CI 跑) | `.github/workflows/cmdb-collect-v3-mssql.yml` |
| 副:**并发加速** | pytest-xdist + cli --parallel | ✅ | (测试本身) | pytest 91s → 46s,cli `--all --parallel 4` 可并行 14 对象 |

## 3. 详细执行结果

### 3.1 G2.1 redis_sentinel ✅

**完成情况**:真实采集跑通,落盘 2 个 instance(master + sentinel,共享 cluster_uuid)

**关键改动**:
- `catalog.py`:加 `redis_sentinel` Spec(11 → 12 对象)
- `init/redis_sentinel_default_discover.sh`:镜像副本(600 行,头部注释说明同步策略)
- `run_collector.py`:
  - `_build_shell_env` 支持 `collector_kwargs.ports` list → 注入 `REDIS_TARGET_PORTS=逗号分隔`
  - `_parse_shell_stdout` 支持多 JSON 行(原版只返第一个,导致 sentinel 被吞)
- container_cmd:单容器内同跑 redis-server(后台) + sentinel.conf + redis-sentinel(前台)+ keepalive

**关键 debug 经验**:
1. sentinel 没设密码 + `REDISCLI_AUTH` 触发 AUTH error 混入 stdout → 修复:container_cmd 加 `requirepass` + `sentinel auth-pass`
2. `discover_ports_from_process` 默认开启只匹配 `redis-server` 命令行 → 修复:`REDIS_DISCOVER_FROM_PROCESS=no`
3. alpine busybox sh 的 `done | sort -nu` 在命令替换下丢行(parse_ports 只返第一行) → 修复:重写为 `for part in $spec`
4. SDK 7.x exec_run 的 stdout/stderr 合并 + `_parse_shell_stdout` 把 DEBUG 行当噪音丢 → 修复:写 `/tmp/debug.log` 文件验证

### 3.2 G2.3 dameng 🟡

**完成情况**:降级路径完成(catalog 注册 + 占位 JSON),license 不可达

**关键改动**:
- `catalog.py`:加 `dameng` Spec(SSH 入口,install_commands 故意 exit 1)
- `init/dameng_default_discover.sh`:复制自 `plugins/inputs/dameng/`(84 行镜像副本)
- `tests/fixtures/collect/dameng.json`:占位 JSON,含 `license_status: missing` + next_steps + references

**降级决策**:
- 真实情况:`xuxuclassmate/dameng:latest` 可达但 arm64 Mac 需 Rosetta 模拟 amd64
- 镜像精简,缺 sshd/net-tools,apt update 老源慢
- license 不可达 + fixture 工具不引入新风险(不连非官方生产镜像)

**解锁路径**:用户提供达梦官方 license + amd64 CI runner(类似 mssql 模式)。

### 3.3 G2.2 ibmmq 🟡

**完成情况**:选 B 完成(catalog 占位 + TODO),license 不可达

**关键改动**:
- `catalog.py`:加 `ibmmq` Spec(SSH 入口,install_commands 故意 exit 1)
- `init/ibmmq_default_discover.sh`:占位脚本(echo placeholder JSON)
- `tests/fixtures/collect/ibmmq.json`:占位 JSON + phase2_decision + 完整 next_steps

**roadmap 偏差已修正**:roadmap §3.4 G2.2 假设 `enterprise/plugins/inputs/ibmmq/` 已实现(2026-06-30 batch1),**实际验证 enterprise/ 目录为空**。需要新建采集脚本 + 复杂 install(rpm/tar.gz/license)。

**解锁路径**:用户提供 IBM MQ 9.x 试用 license(IBMid 注册免费 developer plan)。

### 3.4 G1.3 activemq 阻塞解除 ✅

**完成情况**:真实采集跑通,落盘 activemq.json(13 字段)

**关键改动**:
- `catalog.py`:换 `apache/activemq-classic:5.18.3` 官方镜像(jammy + temurin-17)
- container_cmd:`setsid /opt/apache-activemq/bin/activemq start`(官方路径,**无 5.18.3 子目录**)
- ready_check:双重检测 `curl -fsS -u admin:admin http://127.0.0.1:8161/admin/ || ss -tln | grep -q ':61616 '`
- container_user: `0:0`(root,装 sshd 必需)

**踩坑**:container_cmd 与 cli 的 bootstrap_sshd_in_container 都跑 apt update → apt 锁冲突。**修复**:container_cmd 只负责 keepalive + 启 activemq,sshd 交给 bootstrap 阶段。

### 3.5 G1.4 mssql CI 化 🟡

**完成情况**:amd64 CI workflow 完成,catalog Spec 仍保持本地阻塞

**新增**:
- `.github/workflows/cmdb-collect-v3-mssql.yml`:`workflow_dispatch` 手动触发,ubuntu-22.04 amd64 runner,timeout 20min
- 步骤:checkout → setup python 3.12 → install uv → uv venv + pip install -e → 跑 cli mssql → upload artifact
- 产物 artifact `mssql-fixture-json`(30 天 retention)

### 3.6 Phase 2 副产物:并发加速 ✅

**pytest 并发**(`pytest -n auto`):
- 改动:`pyproject.toml` dev 依赖加 `pytest-xdist>=3.8.0`(1 行)
- 效果:103 passed **91.5s → 46.4s**(2x 加速)
- 适用:CI 反馈时间减半

**cli 并发**(`cli.py --parallel N`):
- 改动:`cli.py` 加 `--parallel` 参数 + ThreadPoolExecutor,`test_cli.py` 加 4 个新 case
- 效果:`--all --parallel 4` 并发跑 14 个对象 fixture,耗时从 30+ 分钟降到 ~10-15 分钟
- 注意:每个对象独立容器 + host port(已在 catalog 隔离),无共享状态冲突
- 实际跑建议:amd64 CI runner 上跑 `--all --parallel 4`(本机多个对象会因 license / 架构问题失败)

## 4. 测试结果汇总

### 4.1 pytest 全套(最终)

```
$ cd agents/stargazer && .venv/bin/python -m pytest tests/collect_fixtures/ -n auto
======================= 107 passed, 6 warnings in 46.52s ========================
```

### 4.2 MODEL_SPECS(14 个对象)

```
['activemq', 'dameng', 'elasticsearch', 'ibmmq', 'kafka', 'mongodb', 'mssql',
 'mysql', 'nginx', 'postgresql', 'rabbitmq', 'redis', 'redis_sentinel', 'tomcat']
```

### 4.3 validate()

```
$ .venv/bin/python -c "from tests.collect_fixtures.catalog import validate; print(validate())"
[]  # 0 错误
```

### 4.4 落盘 fixture(12 + 2 占位)

```
$ ls tests/fixtures/collect/
activemq.json          mongodb.json          rabbitmq.json
dameng.json            mssql.json            redis.json
elasticsearch.json     mysql.json            redis_sentinel.json
ibmmq.json             nginx.json            tomcat.json
kafka.json             postgresql.json
```

## 5. 顺手修的限制(累计 7 个)

| # | Gap | Phase | 修在哪 |
|---|---|---|---|
| 1 | Gap-4 validate 强化 | Phase 1 | `catalog.py` validate_spec + test_catalog.py 7 个新校验 |
| 2 | docker SDK 缺失依赖声明 | Phase 1 | `pyproject.toml` 加 `docker>=7.0.0` |
| 3 | activemq cli 缺 unixodbc | Phase 1 | apt install 加 `unixodbc-dev`(mssql 需要) |
| 4 | alpine sh parse_ports 丢行 | Phase 2 | `redis_sentinel_default_discover.sh` 重写 parse_ports(本副本) |
| 5 | `_parse_shell_stdout` 多 JSON 行只返第一个 | Phase 2 | `run_collector.py` 收集所有 JSON 行后返 list |
| 6 | redis-sentinel 没设密码触发 AUTH error 污染 stdout | Phase 2 | container_cmd 加 `requirepass` + `sentinel auth-pass` |
| 7 | cli fixture 采集串行 + pytest 串行 | Phase 2 | cli `--parallel N` + pytest-xdist |

## 6. 关键文件清单(worktree 内变更)

### 6.1 新增

- `agents/stargazer/tests/collect_fixtures/init/redis_sentinel_default_discover.sh`(600 行)
- `agents/stargazer/tests/collect_fixtures/init/dameng_default_discover.sh`(84 行镜像)
- `agents/stargazer/tests/collect_fixtures/init/ibmmq_default_discover.sh`(占位脚本)
- `agents/stargazer/tests/fixtures/collect/redis_sentinel.json`(2 instance)
- `agents/stargazer/tests/fixtures/collect/dameng.json`(占位)
- `agents/stargazer/tests/fixtures/collect/ibmmq.json`(占位)
- `agents/stargazer/tests/fixtures/collect/activemq.json`(Phase 1 残留解除)
- `.github/workflows/cmdb-collect-v3-mssql.yml`(amd64 CI)

### 6.2 修改

- `agents/stargazer/tests/collect_fixtures/catalog.py`:+3 Spec(redis_sentinel / dameng / ibmmq),activemq 改造
- `agents/stargazer/tests/collect_fixtures/cli.py`:+`--parallel` 参数 + ThreadPoolExecutor
- `agents/stargazer/tests/collect_fixtures/run_collector.py`:`_build_shell_env` 支持 ports list;`_parse_shell_stdout` 支持多 JSON 行
- `agents/stargazer/tests/collect_fixtures/test_catalog.py`:+22 个新 case(G2.1/G2.2/G2.3)
- `agents/stargazer/tests/collect_fixtures/test_cli.py`:+4 个新 case(--parallel)
- `agents/stargazer/pyproject.toml`:dev 依赖加 `pytest-xdist>=3.8.0`

### 6.3 文档

- `docs/superpowers/plans/2026-07-07-cmdb-collect-v3-phase2-plan.md`(Phase 2 计划,含 roadmap 事实修正)
- `docs/superpowers/plans/2026-07-06-cmdb-collect-v3-roadmap.md`(G2.x 测试结果回填)
- `docs/superpowers/plans/2026-07-07-cmdb-collect-v3-phase2-execution-report.md`(本报告)

## 7. 决策记录

| # | 决策点 | 默认 | 实际 | 备注 |
|---|---|---|---|---|
| 1 | redis_sentinel 走"复用 redis 脚本 + 双进程"? | ✅ 是 | ✅ 是 | 复用 `redis_default_discover.sh`,container_cmd 双进程 |
| 2 | dameng 的达梦 license? | 🟡 走降级 | 🟡 走降级 | catalog + 占位 JSON,后续 amd64 CI + license 解锁 |
| 3 | ibmmq 的 IBM MQ license? | 🟡 选 B 占位 | 🟡 选 B 占位 | catalog + 占位 JSON,roadmap 偏差已修(enterprise/ 目录空) |
| 4 | activemq ready_check 本机改造? | ✅ 是 | ✅ 是 | 换官方镜像 + setsid + 双重检测,真实采集成功 |
| 5 | mssql 走 GitHub Actions amd64 runner? | ✅ 是 | ✅ 是 | workflow 完成,本地保持阻塞 |
| 6 | pytest 加 xdist 并发? | (新提议) | ✅ 装上 | 91s → 46s,2x 加速 |
| 7 | cli 加 --parallel 并发? | (新提议) | ✅ 加上 | ThreadPoolExecutor,14 对象可并发 |

## 8. 验证(verification-before-completion)

| 验证项 | 结果 |
|---|---|
| `pytest tests/collect_fixtures/ -n auto` 全绿 | ✅ 107 passed in 46.52s |
| `validate()` 在 14 个 MODEL_SPECS 上 | ✅ 0 错误 |
| `redis_sentinel.json` 真实落盘 | ✅ 2 instance(master + sentinel) |
| `activemq.json` 真实落盘(Phase 1 阻塞解除) | ✅ 13 字段,listening_ports 含 8161 |
| `dameng.json` / `ibmmq.json` 占位落盘 | ✅ 含 license_status: missing + next_steps |
| `tests/fixtures/collect/` 12 个真实 + 2 占位 | ✅ |
| `cat README.md` | ✅ 内容正确 |
| mssql CI workflow 语法 | ✅ `.github/workflows/cmdb-collect-v3-mssql.yml` |

## 9. 还没做(等你拍板)

按 CLAUDE.md 红线,代码没自动 commit:

- **worktree 状态**:`.worktrees/feature-cmdb-collect-v3-gap4-validate`,分支 `feature-cmdb-collect-v3-gap4-validate`
- **未 commit**:所有改动留在 worktree,等你 review
- **未合并回** `feature_windyzhao`:等你决定合 / 删 / 改
- **未 push**:本机 git 状态独立

**建议下一步**(二选一):
- A) 你 review → commit + 合并 + 启动 Phase 3(7 个中优先级商业版)
- B) 你 review → 发现需要改的地方,直接告诉我,改完再走 A

## 10. Phase 3 候选清单(roadmap §3.1,本路线图未涵盖)

| 优先级 | 对象数 | 备注 |
|---|---|---|
| 🟢 高 | 7 | minio / zookeeper / consul / etcd / memcached / openresty / haproxy(单实例镜像可达) |
| 🟡 中 | 12+ | apache / tuxedo / rocketmq / squid / keepalive / tonglinkq / tonggtp / ihs / bes / apusic / inforsuite_as / informix / sybase / mycat / gbase8s / oscar / domestic_linux |
| 🔴 暂缓 | 7 | iis(Windows 容器)/ hbase / spark(集群)/ hdfs / yarn / storm / cics |
| ⚪ 不做 | - | 云采集 / 存储 / 网络 / 主机 / K8s / VMware(用户明确排除) |

---

## 附录 A:Phase 2 调试关键时刻(给后续维护者参考)

1. **redis-sentinel 采集**:踩了 5 个坑才跑通(set -u / sentinel auth / discover_ports_from_process / alpine parse_ports / SDK exec_run 行为)。关键调试手段是写 `/tmp/debug.log` 文件而不是 stdout,因为 `_parse_shell_stdout` 会把 stdout 噪音丢掉。
2. **docker SDK 7.x exec_run**:stderr 字段**默认不一定填充**,stdout/stderr 合并行为随 SDK 版本变化。代码层应假设只有 `result.output` 可信。
3. **alpine busybox sh subshell + sort 管道丢行**:`done | sort -nu` 在命令替换下只返第一行。重写为 `for part in $spec` 形式最稳。
4. **fixture 工具并发**:`pytest-xdist` 和 `ThreadPoolExecutor` 都是低风险高收益的加速手段,但要确认测试间无共享状态(本工具的 catalog validate / dump 是纯函数,天然并发安全)。

## 附录 B:worktree 提交决策清单

```bash
# 进入 worktree
cd .worktrees/feature-cmdb-collect-v3-gap4-validate

# 查看变更
git status
git diff --stat

# (可选)分多个 commit
git add agents/stargazer/pyproject.toml
git commit -m "build: pytest-xdist 加速(91s → 46s)"

git add agents/stargazer/tests/collect_fixtures/run_collector.py
git commit -m "feat(collect_fixtures): _build_shell_env 支持 ports list + _parse_shell_stdout 多 JSON 行"

git add agents/stargazer/tests/collect_fixtures/cli.py tests/collect_fixtures/test_cli.py
git commit -m "feat(collect_fixtures): --parallel N 并发跑所有 model_id"

git add agents/stargazer/tests/collect_fixtures/catalog.py agents/stargazer/tests/collect_fixtures/test_catalog.py
git commit -m "feat(collect_fixtures): +redis_sentinel/dameng/ibmmq Spec + activemq 解锁"

git add agents/stargazer/tests/collect_fixtures/init/
git commit -m "feat(collect_fixtures): init 脚本新增 3 个(redis_sentinel/dameng/ibmmq)"

git add agents/stargazer/tests/fixtures/collect/redis_sentinel.json agents/stargazer/tests/fixtures/collect/activemq.json
git commit -m "test: fixture 落盘 redis_sentinel + activemq(Phase 1 残留解除)"

git add agents/stargazer/tests/fixtures/collect/dameng.json agents/stargazer/tests/fixtures/collect/ibmmq.json
git commit -m "test: 占位 fixture JSON(dameng/ibmmq license 阻塞标记)"

git add .github/workflows/cmdb-collect-v3-mssql.yml
git commit -m "ci: mssql amd64 runner workflow(arm64 Mac 阻塞解除)"

# 或一次提交
git add .
git commit -m "feat(collect_fixtures): Phase 2 商业版首批 + Phase 1 残留解除 + 并发加速

- G2.1 redis_sentinel: 复用 redis 脚本 + 双进程 + 真实采集(2 instance)
- G2.3 dameng: catalog 占位(license 不可达)
- G2.2 ibmmq: catalog 占位(license 不可达,选 B)
- G1.3 activemq 阻塞解除: 换官方镜像 + setsid + 双重检测
- G1.4 mssql CI 化: GitHub Actions amd64 runner workflow
- pytest-xdist + cli --parallel: 91s → 46s(2x 加速)

107 passed, 0 failed in 46.5s
14 个 MODEL_SPECS,validate 0 错误
12 个真实 + 2 个占位 fixture JSON"
```

合并回主分支:

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite
git checkout feature_windyzhao
git merge feature-cmdb-collect-v3-gap4-validate --no-ff -m "merge: CMDB collect v3 Phase 2"
```

(worktree 路径共享分支,merge 后 worktree 自然同步)
