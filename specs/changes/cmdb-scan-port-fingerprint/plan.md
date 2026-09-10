# CMDB 特征库端口指纹与统一数据库扫描 Implementation Plan

> **For agentic workers:** 按任务顺序 TDD 实现；规格见 `specs/changes/cmdb-scan-port-fingerprint/spec.md`。前端 UI 用 Gemini 3.7 Flash 实现。

**Goal:** 特征库增加端口指纹 Tab；扫描任务用一族「数据库」+ 统一账号，按指纹端口拆 mysql/postgresql/mssql 三枪；鉴权失败进未匹配，可补端口指纹。

**Architecture:** `PortFingerprint` 与 `OidMapping` 并列。任务存 `database` 凭据；触发时按白名单拆三枪，端口来自指纹表、账号做端口笛卡尔展开后走现有 `collect_info`。鉴权失败 upsert 空 `credential_id` 占位命中。

**Tech Stack:** Django ORM、DRF、现有扫描触发 / 凭据 NATS / mapping、Next.js、Ant Design。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `server/apps/cmdb/models/collect_model.py` | `PortFingerprint` |
| `server/apps/cmdb/services/port_fingerprint.py` | 种子、按类型取端口、扫描白名单 |
| `server/apps/cmdb/management/commands/init_port_fingerprint.py` | 启动期同步内置三条 |
| `server/apps/cmdb/views/port_fingerprint.py` + serializer | CRUD API `/api/port_fingerprint` |
| `server/apps/cmdb/models/scan_model.py` | `database` 族、加密字段映射 |
| `server/apps/cmdb/serializers/scan_serializer.py` | 旧三族合并、`unmatch_reason`、凭据标签回退 `database` |
| `server/apps/cmdb/services/scan_trigger_service.py` | `database` 拆枪 + 端口展开 |
| `server/apps/cmdb/services/scan_credential_result_service.py` | 鉴权失败占位 / 成功删除占位 |
| `server/apps/cmdb/services/scan_identity.py` | `credential_failed` |
| `server/apps/cmdb/services/scan_classify_service.py` | 网络未匹配手选类型 / SOID 认领 |
| `server/apps/cmdb/views/scan.py` | 命中含 failed 占位 |
| `server/apps/cmdb/services/scan_push_monitor.py` / `scan_collect_generate.py` | 无钥匙拒绝；凭据从 `database` 池取 |
| `web/.../featureLibrary/` | Tab + 端口表（Gemini） |
| `web/.../scan/ScanTaskDrawer.tsx` | 一族数据库（Gemini） |
| `web/.../scan/ScanHitsDrawer.tsx` | 数据库未匹配分组（Gemini） |

---

### Task 1: PortFingerprint 模型、种子、API

- Create: model、service、init 命令、ViewSet、serializer、migration `0053_portfingerprint.py`
- Test: `server/apps/cmdb/tests/test_port_fingerprint.py`

- [x] 唯一 `(port, target_type)`；内置 3306/mysql、5432/postgresql、1433/mssql
- [x] 删除内置拒绝；中间件类型可保存；`ports_for_scan_type` 只返回白名单类型
- [x] `batch_init` 调用 `init_port_fingerprint`
- [x] 权限对齐 `soid_library-View/Add/Delete`

### Task 2: 扫描任务 `database` 族

- Modify: `scan_model.py`、`scan_serializer.py`
- Test: 任务序列化测试（可放 `test_scan_views.py` 或新建 `test_scan_database_family.py`）

- [x] `SCAN_ALLOWED_FAMILIES` 含 `database`；写入时把 mysql/pg/mssql 合并进 `database`
- [x] `credentials.database` 按 mysql 的 SQL 密码字段加密；读取旧任务同样合并

### Task 3: 触发拆枪

- Modify: `scan_trigger_service.py`
- Test: `test_scan_trigger_service.py`

- [x] `database` 不建同名 family_run；按指纹端口拆最多三枪
- [x] 账号复制并按端口展开（每条凭据带 `port`）
- [x] 中间件端口不进请求；无数据库端口则跳过 SQL 枪
- [x] 凭据从 `credentials.database` 读取

### Task 4: 鉴权失败占位命中

- Modify: `scan_credential_result_service.py`、`views/scan.py` hits 查询
- Test: `test_scan_credential_event_nats.py`

- [x] `failed` + 鉴权 `error_code` → upsert `(family_run, host, port, credential_id="")`
- [x] `success` 删除该占位；`unreachable` / 无鉴权码的 failed 不落清单
- [x] 命中列表返回 success **和** 这些占位行（不再只滤 success）

### Task 5: unmatch_reason + 失败行出口

- Modify: `scan_identity.py`、`views/scan.py`
- Test: `test_scan_identity.py`、`test_scan_views.py`

- [x] 三库族、空模型、failed 占位 → `credential_failed`
- [x] 生成采集 / 推监控：无 `credential_id` 拒绝；成功行从 `credentials.database` 取钥匙
- [x] 不提供数据库未匹配建 CI 动作

### Task 6: 前端（Gemini 3.7 Flash）

- [x] 特征库一页两 Tab；菜单改名「特征库」
- [x] 扫描任务勾选 database + 统一 SQL 池，旧任务回填；数据库凭据无端口
- [x] 未匹配数据库按类型分组；组头添加指纹；失败行禁用推/采

### Task 7: 验证

本机验证用当前 `server/.env` 的 Postgres（sqlite 基线 `NewSessionEventRelation has no field named 'event'`，不作为本特性阻断）。

```
cd server && SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest \
  apps/cmdb/tests/test_port_fingerprint.py \
  apps/cmdb/tests/test_scan_identity.py \
  apps/cmdb/tests/test_scan_classify_service.py \
  apps/cmdb/tests/test_scan_views.py \
  apps/cmdb/tests/test_scan_trigger_service.py \
  apps/cmdb/tests/test_scan_credential_event_nats.py --no-cov
cd web && pnpm type-check
```

- [x] 上述扫描/端口指纹相关 pytest：57 passed（2026-09-03）
- [x] `pnpm type-check` 通过
- 已知未纳入本特性阻断：`test_scan_collect_generate.py` 两条 Influx 回归、`test_scan_push_monitor.py::test_scan_push_does_not_import_monitor_internal_ingest` 基线失败
