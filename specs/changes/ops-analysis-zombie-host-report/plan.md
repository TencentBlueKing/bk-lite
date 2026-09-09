# 运营分析僵尸机报表 Implementation Plan

> **For agentic workers:** 按任务顺序 TDD 实现；规格见 `specs/changes/ops-analysis-zombie-host-report/spec.md`。未要求 git commit 时跳过各任务的 Commit 步。

**Goal:** 运营分析内置一张只读 Report：勾选已有 `monitor_id` 的 CMDB 主机后，一次查出时间窗内的 CPU/内存/IO/网卡入包均值峰值和成功登录次数，并按客户阈值过滤。

**Architecture:** CMDB 出已监控主机选项；日志按主机统计成功登录（`counted` / `uncollected`）；监控 NATS 拼表、授权、阈值。运营分析只登记数据源和 YAML，不直连三域内部服务。

**Tech Stack:** Django NATS、VictoriaMetrics `avg_over_time`/`max_over_time`、VictoriaLogs stats、运营分析 Report + 统一筛选、Next.js。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `server/apps/cmdb/services/monitored_host.py` | 行整形：os 标签、白名单、业务名、空 `monitor_id` 丢弃 |
| `server/apps/cmdb/services/host_zombie_whitelist.py` | 幂等补 host 枚举字段 `zombie_whitelist`（人工可改，采集不写） |
| `server/apps/cmdb/nats/nats.py` | `list_monitored_hosts` |
| `server/apps/rpc/cmdb.py` | 转发 `list_monitored_hosts` |
| `server/apps/log/services/successful_login_count.py` | 采集覆盖判定 + 成功登录聚合 |
| `server/apps/log/nats/log.py` | `count_successful_logins_by_host` |
| `server/apps/rpc/log.py` | 转发 |
| `server/apps/monitor/services/zombie_host_report.py` | 阈值、-1、IO 按盘取最大、行装配（无 Django） |
| `server/apps/monitor/nats/monitor.py` | `get_zombie_host_report` |
| `server/apps/monitor/nats/contracts.py` | 登记 handler 名 |
| `server/apps/rpc/monitor.py` | `MonitorOperationAnaRpc.get_zombie_host_report` |
| `server/apps/operation_analysis/support-files/source_api.json` | 两个内置数据源 |
| `server/apps/operation_analysis/support-files/zombie_host_report.yaml` | 内置 Report |
| `server/apps/operation_analysis/management/commands/init_builtin_canvases.py` | 并入 YAML |
| `web/src/app/ops-analysis/utils/dataSourceParamContract.ts` | 统一筛选可绑定 `number` |
| `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx` | 数字输入 |
| `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx` | 扫描 number 参数 |

不要改 Flow 查询、`get_host_resource_top`、OpenAPI 网关。不要把 IIS/MSSQL 脚本纳入本变更。`zombie_whitelist` 不要加入主机采集 field_mapping。

验证（相对 `server/` 或 `web/`）：

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest \
  apps/cmdb/tests/test_monitored_host.py \
  apps/cmdb/tests/test_list_monitored_hosts_handler.py \
  apps/log/tests/test_successful_login_count.py \
  apps/monitor/tests/test_zombie_host_report.py \
  apps/monitor/tests/test_zombie_host_report_handler.py \
  apps/monitor/tests/test_nats_monitor_handlers.py \
  apps/rpc/tests/test_misc_forwarding.py \
  apps/rpc/tests/test_monitor_forwarding.py \
  apps/operation_analysis/tests/test_zombie_host_report_datasource.py \
  apps/operation_analysis/tests/test_zombie_host_report_yaml.py \
  --no-cov

cd web && pnpm exec tsx --test \
  src/app/ops-analysis/utils/__tests__/dataSourceParamContract.number.test.ts
