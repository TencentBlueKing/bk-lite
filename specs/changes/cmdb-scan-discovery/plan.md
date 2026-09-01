# CMDB 扫描纳管 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在自动发现增加「扫描」：按族对现有 Stargazer `collect_info` 打一枪全量采集，Server 收口写 CI 与清单，再按需生成采集 / 推监控。

**Architecture:** 扫描是新模型，不进 `CollectModels`。触发复用 `NodeParamsFactory.custom_headers` + HTTP `collect_info`；进度复用现有凭据 NATS（换 subject）；CI 复用 VM 查询 + 现有 mapping + `Management.controller()`，扫描只做身份后处理。生成采集走现有 `CollectModelService.create`；推监控扩展现有 ingest 带凭据创建。不改 Stargazer，不改 `sync_collect_task`。

**Tech Stack:** Django ORM、DRF、Celery、NATS、VictoriaMetrics、现有 CMDB mapping / NodeParams、Next.js + Ant Design。规格见 `specs/changes/cmdb-scan-discovery/spec.md`。

---

## 先看清的现有逻辑（不要另起一套）

当前专业采集的真实路径是：

```
CollectModels 创建
  → 下发 Telegraf 子配置（常驻，间隔到了会再打）
  → 可选 trigger_first_collection：HTTP collect_info（只等接纳，不等跑完）
  → Beat / 手动 exec_task → sync_collect_task
       → 立刻查 VM last_over_time[1h]
       → plugin.format_data / format_metrics
       → input_method=MANUAL 则 Management.update()，否则 controller()
  → 凭据命中另走 NATS receive_collect_credential_result → CollectTaskCredentialHit
```

Stargazer 侧已经支持无 Telegraf 的一枪：`GET /api/collect/collect_info`，展开 `cmdbhosts`，凭据池 `cmdbcredential_N_*`，HTTP **202**，头 **`X-Task-Status` / `X-Target-Count`**。租约结束即删 Redis，不能回读 completed。配置采集失败目标只发布凭据结果事件，不再生成 VM `collection_status` 占位指标。

扫描要迭代的是这条路的「触发 + 回流 + 写 CI」，不是再做一个运行时。

### 明确不碰

| 现有逻辑 | 为什么不动 |
|---|---|
| `CollectModelService.create` / `push_butch_node_params` / Beat | 一创建就会落 Telegraf、打第二枪 |
| `sync_collect_task` 领取 / CAS | 采集单飞锁，扫描不得挤进去 |
| `CollectCredentialPoolService.MAX_POOL_SIZE = 3` | 扫描把数不限；生成采集才受 3 把约束（且只带 1 把） |
| `input_method` → 自动可新增可改 | 生成出来的采集与手建网段任务一致（AUTO）；扫描落库仍走 controller 新增 |
| `CollectNetworkMetrics.get_default_oid_map` 未知当 switch | 采集债务，扫描后处理丢掉建 CI |
| `receive_collect_credential_result` 必须命中 CollectModels | 扫描换 subject，采集回调零改 |
| Stargazer 调度 / 失败交付 | 扫描不改；失败进度走凭据结果事件，不依赖 VM 失败指标 |
| `CMDB_CREDENTIAL_CREATE_ENABLED` 的信封「默认不带密钥」 | 密钥只进监控 `env_config` |

### 现有契约必须对齐（扫描侧修，不要改错采集）

`StargazerCollectTriggerClient._parse_success` 仍按旧约定吃 HTTP 200、`X-Task-Count` / `queued|skipped`。Stargazer 现在返回 **202 + `X-Target-Count` + `accepted|duplicate_active`**。扫描用**新方法**解析真实契约；不要顺手改 `trigger_first_collection` 的旧解析（那是另一笔债）。

`collect_task_id` 不能用 `ScanFamilyRun.id` 去撞 `CollectModels.id`（两表自增会冲突）。扫描凭据事件走新 NATS subject，handler 只查扫描表。

---

## Global Constraints

- 只改任务范围；不改 Stargazer 插件 / 调度 / 结果发布（除非验收证明目标完全没有凭据事件）。
- 不把扫描行写入 `CollectModels`；不调用 `CollectModelService.create` 直到「生成采集」任务。
- Celery 任务必须在 HTTP 接纳后结束；收口任务只做 VM 查询 + 写库，禁止 `time.sleep` 盯盘。
- 数据库走 Django ORM；日志 `from apps.core.logger import cmdb_logger as logger`。
- 密钥不明文出现在 GET 列表 / 公开 ingest 信封 / 日志。
- 执行用状态机 + execution token：旧执行不得覆盖新执行。
- 权限复用 `auto_collection-*`。
- 中文提交；标识符跟现有风格。
- 测试：`cd server && uv run pytest apps/cmdb/tests/test_<file>.py -v`；Web：`pnpm type-check`（改了 `web/src` 时）。

