# CMDB 扫描中间件族 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扫描任务增加中间件族，复用现有 JOB 发现脚本；空凭据走 Agent、填写走 SSH；清单按监听端口拆行；写入 CMDB 并按同通道生成采集；中间件不自动推监控。

**Architecture:** 任务存 `middleware` 一份凭据（可空或复用主机 SSH）。触发时拆成 7 个 JOB family_run，下发现有 `*_info`。收口只对中间件拉 mapping 指标并按 `listen_port` 拆 hit。写 CI / 生成采集沿用现有扫描出口；推监控对中间件直接跳过。

**Tech Stack:** Django、DRF、现有扫描触发 / 凭据 NATS / mapping、Next.js、Ant Design。

规格：`specs/changes/cmdb-scan-middleware/spec.md`

---

## File Structure

| 文件 | 职责 |
|---|---|
| `server/apps/cmdb/models/scan_model.py` | `middleware` 族常量、加密/驱动/任务类型、Agent 占位池、凭据解析 |
| `server/apps/cmdb/serializers/scan_serializer.py` | 空池放行、Agent 云区域、凭据标签 Agent、主机池回退 |
| `server/apps/cmdb/services/scan_trigger_service.py` | 拆 7 枪、空池占位、复用主机 SSH、中间件带云区域 |
| `server/apps/cmdb/services/scan_finalize_service.py` | 中间件收口拉指标并拆 hit |
| `server/apps/cmdb/services/scan_write_ci_service.py` | 中间件 snapshot → CI，同 IP 主机则挂 run |
| `server/apps/cmdb/services/scan_collect_task.py` | 中间件采集默认超时、Agent 空凭据建任务 |
| `server/apps/cmdb/services/scan_collect_generate.py` | 凭据从 middleware/host 池取 |
| `server/apps/cmdb/services/scan_push_monitor.py` | 中间件跳过；主机 Agent 不走带凭据 Host Remote |
| `server/apps/cmdb/views/scan.py` | 清单含中间件类型（已是 success 过滤，通常不用改查询） |
| `web/.../scan/ScanTaskDrawer.tsx` + `scanTaskForm.ts` | 勾选、提示、复用主机凭据、Agent 云区域 |
| `web/.../scan/ScanHitsDrawer.tsx` + `scanHits.ts` | 中间件 Tab、列、推监控禁用 |
| `web/src/app/cmdb/locales/{zh,en}.json` | 文案 |

验证命令（在 `bk-lite/server`，沿用现有 django_db / PostgreSQL 测试库）：

```bash
uv run pytest apps/cmdb/tests/test_scan_models.py apps/cmdb/tests/test_scan_views.py apps/cmdb/tests/test_scan_trigger_service.py apps/cmdb/tests/test_scan_finalize_service.py apps/cmdb/tests/test_scan_write_ci_service.py apps/cmdb/tests/test_scan_collect_generate.py apps/cmdb/tests/test_scan_push_monitor.py --no-cov
```

Web：`cd bk-lite/web && pnpm type-check`

---

### Task 1: 中间件族常量与凭据解析

**Files:**
- Modify: `bk-lite/server/apps/cmdb/models/scan_model.py`
- Test: `bk-lite/server/apps/cmdb/tests/test_scan_models.py`（若过瘦则新建同文件用例）

- [ ] **Step 1: 写失败测试**

在 `test_scan_models.py` 增加：

```python
from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.scan_model import (
    SCAN_AGENT_CREDENTIAL_ID,
    SCAN_MIDDLEWARE_FAMILY,
    SCAN_MIDDLEWARE_TYPES,
    agent_placeholder_pool,
    is_agent_credential,
    normalize_scan_families,
    resolve_scan_task_credential,
    scan_driver_type_for_model,
    scan_encrypt_model_id,
    scan_task_type_for_model,
)

def test_middleware_family_normalizes_and_maps_job_plugin():
    assert SCAN_MIDDLEWARE_FAMILY in normalize_scan_families(["middleware", "host"])
    assert SCAN_MIDDLEWARE_TYPES == frozenset(
        {"nginx", "tomcat", "kafka", "zookeeper", "rabbitmq", "consul", "etcd"}
    )
    assert scan_encrypt_model_id("middleware") == "host"
    assert scan_driver_type_for_model("nginx") == CollectDriverTypes.JOB
    assert scan_task_type_for_model("nginx") == CollectPluginTypes.MIDDLEWARE
    assert is_agent_credential({}) is True
    assert is_agent_credential({"credential_id": SCAN_AGENT_CREDENTIAL_ID}) is True
    assert is_agent_credential({"username": "root", "password": "x"}) is False
    assert agent_placeholder_pool() == [{"credential_id": SCAN_AGENT_CREDENTIAL_ID}]


def test_resolve_middleware_credential_falls_back_to_host_pool():
    task = ScanTask.objects.create(
        name="scan-mw-resolve",
        team=["1"],
        families=["host", "middleware"],
        credentials={
            "host": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}],
        },
    )
    found = resolve_scan_task_credential(task, "nginx", "cred-ssh")
    assert found["username"] == "root"
    agent = resolve_scan_task_credential(task, "nginx", SCAN_AGENT_CREDENTIAL_ID)
    assert agent == {"credential_id": SCAN_AGENT_CREDENTIAL_ID}
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest apps/cmdb/tests/test_scan_models.py::test_middleware_family_normalizes_and_maps_job_plugin --no-cov
```