# 以及现有统一筛选 / param-contract 脚本：
cd web && pnpm exec tsx scripts/ops-analysis-param-contract-test.ts
```

---

### Task 1: CMDB 行整形与白名单字段

**Files:**
- Create: `server/apps/cmdb/services/monitored_host.py`
- Create: `server/apps/cmdb/services/host_zombie_whitelist.py`
- Create: `server/apps/cmdb/tests/test_monitored_host.py`
- Modify: `server/apps/cmdb/services/model.py`（`_apply_model_config_post_import_extras` 对 `host` 调用 ensure）

- [ ] **Step 1: 写失败测试**

```python
from apps.cmdb.services.monitored_host import build_monitored_host_row, normalize_zombie_whitelist

def test_drop_host_without_monitor_id():
    assert build_monitored_host_row({"inst_uuid": "u1", "inst_name": "h1", "ip_addr": "10.0.0.1"}) is None

def test_row_maps_os_and_empty_whitelist_as_no():
    row = build_monitored_host_row({
        "inst_uuid": "u1",
        "inst_name": "web-1",
        "ip_addr": "10.0.0.1",
        "os_type": "1",
        "monitor_id": "m-1",
        "organization": [3],
    }, org_names={3: "交易"})
    assert row["os_type_label"] == "Linux"
    assert row["zombie_whitelist"] == "no"
    assert row["biz_name"] == "交易"
    assert row["display_name"] == "web-1 (10.0.0.1)"

def test_whitelist_yes_only_when_enum_yes():
    assert normalize_zombie_whitelist("yes") == "yes"
    assert normalize_zombie_whitelist("") == "no"
    assert normalize_zombie_whitelist(None) == "no"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest apps/cmdb/tests/test_monitored_host.py --no-cov
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: 最小实现**

`monitored_host.py`：

- `OS_TYPE_LABELS = {"1": "Linux", "2": "Windows", "3": "AIX", "4": "Unix"}`（`other` → `Other`）
- `normalize_zombie_whitelist`：仅 `"yes"` 为 yes，其余为 `"no"`
- `build_monitored_host_row(entity, org_names=None)`：无 `inst_uuid` 或空 `monitor_id` 返回 `None`；`host_name` 用 `inst_name`；`ip` 用 `ip_addr`；`biz_name` 用组织 ID 在 `org_names` 中的显示名，多组织以顿号拼接，没有则空串

`host_zombie_whitelist.py`：

- 属性模板：`attr_id=zombie_whitelist`，`attr_type=enum`，`editable=True`，`is_required=False`，`option=[{"id":"yes","name":"是"},{"id":"no","name":"否"}]`，**不是** system link
- `ensure_host_zombie_whitelist_attr(username="admin")` 幂等创建/补 option，对标 `ensure_model_monitor_id_attr` 的查找-创建路径，但不要走 `_ensure_system_link_attr`

`model.py` 的 post-import extras：在 host 模型导入后调用 `ensure_host_zombie_whitelist_attr`。

- [ ] **Step 4: 再跑测试**

Expected: PASS。

---

### Task 2: `list_monitored_hosts` NATS

**Files:**
- Modify: `server/apps/cmdb/nats/nats.py`
- Modify: `server/apps/rpc/cmdb.py`
- Create: `server/apps/cmdb/tests/test_list_monitored_hosts_handler.py`
- Modify: `server/apps/rpc/tests/test_misc_forwarding.py`

- [ ] **Step 1: 写失败测试**

Handler（mock `InstanceManage.instance_list` 与 `_build_nats_permission_map`）：

```python
def test_list_monitored_hosts_omits_empty_monitor_id(monkeypatch):
    monkeypatch.setattr(nats, "_build_nats_permission_map", lambda user_info, **kw: {"ok": True})
    monkeypatch.setattr(
        nats.InstanceManage,
        "instance_list",
        lambda **kw: ([
            {"inst_uuid": "u1", "inst_name": "h1", "ip_addr": "10.0.0.1", "os_type": "2", "monitor_id": "m1", "organization": [1]},
            {"inst_uuid": "u2", "inst_name": "h2", "ip_addr": "10.0.0.2", "os_type": "1", "monitor_id": "", "organization": [1]},
        ], 2),
    )
    out = nats.list_monitored_hosts(user_info={"user": "u", "team": 1})
    assert out["result"] is True
    assert [row["inst_uuid"] for row in out["data"]] == ["u1"]

def test_list_monitored_hosts_empty_permission_returns_empty(monkeypatch):
    monkeypatch.setattr(nats, "_build_nats_permission_map", lambda user_info, **kw: None)
    out = nats.list_monitored_hosts(user_info={})
    assert out == {"result": True, "data": [], "message": ""}
```