## 切片（可独立交付）

1. **发现闭环**：扫描 CRUD + 触发 + 进度 + 写 CI + 清单。
2. **生成采集**：一把钥匙一张 CollectModels。
3. **推监控**：扩展带凭据创建到本章 7 类。

未做完切片 2/3 时，清单按钮可存在但返回明确未就绪；开关默认关。

## File Structure

| 文件 | 职责 |
|---|---|
| `server/apps/cmdb/models/scan_model.py` | **新建** ScanTask / ScanExecution / ScanFamilyRun / ScanHit |
| `server/apps/cmdb/migrations/0049_scan_models.py` | 迁移（编号以当时最新 +1 为准） |
| `server/apps/cmdb/models/__init__.py` | 导出新模型 |
| `server/apps/cmdb/services/scan_shot.py` | **新建** 扫描枪：duck-type 给 NodeParamsFactory 用 |
| `server/apps/cmdb/services/stargazer_collect_trigger.py` | 新增 `admit()`：解析 202 / X-Target-Count；`trigger(task)` 不动 |
| `server/apps/cmdb/services/scan_trigger_service.py` | **新建** 按族打枪、写 FamilyRun |
| `server/apps/cmdb/services/scan_credential_result_service.py` | **新建** 扫描凭据事件 → ScanHit 进度 |
| `server/apps/cmdb/nats/nats.py` | 注册 `receive_scan_credential_result` |
| `server/apps/cmdb/collection/collect_plugin/base.py` | **最小钩子**：`collect_inst=` 可跳过 `CollectModels.objects.get` |
| `server/apps/cmdb/services/scan_identity.py` | **新建** 扫描后处理（未知 SOID、物理机键、挂靠） |
| `server/apps/cmdb/services/scan_finalize_service.py` | **新建** 查 VM、mapping、controller、收口 |
| `server/apps/cmdb/tasks/celery_tasks.py` | `trigger_scan_execution` / `finalize_scan_execution`（短任务） |
| `server/apps/cmdb/services/scan_collect_generate.py` | **新建** 调用 CollectModelService 生成一张任务 |
| `server/apps/cmdb/views/scan.py` + serializers | CRUD / exec / hits / generate / push |
| `server/apps/monitor/services/module_ingest.py` | 扩展 `CMDB_CREATE_ADAPTED_MODEL_IDS` + 各类型 `_build_*_config` |
| `server/apps/cmdb/services/module_push.py` | 扫描/显式推送带凭据创建；信封仍无密钥；回填 monitor_id |
| `web/src/app/cmdb/constants/menu.json` | 采集前插入「扫描」 |
| `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/scan/` | **新建** 列表 + 抽屉 + 清单 |
| `web/src/app/cmdb/api/scan.ts` | **新建** API 客户端 |
| `web/src/app/cmdb/locales/{zh,en}.json` | `Scan.*` 文案 |
| `server/apps/cmdb/tests/test_scan_*.py` | 服务 / NATS / API |
| `server/apps/monitor/tests/test_module_ingest.py` | 扩 7 类创建 |

复用、不复制：`NodeParamsFactory`、`CollectCredentialPoolService.normalize_pool`（不调用 `validate_pool_shape`）、`CollectTargetService` 的 IP 展开、`IpInput`、`CredentialPoolEditor`、`Collection.query`、各 `collect_plugin` mapping、`Management.controller`、`CollectModelService.create`、`CmdbToMonitorPushService.push_with_credential` → `Monitor.ingest_from_source`、`OidMapping`。

---

### Task 1: 扫描模型与加密

**Files:**
- Create: `server/apps/cmdb/models/scan_model.py`
- Create: `server/apps/cmdb/migrations/0049_scan_models.py`
- Modify: `server/apps/cmdb/models/__init__.py`
- Test: `server/apps/cmdb/tests/test_scan_models.py`

**字段（保持瘦）：**