Expected: FAIL（常量未定义）

- [ ] **Step 3: 最小实现**

在 `scan_model.py` 现有 `SCAN_DATABASE_*` 旁增加：

```python
SCAN_MIDDLEWARE_FAMILY = "middleware"
SCAN_MIDDLEWARE_TYPES = frozenset(
    {"nginx", "tomcat", "kafka", "zookeeper", "rabbitmq", "consul", "etcd"}
)
SCAN_JOB_OPTIONAL_FAMILIES = frozenset({"host", SCAN_MIDDLEWARE_FAMILY})
SCAN_AGENT_CREDENTIAL_ID = "agent"
```

`SCAN_ALLOWED_FAMILIES` 加入 `SCAN_MIDDLEWARE_FAMILY` 与 `*SCAN_MIDDLEWARE_TYPES`。

`normalize_scan_families`：见到中间件类型或 `middleware` 时折叠成一次 `middleware`（对齐 database）。

```python
def scan_encrypt_model_id(model_id: str) -> str:
    if model_id == SCAN_DATABASE_FAMILY:
        return "mysql"
    if model_id == SCAN_MIDDLEWARE_FAMILY or model_id in SCAN_MIDDLEWARE_TYPES:
        return "host"
    return model_id

def scan_driver_type_for_model(model_id: str) -> str:
    if model_id == "host" or model_id in SCAN_MIDDLEWARE_TYPES:
        return CollectDriverTypes.JOB
    return CollectDriverTypes.PROTOCOL

def scan_task_type_for_model(model_id: str) -> str:
    if model_id == "network":
        return CollectPluginTypes.SNMP
    if model_id == "host":
        return CollectPluginTypes.HOST
    if model_id in SCAN_MIDDLEWARE_TYPES:
        return CollectPluginTypes.MIDDLEWARE
    return CollectPluginTypes.PROTOCOL
```

```python
def is_agent_credential(item) -> bool:
    if not item:
        return True
    if not isinstance(item, dict):
        return False
    if str(item.get("credential_id") or "") == SCAN_AGENT_CREDENTIAL_ID:
        return True
    return not any(item.get(key) for key in ("username", "password", "key", "private_key"))

def agent_placeholder_pool() -> list[dict]:
    return [{"credential_id": SCAN_AGENT_CREDENTIAL_ID}]
```

`resolve_scan_task_credential`：除 family 池和 database 回退外，若 `family_model_id in SCAN_MIDDLEWARE_TYPES`，再查 `raw.get("middleware")` 与 `raw.get("host")`。`credential_id == SCAN_AGENT_CREDENTIAL_ID` 时若池中没有该项，返回 `{"credential_id": SCAN_AGENT_CREDENTIAL_ID}`，这样 generate / push 不会 `credential_not_found`。

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(cmdb): 扫描增加中间件族常量与 JOB 映射

