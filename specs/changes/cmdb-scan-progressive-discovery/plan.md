# CMDB 扫描三阶段渐进发现 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans，按任务顺序 TDD 实现。步骤用 `- [ ]`。前端 UI 用 Gemini 3.7 Flash。

**Goal:** 扫描改为网络指纹 → 进程指纹 → 有凭据才复用采集；特征库决定扫什么，任务勾选只录凭据；命中带可信度并回填清单；数据库/中间件进监控走 CMDB→监控同步任务；Stargazer 扫描不占配置采集队列。

**Architecture:** 特征库扩展端口种子并新增进程指纹。Server 触发时把网段 + 指纹快照交给 Stargazer 新入口 `scan_discover`（`WorkloadClass.SCAN` 独立配额）。命中经现有扫描 NATS subject 回填 `ScanHit`。三阶段只对已有采集凭据的命中调用现有 `*_info`。清单出口：写 CI 允许低/中可信；生成采集要凭据；库/中间件推监控改走 `module_link`。

**Tech Stack:** Django ORM、DRF、NATS、Celery、Stargazer collection scheduler、Next.js、Ant Design。

规格：`specs/changes/cmdb-scan-progressive-discovery/spec.md`

---

## File Structure

| 文件 | 职责 |
|---|---|
| `server/apps/cmdb/models/collect_model.py` | `PortFingerprint.enabled`；新建 `ProcessFingerprint` |
| `server/apps/cmdb/services/port_fingerprint.py` | 扩展内置端口；去掉扫描三库白名单 |
| `server/apps/cmdb/services/process_fingerprint.py` | 内置进程规则同步；本轮启用列表 |
| `server/apps/cmdb/management/commands/init_port_fingerprint.py` | 扩种子 |
| `server/apps/cmdb/management/commands/init_process_fingerprint.py` | 新建；`batch_init` 调用 |
| `server/apps/cmdb/views/port_fingerprint.py` + process 对应 ViewSet | CRUD、停用、禁删内置 |
| `server/apps/cmdb/models/scan_model.py` | `ScanHit.confidence` / `evidence` |
| `server/apps/cmdb/services/scan_fingerprint_snapshot.py` | 触发时冻结端口+进程指纹 |
| `server/apps/cmdb/services/scan_trigger_service.py` | 改走 `scan_discover`；勾选不再拆全量 JOB 枪 |
| `server/apps/cmdb/services/scan_credential_result_service.py` | 无 `credential_id` 的发现事件可写命中 |
| `server/apps/cmdb/services/scan_write_ci_service.py` | 低/中可信允许用户写入 |
| `server/apps/cmdb/services/scan_collect_generate.py` | 无采集凭据拒绝 |
| `server/apps/cmdb/services/scan_push_monitor.py` | 库/中间件改走 `module_link` |
| `agents/stargazer/core/collection/enums.py` | `WorkloadClass.SCAN` |
| `agents/stargazer/api/collect.py` | `GET/POST /collect/scan_discover` |
| `agents/stargazer/core/scan/` | 调度、TCP 探测、进程匹配、阶段推进 |
| `web/.../featureLibrary/` | 第三 Tab 进程指纹 |
| `web/.../scan/` | 勾选=凭据文案、清单可信度 |

验证（Postgres，不要 sqlite `--reuse-db`）：

```bash
cd server && SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest \
  apps/cmdb/tests/test_port_fingerprint.py \
  apps/cmdb/tests/test_process_fingerprint.py \
  apps/cmdb/tests/test_scan_trigger_service.py \
  apps/cmdb/tests/test_scan_credential_event_nats.py \
  apps/cmdb/tests/test_scan_write_ci_service.py \
  apps/cmdb/tests/test_scan_collect_generate.py \
  apps/cmdb/tests/test_scan_push_monitor.py --no-cov
cd ../agents/stargazer && python -m pytest tests/test_scan_scheduler.py tests/test_scan_discover_http.py -q
cd ../../web && pnpm type-check
```

---

### Task 1: 端口指纹扩种子 + enabled + 取消三库白名单

**Files:**
- Modify: `server/apps/cmdb/models/collect_model.py`（`enabled` 默认 True）
- Modify: `server/apps/cmdb/services/port_fingerprint.py`
- Modify: `server/apps/cmdb/serializers/port_fingerprint_serializer.py`、`views/port_fingerprint.py`
- Modify: `server/apps/cmdb/management/commands/init_port_fingerprint.py`
- Test: `server/apps/cmdb/tests/test_port_fingerprint.py`