`ScanTask`：`name`、`team`、`access_point`、`ip_ranges`（JSON 列表，每项 `{begin,end}`）、`cloud_region`（主机族必填）、`families`（JSON，如 `["network","host","physcial_server","mysql",...]`）、`credentials`（JSON，按族 → 凭据列表，加密字段复用 `get_collect_model_passwords`）、`auto_push_monitor` / `auto_generate_collect`（默认 False）、`timeout`。无 `is_interval` / `cycle_*`。

`ScanExecution`：`task` FK、`status`（pending/running/finalizing/completed/failed/timed_out）、`claim_token`、`started_at` / `deadline_at` / `finished_at`、`target_count`、`received_count`。

`ScanFamilyRun`：`execution` FK、`model_id`、`driver_type`、`target_count`、`received_count`、`admit_status`。

`ScanHit`：`execution` FK、`family_run` FK、`protocol`、`host`、`port`、`credential_id`、`status`（success/failed/unreachable）、`soid`、`cmdb_model_id`、`inst_uuid`、`error_code`。清单主键语义：`(protocol, host, port, credential_id)`。

- [ ] **Step 1: 写失败测试**

```python
# server/apps/cmdb/tests/test_scan_models.py
import pytest
from apps.cmdb.models.scan_model import ScanTask

pytestmark = pytest.mark.django_db

def test_scan_task_defaults_auto_push_off():
    task = ScanTask.objects.create(name="scan-model-probe", team=["1"], ip_ranges=[], families=[], credentials={})
    assert task.auto_push_monitor is False
    assert task.auto_generate_collect is False
```

- [ ] **Step 2: 运行确认失败**

```bash
cd server && uv run pytest apps/cmdb/tests/test_scan_models.py::test_scan_task_defaults_auto_push_off -v
```

Expected: import / table missing。

- [ ] **Step 3: 落地模型 + 迁移；`decrypt_credentials` 抄 CollectModels 的加解密，按族分别 `get_collect_model_passwords(model_id)`。**

- [ ] **Step 4: 测试通过后提交** `feat(cmdb): 增加扫描任务模型`

---

### Task 2: 扫描枪 duck-type + 真实接纳契约

**Files:**
- Create: `server/apps/cmdb/services/scan_shot.py`
- Modify: `server/apps/cmdb/services/stargazer_collect_trigger.py`
- Test: `server/apps/cmdb/tests/test_scan_shot.py`、`server/apps/cmdb/tests/test_stargazer_admit.py`

**关键：不要 new 一套 header 拼装。** `NodeParamsFactory.get_node_params(instance)` 只要求 instance 有 `model_id`、`driver_type`、`ip_range`、`instances`、`credential` / `decrypt_credentials`、`timeout`、`params`、`id`、`access_point`。

```python
# scan_shot.py 形状
@dataclass
class ScanShot:
    id: int                  # ScanFamilyRun.id，变成 cmdb_{id} 的 instance_id
    model_id: str
    driver_type: str
    ip_range: str            # 多段用逗号拼接，与 CollectModels.ip_range 相同
    instances: list
    credential: list
    timeout: int
    params: dict
    access_point: list
    @property
    def decrypt_credentials(self):
        return self.credential
```

`params` 里扫描固定 `has_network_topo=False`，避免网络插件多查拓扑指标。

主机族：把 `cloud_region` 写进 `params` / instances 快照，复用 `CollectModelService.enrich_host_cloud_snapshot_payload` 的字段名，不要自创云区域键。

headers 在 `custom_headers()` 之后覆盖两处：

- `cmdbcredential_result_subject` = `receive_scan_credential_result`
- 不要改 `cmdbcollect_task_id` 以外的 NodeParams 字段；`collect_task_id` 用 `str(family_run.id)`（扫描 handler 自己解析）

`StargazerCollectTriggerClient.admit(headers) -> TriggerResult`：

- HTTP 202 + `X-Task-Status in {accepted, duplicate_active}` + `X-Target-Count` → 成功
- 429 / `busy` → Retryable
- `duplicate_active` 视为本枪已在跑（同 family_run 头指纹），扫描记 `admit_status=duplicate`，不报错中断其他族
- **不要改** 现有 `trigger(task)` / `_parse_success`

- [ ] **Step 1: 单测 `admit` 解析 202 / X-Target-Count；200+queued 不是扫描成功路径。**
- [ ] **Step 2: 单测 ScanShot + 真实 NodeParams 子类能产出 `cmdbplugin_name`、`cmdbhosts`、`cmdbcredential_count`（mock 网络/SSH 凭据）。**
- [ ] **Step 3: 实现。凭据池用 `normalize_pool`，禁止 `validate_pool_shape`（那会砍到 3 把）。**
- [ ] **Step 4: 提交** `feat(cmdb): 扫描复用 NodeParams 打 collect_info`