EOF
)"
```

---

### Task 2: 任务保存允许空凭据，Agent 要云区域

**Files:**
- Modify: `bk-lite/server/apps/cmdb/serializers/scan_serializer.py`
- Test: `bk-lite/server/apps/cmdb/tests/test_scan_views.py`

- [ ] **Step 1: 写失败测试**

```python
def test_create_allows_empty_host_and_middleware_credentials(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    request = _req(
        "post",
        superuser,
        data=_payload(
            families=["host", "middleware"],
            credentials={"host": [], "middleware": []},
            cloud_region={"id": 1, "name": "default"},
        ),
    )
    response = ScanTaskViewSet.as_view({"post": "create"})(request)
    assert response.status_code == 201
    task = ScanTask.objects.get()
    assert task.families == ["host", "middleware"]


def test_create_middleware_agent_requires_cloud_region(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    request = _req(
        "post",
        superuser,
        data=_payload(families=["middleware"], credentials={"middleware": []}),
    )
    response = ScanTaskViewSet.as_view({"post": "create"})(request)
    assert response.status_code == 400


def test_create_middleware_ssh_does_not_require_cloud_region(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    request = _req(
        "post",
        superuser,
        data=_payload(
            families=["middleware"],
            credentials={"middleware": [{"username": "root", "password": "p", "port": 22}]},
        ),
    )
    response = ScanTaskViewSet.as_view({"post": "create"})(request)
    assert response.status_code == 201


def test_create_still_requires_database_credentials(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    request = _req("post", superuser, data=_payload(families=["database"], credentials={"database": []}))
    response = ScanTaskViewSet.as_view({"post": "create"})(request)
    assert response.status_code == 400
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 改 `ScanTaskSerializer.validate`**

- `families` 校验已走 `SCAN_ALLOWED_FAMILIES`，确认含 `middleware`。
- 规范化后：若同时有 `host` 与 `middleware`，且 middleware 池空，则 `credentials.middleware = host 池`（可同为空）。
- 对每个 family：若 `model_id in SCAN_JOB_OPTIONAL_FAMILIES` 且池空，写入 `[]`，不要报「至少一把凭据」。
- 其它族空池仍报错。
- 云区域：`host in families` 仍必填；`middleware in families` 且 middleware 池为 Agent（空或 `is_agent_credential` 全为真）也必填。SSH 中间件可不填。

`_credential_label_for_hit`：`credential_id == SCAN_AGENT_CREDENTIAL_ID` 返回 `"Agent"`。查池时中间件类型回退 `middleware` / `host`（与 resolve 一致）。

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(cmdb): 扫描主机与中间件允许空凭据走 Agent

EOF
)"
```

---

### Task 3: 触发拆 7 枪，空池用 Agent 占位

**Files:**
- Modify: `bk-lite/server/apps/cmdb/services/scan_trigger_service.py`
- Test: `bk-lite/server/apps/cmdb/tests/test_scan_trigger_service.py`

- [ ] **Step 1: 写失败测试**

```python
def test_trigger_middleware_family_splits_job_types_and_skips_redis_ports(mocker):
    from apps.cmdb.models.collect_model import PortFingerprint
    from apps.cmdb.models.scan_model import SCAN_MIDDLEWARE_TYPES

    PortFingerprint.objects.create(port=6379, target_type="redis", protocol="tcp", built_in=False)
    task = _scan_task(
        families=["middleware"],
        credentials={"middleware": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}]},
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    headers_by_model = {}

    def fake_admit(headers):
        headers_by_model[headers.get("cmdbmodel_id") or headers.get("config_type")] = headers
        return TriggerResult("accepted", 2, 2)

    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=fake_admit,
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")

    trigger_scan_execution(execution.id)

    model_ids = set(ScanFamilyRun.objects.filter(execution=execution).values_list("model_id", flat=True))
    assert model_ids == set(SCAN_MIDDLEWARE_TYPES)
    assert "middleware" not in model_ids
    assert "redis" not in model_ids
    nginx = headers_by_model["nginx"]
    assert nginx.get("cmdbexecutor_type") == "job" or nginx.get("config_type") == "nginx"
    assert "6379" not in json.dumps(headers_by_model)


def test_trigger_empty_middleware_pool_admits_agent_placeholder(mocker):
    task = _scan_task(
        families=["middleware"],
        credentials={"middleware": []},
        cloud_region={"id": 1, "name": "default"},
    )
    execution = ScanExecution.objects.create(task=task)
    admit = mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        return_value=TriggerResult("accepted", 1, 1),
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")

    result = trigger_scan_execution(execution.id)
    assert admit.call_count == 7
    assert result["target_count"] == 7
    assert ScanFamilyRun.objects.filter(execution=execution, admit_status=ScanFamilyRun.ADMIT_FAILED).count() == 0
    first_headers = admit.call_args_list[0].args[0]
    assert "agent" in json.dumps(first_headers)


def test_trigger_empty_host_pool_admits_agent_placeholder(mocker):
    task = _scan_task(
        families=["host"],
        credentials={"host": []},
        cloud_region={"id": 1, "name": "default"},
    )
    execution = ScanExecution.objects.create(task=task)
    admit = mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        return_value=TriggerResult("accepted", 1, 1),
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")
    trigger_scan_execution(execution.id)
    assert admit.call_count == 1
    assert ScanFamilyRun.objects.get(execution=execution, model_id="host").admit_status != ScanFamilyRun.ADMIT_FAILED


def test_trigger_middleware_reuses_host_ssh_pool(mocker):
    task = _scan_task(
        families=["host", "middleware"],
        credentials={"host": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}]},
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    seen = []

    def fake_admit(headers):
        seen.append(headers)
        return TriggerResult("accepted", 1, 1)

    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=fake_admit,
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")
    trigger_scan_execution(execution.id)
    nginx_headers = [h for h in seen if (h.get("cmdbmodel_id") or h.get("config_type")) == "nginx"][0]
    assert "root" in json.dumps(nginx_headers)
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 改 `iter_scan_family_pools` 与 `_admit_family`**

在 database 分支之后、普通循环里：

- 遇到 `middleware`：不要 yield `middleware`；对每个 `SCAN_MIDDLEWARE_TYPES` yield `(model_id, pool)`。
- 池来源：`decrypted["middleware"]`；若空且任务 `families` 含 host，用 host 池。
- 仍空：`agent_placeholder_pool()`。
- 不要把端口特征库笛卡尔进 JOB 凭据。

`_admit_family`：

```python
if not pool and model_id in {"host", *SCAN_MIDDLEWARE_TYPES}:
    pool = agent_placeholder_pool()
if not pool:
    family_run.admit_status = ScanFamilyRun.ADMIT_FAILED
    ...
params = {"has_network_topo": False}
if task.cloud_region and (model_id == "host" or model_id in SCAN_MIDDLEWARE_TYPES):
    params["cloud_region"] = task.cloud_region
```

- [ ] **Step 4: 跑测试确认通过**（顺带跑原有 `test_trigger_database_family_splits_catalog_ports_and_skips_middleware`）

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(cmdb): 扫描中间件按 JOB 类型拆枪并支持 Agent 空池

EOF
)"
```

---

### Task 4: 收口按监听端口拆中间件 hit

**Files:**
- Modify: `bk-lite/server/apps/cmdb/services/scan_finalize_service.py`
- Test: `bk-lite/server/apps/cmdb/tests/test_scan_finalize_service.py`

**行为：** 现有 `write_scan_execution` 对网络只 polish snapshot、不拉 VM。中间件必须额外拉 mapping。SSH 成功常是 `port=22` 一行；收口后变成 N 条业务端口行。无进程则删掉通道行。

- [ ] **Step 1: 写失败测试**

```python
def test_finalize_explodes_middleware_listen_ports_and_drops_empty_host(mocker):
    from apps.cmdb.constants.constants import CollectDriverTypes

    task = _scan_task(families=["middleware"], credentials={"middleware": [{"credential_id": "cred-ssh"}]})
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_RUNNING, claim_token="t")
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="nginx",
        driver_type=CollectDriverTypes.JOB,
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="nginx",
        host="10.0.1.10",
        port=22,
        credential_id="cred-ssh",
        status=ScanHit.STATUS_SUCCESS,
    )
    ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="nginx",
        host="10.0.1.11",
        port=22,
        credential_id="cred-ssh",
        status=ScanHit.STATUS_SUCCESS,
    )
    mocker.patch(
        "apps.cmdb.services.scan_finalize_service.collect_family_metrics",
        return_value={
            "nginx": [
                {
                    "ip_addr": "10.0.1.10",
                    "listen_port": "80",
                    "version": "1.24",
                    "conf_path": "/etc/nginx/nginx.conf",
                    "inst_name": "10.0.1.10-nginx-80",
                }
            ]
        },
    )
    write_scan_execution(execution)
    ports = set(ScanHit.objects.filter(family_run=family_run, status=ScanHit.STATUS_SUCCESS).values_list("host", "port"))
    assert ports == {("10.0.1.10", 80)}
    hit = ScanHit.objects.get(host="10.0.1.10", port=80)
    assert hit.snapshot.get("version") == "1.24"
    assert hit.cmdb_model_id == "nginx"
    assert not ScanHit.objects.filter(host="10.0.1.11").exists()
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**