RPC：

```python
def test_cmdb_list_monitored_hosts(cmdb):
    cmdb.list_monitored_hosts(user_info={"team": 1})
    assert _last(cmdb.client)[1] == "list_monitored_hosts"
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现 handler**

契约：`list_monitored_hosts(user_info=None, **kwargs)` → `{result, data: [row], message}`。

- 进入时 `ensure_host_zombie_whitelist_attr()`（幂等，存量环境也能出字段）
- `permission_map = _build_nats_permission_map(user_info, model_id="host")`；`None` 则空成功
- `InstanceManage.instance_list("host", params=[], page=1, page_size=5000, order="inst_name", permission_map=permission_map)`
- 用 Task 1 的 `build_monitored_host_row` 过滤；组织名用现有 `_build_authoritative_maps` 或 `Group.objects` 与 `get_monitor_ids_by_inst_uuids` 同一套权限用户规范化
- 不返回无 `monitor_id` 的主机

`CMDB.list_monitored_hosts`：`return self.client.run("list_monitored_hosts", **kwargs)`。

- [ ] **Step 4: 再跑测试** Expected: PASS。

---

### Task 3: 成功登录计数

**Files:**
- Create: `server/apps/log/services/successful_login_count.py`
- Create: `server/apps/log/tests/test_successful_login_count.py`
- Modify: `server/apps/log/nats/log.py`
- Modify: `server/apps/rpc/log.py`
- Modify: `server/apps/rpc/tests/test_misc_forwarding.py`

覆盖规则（规格：对得上采集实例 → `counted`，否则 `uncollected`）：

- 入参主机：`{host_name, ip, os_type, node_id?}`
- Windows（`os_type` 为 `2`）：存在授权 `CollectInstance`，`collect_type.name == "winlogbeat"`，且 `node_id` 与主机 `node_id` 相同（都空则不能凭空算 counted）
- Linux（`os_type` 为 `1` 或其它非 Windows）：存在授权 file/filebeat 类采集实例，同样优先 `node_id` 对齐
- 无匹配实例：`login_status=uncollected`，`login_count=None`

计数（仅 `counted` 主机，mock VictoriaLogs）：

- Windows 查询：`collect_type:winlogbeat AND event_id:4624`
- Linux 查询：成功 SSH/本地（message 含 `Accepted password` / `Accepted publickey` / `session opened`），排除 `Failed` / `Invalid user`
- 用 `SearchService` 同款 LogSQL：`{query} | stats by (host) count() as entry_count`，匹配键先 `host`/`hostname` 对 `host_name`（大小写不敏感），再对 `ip`
- 匹配到采集但 stats 无行 → `counted` 且 `login_count=0`

- [ ] **Step 1: 写失败测试（纯函数，不打 VL）**

```python
from apps.log.services.successful_login_count import (
    classify_login_coverage,
    merge_login_counts,
)

def test_no_collect_instance_is_uncollected():
    hosts = [{"host_name": "web-1", "ip": "10.0.0.1", "os_type": "2", "node_id": "n1"}]
    out = classify_login_coverage(hosts, collect_instances=[])
    assert out[0]["login_status"] == "uncollected"
    assert out[0]["login_count"] is None

def test_winlogbeat_same_node_is_counted_zero_until_stats():
    hosts = [{"host_name": "web-1", "ip": "10.0.0.1", "os_type": "2", "node_id": "n1"}]
    inst = SimpleNamespace(node_id="n1", collect_type=SimpleNamespace(name="winlogbeat"))
    covered = classify_login_coverage(hosts, collect_instances=[inst])
    assert covered[0]["login_status"] == "counted"
    merged = merge_login_counts(covered, [{"value": "web-1", "count": 4}])
    assert merged[0]["login_count"] == 4