---

### Task 3: 短 Celery 触发（不盯盘）

**Files:**
- Create: `server/apps/cmdb/services/scan_trigger_service.py`
- Modify: `server/apps/cmdb/tasks/celery_tasks.py`、`server/apps/cmdb/tasks/__init__.py`
- Test: `server/apps/cmdb/tests/test_scan_trigger_service.py`

族 → `(model_id, driver_type)`：

| 族 | model_id | driver_type |
|---|---|---|
| 网络 | `network` | protocol |
| 主机 | `host` | job |
| 物理机 | `physcial_server` | protocol（IPMI，不要 SSH job） |
| MySQL | `mysql` | protocol |
| PostgreSQL | `postgresql` | protocol |
| MSSQL | `mssql` | protocol |
| InfluxDB | `influxdb` | protocol |

`trigger_scan_execution(execution_id)`：

1. `select_for_update` 领取 execution，写入 `claim_token`，status=`running`，`deadline_at = now + wall_clock`。墙钟：`max(15min, target_estimate * 单目标超时 / 经验并发)`，上限建议 2h，写入常量，禁止无界。
2. 每族：建 `ScanFamilyRun` → `ScanShot` → `admit()` → 存 `target_count`。一族失败（Permanent）记该族 failed，其他族继续。
3. `execution.target_count = sum(family.target_count)`。
4. `finalize_scan_execution.apply_async(args, countdown=30)` 作为轮询种子；**本任务 return**。
5. 禁止在本任务里 `requests` 等到采集结束、禁止 sleep 循环。

`finalize_scan_execution` 在 Task 5 才写实逻辑；本任务先做成：若 `received_count < target_count` 且未过 deadline，再 `apply_async(countdown=30)`；过 deadline 则标 `timed_out` 并仍进入 finalize（部分结果）。每次 finalize 必须校验 `claim_token`，旧执行直接 return。

- [ ] **Step 1: 测试 mock `admit`：两族各返回 target_count=3，Celery 任务在 mock 返回后结束，且 schedule 了 finalize。**
- [ ] **Step 2: 测试创建扫描 trigger 路径不调用 `NodeMgmt.delete_child_configs` / `push_butch_node_params`。**
- [ ] **Step 3: 实现并提交** `feat(cmdb): 扫描 Celery 只触发不盯盘`

---

### Task 4: 扫描凭据 NATS（采集回调零改）

**Files:**
- Create: `server/apps/cmdb/services/scan_credential_result_service.py`
- Modify: `server/apps/cmdb/nats/nats.py`
- Test: `server/apps/cmdb/tests/test_scan_credential_event_nats.py`

照 `CollectCredentialResultService` 的 v2 身份校验抄一份，但：

- 查找 `ScanFamilyRun.objects.filter(pk=collect_task_id)`，找不到则忽略（不要去查 CollectModels）。
- **仅 `success` 写 `ScanHit` upsert**，按 `(family_run, host, port, credential_id)`；`failed` / `unreachable` 不落清单。
- **进度**：`progress_hosts` 记录该 family 下已回传过的 distinct `host`（失败也算）；`received_count = len(progress_hosts)`。
- `success` 时把 snapshot 里能拿到的 `sysobjectid` / port 写入 hit。
- `received_count` 达到 `target_count` 时 `finalize_scan_execution.delay(execution_id, token)`（debounce：已 finalizing 则跳过）。
- 新 handler 名必须是 `receive_scan_credential_result`，与 header 一致。
- 不写 `CollectTaskCredentialHit`。

Prior art：`test_collect_credential_event_nats.py`。事件夹具可复用其 v2 字段，只改 subject 与 task_id。

- [x] **Step 1: 测试采集 handler 仍要求 CollectModels；扫描事件不进 CollectTaskCredentialHit。**
- [x] **Step 2: 测试 unreachable / failed 增加 received_count 但不写清单；success 写命中。**
- [x] **Step 3: 实现** 扫描凭据事件走独立 NATS subject；清单仅 success。

---

### Task 5: VM 收口 + mapping + 身份后处理 + 写 CI