增加 `_MIDDLEWARE_SNAPSHOT_KEYS = ("inst_name", "ip_addr", "port", "listen_port", "version", "bin_path", "nginx_path", "conf_path", "config_path", "install_path", "log_path")`。

`_snapshot_keys_for_family`：`model_id in SCAN_MIDDLEWARE_TYPES` 用这组。

新增 `explode_middleware_hits(family_run, plugin_result)`：

- 仅 `family_run.model_id in SCAN_MIDDLEWARE_TYPES`。
- 从 `plugin_result[model_id]` 取行，host 用 `_row_host`，端口用 `listen_port` 或 `port`；逗号串取第一个数字作 `hit.port`，全文进 snapshot。
- 按原 success hit 的 `(host, credential_id)` 找到通道行。
- 有行：按 `(host, listen_port, credential_id)` upsert success，`cmdb_model_id=model_id`，snapshot 合并行字段；删除该 host 上 port 等于 SSH/0/22 且不在新端口集合里的旧行。
- 无行：**保留** success 通道行（VM 晚于凭据回传），把 22 改成该类型默认监听口；不得删除。有指标但无既有 hit 时按指标建行。

`write_scan_execution`：对中间件 family_run 先 `collect_family_metrics`（失败记日志、不拆），再 explode，再 `polish_hit_snapshots`。网络 / 主机路径不变，测试里 `collect.assert_not_called()` 继续成立。