- [ ] **Step 1: 失败测试**

`ports_for_scan_type("nginx")` 在同步内置后返回 `{80, 443}`；`ports_for_scan_type("mysql")` 仍含 3306。`enabled=False` 的用户行不出现在 `enabled_port_fingerprints()`。内置行不可删除。用户占用同一 `(port, target_type)` 时 `sync` 跳过。

- [ ] **Step 2: 实现**

`BUILTIN_PORT_FINGERPRINTS` 换成规格表（mysql/pg/mssql/oracle/influx/redis/mongo/es + 中间件监听口）。`ports_for_scan_type` 不再判断 `SCAN_DATABASE_TYPES`。新增 `enabled_port_fingerprints()` 返回 `[{port, target_type, protocol}]`，过滤 `enabled=True`。PATCH 可改用户行 `enabled`；内置允许停用、禁止删除。

- [ ] **Step 3: 跑测**

`uv run pytest apps/cmdb/tests/test_port_fingerprint.py --no-cov`

---

### Task 2: 进程指纹模型、种子、API

**Files:**
- Create: model `ProcessFingerprint`、migration、`services/process_fingerprint.py`、`init_process_fingerprint.py`、ViewSet/serializer/filter
- Modify: `server/apps/cmdb/urls.py`、`batch_init.py` 增加 `call_command("init_process_fingerprint")`
- Test: `server/apps/cmdb/tests/test_process_fingerprint.py`

- [ ] **Step 1: 失败测试**

同步后存在 `target_type=mysql` 且 `linux_process` 能匹配 `mysqld` 的内置行。不能删内置。用户同键跳过。`enabled_process_fingerprints()` 不含停用行。`batch_init.py` 源码含 `init_process_fingerprint`。

- [ ] **Step 2: 实现**

字段：`target_type`、`linux_process`、`windows_image`（blank）、`built_in`、`enabled`。唯一 `(target_type, linux_process, windows_image)`。权限 `soid_library-View/Add/Delete`。内置规则按规格：库/缓存/中间件 Linux 正则；能确定的 Windows 映像一并写入。`target_type` 校验：必须是可网段发现的采集模型（与端口指纹下拉同一名单），拒绝 `aliyun_account` / `k8s_cluster`。

- [ ] **Step 3: 跑测**

`uv run pytest apps/cmdb/tests/test_process_fingerprint.py --no-cov`

---

### Task 3: 特征库第三 Tab（Gemini）

**Files:**
- Modify: `web/.../featureLibrary/layout.tsx` 增加进程 Tab
- Create: `web/.../featureLibrary/process/page.tsx`（对齐端口页：表格、新增、删除、内置标记、停用）
- Create: `web/src/app/cmdb/api/processFingerprint.ts`
- Modify: `web/.../featureLibrary/__tests__/surfaceHierarchy.contract.test.ts`
- Modify: `web/src/app/cmdb/locales/{zh,en}.json`
- Modify: 端口页 `PORT_TARGET_TYPE_OPTIONS` 扩到与内置 `target_type` 一致（进程页共用）

- [ ] Tab 路由 `/featureLibrary/process`；layout 的 `isFeatureLibrary` 识别该路径
- [ ] 不可删内置；可停用；新增校验进程规则非空
- [ ] `pnpm type-check`；契约测试包含 process page 与三 Tab

---

### Task 4: ScanHit 可信度 + 发现事件可无凭据落清单

**Files:**
- Modify: `scan_model.py` + migration（`confidence` CharField 默认 `low`；`evidence` JSONField 默认 list）
- Modify: `scan_credential_result_service.py`、`serializers/scan_serializer.py`
- Test: `test_scan_credential_event_nats.py`、`test_scan_models.py`

事件约定（扫描 NATS subject 不变，payload 增加字段）：

```text
stage: port | process | collect
status: success | unreachable | failed
host, port, target_type
credential_id: 可空
confidence: low | medium | high
evidence: ["port"] | ["process"] | ["port","process"] | ["collect"]
```

- [ ] **失败测试**

`stage=port` 且无 `credential_id`、`status=success` → 写 `ScanHit`，`cmdb_model_id=target_type`，`confidence=low`，`evidence` 含 `port`。同一 `(family_run, host, port, credential_id="")` 再来 `stage=process` → 升级 `medium`，evidence 合并，不新增行。`stage=collect` 失败不删该行。

- [ ] **实现**