def test_stats_miss_stays_zero_not_uncollected():
    covered = [{"host_name": "web-1", "ip": "10.0.0.1", "login_status": "counted", "login_count": None}]
    merged = merge_login_counts(covered, [])
    assert merged[0]["login_status"] == "counted"
    assert merged[0]["login_count"] == 0
```

Handler：非法 `hosts` 非列表 → `result=False`；空列表 → 空成功且 **不得** 调 VL。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现服务 + NATS**

`count_successful_logins_by_host(hosts, time_range, user_info=None, **kwargs)`：

1. 规范化 `hosts`、时间窗（复用 `_normalize_query_time_range`）
2. 按当前组织取授权 `CollectInstance`（与 log search 同一组织范围）
3. classify → 对 `counted` 分组查 Windows / Linux 各一次 stats（mock `VictoriaMetricsAPI.query`）
4. merge 后返回 `{result: True, data: [...], message: ""}`

`LogOperationAnaRpc.count_successful_logins_by_host` 转发同名。

生产日志：只打 counted/uncollected 台数和 `error_type`，禁止 query 正文、主机清单。

- [ ] **Step 4: 再跑测试** Expected: PASS。

---

### Task 4: 监控拼表纯函数

**Files:**
- Create: `server/apps/monitor/services/zombie_host_report.py`
- Create: `server/apps/monitor/tests/test_zombie_host_report.py`

常量：

```python
MAX_HOSTS = 100
UNBOUNDED = -1
DEFAULT_THRESHOLDS = {
    "login_min": -1, "login_max": 9,
    "packets_recv_max_min": -1, "packets_recv_max_max": 999,
    "packets_recv_avg_min": -1, "packets_recv_avg_max": 499,
    "cpu_avg_min": -1, "cpu_avg_max": 19,
    "cpu_max_min": -1, "cpu_max_max": 39,
    "mem_avg_min": -1, "mem_avg_max": 19,
    "mem_max_min": -1, "mem_max_max": 39,
    "io_max_min": -1, "io_max_max": -1,
}
```

`login_max=9` 表达客户「< 10」；比较用闭区间 `[min, max]`，`min/max == -1` 跳过该侧。

- [ ] **Step 1: 写失败测试**

```python
from apps.monitor.services.zombie_host_report import (
    apply_thresholds,
    fold_io_max,
    parse_threshold,
    row_passes,
)

def test_minus_one_skips_bound():
    t = parse_threshold({"login_min": -1, "login_max": 9})
    assert row_passes({"login_count": 0, "login_status": "counted"}, t) is True
    assert row_passes({"login_count": 10, "login_status": "counted"}, t) is False

def test_uncollected_skips_login_threshold_but_keeps_other_filters():
    t = parse_threshold({"login_max": 9, "cpu_avg_max": 19})
    assert row_passes({"login_status": "uncollected", "login_count": None, "cpu_avg": 5}, t) is True
    assert row_passes({"login_status": "uncollected", "login_count": None, "cpu_avg": 50}, t) is False

def test_io_fold_takes_max_disk():
    series = [
        {"instance_id": "m1", "device": "sda", "value": 10},
        {"instance_id": "m1", "device": "sdb", "value": 40},
        {"instance_id": "m2", "device": "sda", "value": 3},
    ]
    assert fold_io_max(series) == {"m1": 40.0, "m2": 3.0}
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现** `parse_threshold`、`row_passes`（AND 所有已设边界）、`apply_thresholds(rows, t)`、`fold_io_max`、`validate_inst_uuids(values)`：非列表 raise；去空去重后 `len>100` raise `ValueError("一次最多查询 100 台主机")`；空列表合法。

指标查询模板（handler 用，本任务只把名字和 fold 策略放进模块常量，对齐主机盘）：