`listen_port == "unknown"`：`port=0`，仍留一行。

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(cmdb): 扫描收口按中间件监听端口拆命中

EOF
)"
```

---

### Task 5: 写 CI

**Files:**
- Modify: `bk-lite/server/apps/cmdb/services/scan_write_ci_service.py`
- Test: `bk-lite/server/apps/cmdb/tests/test_scan_write_ci_service.py`

- [ ] **Step 1: 写失败测试**

```python
def test_write_ci_maps_nginx_snapshot(mocker):
    execution, hit = _execution(
        family="nginx",
        port=80,
        snapshot={
            "inst_name": "10.0.1.10-nginx-80",
            "ip_addr": "10.0.1.10",
            "listen_port": "80",
            "version": "1.24",
            "conf_path": "/etc/nginx/nginx.conf",
        },
        cmdb_model_id="",
        soid="",
    )
    captured = _capture_cannula(mocker)
    mocker.patch(
        "apps.cmdb.services.scan_write_ci_service.InstanceManage.query_entity_by_uuids",
        return_value=[],
    )
    result = ScanWriteCiService.write(execution, [hit.id])
    assert result["written"] == 1
    assert captured["default_metrics"]["nginx"][0]["port"] == 80
    assert captured["default_metrics"]["nginx"][0]["version"] == "1.24"
    hit.refresh_from_db()
    assert hit.cmdb_model_id == "nginx"
```

`_execution` 当前 `driver_type="protocol"`，nginx 测例里把 family_run.driver_type 改为 job（可在 `_execution` 增加参数）。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: `_map_middleware_row`**

```python
def _map_middleware_row(hit, snapshot, host, family):
    port = hit.port or snapshot.get("port") or snapshot.get("listen_port") or ""
    if isinstance(port, str) and "," in port:
        port = port.split(",")[0].strip() or port
    inst_name = str(snapshot.get("inst_name") or "").strip() or (
        f"{host}-{family}-{port}" if port not in (None, "", "unknown") else f"{host}-{family}"
    )
    return family, {
        "ip_addr": host,
        "host": host,
        "inst_name": inst_name,
        "port": port if port not in ("unknown",) else "",
        "version": snapshot.get("version") or "",
        "bin_path": snapshot.get("bin_path") or snapshot.get("nginx_path") or "",
        "conf_path": snapshot.get("conf_path") or snapshot.get("config_path") or "",
        "install_path": snapshot.get("install_path") or "",
        "log_path": snapshot.get("log_path") or "",
        "model_id": family,
    }
```

`mapping_row_from_hit`：`family in SCAN_MIDDLEWARE_TYPES` 走上面。其它模型字段有则从 snapshot 原样带上（catalina_path 等），不要丢插件已有键。

写 CI 行带上采集同结构的 `assos`（`MetricsCannula.setting_assos` 按 `inst_name` 找对端；主机实例名常常是 hostname 不是 IP，所以再补一层按 IP 查找）：

```python
row["assos"] = [
    {
        "model_id": "host",
        "inst_name": host,
        "asst_id": "run",
        "model_asst_id": f"{family}_run_host",
    }
]
```

写完后 `attach_middleware_hits_to_host(execution)`，紧挨现有 `attach_snmp_hits_to_physical(execution)`：

```python
def attach_middleware_hits_to_host(execution):
    from apps.cmdb.services.instance import InstanceManage

    hits = execution.hits.filter(
        family_run__model_id__in=SCAN_MIDDLEWARE_TYPES,
        status=ScanHit.STATUS_SUCCESS,
    ).exclude(inst_uuid="")
    for hit in hits:
        host_row = _lookup_host_by_ip(hit.host)
        if not host_row:
            continue
        host_uuid = str(host_row.get("inst_uuid") or "")
        if host_uuid and hit.attached_inst_uuid != host_uuid:
            hit.attached_inst_uuid = host_uuid
            hit.save(update_fields=["attached_inst_uuid", "updated_at"])
        if hit.inst_uuid and host_uuid:
            try:
                InstanceManage.instance_association_create_by_uuid(
                    src_inst_uuid=hit.inst_uuid,
                    dst_inst_uuid=host_uuid,
                    model_asst_id=f"{hit.family_run.model_id}_run_host",
                    operator="scan",
                )
            except Exception:
                logger.info("event=scan_middleware_run_host_skipped hit=%s host=%s", hit.id, hit.host)
```

`_lookup_host_by_ip` 用 Graph `model_id=host` + `ip_addr=hit.host`。查不到则跳过，禁止新建主机。`instance_association_create` 已存在则忽略。测试 mock `query_entity` 返回一台同 IP 主机，断言 `attached_inst_uuid` 被写入，且 association 被调用一次。

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(cmdb): 扫描中间件命中写入 CI

EOF
)"
```