`family_run`：该 `target_type` 在本次 execution 上 `get_or_create(model_id=target_type, batch_index=0)`。进度分母改到执行级 IP 数（见 Task 6），本任务不要再用「每枪凭据成功才计进度」挡住发现行。序列化输出 `confidence`、`evidence`。

- [ ] 跑 `test_scan_credential_event_nats.py`

---

### Task 5: Stargazer `WorkloadClass.SCAN` + `scan_discover`

**Files:**
- Modify: `agents/stargazer/core/collection/enums.py` 增加 `SCAN = "scan"`
- Modify: `constants.py` / `application.py`：`DEFAULT_SCAN_MAX_ACTIVE_TARGETS = 40`；`max_active_targets` 默认加上 40，**保持** `CONFIGURATION=80`
- Modify: scheduler `workload_weights` 加入 SCAN
- Create: `agents/stargazer/core/scan/`（scheduler 编排、tcp_probe、process_match）
- Create: `agents/stargazer/api/collect.py` 路由 `POST /collect/scan_discover`（不要复用 GET `collect_info`）
- Test: `agents/stargazer/tests/test_scan_scheduler.py`、`test_scan_discover_http.py`

- [ ] **队列隔离测试（先写）**

配置采集槽打满（CONFIGURATION active == 80）时提交 `scan_discover`：SCAN 队列 `accepted`，CONFIGURATION `active` 不变。SCAN 打满时 `collect_info` 仍 `accepted`。`scan_discover` 的 `workload_class is WorkloadClass.SCAN`。Stage 1 探测不得进入 `remote_job` capacity_group。

- [ ] **阶段行为测试（mock socket / 进程列表）**

给定指纹 `{3306: mysql}`、`{mysqld: mysql}`、网段单 IP：端口开放 → 发 port 成功事件；再给定进程列表含 `mysqld` → process 事件升级。无 SSH/Agent 时只发 port 事件。进程匹配每主机调用一次「列进程」，不按类型重复。

- [ ] **实现要点**

`scan_discover` 请求体：`execution_id`、`ip_ranges`、`port_fingerprints`、`process_fingerprints`、可选 `host_login`（SSH 池或 Agent+cloud_region）、`credential_result_subject`、`access_point`。触发时冻结的指纹快照由 Server 传入，Stargazer 不读 Django。TCP 探测用扫描配额；SSH/Agent 走扫描专用 job 限额（建议 ≤8 并发），禁止把整段 IP 一次打进原 Ansible `remote_job`。结果发布沿用扫描凭据 subject，payload 见 Task 4。

---

### Task 6: Server 触发改走 `scan_discover`

**Files:**
- Create: `scan_fingerprint_snapshot.py`（读 enabled 端口+进程）
- Modify: `stargazer_collect_trigger.py` 增加 `scan_discover` 客户端（解析 202 + `X-Target-Count`）
- Modify: `scan_trigger_service.py`：创建 execution 后 **不再** 为 middleware 拆 7 枪 `collect_info`；一次接纳 `scan_discover`
- Modify: `scan_schedule_service.py`：JOB 切批不再作为中间件发现本体；`schedule` 改为阶段游标（`port` → `process` → `collect`）
- Test: `test_scan_trigger_service.py`

- [ ] **失败测试（mock Stargazer）**

任务只勾 `host`、families 不含 `database`/`middleware`：触发仍把 mysql/nginx 指纹放进 `scan_discover` body；**不**对 nginx_info admit。`target_count` = 展开后的 IP 数。无主机登录凭据：body 无 `host_login`（或空），仍接纳一阶段。

- [ ] **实现**

`iter_scan_family_pools` / `_admit_family` 仅用于三阶段（Task 7）和仍走协议采集的网络 SNMP / 物理机 / Influx（勾选了才 admit `collect_info`）。中间件 / 三库 / 特征库内其它 JOB 对象的发现全部交给 `scan_discover`。SNMP 成功地址可写入 schedule，供二阶段剔除。

- [ ] 跑 `test_scan_trigger_service.py`；旧「中间件 7 枪同时 admit」断言改为「scan_discover 一次 + 指纹含 7 类」。

---

### Task 7: 三阶段复用采集（有凭据才打 `*_info`）

**Files:**
- Modify: `scan_trigger_service.py` / `poll_scan_finalize` 或 Stargazer 调度在 process 完成后对命中子集调用现有 collection application（`WorkloadClass.SCAN`）
- Test: `test_scan_trigger_service.py` 或新建 `test_scan_stage_collect.py`