| 字段 | Linux | Windows WMI | 窗内 | 多序列 |
|---|---|---|---|---|
| cpu | `100 - cpu_usage_idle{cpu="cpu-total"}` | `cpu_usage_total_gauge_value` / `host_cpu_usage_percent_gauge` | avg + max | identity |
| mem | `mem_used_percent` | `*_gauge_value` | avg + max | identity |
| packets | `rate(net_packets_recv[5m])` | `rate(net_packets_recv_gauge_value[5m])` | avg + max | sum 网卡 |
| io | `diskio_io_util` | `diskio_io_util_gauge_value` | max | 先盘后主机最大 |

用 `or` 拼跨平台查询，与 `dashboard_query_capabilities` 主机 CPU 合同一致。`window_selector` 复用 `apps.monitor.services.metric_series.window_selector`。

- [ ] **Step 4: 再跑测试** Expected: PASS。

---

### Task 5: `get_zombie_host_report` NATS

**Files:**
- Modify: `server/apps/monitor/nats/monitor.py`
- Modify: `server/apps/monitor/nats/contracts.py`（`MONITOR_NATS_HANDLER_NAMES` 加 `get_zombie_host_report`）
- Modify: `server/apps/monitor/tests/test_nats_monitor_handlers.py` 的 `EXPECTED_MONITOR_NATS_HANDLER_NAMES`
- Create: `server/apps/monitor/tests/test_zombie_host_report_handler.py`
- Modify: `server/apps/rpc/monitor.py`（`MonitorOperationAnaRpc`）
- Modify: `server/apps/rpc/tests/test_monitor_forwarding.py`

- [ ] **Step 1: 写失败测试**

```python
def test_empty_inst_uuids_does_not_query(monkeypatch):
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", lambda: (_ for _ in ()).throw(AssertionError("no vm")))
    out = nm.get_zombie_host_report(inst_uuids=[], time=10080, user_info={"user": "u", "team": 1})
    assert out == {"result": True, "data": [], "message": ""}

def test_over_100_hosts_fails_without_truncate():
    out = nm.get_zombie_host_report(inst_uuids=[f"u{i}" for i in range(101)], user_info={})
    assert out["result"] is False
    assert "100" in out["message"]

def test_drops_unauthorized_monitor_id(monkeypatch):
    identities = [
        {"inst_uuid": "u1", "monitor_id": "m1", "host_name": "h1", "ip": "10.0.0.1", "os_type": "1", "node_id": "n1"},
        {"inst_uuid": "u2", "monitor_id": "m2", "host_name": "h2", "ip": "10.0.0.2", "os_type": "1", "node_id": "n2"},
    ]
    monkeypatch.setattr(
        nm,
        "load_selected_hosts",
        lambda inst_uuids, user_info: identities,
    )
    _patch_scope(monkeypatch, {"m1": SimpleNamespace(id="m1")})
    queried = []

    class FakeVM:
        def query(self, q, *a, **k):
            queried.append(q)
            return {"status": "success", "data": {"result": []}}

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    login_hosts = []

    def fake_logins(hosts, *a, **k):
        login_hosts.extend(hosts)
        return {"result": True, "data": []}

    monkeypatch.setattr(nm, "count_successful_logins", fake_logins)
    out = nm.get_zombie_host_report(
        inst_uuids=["u1", "u2"],
        time=10080,
        user_info={"user": "u", "team": 1},
    )
    assert out["result"] is True
    assert [h["monitor_id"] for h in login_hosts] == ["m1"]
```

空选择断言：不得调用 `VictoriaMetricsAPI`、不得调用 `Log.count_successful_logins_by_host`。

超限：失败，`data=[]`。

无权：CMDB 给出 `monitor_id=m2`，`_get_authorized_monitor_instances` 只有 `m1` → 结果不含 m2，不报错。

过滤后为零：空成功。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现 handler**

`get_zombie_host_report(inst_uuids=None, time=None, os_type=None, zombie_whitelist=None, user_info=None, page=1, page_size=20, **thresholds)`：

内部接缝（供测试 patch，不要把 CMDB/Log 查询写死在 handler 里）：`load_selected_hosts(inst_uuids, user_info)`、`count_successful_logins(hosts, time_range, user_info)`。NATS 文件可 from 服务模块 import 这两个名字，测试 `monkeypatch.setattr(nm, "load_selected_hosts", ...)`。