---

### Task 6: 生成采集保持 SSH / Agent 通道

**Files:**
- Modify: `bk-lite/server/apps/cmdb/services/scan_collect_task.py`
- Modify: `bk-lite/server/apps/cmdb/services/scan_collect_generate.py`（若凭据解析已在 model 层则可能不用改）
- Test: `bk-lite/server/apps/cmdb/tests/test_scan_collect_generate.py`

- [ ] **Step 1: 写失败测试**

在 `test_scan_collect_generate.py` 增加 nginx UUID，并入 `ALL_UUIDS`。扩展 `_graph_row`：`inst_uuid in NGINX_UUIDS.values()` 时 `model_id="nginx"`、`inst_name=f"{host}-nginx-80"`。

```python
NGINX_UUIDS = {
    "10.0.1.80": "88888888-8888-4888-8888-888888888888",
    "10.0.1.81": "99999999-9999-4999-8999-999999999999",
}

def test_nginx_ssh_generate_merges_hosts_into_one_job_task(mocker, authenticated_user):
    _patch_side_effects(mocker)
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    task = _task(
        families=["middleware"],
        credentials={"middleware": [{"credential_id": "cred-ssh", "username": "root", "password": "p", "port": 22}]},
    )
    execution, hits = _execution_with_hits(
        task,
        ["10.0.1.80", "10.0.1.81"],
        family="nginx",
        driver_type="job",
        protocol="nginx",
        port=80,
        credential_id="cred-ssh",
        cmdb_model_id="nginx",
        uuids=NGINX_UUIDS,
    )
    result = ScanCollectGenerateService.generate(execution, [hit.id for hit in hits], operator="tester")
    assert result["created"] == 1
    collect = CollectModels.objects.get(model_id="nginx")
    assert collect.task_type == "middleware"
    assert collect.driver_type == "job"
    assert collect.decrypt_credentials[0]["username"] == "root"
    assert {item.get("inst_uuid") for item in (collect.instances or [])} == set(NGINX_UUIDS.values())


def test_nginx_agent_generate_has_no_ssh_password(mocker, authenticated_user):
    _patch_side_effects(mocker)
    mocker.patch.object(CollectModelService, "push_butch_node_params")
    task = _task(
        families=["middleware"],
        credentials={"middleware": []},
        cloud_region={"id": 1, "name": "default"},
    )
    execution, hits = _execution_with_hits(
        task,
        ["10.0.1.80"],
        family="nginx",
        driver_type="job",
        protocol="nginx",
        port=80,
        credential_id="agent",
        cmdb_model_id="nginx",
        uuids=NGINX_UUIDS,
    )
    ScanCollectGenerateService.generate(execution, [hits[0].id], operator="tester")
    collect = CollectModels.objects.get(model_id="nginx")
    pool = collect.decrypt_credentials or []
    assert pool
    assert all(not item.get("password") and not item.get("username") for item in pool)
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**

- `_COLLECT_FORM_DEFAULTS` 为 7 个中间件类型各加 `timeout=20, cycle_minutes=30`。
- `collect_params`：`family_model_id in SCAN_MIDDLEWARE_TYPES` 时同样写入 `host_cloud_from_scan(scan_task)`，Agent 后续刷新才能按云区域匹配节点。
- `normalize_scan_credential_item`：`is_agent_credential(item)` 时返回 `{}`（无 username/password）。`create_scan_collect_task` 允许最终池为 `[{}]`。
- `resolve_scan_task_credential` 已回退 host / middleware 池时，generate 不再因 `credential_not_found` 跳过；`credential_id=agent` 解析为占位项。

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(cmdb): 扫描中间件按 SSH 或 Agent 生成采集任务

EOF
)"
```

---

### Task 7: 推监控跳过中间件，主机 Agent 不走 Host Remote

**Files:**
- Modify: `bk-lite/server/apps/cmdb/services/scan_push_monitor.py`
- Test: `bk-lite/server/apps/cmdb/tests/test_scan_push_monitor.py`

- [ ] **Step 1: 写失败测试**