**Files:**
- Modify: `server/apps/cmdb/collection/collect_plugin/base.py`（最小钩子）
- Create: `server/apps/cmdb/services/scan_identity.py`
- Create: `server/apps/cmdb/services/scan_finalize_service.py`
- Test: `server/apps/cmdb/tests/test_scan_identity.py`、`server/apps/cmdb/tests/test_scan_finalize_service.py`

**CollectBase 钩子（采集行为不变）：**

```python
def __init__(self, inst_name, inst_id, task_id, *args, collect_inst=None, **kwargs):
    self._collect_inst = collect_inst
    ...

def get_collect_inst(self):
    if self._collect_inst is not None:
        return self._collect_inst
    return CollectModels.objects.get(id=self.task_id)
```

现有测试应继续通过：不传 `collect_inst` 仍查 CollectModels。补一条：传入 shim 时不打 ORM。

**Finalize（每个 FamilyRun）：**

1. 用该族插件（`CollectNetworkMetrics` / `HostCollectMetrics` / `ProtocolCollectMetrics` / `DBCollectCollectMetrics`）`task_id=family_run.id`，`collect_inst=shim`（`model_id`、`is_network_topo=False`）。
2. `plugin.run()` → 内部 `instance_id=cmdb_{family_run.id}`，与 NodeParams `_instance_id` 一致。
3. `scan_identity.refine(model_id, plugin.result, hits)`：
   - 网络：`sysobjectid` 在 `OidMapping` 且 `device_type in {switch,router,firewall,loadbalance}` 才保留进 CI 列表；否则 CI 丢弃，hit 保留，`cmdb_model_id` 空，`push_monitor=False`。**不要调用** `get_default_oid_map` 来建 CI。
   - 物理机：有序列号/UUID 用其做认领提示（写入 hit snapshot）；CI 仍走现有 mapping 的 `inst_name`，与采集同一套 `Management` unique_keys=`["inst_name"]`。扫描不新发明图唯一键。
   - SNMP 未建网络 CI 且同 IP 已有 IPMI 成功 hit：把 SNMP hit 挂到该物理机（hit 上记 `attached_inst_uuid`），仍不建网络 CI。
   - host 与 `physcial_server` 同 IP：两行，不合并。
4. `MetricsCannula(..., manual=False, default_metrics=refined, filter_collect_task=False)`。`filter_collect_task=False` 是因为扫描实例没有 `collect_task=family_run.id`；对比键仍是 `inst_name`，与采集一致。`data_cleanup_strategy=NO_CLEANUP`，扫描不得删已有 CI。
5. 成功写入后回填 hit.`inst_uuid`。
6. 若任务开关打开，再调切片 2/3；默认关则停。

Mock `Collection.query` 返回成功 SNMP 指标（含未知 oid 与已知 switch oid）即可，不启 VM。

- [ ] **Step 1: 测试未知 SOID 不出现在 controller 的 add 列表，hit 仍在。**
- [ ] **Step 2: 测试已知 switch SOID 会走 controller（mock Management）。**
- [ ] **Step 3: 测试 CollectBase 不传 collect_inst 仍查 CollectModels（回归）。**
- [ ] **Step 4: 实现并提交** `feat(cmdb): 扫描收口复用 mapping 并后处理身份`

---

### Task 6: 扫描 API

**Files:**
- Create: `server/apps/cmdb/serializers/scan_serializer.py`
- Create: `server/apps/cmdb/views/scan.py`
- Modify: CMDB urls 注册
- Test: `server/apps/cmdb/tests/test_scan_views.py`

API（权限均 `@HasPermission("auto_collection-*")`，与采集平行）：

| 方法 | 路径 | 权限 |
|---|---|---|
| CRUD | `/cmdb/api/scan/` | View/Add/Edit/Delete |
| POST | `/{id}/exec/` | Execute |
| GET | `/executions/{eid}/` | View（含 received/target） |
| GET | `/executions/{eid}/hits/` | View，强制分页 |
| POST | `/executions/{eid}/generate_collect/` | Execute，body: hit ids |
| POST | `/executions/{eid}/push_monitor/` | Execute，body: hit ids |

约束：

- Serializer **禁止** `fields = "__all__"`；密钥字段 `write_only`，GET 脱敏。
- `ip_ranges` 校验顺序与上限：与前端 `IP_RANGE_MIN_PREFIX=21` 一致（现有采集控件）。
- 主机在 `families` 含 `host` 时 `cloud_region` 必填。
- `destroy` 只删扫描任务 / 执行 / hit，**不**删 CollectModels、不调监控 lifecycle。
- 列表分页有上界。