1. 规范化 `inst_uuids`；空 → 空成功
2. `>100` → 失败消息
3. `CMDB().list` 不要用选项接口翻全量：用已有 `get_monitor_ids_by_inst_uuids` **不够**（缺主机名/IP/白名单）。改为 `CMDB.list_monitored_hosts` 拿选项后按 `inst_uuids` 过滤，**或** 新增内部读取：对所选 UUID `InstanceManage.search_inst_batch(model_id="host", inst_uuids=...)` 再 `build_monitored_host_row`。推荐 **search_inst_batch**，避免选项源 5000 条上限影响查询。权限：只保留调用方有权的 UUID（与 `get_monitor_ids_by_inst_uuids` 同一 `_has_topology_view_permission` / instance_list 权限）。
4. 可选 `os_type`、`zombie_whitelist` 再滤身份行
5. 取出 `monitor_id`，`_get_authorized_monitor_instances` 白名单过滤
6. 解析 `time`（运营分析 timeRange：相对分钟或 RFC3339 对），`window_selector` 后对 cpu/mem/packets/io 发 `avg_over_time`/`max_over_time`（IO 只要 max）。查询必须带授权 `instance_id` 正则，结果再过滤一遍
7. `LogOperationAnaRpc().count_successful_logins_by_host(hosts, time_range, user_info=user_info)`
8. 拼行 → `apply_thresholds` → 分页（过滤在分页前）→ `{result, data: {items, count, page, page_size}, message}`  

表格数据源若现有 table 只认数组：看 `field_schema` 与 host resource top。**若运营分析 table 期望 `data` 为 list**，则 handler 返回 list，分页参数仍传入但由前端 table 的 page/page_size 约定决定。对齐 `get_host_resource_top`：它返回 list。本查询有过滤+分页：若 `source_api.json` 声明 `page`/`page_size`（对标 CMDB 费用明细），返回 `{items, count, page, page_size}`；测试锁定该形状。

失败：CMDB/VM/日志 `result=False` 时整个请求失败，不返回半截表。日志调用失败要带 `failed_stage=login_count`，无 traceback 重复。

RPC：`MonitorOperationAnaRpc.get_zombie_host_report(**kwargs)` → `self.client.run("get_zombie_host_report", **kwargs)`。

- [ ] **Step 4: 再跑测试 + contracts 集合测试** Expected: PASS。

---

### Task 6: 运营分析数据源与内置报表

**Files:**
- Modify: `server/apps/operation_analysis/support-files/source_api.json`
- Create: `server/apps/operation_analysis/support-files/zombie_host_report.yaml`
- Modify: `server/apps/operation_analysis/management/commands/init_builtin_canvases.py`（`_get_builtin_canvas_file_paths` 加入该 YAML）
- Create: `server/apps/operation_analysis/tests/test_zombie_host_report_datasource.py`
- Create: `server/apps/operation_analysis/tests/test_zombie_host_report_yaml.py`

- [ ] **Step 1: 写失败测试**

数据源：

- `cmdb/list_monitored_hosts`：`chart_type == []`，`field_schema` 含 `inst_uuid`、`display_name`
- `monitor/get_zombie_host_report`：`chart_type == ["table"]`
- `inst_uuids`：`type=string`，`filterType=filter`，`inputConfig.multiple=true`，`optionsSource.sourceRef.value == "cmdb/list_monitored_hosts"`，`valueField=inst_uuid`，`labelField=display_name`
- `time`：`type=timeRange`，`value=10080`，`filterType=filter`
- 阈值参数为 `type=number`，`filterType=filter`，默认值与 `DEFAULT_THRESHOLDS` 一致
- `field_schema` 含规格列出的表格列（含 `login_status`）

YAML：可解析；`reports` 一条；唯一 `table` 绑定僵尸机数据源；`filterType=filter` 的参数会出现在报表统一筛选；`is_build_in` 路径随 `init_builtin_canvases` 合并（对标 `test_flow_dashboard_yaml.py` / `test_host_comprehensive_dashboard_yaml.py`）。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 写 JSON / YAML / 合并路径**