```python
def test_middleware_hit_skips_monitor_push(mocker):
    ingest = _patch_monitor_ingest(mocker)
    task = ScanTask.objects.create(
        name="scan-mw",
        team=[1],
        families=["middleware"],
        access_point=[{"id": "node-1"}],
        credentials={"middleware": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}]},
    )
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_COMPLETED)
    family_run = ScanFamilyRun.objects.create(execution=execution, model_id="nginx", driver_type="job")
    hit = ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="nginx",
        host="10.0.1.10",
        port=80,
        credential_id="cred-ssh",
        status=ScanHit.STATUS_SUCCESS,
        cmdb_model_id="nginx",
        inst_uuid=UUID_SWITCH,
    )
    result = ScanPushMonitorService.push(execution, [hit.id])
    assert result["items"][0]["status"] == "skipped"
    assert result["items"][0]["reason"] == "middleware_needs_monitor_credential"
    ingest.assert_not_called()


def test_agent_host_without_node_skips_and_never_sends_ssh(mocker):
    ingest = _patch_monitor_ingest(mocker)
    push_with = mocker.patch("apps.cmdb.services.scan_push_monitor.CmdbToMonitorPushService.push_with_credential")
    task = ScanTask.objects.create(
        name="scan-agent-host",
        team=[1],
        families=["host"],
        access_point=[{"id": "node-1"}],
        credentials={"host": []},
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_COMPLETED)
    family_run = ScanFamilyRun.objects.create(execution=execution, model_id="host", driver_type="job")
    hit = ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="host",
        host="10.0.1.10",
        port=22,
        credential_id="agent",
        status=ScanHit.STATUS_SUCCESS,
        cmdb_model_id="host",
        inst_uuid=UUID_SWITCH,
    )
    mocker.patch(
        "apps.cmdb.services.scan_push_monitor.InstanceManage.query_entity_by_uuids",
        return_value=[{"inst_uuid": UUID_SWITCH, "model_id": "host", "ip_addr": "10.0.1.10"}],
    )
    result = ScanPushMonitorService.push(execution, [hit.id])
    assert result["items"][0]["status"] == "skipped"
    assert result["items"][0]["reason"] == "agent_host_no_node"
    push_with.assert_not_called()
    ingest.assert_not_called()
```

主机 Agent：无 `node_id` 则 skipped `agent_host_no_node`；有 `node_id` 才 `CmdbToMonitorPushService.push_instance`（无凭据）。禁止 `push_with_credential`。

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 在 `ScanPushMonitorService.push` 循环里，解析凭据之前先按族短路**

```python
if family_model_id in SCAN_MIDDLEWARE_TYPES:
    item.update({"status": "skipped", "reason": "middleware_needs_monitor_credential"})
    results.append(item)
    continue

credential = _resolve_credential_item(scan_task, family_model_id, credential_id)
if family_model_id == "host" and is_agent_credential(credential or {"credential_id": credential_id}):
    instance = _resolve_graph_instance(hit)
    node_id = (instance or {}).get("node_id") or (instance or {}).get("id")
    if not node_id:
        item.update({"status": "skipped", "reason": "agent_host_no_node"})
        results.append(item)
        continue
    CmdbToMonitorPushService.push_instance(instance, ...)  # 无 credential
    ...
    continue
```

中间件行不要落到 `credential_not_found`（空池 / agent 占位本来就没有 SSH）。

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(cmdb): 扫描中间件不推监控，主机 Agent 不走 SSH 建采

EOF
)"
```

---

### Task 8: 表单、清单、提示文案

**Files:**
- Modify: `bk-lite/web/src/app/cmdb/(pages)/assetManage/autoDiscovery/scan/ScanTaskDrawer.tsx`
- Modify: `bk-lite/web/src/app/cmdb/(pages)/assetManage/autoDiscovery/scan/scanTaskForm.ts`
- Test: `bk-lite/web/src/app/cmdb/(pages)/assetManage/autoDiscovery/scan/__tests__/scanTaskForm.test.ts`
- Modify: `bk-lite/web/src/app/cmdb/(pages)/assetManage/autoDiscovery/scan/ScanHitsDrawer.tsx`
- Modify: `bk-lite/web/src/app/cmdb/(pages)/assetManage/autoDiscovery/scan/scanHits.ts`
- Modify: `bk-lite/web/src/app/cmdb/locales/zh.json`
- Modify: `bk-lite/web/src/app/cmdb/locales/en.json`

文案（必须原样落地）：

| key | zh | en |
|---|---|---|
| `Scan.familyHost` | 主机 | Host |
| `Scan.familyMiddleware` | 中间件 | Middleware |
| `Scan.familyNginx` 等 7 个 | Nginx / Tomcat / … | 同名 |
| `Scan.jobCredentialOptionalTip` | 凭据可不填；留空时走节点管理 Agent 在目标机本地执行发现脚本。填写后走 SSH 远程执行。用户名和密码均可为空。 | Credentials are optional. Leave them empty to run discovery via Agent. When filled, scripts run over SSH. Username and password can both be blank. |
| `Scan.agentCloudRegionHint` | Agent 模式按 IP + 云区域匹配已纳管节点，未安装 Agent 的地址不会出现在清单中。 | Agent mode matches managed nodes by IP and cloud region. Addresses without an Agent do not appear in the hit list. |
| `Scan.middlewarePushMonitorHint` | 中间件监控需要 URL / Exporter 等凭据，扫描阶段不自动创建采集。 | Middleware monitoring needs URL or exporter credentials. Scan does not create those collectors. |
| `Scan.cloudRegionRequiredAgent` | 主机或 Agent 中间件扫描必须填写云区域 | Cloud region is required for Host or Agent middleware scan |

- [ ] **Step 1: 改 locales**（上面整表写入 `Scan` 段）

- [ ] **Step 2: 表单提交云区域**

把 `scanTaskForm.ts` 的 `includeHost` 改名为 `includeCloudRegion`（调用点同步）。语义：勾了 host，或（勾了 middleware 且当前凭据是 Agent）。SSH-only 中间件仍传 `{}`。

在 `scanTaskForm.test.ts` 增加：

```ts
it('Agent 中间件提交云区域，SSH 中间件不强制带出', () => {
  expect(
    resolveScanCloudRegion({
      includeCloudRegion: true,
      origin: { cloud_region_id: 1, cloud_region_name: 'default' },
    })
  ).toEqual({ id: 1, name: 'default' });
  expect(
    resolveScanCloudRegion({
      includeCloudRegion: false,
      origin: { cloud_region_id: 1, cloud_region_name: 'default' },
    })
  ).toEqual({});
});
```

`SCAN_FAMILIES` 增加 `{ modelId: 'middleware', labelKey: 'Scan.familyMiddleware', shape: 'ssh' }`。

`ScanTaskDrawer.tsx`：

```ts
const poolHasSshSecret = (pool: CredentialPoolItem[] = []) =>
  pool.some((item) => Boolean(item.username || item.password || item.key));