exec：创建 `ScanExecution` 后 `transaction.on_commit(lambda: trigger_scan_execution.delay(eid))`。

- [ ] **Step 1: API 测试：create 后 `CollectModels.objects.count()` 不变。**
- [ ] **Step 2: delete 扫描不调用监控 ingest lifecycle。**
- [ ] **Step 3: 实现并提交** `feat(cmdb): 扫描任务 API`

---

### Task 7: 前端 — 采集的兄妹页

**Files:**
- Modify: `web/src/app/cmdb/constants/menu.json`（zh + en，插在 `auto_collection` **之前**）
- Create: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/scan/page.tsx` 及抽屉 / 清单组件
- Create: `web/src/app/cmdb/api/scan.ts`
- Modify: `web/src/app/cmdb/locales/zh.json`、`en.json`（`Scan.*`）
- **不要改** `featureLibrary/scanFeature/page.tsx`

复用：`IpInput`（`web/src/app/cmdb/components/ipInput`）、`CredentialPoolEditor`。不要复用 `useTaskForm` / `createCollect`（那会打采集 API）。

页面最小集：任务列表、新建/编辑抽屉（多网段、族卡片勾选凭据、接入点、组织、主机云区域、两个默认关的开关）、执行按钮、执行进度 `received/target`、命中清单、两个分开的批量按钮。

布局：Tailwind `className`；颜色语义 token；不要新 SCSS Module。抽屉宽度可参考 `docs/design/cmdb-scan-placement-prototype.html`（约 960px），但实现跟现有采集抽屉组件走，不要引入原型 HTML。

- [ ] **Step 1: 菜单与空列表页可编译。**
- [ ] **Step 2: 抽屉提交走 `/cmdb/api/scan/` 而非 `/cmdb/api/collect/`。**
- [ ] **Step 3: `pnpm type-check`（在 web/）。**
- [ ] **Step 4: 提交** `feat(cmdb): 自动发现增加扫描入口`

---

### Task 8: 生成采集任务（切片 2）

**Files:**
- Create: `server/apps/cmdb/services/scan_collect_generate.py`
- Test: `server/apps/cmdb/tests/test_scan_collect_generate.py`

对每个选中且 `status=success` 的 hit：

**覆盖（只用于是否建采集，不跳过 CI 更新）：**

1. 已有 **其他** CollectModels（`is_system=False`）的 `instances` 含该 `inst_uuid` → 跳过。本扫描生成的任务已挂该实例 → 复用并认领，不跳过。
2. 已有 `CollectTaskCredentialHit` 对该 `host` + `credential_id` 为 success → 跳过（本扫描生成的那张除外，仍要认领）。
3. 仅 `ip_range` 覆盖到该 IP、从未命中 → 未覆盖，可生成。
4. IP 段族：本扫描已为这把 `credential_id` 建过任务 → 复用，把新命中所在的扫描起止段并进 `ip_range`，不新建第三张，也不挂 instances。InfluxDB：按凭据 + 端点复用，多端点多张任务。

新建时调用 `CollectModelService.create` 的内部等价路径（构造与 serializer 相同的 payload，走现有 create，以便 Beat + 节点下发 + first_collection 仍按采集语义工作）：

- `credential` = 仅命中的那一把（normalize 后长度 1）
- 网络 / 主机 / 物理机 / MySQL / PostgreSQL / MSSQL：`instances=[]`，`ip_range` = 扫描起止段 `begin-end`（命中落在哪段用哪段；禁止命中 IP 逗号串、禁止挂 switch CI）
- InfluxDB：`ip_range` 为空，`instances` 恰好 1 条（该命中 CI）；同一把凭据的多个端点拆成多张任务
- 主机：把扫描 `cloud_region` 写入 `params.cloud` / `params.cloud_name`
- `is_interval=True`，`cycle_value_type='cycle'`，`cycle_value` 用该类 NodeParams 默认 interval 分钟（`BaseNodeParams.interval // 60`，至少 1）
- `input_method=AUTO`（与手建网段任务一致；再次生成会把旧手动任务改成自动）
- 生成后把命中 CI 的 `collect_task` 认领成本 `CollectModels.id`。IP 段族不要挂 instances；InfluxDB 必须挂那一个端点。扫描落库用的是 `family_run.id`，不认领则自动模式会把已有 CI 当成新增并撞唯一约束
- **禁止改采集执行 / plugin registry** 来迁就选实例任务
- `name` 满足 `unique_together = (name, driver_type, model_id)`；IP 段族 `{scan.name}-{model_id}-{credential_id[:8]}`，InfluxDB 再拼 host/port