报表说明文案写清：时间默认 7 天，阈值不随窗口缩放；登录未采集不按 0 过滤。内置报表只读（现有 `is_build_in` 行为，不必新权限）。

`meta.object_counts` 必须与 YAML 各 section 长度一致，否则 init 校验失败。

- [ ] **Step 4: 再跑测试** Expected: PASS。

---

### Task 7: 统一筛选绑定 number

生产报表用的是 `web/src/app/ops-analysis/components/unifiedFilter/`（`report/index.tsx` 从这里 import）。`ops-analysis-unified-filter` 仅 Storybook，若改契约测试扫到它再同步。

**Files:**
- Modify: `web/src/app/ops-analysis/utils/dataSourceParamContract.ts`
- Create: `web/src/app/ops-analysis/utils/__tests__/dataSourceParamContract.number.test.ts`
- Modify: `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx`（`ScannedParam.type` 含 `number`）
- Modify: `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx`（`case 'number'` → `InputNumber`，允许 -1）
- Modify: `web/src/app/ops-analysis/types/dashBoard.ts` 若 `UnifiedFilterDefinition.type` 联合类型未含 `number` 则补上
- Modify: `web/scripts/ops-analysis-param-contract-test.ts` 若断言可绑定类型集合

- [ ] **Step 1: 写失败测试**

```ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { isBindableDataSourceParamType } from '../dataSourceParamContract';

test('number is bindable for unified filter', () => {
  assert.equal(isBindableDataSourceParamType('number'), true);
  assert.equal(isBindableDataSourceParamType('boolean'), false);
});
```

Config modal：`scanUnifiedFilterParams` 对 `type:number` + `filterType:filter` 的参数要扫出来（若 scan 在 `widgetDataTransform.getBindableFilterParams`，改合同即可，modal 不用分支）。

Bar：number 用 `InputNumber`，值为 `number | null`，不要 stringify 成逗号拼接。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现** `BINDABLE_DATA_SOURCE_PARAM_TYPES` 加 `number`；Bar 增加 number 分支；重置时用定义的 `defaultValue`（含 -1）。

- [ ] **Step 4: 再跑** `dataSourceParamContract.number.test.ts` 与 `pnpm exec tsx scripts/ops-analysis-param-contract-test.ts` Expected: PASS。

---

### Task 8: 回归与规格收口

- [ ] **Step 1: 跑本变更全部验证命令（见文首）**
- [ ] **Step 2: 补规格测试缺口**
  - 未采集登录不按 0 过滤：已在 Task 4
  - 空选择不查 VM/日志：已在 Task 5
  - 超 100 失败：已在 Task 5
  - YAML 绑定选项源：已在 Task 6
- [ ] **Step 3: 将 `specs/changes/ops-analysis-zombie-host-report/spec.md` 的 Status 改为 `implemented`，并在 Further Notes 写上实际验证命令与结果（实现完成时再改，不要提前改）**

---

## Spec coverage

| 规格项 | 任务 |
|---|---|
| CMDB 已监控主机选项 | 1–2 |
| `zombie_whitelist` 字段 | 1 |
| 成功登录 counted/uncollected | 3 |
| 空选不退回全量、100 台上限 | 5 |
| 主机网卡入包 + CPU/内存/IO 窗内均值峰值 | 4–5 |
| 阈值照抄、-1、AND、未采集跳过登录阈 | 4 |
| Report + 数据源 + timeRange 默认 7 天 | 6 |
| 统一筛选 number | 7 |
| 不经 OpenAPI、不用 Flow | 未做即为遵守 |

## 实现时注意

- 运营分析 `services/` 禁止 import `apps.cmdb.services` / `apps.monitor.services`。
- 表格 `login_count` 在 `uncollected` 时给 `null`，前端空值走现有 table 空展示，不要显示 0。
- 不要为阈值发明 `numberRange` 类型。
- 不要在 handler 里 raw SQL。