const includeMiddleware = selectedFamilies.includes('middleware');
const includeHost = selectedFamilies.includes('host');
const middlewareAgent =
  includeMiddleware && !poolHasSshSecret(values.credentials?.middleware || values.credentials?.host || []);
const includeCloudRegion = includeHost || middlewareAgent;
```

- 勾了 `host` 时不渲染中间件 `CredentialPoolEditor`；提交时 `credentials.middleware = sanitizePool(values.credentials?.host || [])`。
- 只勾中间件时渲染 SSH 池；`Alert` 用 `jobCredentialOptionalTip`。主机勾选时同一提示挂在主机凭据区。
- `middlewareAgent` 时展示 `agentCloudRegionHint`；`includeCloudRegion && !hasScanCloudRegion(payload.cloud_region)` 报 `Scan.cloudRegionRequiredAgent`。
- `buildScanTaskSubmitMeta({ includeCloudRegion, ... })`。
- 提交仍 `auto_push_monitor: false`、`auto_generate_collect: false`。

- [ ] **Step 3: 清单**

- `FAMILY_ORDER` 加入 `middleware` 及 7 个类型。
- `familyLabel` 覆盖 7 个类型。
- 中间件子 tab 列：host、port、version、模型、`conf_path`/`install_path`、凭据。
- `handleBatch('monitor')`：所选 hit 的 `family_model_id` 属于中间件类型时 `message.warning(t('Scan.middlewarePushMonitorHint'))` 并 return。
- 凭据列已由后端返回 `Agent`。

- [ ] **Step 4: 验证**

```bash
cd bk-lite/web && pnpm exec vitest run src/app/cmdb/\(pages\)/assetManage/autoDiscovery/scan/__tests__/scanTaskForm.test.ts
cd bk-lite/web && pnpm type-check
```

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(cmdb): 扫描任务与清单支持中间件及 Agent 提示

EOF
)"
```

---

## Spec coverage

| 规格点 | 任务 |
|---|---|
| `middleware` 族 + 拆 7 类型 + 复用 `*_info` | 1, 3 |
| 空凭据 Agent / 填 SSH；与主机共用 | 2, 3, 8 |
| Agent 云区域；SSH 中间件可不填 | 2, 8 |
| 提示四处 | 8 |
| 按 listen_port 拆行；无进程不进清单 | 4 |
| 写 CI 字段；不新建主机；run host | 5 |
| 生成采集通道一致 | 6 |
| 中间件不推监控；主机 Agent 不走 Host Remote | 7 |
| Redis/端口探测不当发现本体 | 3（断言 redis 不进枪） |
| 主机空池也按 Agent 接纳 | 3 |
| 不改发现脚本 | 无 Stargazer 任务 |

## 实现时不要做

- 新写 `middleware_info` 总脚本
- 把中间件加入 `CMDB_CREATE_ADAPTED_MODEL_IDS`
- 猜 stub_status URL
- 界面子勾选 Nginx/Tomcat
- 改专业采集空凭据语义