- [ ] 勾选 database 且池内有 SQL 账号：仅对 `target_type in {mysql,postgresql,mssql}` **且已有命中** 的 IP:port 调用 `mysql_info` 等；不要对全网段展开。
- [ ] 未勾选 database：没有任何 `mysql_info` admit。
- [ ] 勾选 middleware + SSH/Agent：仅对已有 nginx 等命中调用对应 `*_info`。
- [ ] 采集失败：NATS `stage=collect` `failed`，命中仍在，confidence 保持 medium/low。
- [ ] 采集成功：confidence=`high`，snapshot 合并版本/路径；**禁止**空 VM 结果删 hit（沿用现 finalize 红线，可删掉「按 7 枪 explode 再猜默认口」中与指纹重复的部分，保留补路径）。

实现落点二选一（优先 A，避免 Server 再切批）：

- A. Stargazer 扫描模块在二阶段结束后，用同一 SCAN 配额跑插件，结果仍发扫描 subject。
- B. Server 在 process 进度齐后，对命中 `admit(collect_info)` 且 `workload` 无法从 collect_info 表达时不要走这条。

本计划选 A。`collect_info` 保持 `WorkloadClass.CONFIGURATION`。

---

### Task 8: 写 CI / 生成采集 / 推监控出口

**Files:**
- Modify: `scan_write_ci_service.py`、`scan_identity.py`（低可信不再当 `credential_failed` 拒绝写入）
- Modify: `scan_collect_generate.py`
- Modify: `scan_push_monitor.py`
- Test: `test_scan_write_ci_service.py`、`test_scan_collect_generate.py`、`test_scan_push_monitor.py`

- [ ] 用户勾选的 `confidence=low` mysql 命中可写 CI；未勾选不写。
- [ ] 无数据库采集凭据的行生成采集 → `skipped` / `no_credential`。
- [ ] `family_run.model_id in SCAN_MIDDLEWARE_TYPES` 或数据库类型：推监控 **不** 调 `push_with_credential`；改为创建 `module_link` CMDB→监控任务（mock `MonitorLinkService` / 现有建任务入口），返回 task id。网络 SNMP / 主机 SSH 契合监控插件的维持原推送。
- [ ] 只扫中间件时仍不新建主机；已有同 IP 主机才建 `run`。

---

### Task 9: 扫描任务 / 清单 UI（Gemini）

**Files:**
- `ScanTaskDrawer.tsx` + locales：勾选说明改为「展开该族凭据；端口/进程扫描范围由特征库决定」
- `ScanHitsDrawer.tsx` + `scanHits.ts`：已匹配表增加可信度列；低/中可信可勾选写 CI；无凭据行禁用生成采集；库/中间件推监控按钮改为「同步到监控」（走 Task 8）
- 测试：现有 `scanTaskForm.test.ts` / `scanExecutionStatus.test.ts` 补文案与列；`pnpm type-check`

---

### Task 10: 回归与收口

```bash
cd server && SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest \
  apps/cmdb/tests/test_port_fingerprint.py \
  apps/cmdb/tests/test_process_fingerprint.py \
  apps/cmdb/tests/test_scan_models.py \
  apps/cmdb/tests/test_scan_trigger_service.py \
  apps/cmdb/tests/test_scan_credential_event_nats.py \
  apps/cmdb/tests/test_scan_finalize_service.py \
  apps/cmdb/tests/test_scan_write_ci_service.py \
  apps/cmdb/tests/test_scan_collect_generate.py \
  apps/cmdb/tests/test_scan_push_monitor.py \
  apps/cmdb/tests/test_scan_views.py --no-cov
cd ../agents/stargazer && python -m pytest tests/test_scan_scheduler.py tests/test_scan_discover_http.py tests/test_collection_http_admission.py -q
cd ../../web && pnpm type-check
```

- [ ] 上述命令新鲜跑过；失败则留原始输出，不拿旧日志充数
- [ ] `collect_info` 仍是 CONFIGURATION；扫描满载不让 `test_collection_http_admission` 退化
- [ ] `batch_init` 含两个 init 命令；非关键种子失败不得阻断启动（沿用现有 call_command 失败策略，不要为此新加 sleep/重试）

---

## 顺序与依赖

```text
Task 1 → Task 2 → Task 3
                ↘ Task 4 → Task 6 → Task 7 → Task 8 → Task 9 → Task 10
Task 5 可与 1–4 并行，必须在 Task 6 之前完成
```

不要在 Task 6 之前改触发器去调尚不存在的 `scan_discover`。不要把扫描请求改回 `collect_info` 来「先跑起来」。