未知 SOID 的 SNMP hit：无 CI 时按 IP 仍可生成采集（产品允许）；`instances` 用 IP 占位需符合 serializer 对 inst_uuid 的校验——若现网 serializer **必须** 已有 CMDB 实例，则这条改为「只生成 ip_range 任务、instances 空、input_method=AUTO」会重新打开「手动只更新 / 发现」口子。**默认保守：没有 `inst_uuid` 的 hit 不能生成采集**，与「未知 SOID 不建网络 CI」一致；若产品要坚持「按 IP 出任务」，在实现前用测试钉死 serializer 是否允许无 inst_uuid 的 ip_range 任务（采集创建本身允许 ip_range）。计划默认：**无 inst_uuid 则跳过生成并在 API 结果里标明 reason=`no_ci`。** 未知 SOID 若仍要采集，用户可随后在采集页手建。

删扫描不碰这些 CollectModels。

- [x] **Step 1: 测试一把 cred 多个 IP → 一张 CollectModels。**
- [x] **Step 2: 测试已挂在采集实例上的 hit 被跳过。**
- [x] **Step 3: 测试生成后 `input_method=AUTO` 且 `is_interval=True`。**
- [x] **Step 4: 实现** `feat(cmdb): 扫描命中生成单凭据采集任务`
- [x] **Step 5: InfluxDB 每个端点一张选实例任务；主机拷贝 cloud_region。**

---

### Task 9: 推监控扩到 7 类（切片 3）

**Files:**
- Modify: `server/apps/monitor/services/module_ingest.py`
- Modify: `server/apps/cmdb/services/module_push.py`
- Test: `server/apps/monitor/tests/test_module_ingest.py`、`server/apps/cmdb/tests/test_push_to_monitor.py`

现有墙：

- `CMDB_CREDENTIAL_CREATE_ENABLED = False`
- `CMDB_CREATE_ADAPTED_MODEL_IDS = {"host"}`
- `_create_for_source` 只走 Host Remote
- `push_instance` 信封无密钥且不回填 `monitor_id`

扫描 / 清单显式「推送到监控」走 CMDB→Monitor 固定 IoC：`CmdbToMonitorPushService.push_with_credential` → `Monitor().ingest_from_source`（与资产页同一 NATS 入口；特权路径才带 `raw.credential` + `allow_credential_create=True`）。禁止扫描侧 import/调用 `MonitorModuleIngestService`。不要把密钥塞进普通 `_build_envelope` / `push_instance`：

1. 对扫描打开的创建：`CMDB_CREDENTIAL_CREATE_ENABLED` 保持模块常量，但增加按调用方的显式参数 `allow_credential_create=True`（仅 scan push / 未来的显式「带监控创建」使用）。**不要**把全局默认改 True，以免节点创建钩子突然建监控。
2. 扩展 adapted set：`host`、`switch`、`router`、`firewall`、`loadbalance`、`physcial_server`、`mysql`、`postgresql`、`mssql`、`influxdb`。扫描 hit 的网络模型用 SOID 分出的具体模型，不是 `network`。
3. 按插件**名**查询后走 `create_monitor_instance_by_node_mgmt`，字段对齐现成 Telegraf 插件 `UI.json`：
   - host → `Host Remote`（`type=host`，`ENV_PASSWORD` / `ENV_PRIVATE_KEY_*`；扫描 `authType=privateKey` 映射为 `auth_type=private_key`）
   - 网络 → 各自 General：`Switch SNMP General` / `Router SNMP General` / `Firewall SNMP General` / `Loadbalance SNMP General`；config `type` 与 `instance_type` 为 `switch|router|firewall|loadbalance`，禁止一律写成 switch
   - physcial_server → `Hardware Server IPMI`（`type=hardware_server`，`ENV_PASSWORD`）
   - mysql / postgresql / mssql / influxdb → `Mysql` / `Postgres` / `MSSQL` / `InfluxDB`；Influx `server` 为 `{scheme}://{ip}:{port}/debug/vars`，token 进 `ENV_PASSWORD`
   - 查不到插件名、无容器采集节点、套模板失败 → **该行失败**，禁止 `_create_instance` 回退空壳
   - `_extract_credential` 把 username / community / token / password / private_key 任一视为有效钥匙
   - 成功后 `_backfill_monitor_id` 按实际 `model_id` 回写图属性
4. `_resolve_monitor_object` 按模型解析，禁止 DB 落到 Host。
5. `_backfill_monitor_id` 按实际 `model_id` 调 `ensure_model_monitor_id_attr`，不要写死 host。
6. 未知 SOID / 无命中凭据 / ingest ignored → 该行失败，不影响其他行。
7. 公开 envelope 测试继续断言 `"credential" not in envelope["raw"]"`。

- [x] **Step 1: 测试全局默认仍忽略无开关的 CMDB 创建。**
- [x] **Step 2: 测试 allow_credential_create + mysql 凭据会建非 Host 对象（mock InstanceConfigService）。**
- [x] **Step 3: 测试 switch 未知 SOID hit 不调用 ingest create。**
- [x] **Step 4: 实现** `feat(monitor): CMDB 扫描带凭据创建扩到七类对象`

---

### Task 10: 执行状态机回归与走查例子

**Files:**
- Test: `server/apps/cmdb/tests/test_scan_execution_fencing.py`
- 对照规格走查例子 `10.0.1.0/24` 写成服务层测试（mock admit + 注入 hits + mock VM）

必测：

- 第二次 exec 领取新 token；第一次 finalize 带着旧 token 不能改 hit / CI。
- deadline 到达：status=`timed_out`，已成功 hit 仍 finalize。
- 10.0.1.10 已知 SOID → CI + 可推 + 可生成；10.0.1.11 未知 SOID → 无网络 CI、不可推、生成按 Task 8 的 `no_ci`；10.0.1.12 SNMP+IPMI → 物理机 CI，SNMP 挂靠；10.0.1.20 host 已在采集实例 → 生成跳过；10.0.1.20:3306 MySQL → 可生成；无响应 / 鉴权失败不写 CI。

- [ ] **Step 1: 写测试并跑红。**
- [ ] **Step 2: 补齐 fencing 后跑绿。**
- [ ] **Step 3: 提交** `test(cmdb): 扫描执行 fencing 与走查例子`

---

## 验证命令

```bash
cd server
uv run pytest apps/cmdb/tests/test_scan_models.py \
  apps/cmdb/tests/test_scan_shot.py \
  apps/cmdb/tests/test_stargazer_admit.py \
  apps/cmdb/tests/test_scan_trigger_service.py \
  apps/cmdb/tests/test_scan_credential_event_nats.py \
  apps/cmdb/tests/test_scan_identity.py \
  apps/cmdb/tests/test_scan_finalize_service.py \
  apps/cmdb/tests/test_scan_views.py \
  apps/cmdb/tests/test_scan_collect_generate.py \
  apps/cmdb/tests/test_scan_push_monitor.py \
  apps/cmdb/tests/test_scan_execution_fencing.py \
  apps/cmdb/tests/test_push_to_monitor.py \
  apps/monitor/tests/test_module_ingest.py \
  apps/cmdb/tests/test_first_collection_task.py \
  apps/cmdb/tests/test_collect_credential_event_nats.py -v
```

```bash
cd web && pnpm type-check
```

采集回归（`test_first_collection_task` / `test_collect_credential_event_nats`）必须仍绿：证明扫描没改采集回调和旧 trigger 解析。

---

## Self-review

| 规格条目 | 任务 |
|---|---|
| 扫描不进 CollectModels / 不下发 Telegraf | 1, 3, 6 |
| 按族 collect_info 一枪、Celery 不盯盘 | 2, 3 |
| Stargazer 零改 | 全程；NATS 换 subject |
| 进度 已回传/目标数 | 4（distinct host）+ 3（X-Target-Count） |
| 全量 mapping + 身份后处理 | 5 |
| 未知 SOID 不建网络 CI、不推监控 | 5, 9 |
| 清单每次都有；两开关默认关 | 1, 6, 7 |
| 一把钥匙一张采集、手动只更新、默认周期 | 8 |
| 删扫描不级联 | 6, 8 |
| 推监控扩 7 类、信封无密钥 | 9 |
| 同 IP 多模型 / 物理机挂靠 SNMP | 5, 10 |

无 TBD /「类似 Task N」。`CollectBase.collect_inst` 与 `admit()` 命名在后续任务保持一致。
